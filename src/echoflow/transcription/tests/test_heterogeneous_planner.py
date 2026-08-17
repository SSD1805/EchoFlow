from pathlib import Path
from unittest.mock import Mock

import pytest

from echoflow.core.file_manager_facade import FileManagerFacade
from echoflow.core.performance_tracker import PerformanceTracker
from echoflow.interfaces.local_file_manager import LocalFileManager
from echoflow.media.models import InputIdentity, MediaInfo, MediaStream, StreamKind
from echoflow.runner.models import ExecutionPolicy, ProcessingProfile, RunnerResources
from echoflow.runner.policy import RunnerPolicyPlanner
from echoflow.runner.topology import (
    AcceleratorBackend,
    AcceleratorDevice,
    HardwareTopology,
    MemoryTopology,
)
from echoflow.transcription.capabilities import (
    EngineCapabilities,
    EngineCapabilityRegistry,
    EngineExecutionTarget,
)
from echoflow.transcription.errors import ResourceAdmissionError
from echoflow.transcription.models import CpuEngineConfiguration
from echoflow.transcription.planner import TranscriptionJobPlanner
from echoflow.transcription.strategy import faster_whisper_catalog
from echoflow.workspace.models import WorkspacePaths
from echoflow.workspace.service import WorkspaceService

MIB = 1024**2
GIB = 1024**3


def resources(memory=16 * GIB) -> RunnerResources:
    return RunnerResources(
        platform="TestOS",
        machine="x86_64",
        logical_cpus=8,
        physical_cpus=4,
        affinity_cpus=4,
        cpu_quota_cores=None,
        effective_cpus=4,
        memory_total_bytes=memory,
        memory_available_bytes=memory,
        memory_limit_bytes=None,
        effective_memory_available_bytes=memory,
    )


def cuda(
    *,
    available=4 * GIB,
    total=8 * GIB,
    memory_topology=MemoryTopology.DEDICATED,
) -> AcceleratorDevice:
    return AcceleratorDevice(
        accelerator_id="cuda:0",
        backend=AcceleratorBackend.CUDA,
        device_index=0,
        name="Laptop GPU",
        memory_topology=memory_topology,
        memory_total_bytes=total,
        memory_available_bytes=available,
    )


class CapabilityProvider:
    engine = "faster-whisper"

    def __init__(self, compute_types=("float16", "int8_float16")):
        self.compute_types = compute_types

    def inspect(self, topology):
        targets = [EngineExecutionTarget("cpu", 0, ("int8",), verified=False)]
        if topology.find(AcceleratorBackend.CUDA, 0) is not None:
            targets.append(
                EngineExecutionTarget(
                    "cuda",
                    0,
                    self.compute_types,
                    accelerator_backend=AcceleratorBackend.CUDA,
                )
            )
        return EngineCapabilities(self.engine, tuple(targets))


def media(source, duration=30.0):
    return MediaInfo(
        InputIdentity(
            source.resolve(),
            source.stat().st_size,
            source.stat().st_mtime_ns,
            "0" * 64,
        ),
        "wav",
        duration,
        (
            MediaStream(
                0,
                StreamKind.AUDIO,
                "pcm_s16le",
                duration,
                16_000,
                1,
                "mono",
            ),
        ),
        0,
    )


def planner(
    tmp_path,
    *,
    memory=16 * GIB,
    accelerator=None,
    compute_types=("float16", "int8_float16"),
):
    source = tmp_path / "interview.wav"
    source.write_bytes(b"audio")
    paths = WorkspacePaths(
        tmp_path / "state",
        tmp_path / "cache",
        tmp_path / "cache/models",
        tmp_path / "output",
    )
    facade = FileManagerFacade(LocalFileManager(), Mock(), PerformanceTracker())
    workspace = WorkspaceService(paths, facade, id_factory=lambda: "gpu-plan")
    media_probe = Mock()
    media_probe.probe.return_value = media(source)
    runner_inspector = Mock()
    runner_inspector.inspect.return_value = resources(memory)
    topology_inspector = Mock()
    devices = () if accelerator is None else (accelerator,)
    topology_inspector.inspect.return_value = HardwareTopology(
        resources(memory), devices
    )
    model_registry = Mock()
    model_registry.resolved_revision.return_value = "revision-1"
    service = TranscriptionJobPlanner(
        media_probe=media_probe,
        workspace_service=workspace,
        runner_inspector=runner_inspector,
        policy_planner=RunnerPolicyPlanner(memory_budget_fraction=1),
        strategy_catalog=faster_whisper_catalog(),
        topology_inspector=topology_inspector,
        capability_registry=EngineCapabilityRegistry(
            (CapabilityProvider(compute_types),)
        ),
        model_registry=model_registry,
    )
    return service, source, paths, topology_inspector


def test_balanced_laptop_uses_cuda_when_runtime_and_safe_vram_are_available(tmp_path):
    service, source, paths, topology_inspector = planner(tmp_path, accelerator=cuda())

    plan = service.plan(source)

    assert plan.engine.model == "small"
    assert plan.engine.device == "cuda"
    assert plan.engine.compute_type == "float16"
    assert plan.engine.model_revision == "revision-1"
    assert plan.policy.cpu_threads == 4
    assert plan.engine.cpu_threads == 3
    assert plan.engine.model_cache_path == paths.model_dir / "faster-whisper"
    assert plan.resources.estimated_peak_memory_bytes == 1_280 * MIB
    assert plan.resources.fits_memory_budget is True
    assert plan.warnings == (
        "paths_are_unreserved",
        "accelerator_strategy_selected",
        "accelerator_estimate_is_heuristic",
    )
    topology_inspector.inspect.assert_called_once_with()


def test_accelerated_engine_does_not_reserve_prefetch_cpu_when_only_one_thread_exists(
    tmp_path,
):
    service, _, _, _ = planner(tmp_path, accelerator=cuda())
    strategy = next(
        item
        for item in faster_whisper_catalog().strategies
        if item.strategy_id == "small-cuda-float16"
    )
    policy = ExecutionPolicy(
        profile=ProcessingProfile.BALANCED,
        provisional=False,
        cpu_threads=1,
        memory_budget_bytes=8 * GIB,
    )

    engine = service._engine(policy, strategy)

    assert engine.cpu_threads == 1
    assert service._prefetch_depth(policy, engine) == 0


def test_low_vram_falls_back_to_same_quality_cpu_strategy(tmp_path):
    service, source, _, _ = planner(tmp_path, accelerator=cuda(available=1 * GIB))

    plan = service.plan(source)

    assert plan.engine.model == "small"
    assert plan.engine.device == "cpu"
    assert plan.engine.compute_type == "int8"
    assert "accelerator_strategy_selected" not in plan.warnings


def test_runtime_without_float16_uses_supported_compact_cuda_compute_type(tmp_path):
    service, source, _, _ = planner(
        tmp_path,
        accelerator=cuda(),
        compute_types=("int8_float16",),
    )

    plan = service.plan(source)

    assert plan.engine.device == "cuda"
    assert plan.engine.compute_type == "int8_float16"


def test_visible_gpu_without_engine_capability_is_not_treated_as_executable(tmp_path):
    service, source, _, _ = planner(
        tmp_path,
        accelerator=cuda(),
        compute_types=("int8",),
    )

    plan = service.plan(source)

    assert plan.engine.device == "cpu"
    assert plan.engine.compute_type == "int8"


def test_explicit_unavailable_accelerator_strategy_never_silently_downgrades(tmp_path):
    service, source, _, _ = planner(tmp_path, accelerator=None)

    with pytest.raises(
        ResourceAdmissionError,
        match="^Selected transcription strategy is not feasible on the current runner$",
    ):
        service.plan(source, strategy_id="small-cuda-float16")


def test_explicit_accelerator_strategy_fails_when_vram_headroom_is_too_small(tmp_path):
    service, source, _, _ = planner(tmp_path, accelerator=cuda(available=1 * GIB))

    with pytest.raises(ResourceAdmissionError):
        service.plan(source, strategy_id="small-cuda-float16")


def test_unified_memory_explicit_strategy_counts_gpu_requirement_against_ram(tmp_path):
    service, source, _, _ = planner(
        tmp_path,
        memory=2 * GIB,
        accelerator=cuda(
            available=4 * GIB,
            total=4 * GIB,
            memory_topology=MemoryTopology.UNIFIED,
        ),
    )

    with pytest.raises(ResourceAdmissionError):
        service.plan(source, strategy_id="small-cuda-float16")


def test_low_system_memory_can_still_use_a_smaller_accelerated_quality_tier(tmp_path):
    service, source, _, _ = planner(
        tmp_path,
        memory=1 * GIB,
        accelerator=cuda(available=4 * GIB),
    )

    plan = service.plan(source, profile=ProcessingProfile.BALANCED)

    assert plan.engine.model == "tiny"
    assert plan.engine.device == "cuda"
    assert plan.resources.estimated_peak_memory_bytes == 768 * MIB


def test_strategy_listing_exposes_reasons_and_only_one_recommendation(tmp_path):
    service, _, _, _ = planner(tmp_path, accelerator=cuda(available=1 * GIB))

    assessments = service.assess_strategies(profile=ProcessingProfile.BALANCED)

    assert len(assessments) == 9
    assert sum(bool(item["recommended"]) for item in assessments) == 1
    recommendation = next(item for item in assessments if item["recommended"])
    assert recommendation["strategy"]["strategy_id"] == "small-cpu-int8"
    rejected = next(
        item
        for item in assessments
        if item["strategy"]["strategy_id"] == "small-cuda-float16"
    )
    assert "insufficient_device_memory" in rejected["rejection_reasons"]


def test_accelerator_resume_readmission_succeeds_only_when_current_topology_matches(
    tmp_path,
):
    service, _, paths, _ = planner(tmp_path, accelerator=cuda())
    engine = CpuEngineConfiguration(
        engine="faster-whisper",
        model="small",
        device="cuda",
        compute_type="float16",
        cpu_threads=3,
        beam_size=5,
        language=None,
        model_cache_path=paths.model_dir / "faster-whisper",
        model_revision="revision-1",
    )
    policy = ExecutionPolicy(
        profile=ProcessingProfile.BALANCED,
        provisional=False,
        cpu_threads=4,
        memory_budget_bytes=8 * GIB,
    )

    service._admit_resume_accelerator(
        engine,
        HardwareTopology(resources(), (cuda(),)),
        policy,
    )

    with pytest.raises(
        ResourceAdmissionError,
        match="^Current accelerator capacity is below the interrupted job requirement$",
    ):
        service._admit_resume_accelerator(
            engine,
            HardwareTopology(resources(), ()),
            policy,
        )


def test_unknown_resume_strategy_is_typed_instead_of_mutated(tmp_path):
    service, _, paths, _ = planner(tmp_path, accelerator=cuda())
    engine = CpuEngineConfiguration(
        engine="faster-whisper",
        model="large-v3",
        device="cuda",
        compute_type="float16",
        cpu_threads=3,
        beam_size=5,
        language=None,
        model_cache_path=Path(paths.model_dir / "faster-whisper"),
        model_revision="revision-1",
    )
    policy = ExecutionPolicy(
        ProcessingProfile.BALANCED,
        False,
        4,
        8 * GIB,
    )

    with pytest.raises(
        ResourceAdmissionError,
        match="^Interrupted job accelerator strategy is no longer supported$",
    ):
        service._admit_resume_accelerator(
            engine,
            HardwareTopology(resources(), (cuda(),)),
            policy,
        )