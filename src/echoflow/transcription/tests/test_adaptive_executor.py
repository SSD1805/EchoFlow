from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import pytest

from echoflow.core.measurements import MeasurementRecorder
from echoflow.runner.models import RunnerResources
from echoflow.runner.topology import (
    AcceleratorBackend,
    AcceleratorDevice,
    MemoryTopology,
)
from echoflow.transcription.adaptive_executor import AdaptiveTranscriptionExecutor
from echoflow.transcription.audio import DecodedAudio
from echoflow.transcription.capabilities import (
    EngineCapabilities,
    EngineCapabilityRegistry,
    EngineExecutionTarget,
)
from echoflow.transcription.checkpoint import RestoredCheckpoint
from echoflow.transcription.errors import (
    CheckpointError,
    ResourceAdmissionError,
    TranscriptionError,
)
from echoflow.transcription.executor import TranscriptionExecutor
from echoflow.transcription.models import AudioSegmentWindow, EngineTranscript
from echoflow.transcription.segmentation import MaterializedAudioSegment
from echoflow.transcription.strategy import (
    StrategyCatalog,
    StrategyDefinition,
    StrategyEvaluator,
)
from echoflow.workspace.models import Job, JobId

GIB = 1024**3


def resources() -> RunnerResources:
    return RunnerResources(
        platform="TestOS",
        machine="x86_64",
        logical_cpus=8,
        physical_cpus=4,
        affinity_cpus=4,
        cpu_quota_cores=None,
        effective_cpus=4,
        memory_total_bytes=16 * GIB,
        memory_available_bytes=12 * GIB,
        memory_limit_bytes=None,
        effective_memory_available_bytes=12 * GIB,
    )


def cuda(available=4 * GIB) -> AcceleratorDevice:
    return AcceleratorDevice(
        accelerator_id="cuda:0",
        backend=AcceleratorBackend.CUDA,
        device_index=0,
        name="Laptop GPU",
        memory_topology=MemoryTopology.DEDICATED,
        memory_total_bytes=8 * GIB,
        memory_available_bytes=available,
    )


def gpu_strategy() -> StrategyDefinition:
    return StrategyDefinition(
        strategy_id="small-cuda-float16",
        model="small",
        quality_rank=2,
        model_cache_bytes=1,
        estimated_peak_memory_bytes=1 * GIB,
        device="cuda",
        compute_type="float16",
        accelerator_backend=AcceleratorBackend.CUDA,
        estimated_peak_device_memory_bytes=1 * GIB,
        performance_rank=30,
    )


def capabilities() -> EngineCapabilities:
    return EngineCapabilities(
        "faster-whisper",
        (
            EngineExecutionTarget(
                "cuda",
                0,
                ("float16",),
                accelerator_backend=AcceleratorBackend.CUDA,
            ),
        ),
    )


class CapabilityProvider:
    engine = "faster-whisper"

    def __init__(self, value):
        self.value = value

    def inspect(self, _topology):
        return self.value


def bare_service() -> AdaptiveTranscriptionExecutor:
    service = object.__new__(AdaptiveTranscriptionExecutor)
    service.observer = MeasurementRecorder()
    logger = Mock()
    logger.bind.return_value = logger
    service.logger = logger
    service.audio_segmenter = Mock()
    service.checkpoint_store = Mock()
    service.transcript_assembler = Mock()
    return service


def job(tmp_path) -> Job:
    input_path = tmp_path / "input.wav"
    input_path.write_bytes(b"audio")
    return Job(
        JobId("job-1"),
        input_path,
        tmp_path / "state/jobs/job-1",
        tmp_path / "output",
    )


def windows(count=3):
    return tuple(
        AudioSegmentWindow(index, index * 10, (index + 1) * 10, 10)
        for index in range(count)
    )


def engine_result(version="1.2.1"):
    return EngineTranscript((), None, None, version)


def execution_plan(*, device="cuda", compute_type="float16"):
    return SimpleNamespace(
        engine=SimpleNamespace(
            engine="faster-whisper",
            model="small",
            device=device,
            compute_type=compute_type,
        ),
        runner=resources(),
        resources=SimpleNamespace(memory_budget_bytes=8 * GIB),
        decoder=SimpleNamespace(),
    )


def configure_admission(service, *, devices=(None,), caps=None):
    actual_devices = tuple(device for device in devices if device is not None)
    service.accelerator_probe = Mock()
    service.accelerator_probe.inspect.return_value = actual_devices
    service.capability_registry = EngineCapabilityRegistry(
        (CapabilityProvider(caps or capabilities()),)
    )
    service.strategy_catalog = StrategyCatalog((gpu_strategy(),), version=2)
    service.strategy_evaluator = StrategyEvaluator()


def test_accelerator_admission_requires_strategy_current_device_and_runtime_support():
    service = bare_service()
    configure_admission(service, devices=(cuda(),))

    service._admit_accelerator(execution_plan())

    service.accelerator_probe.inspect.assert_called_once_with()


def test_accelerator_disappearing_between_plan_and_execution_fails_closed():
    service = bare_service()
    configure_admission(service, devices=())

    with pytest.raises(
        ResourceAdmissionError,
        match="^Selected accelerator is unavailable or below its safe resource budget$",
    ):
        service._admit_accelerator(execution_plan())


def test_accelerator_vram_drop_before_model_load_fails_closed():
    service = bare_service()
    configure_admission(service, devices=(cuda(available=1 * GIB),))

    with pytest.raises(ResourceAdmissionError):
        service._admit_accelerator(execution_plan())


def test_removed_accelerator_strategy_requires_new_plan():
    service = bare_service()
    configure_admission(service, devices=(cuda(),))

    with pytest.raises(
        ResourceAdmissionError,
        match="^Selected accelerator strategy is no longer supported$",
    ):
        service._admit_accelerator(execution_plan(compute_type="int8_float16"))


def test_cpu_admission_uses_existing_base_path_without_accelerator_probe():
    service = bare_service()
    service.accelerator_probe = Mock()
    plan = execution_plan(device="cpu", compute_type="int8")

    with patch.object(TranscriptionExecutor, "_admit") as base_admit:
        service._admit(plan)

    base_admit.assert_called_once_with(plan)
    service.accelerator_probe.inspect.assert_not_called()


def test_gpu_admission_runs_base_resource_check_before_accelerator_check():
    service = bare_service()
    service._admit_accelerator = Mock()
    plan = execution_plan()

    with patch.object(TranscriptionExecutor, "_admit") as base_admit:
        service._admit(plan)

    base_admit.assert_called_once_with(plan)
    service._admit_accelerator.assert_called_once_with(plan)


def test_accelerated_segments_prefetch_but_checkpoint_strictly_in_order(tmp_path):
    service = bare_service()
    planned = execution_plan()
    planned_job = job(tmp_path)
    segment_windows = windows(3)
    materialized = tuple(
        MaterializedAudioSegment(window, Path.cwd() / f"test-{window.segment_id}.wav")
        for window in segment_windows
    )
    service.audio_segmenter.materialize.side_effect = materialized
    session = Mock(engine_version="1.2.1")
    session.transcribe.side_effect = tuple(engine_result() for _ in segment_windows)
    service._open_session = Mock(return_value=session)
    service.transcript_assembler.assemble.return_value = engine_result()

    result = service._transcribe_accelerated(
        planned,
        DecodedAudio(Path.cwd() / "decoded.wav", False),
        segment_windows,
        planned_job,
        RestoredCheckpoint((), None, None),
        allow_model_download=False,
    )

    assert result.engine_version == "1.2.1"
    assert session.transcribe.call_args_list == [
        call(segment.path) for segment in materialized
    ]
    assert service.checkpoint_store.save_segment.call_args_list == [
        call(planned_job, planned, segment_windows, window, engine_result())
        for window in segment_windows
    ]
    assert service.audio_segmenter.cleanup.call_args_list == [
        call(segment) for segment in materialized
    ]
    assert service.observer.values()["segments.prefetch_depth"] == 1
    assert service.observer.values()["segments.completed"] == 3


def _blocking_materializer(service, materialized, started, release):
    def materialize(_audio_path, window, _decoder, _workspace):
        if window.index == 1:
            started.set()
            assert release.wait(timeout=1)
        return materialized[window.index]

    service.audio_segmenter.materialize.side_effect = materialize


def test_transcription_failure_cleans_started_prefetch_segment(tmp_path):
    service = bare_service()
    planned = execution_plan()
    planned_job = job(tmp_path)
    segment_windows = windows(2)
    materialized = tuple(
        MaterializedAudioSegment(
            window, Path.cwd() / f"failure-{window.segment_id}.wav"
        )
        for window in segment_windows
    )
    second_started = Event()
    release_second = Event()
    _blocking_materializer(service, materialized, second_started, release_second)
    session = Mock(engine_version="1.2.1")

    def fail_transcription(_path):
        assert second_started.wait(timeout=1)
        release_second.set()
        raise TranscriptionError("engine failed")

    session.transcribe.side_effect = fail_transcription
    service._open_session = Mock(return_value=session)

    with pytest.raises(TranscriptionError, match="^engine failed$"):
        service._transcribe_accelerated(
            planned,
            DecodedAudio(Path.cwd() / "decoded.wav", False),
            segment_windows,
            planned_job,
            RestoredCheckpoint((), None, None),
            allow_model_download=False,
        )

    service.audio_segmenter.cleanup.assert_has_calls(
        [call(materialized[0]), call(materialized[1])]
    )
    assert service.audio_segmenter.cleanup.call_count == 2
    service.checkpoint_store.save_segment.assert_not_called()


def test_checkpoint_failure_cleans_started_prefetch_without_committing_it(tmp_path):
    service = bare_service()
    planned = execution_plan()
    planned_job = job(tmp_path)
    segment_windows = windows(2)
    materialized = tuple(
        MaterializedAudioSegment(
            window, Path.cwd() / f"checkpoint-{window.segment_id}.wav"
        )
        for window in segment_windows
    )
    second_started = Event()
    release_second = Event()
    _blocking_materializer(service, materialized, second_started, release_second)
    session = Mock(engine_version="1.2.1")

    def transcribe(_path):
        assert second_started.wait(timeout=1)
        release_second.set()
        return engine_result()

    session.transcribe.side_effect = transcribe
    service._open_session = Mock(return_value=session)
    service.checkpoint_store.save_segment.side_effect = CheckpointError("write failed")

    with pytest.raises(CheckpointError, match="^write failed$"):
        service._transcribe_accelerated(
            planned,
            DecodedAudio(Path.cwd() / "decoded.wav", False),
            segment_windows,
            planned_job,
            RestoredCheckpoint((), None, None),
            allow_model_download=False,
        )

    service.audio_segmenter.cleanup.assert_has_calls(
        [call(materialized[0]), call(materialized[1])]
    )
    assert service.audio_segmenter.cleanup.call_count == 2
    assert service.checkpoint_store.save_segment.call_count == 1


def test_resume_engine_version_mismatch_happens_before_new_materialization(tmp_path):
    service = bare_service()
    planned = execution_plan()
    planned_job = job(tmp_path)
    session = Mock(engine_version="2.0")
    service._open_session = Mock(return_value=session)

    with pytest.raises(
        CheckpointError,
        match="^Installed transcription engine version does not match checkpoints$",
    ):
        service._transcribe_accelerated(
            planned,
            DecodedAudio(Path.cwd() / "decoded.wav", False),
            windows(2),
            planned_job,
            RestoredCheckpoint((), None, "1.0"),
            allow_model_download=False,
        )

    service.audio_segmenter.materialize.assert_not_called()


def test_completed_resume_assembles_without_opening_engine_or_prefetching(tmp_path):
    service = bare_service()
    planned = execution_plan()
    planned_job = job(tmp_path)
    segment_windows = windows(1)
    completed_result = engine_result()
    service.transcript_assembler.assemble.return_value = completed_result
    service._open_session = Mock()

    result = service._transcribe_accelerated(
        planned,
        DecodedAudio(Path.cwd() / "decoded.wav", False),
        segment_windows,
        planned_job,
        RestoredCheckpoint(((segment_windows[0], completed_result),), None, "1.2.1"),
        allow_model_download=False,
    )

    assert result is completed_result
    service._open_session.assert_not_called()
    service.audio_segmenter.materialize.assert_not_called()
