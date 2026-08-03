from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from echoflow.media.models import InputIdentity, MediaInfo, MediaStream, StreamKind
from echoflow.runner.models import (
    ExecutionPolicy,
    ModelTier,
    ProcessingProfile,
    RunnerResources,
)
from echoflow.transcription.models import (
    CpuEngineConfiguration,
    DecodeConfiguration,
    DecodeStrategy,
    ResourceEstimate,
    TranscriptionJobPlan,
)
from echoflow.workspace.models import Artifact, ArtifactKind, Job, JobId


def values(tmp_path):
    source = (tmp_path / "input.wav").resolve()
    job = Job(
        JobId("job-1"),
        source,
        tmp_path / "state/jobs/job-1",
        tmp_path / "output",
    )
    artifact = Artifact(
        job.job_id, ArtifactKind.CANONICAL_JSON, job.output_dir / "input.json"
    )
    identity = InputIdentity(source, 100, 200, "0" * 64)
    media = MediaInfo(
        identity,
        "wav",
        2.0,
        (
            MediaStream(
                0,
                StreamKind.AUDIO,
                "pcm_s16le",
                2.0,
                16_000,
                1,
                "mono",
                256_000,
            ),
        ),
        0,
    )
    runner = RunnerResources(
        platform="TestOS",
        machine="x86_64",
        logical_cpus=4,
        physical_cpus=2,
        affinity_cpus=4,
        cpu_quota_cores=None,
        effective_cpus=4,
        memory_total_bytes=8 * 1024**3,
        memory_available_bytes=6 * 1024**3,
        memory_limit_bytes=None,
        effective_memory_available_bytes=6 * 1024**3,
    )
    policy = ExecutionPolicy(
        ProcessingProfile.BALANCED,
        False,
        4,
        6 * 1024**3,
        ModelTier.STANDARD,
    )
    engine = CpuEngineConfiguration(
        "faster-whisper",
        "small",
        "cpu",
        "int8",
        4,
        5,
        None,
        tmp_path / "cache/models/faster-whisper/nested/../small",
    )
    decoder = DecodeConfiguration(DecodeStrategy.DIRECT, "pcm_s16le", 16_000, 1)
    resources = ResourceEstimate(10, 20, 30, 40, 50, True)
    return job, artifact, media, runner, policy, engine, decoder, resources


def test_job_plan_is_frozen_slotted_complete_and_json_safe(tmp_path):
    plan = TranscriptionJobPlan(*values(tmp_path), warnings=("paths_are_unreserved",))
    document = plan.to_dict()
    assert document["schema_version"] == 1
    assert document["dry_run"] is True
    assert document["paths_reserved"] is False
    assert document["job"] == plan.job.to_dict()
    assert document["artifact"] == plan.artifact.to_dict()
    assert document["media"] == plan.media.to_dict()
    assert document["runner"] == plan.runner.to_dict()
    assert document["policy"] == plan.policy.to_dict()
    assert document["engine"] == plan.engine.to_dict()
    assert document["decoder"] == plan.decoder.to_dict()
    assert document["resources"] == plan.resources.to_dict()
    assert document["warnings"] == ["paths_are_unreserved"]
    assert not hasattr(plan, "__dict__")
    with pytest.raises(FrozenInstanceError):
        plan.paths_reserved = True


def test_decode_and_engine_configuration_serialize_stable_wire_values(tmp_path):
    *_, engine, decoder, _ = values(tmp_path)
    assert decoder.to_dict() == {
        "strategy": "direct",
        "output_codec": "pcm_s16le",
        "sample_rate_hz": 16_000,
        "channels": 1,
    }
    assert engine.to_dict() == {
        "engine": "faster-whisper",
        "model": "small",
        "device": "cpu",
        "compute_type": "int8",
        "cpu_threads": 4,
        "beam_size": 5,
        "language": None,
        "model_cache_path": str(
            (tmp_path / "cache/models/faster-whisper/small").resolve()
        ),
    }
    assert [strategy.value for strategy in DecodeStrategy] == [
        "direct",
        "ffmpeg_normalize",
    ]
    assert not hasattr(decoder, "__dict__")
    with pytest.raises(FrozenInstanceError):
        decoder.strategy = DecodeStrategy.FFMPEG_NORMALIZE
    assert not hasattr(engine, "__dict__")
    with pytest.raises(FrozenInstanceError):
        engine.model = "medium"


def test_execution_configuration_positive_lower_boundaries_are_valid(tmp_path):
    decoder = DecodeConfiguration(DecodeStrategy.DIRECT, "pcm", 1, 1)
    engine = CpuEngineConfiguration(
        "engine", "model", "cpu", "int8", 1, 1, None, tmp_path / "model"
    )
    assert decoder.sample_rate_hz == 1
    assert decoder.channels == 1
    assert engine.cpu_threads == 1
    assert engine.beam_size == 1


@pytest.mark.parametrize(
    ("constructor", "args", "message"),
    [
        (
            DecodeConfiguration,
            (DecodeStrategy.DIRECT, "", 16_000, 1),
            "output_codec cannot be empty",
        ),
        (
            DecodeConfiguration,
            (DecodeStrategy.DIRECT, "pcm", 0, 1),
            "sample_rate_hz must be positive",
        ),
        (
            DecodeConfiguration,
            (DecodeStrategy.DIRECT, "pcm", 16_000, 0),
            "channels must be positive",
        ),
        (
            CpuEngineConfiguration,
            ("", "small", "cpu", "int8", 1, 1, None, Path(".")),
            "engine cannot be empty",
        ),
        (
            CpuEngineConfiguration,
            ("fw", "", "cpu", "int8", 1, 1, None, Path(".")),
            "model cannot be empty",
        ),
        (
            CpuEngineConfiguration,
            ("fw", "small", "", "int8", 1, 1, None, Path(".")),
            "device cannot be empty",
        ),
        (
            CpuEngineConfiguration,
            ("fw", "small", "cpu", "", 1, 1, None, Path(".")),
            "compute_type cannot be empty",
        ),
        (
            CpuEngineConfiguration,
            ("fw", "small", "cpu", "int8", 0, 1, None, Path(".")),
            "cpu_threads must be positive",
        ),
        (
            CpuEngineConfiguration,
            ("fw", "small", "cpu", "int8", 1, 0, None, Path(".")),
            "beam_size must be positive",
        ),
    ],
)
def test_execution_configuration_rejects_invalid_values(constructor, args, message):
    with pytest.raises(ValueError, match=f"^{message}$"):
        constructor(*args)


@pytest.mark.parametrize(
    "field",
    [
        "private_workspace_bytes",
        "public_output_bytes",
        "model_cache_bytes",
        "estimated_peak_memory_bytes",
        "memory_budget_bytes",
    ],
)
def test_resource_estimate_rejects_negative_values(field):
    values = {
        "private_workspace_bytes": 1,
        "public_output_bytes": 2,
        "model_cache_bytes": 3,
        "estimated_peak_memory_bytes": 4,
        "memory_budget_bytes": 5,
        "fits_memory_budget": True,
    }
    values[field] = -1
    with pytest.raises(ValueError, match=f"^{field} cannot be negative$"):
        ResourceEstimate(**values)


def test_resource_estimate_reports_total_and_heuristic_contract():
    estimate = ResourceEstimate(1, 2, 3, 4, 5, True)
    assert estimate.total_disk_bytes == 6
    assert estimate.to_dict() == {
        "private_workspace_bytes": 1,
        "public_output_bytes": 2,
        "model_cache_bytes": 3,
        "total_disk_bytes": 6,
        "estimated_peak_memory_bytes": 4,
        "memory_budget_bytes": 5,
        "fits_memory_budget": True,
        "heuristic": True,
    }
    assert not hasattr(estimate, "__dict__")
    with pytest.raises(FrozenInstanceError):
        estimate.memory_budget_bytes = 6


def test_zero_resource_estimates_are_valid_and_exact():
    estimate = ResourceEstimate(0, 0, 0, 0, 0, False)
    assert estimate.total_disk_bytes == 0
    assert estimate.to_dict()["estimated_peak_memory_bytes"] == 0


def test_job_plan_rejects_reserved_wrong_version_or_inconsistent_values(tmp_path):
    arguments = values(tmp_path)
    with pytest.raises(
        ValueError, match="^a dry-run plan cannot claim reserved paths$"
    ):
        TranscriptionJobPlan(*arguments, warnings=(), paths_reserved=True)
    with pytest.raises(ValueError, match="^unsupported job-plan schema version$"):
        TranscriptionJobPlan(*arguments, warnings=(), schema_version=2)

    job, artifact, media, runner, policy, engine, decoder, resources = arguments
    wrong_artifact = Artifact(
        JobId("job-2"), ArtifactKind.CANONICAL_JSON, artifact.path
    )
    with pytest.raises(ValueError, match="^job and artifact IDs must match$"):
        TranscriptionJobPlan(
            job,
            wrong_artifact,
            media,
            runner,
            policy,
            engine,
            decoder,
            resources,
            (),
        )
    other_media = MediaInfo(
        InputIdentity(tmp_path / "other.wav", 1, 0, "1" * 64),
        "wav",
        1,
        (MediaStream(0, StreamKind.AUDIO, "pcm"),),
        0,
    )
    with pytest.raises(ValueError, match="^job and media input paths must match$"):
        TranscriptionJobPlan(
            job,
            artifact,
            other_media,
            runner,
            policy,
            engine,
            decoder,
            resources,
            (),
        )
