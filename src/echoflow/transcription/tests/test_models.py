from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from echoflow.media.models import InputIdentity, MediaInfo, MediaStream, StreamKind
from echoflow.runner.models import ExecutionPolicy, ProcessingProfile, RunnerResources
from echoflow.transcription.models import (
    CanonicalTranscript,
    CpuEngineConfiguration,
    DecodeConfiguration,
    DecodeStrategy,
    EngineProvenance,
    EngineTranscript,
    RecognizedSegment,
    ResourceEstimate,
    TranscriptionJobPlan,
    TranscriptSource,
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
        profile=ProcessingProfile.BALANCED,
        provisional=False,
        cpu_threads=4,
        memory_budget_bytes=6 * 1024**3,
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
        "revision-1",
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
        "model_revision": "revision-1",
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
        "engine",
        "model",
        "cpu",
        "int8",
        1,
        1,
        None,
        tmp_path / "model",
        "revision-1",
    )
    assert decoder.sample_rate_hz == 1
    assert decoder.channels == 1
    assert engine.cpu_threads == 1
    assert engine.beam_size == 1
    assert engine.model_revision == "revision-1"


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
            ("", "small", "cpu", "int8", 1, 1, None, Path("."), "revision-1"),
            "engine cannot be empty",
        ),
        (
            CpuEngineConfiguration,
            ("fw", "", "cpu", "int8", 1, 1, None, Path("."), "revision-1"),
            "model cannot be empty",
        ),
        (
            CpuEngineConfiguration,
            ("fw", "small", "", "int8", 1, 1, None, Path("."), "revision-1"),
            "device cannot be empty",
        ),
        (
            CpuEngineConfiguration,
            ("fw", "small", "cpu", "", 1, 1, None, Path("."), "revision-1"),
            "compute_type cannot be empty",
        ),
        (
            CpuEngineConfiguration,
            ("fw", "small", "cpu", "int8", 0, 1, None, Path("."), "revision-1"),
            "cpu_threads must be positive",
        ),
        (
            CpuEngineConfiguration,
            ("fw", "small", "cpu", "int8", 1, 0, None, Path("."), "revision-1"),
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
        TranscriptionJobPlan(*arguments, warnings=(), schema_version=3)

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


def test_recognized_segment_is_stable_slotted_and_json_safe():
    segment = RecognizedSegment(7, 1.25, 2.5, "spoken words", -0.4, 0.15)
    assert segment.segment_id == "segment-000007"
    assert segment.to_dict() == {
        "segment_id": "segment-000007",
        "index": 7,
        "start_seconds": 1.25,
        "end_seconds": 2.5,
        "text": "spoken words",
        "average_log_probability": -0.4,
        "no_speech_probability": 0.15,
        "detected_language": None,
        "language_probability": None,
        "language": None,
        "language_spans": [],
        "speaker_ref": None,
    }
    assert not hasattr(segment, "__dict__")
    with pytest.raises(FrozenInstanceError):
        segment.text = "changed"


@pytest.mark.parametrize(
    ("args", "message"),
    [
        ((-1, 0, 1, "text"), "segment index cannot be negative"),
        ((0, -1, 1, "text"), "segment timestamps must be finite and ordered"),
        ((0, 2, 1, "text"), "segment timestamps must be finite and ordered"),
        ((0, float("inf"), 1, "text"), "segment timestamps must be finite and ordered"),
        ((0, 0, 1, " "), "segment text cannot be empty"),
        (
            (0, 0, 1, "text", float("nan")),
            "average_log_probability must be finite",
        ),
        (
            (0, 0, 1, "text", None, -0.1),
            "no_speech_probability must be between 0 and 1",
        ),
        (
            (0, 0, 1, "text", None, 1.1),
            "no_speech_probability must be between 0 and 1",
        ),
    ],
)
def test_recognized_segment_rejects_invalid_values(args, message):
    with pytest.raises(ValueError, match=f"^{message}$"):
        RecognizedSegment(*args)


def test_engine_transcript_validates_language_probability_and_version():
    segment = RecognizedSegment(0, 0, 1, "text")
    result = EngineTranscript((segment,), "en", 0.0, "1.2.1")
    assert result.segments == (segment,)
    assert not hasattr(result, "__dict__")
    assert EngineTranscript((), None, 1.0, "1.2.1").segments == ()
    for arguments, message in (
        (((), " ", None, "1"), "language cannot be empty"),
        (((), "en", -0.1, "1"), "language_probability must be between 0 and 1"),
        (((), "en", 1.1, "1"), "language_probability must be between 0 and 1"),
        (((), "en", float("nan"), "1"), "language_probability must be between 0 and 1"),
        (((), "en", 1.0, ""), "engine_version cannot be empty"),
    ):
        with pytest.raises(ValueError, match=f"^{message}$"):
            EngineTranscript(*arguments)


def test_transcript_source_derives_media_identity_without_disclosing_path(tmp_path):
    *_, media, _, _, _, _, _ = values(tmp_path)
    source = TranscriptSource.from_media(media)
    document = source.to_dict()
    assert document == {
        "sha256": "0" * 64,
        "size_bytes": 100,
        "modified_ns": 200,
        "container_format": "wav",
        "duration_seconds": 2.0,
        "audio_stream_index": 0,
    }
    assert "path" not in document


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"sha256": "A" * 64}, "source sha256 must be a lowercase 64-character digest"),
        ({"size_bytes": 0}, "source size_bytes must be positive"),
        ({"modified_ns": -1}, "source modified_ns cannot be negative"),
        ({"container_format": ""}, "source container_format cannot be empty"),
        (
            {"duration_seconds": 0},
            "source duration_seconds must be finite and positive",
        ),
        (
            {"duration_seconds": float("inf")},
            "source duration_seconds must be finite and positive",
        ),
        ({"audio_stream_index": -1}, "source audio_stream_index cannot be negative"),
    ],
)
def test_transcript_source_rejects_invalid_values(overrides, message):
    fields = {
        "sha256": "0" * 64,
        "size_bytes": 1,
        "modified_ns": 0,
        "container_format": "wav",
        "duration_seconds": 1.0,
        "audio_stream_index": 0,
    }
    fields.update(overrides)
    with pytest.raises(ValueError, match=f"^{message}$"):
        TranscriptSource(**fields)


def test_engine_provenance_records_plan_without_cache_path(tmp_path):
    *_, engine, _, _ = values(tmp_path)
    provenance = EngineProvenance.from_engine(engine, "1.2.1")
    assert provenance.to_dict() == {
        "name": "faster-whisper",
        "package_version": "1.2.1",
        "model": "small",
        "model_revision": "revision-1",
        "device": "cpu",
        "compute_type": "int8",
        "cpu_threads": 4,
        "beam_size": 5,
        "requested_language": None,
    }
    assert "cache" not in provenance.to_dict()


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"name": ""}, "name cannot be empty"),
        ({"package_version": ""}, "package_version cannot be empty"),
        ({"model": ""}, "model cannot be empty"),
        ({"model_revision": " "}, "model_revision cannot be empty"),
        ({"device": ""}, "device cannot be empty"),
        ({"compute_type": ""}, "compute_type cannot be empty"),
        ({"cpu_threads": 0}, "cpu_threads must be positive"),
        ({"beam_size": 0}, "beam_size must be positive"),
    ],
)
def test_engine_provenance_rejects_invalid_values(overrides, message):
    fields = {
        "name": "engine",
        "package_version": "1",
        "model": "tiny",
        "model_revision": "revision-1",
        "device": "cpu",
        "compute_type": "int8",
        "cpu_threads": 1,
        "beam_size": 1,
        "requested_language": None,
    }
    fields.update(overrides)
    with pytest.raises(ValueError, match=f"^{message}$"):
        EngineProvenance(**fields)


def canonical(tmp_path, **overrides):
    *_, media, _, policy, engine, decoder, _ = values(tmp_path)
    fields = {
        "job_id": "job-1",
        "source": TranscriptSource.from_media(media),
        "profile": policy.profile,
        "provisional": policy.provisional,
        "decode_strategy": decoder.strategy,
        "engine": EngineProvenance.from_engine(engine, "1.2.1"),
        "detected_language": "en",
        "language_probability": 0.9,
        "segments": (
            RecognizedSegment(0, 0, 1, "Hello"),
            RecognizedSegment(1, 1, 2, "world."),
        ),
    }
    fields.update(overrides)
    return CanonicalTranscript(**fields)


def test_canonical_transcript_is_complete_and_does_not_embed_private_paths(tmp_path):
    transcript = canonical(tmp_path)
    document = transcript.to_dict()
    assert document["schema_version"] == 1
    assert document["job_id"] == "job-1"
    assert document["profile"] == "balanced"
    assert document["provisional"] is False
    assert document["decode_strategy"] == "direct"
    assert document["detected_language"] == "en"
    assert document["language_probability"] == 0.9
    assert document["text"] == "Hello world."
    assert len(document["segments"]) == 2
    assert "path" not in str(document)
    assert not hasattr(transcript, "__dict__")


def test_screening_canonical_transcript_must_remain_provisional(tmp_path):
    transcript = canonical(
        tmp_path, profile=ProcessingProfile.SCREENING, provisional=True
    )
    assert transcript.provisional is True
    with pytest.raises(
        ValueError, match="^provisional flag must match the processing profile$"
    ):
        canonical(tmp_path, profile=ProcessingProfile.SCREENING, provisional=False)
    with pytest.raises(
        ValueError, match="^provisional flag must match the processing profile$"
    ):
        canonical(tmp_path, profile=ProcessingProfile.BALANCED, provisional=True)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"job_id": ""}, "job_id cannot be empty"),
        ({"schema_version": 4}, "unsupported transcript schema version"),
        ({"detected_language": " "}, "detected_language cannot be empty"),
        (
            {"language_probability": -0.1},
            "language_probability must be between 0 and 1",
        ),
        ({"language_probability": 1.1}, "language_probability must be between 0 and 1"),
        (
            {"language_probability": float("nan")},
            "language_probability must be between 0 and 1",
        ),
        (
            {"segments": (RecognizedSegment(1, 0, 1, "wrong index"),)},
            "segment indices must be contiguous and zero-based",
        ),
    ],
)
def test_canonical_transcript_rejects_invalid_values(tmp_path, overrides, message):
    with pytest.raises(ValueError, match=f"^{message}$"):
        canonical(tmp_path, **overrides)


def test_engine_configuration_rejects_empty_model_revision(tmp_path):
    with pytest.raises(ValueError, match="^model_revision cannot be empty$"):
        CpuEngineConfiguration(
            "engine", "model", "cpu", "int8", 1, 1, None, tmp_path, " "
        )
