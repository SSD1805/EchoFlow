import json
from unittest.mock import Mock

import pytest

from echoflow.core.file_manager_facade import FileManagerFacade
from echoflow.core.performance_tracker import PerformanceTracker
from echoflow.interfaces.local_file_manager import LocalFileManager
from echoflow.media.errors import InputChangedError
from echoflow.media.models import InputIdentity, MediaInfo, MediaStream, StreamKind
from echoflow.runner.models import (
    ExecutionPolicy,
    ModelTier,
    ProcessingProfile,
    RunnerResources,
)
from echoflow.runner.policy import RunnerPolicyPlanner
from echoflow.transcription.audio import DecodedAudio
from echoflow.transcription.errors import ResourceAdmissionError, TranscriptionError
from echoflow.transcription.executor import TranscriptionExecutor
from echoflow.transcription.models import (
    CpuEngineConfiguration,
    DecodeConfiguration,
    DecodeStrategy,
    EngineTranscript,
    RecognizedSegment,
    ResourceEstimate,
    TranscriptionJobPlan,
)
from echoflow.workspace.models import Artifact, ArtifactKind, Job, JobId, WorkspacePaths
from echoflow.workspace.service import WorkspaceService

MIB = 1024**2
GIB = 1024**3


def resources(*, memory=8 * GIB, cpus=4):
    return RunnerResources(
        platform="TestOS",
        machine="x86_64",
        logical_cpus=cpus,
        physical_cpus=cpus,
        affinity_cpus=cpus,
        cpu_quota_cores=None,
        effective_cpus=cpus,
        memory_total_bytes=memory,
        memory_available_bytes=memory,
        memory_limit_bytes=None,
        effective_memory_available_bytes=memory,
    )


def plan(tmp_path, *, decode=DecodeStrategy.DIRECT, fits=True):
    source = tmp_path / "private participant video.mp4"
    source.write_bytes(b"recording")
    paths = WorkspacePaths(
        tmp_path / "state",
        tmp_path / "cache",
        tmp_path / "cache/models",
        tmp_path / "output",
    )
    job = Job(JobId("job-1"), source, paths.jobs_dir / "job-1", paths.output_dir)
    media = MediaInfo(
        InputIdentity(
            source.resolve(),
            source.stat().st_size,
            source.stat().st_mtime_ns,
            "0" * 64,
        ),
        "mov,mp4,m4a,3gp,3g2,mj2",
        2.0,
        (
            MediaStream(0, StreamKind.VIDEO, "h264", 2.0),
            MediaStream(1, StreamKind.AUDIO, "aac", 2.0, 48_000, 2),
        ),
        1,
    )
    artifact = Artifact(
        job.job_id,
        ArtifactKind.CANONICAL_JSON,
        paths.output_dir / "private participant video.json",
    )
    runner = resources()
    policy = ExecutionPolicy(
        ProcessingProfile.BALANCED,
        False,
        4,
        8 * GIB,
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
        paths.model_dir / "faster-whisper",
        "revision-1",
    )
    decoder = DecodeConfiguration(decode, "pcm_s16le", 16_000, 1)
    estimate = ResourceEstimate(
        16 * MIB,
        64 * 1024,
        750 * MIB,
        2_304 * MIB,
        8 * GIB,
        fits,
    )
    return (
        TranscriptionJobPlan(
            job,
            artifact,
            media,
            runner,
            policy,
            engine,
            decoder,
            estimate,
            ("paths_are_unreserved",),
        ),
        paths,
    )


def executor(tmp_path, planned, paths, *, available=None):
    facade = FileManagerFacade(LocalFileManager(), Mock(), PerformanceTracker())
    workspace = WorkspaceService(paths, facade, id_factory=lambda: "unused")
    probe = Mock()
    probe.probe.return_value = planned.media
    inspector = Mock()
    inspector.inspect.return_value = available or resources()
    decoder = Mock()
    decoder.decode.return_value = DecodedAudio(planned.job.input_path, False)
    transcriber = Mock()
    transcriber.transcribe.return_value = EngineTranscript(
        (
            RecognizedSegment(0, 0.0, 1.0, "Hello", -0.2, 0.1),
            RecognizedSegment(1, 1.0, 2.0, "world.", -0.3, 0.2),
        ),
        "en",
        0.98,
        "1.2.1",
    )
    service = TranscriptionExecutor(
        media_probe=probe,
        workspace_service=workspace,
        file_manager=facade,
        runner_inspector=inspector,
        policy_planner=RunnerPolicyPlanner(memory_budget_fraction=1),
        audio_decoder=decoder,
        transcriber=transcriber,
    )
    return service, probe, inspector, decoder, transcriber


def test_execution_claims_paths_transcribes_audio_and_writes_private_safe_json(
    tmp_path,
):
    planned, paths = plan(tmp_path, decode=DecodeStrategy.FFMPEG_NORMALIZE)
    service, probe, inspector, decoder, transcriber = executor(tmp_path, planned, paths)
    normalized = planned.job.workspace_dir / "normalized.wav"
    decoder.decode.return_value = DecodedAudio(normalized, True)

    result = service.execute(planned, allow_model_download=True)

    assert result.job.workspace_dir.is_dir()
    assert result.artifact.path.is_file()
    document = json.loads(result.artifact.path.read_text())
    assert document["schema_version"] == 1
    assert document["job_id"] == "job-1"
    assert document["source"]["sha256"] == "0" * 64
    assert "path" not in document["source"]
    assert document["decode_strategy"] == "ffmpeg_normalize"
    assert document["engine"] == {
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
    assert document["detected_language"] == "en"
    assert document["language_probability"] == 0.98
    assert document["text"] == "Hello world."
    assert [item["segment_id"] for item in document["segments"]] == [
        "segment-000000",
        "segment-000001",
    ]
    assert str(planned.job.input_path) not in result.artifact.path.read_text()
    assert str(planned.engine.model_cache_path) not in result.artifact.path.read_text()
    probe.probe.assert_called_once_with(planned.job.input_path)
    assert inspector.inspect.call_count == 2
    decoder.decode.assert_called_once_with(
        planned.media, planned.decoder, result.job.workspace_dir
    )
    decoder.cleanup.assert_called_once_with(DecodedAudio(normalized, True))
    transcriber.transcribe.assert_called_once_with(
        normalized,
        planned.engine,
        allow_model_download=True,
    )
    assert result.to_dict()["paths_reserved"] is True
    assert result.to_dict()["dry_run"] is False


def test_artifact_collision_is_resolved_at_reservation_not_assumed_from_plan(tmp_path):
    planned, paths = plan(tmp_path)
    paths.output_dir.mkdir(parents=True)
    planned.artifact.path.write_text("existing")
    service, *_ = executor(tmp_path, planned, paths)

    result = service.execute(planned)

    assert planned.artifact.path.read_text() == "existing"
    assert result.artifact.path.name == "private participant video-2.json"


def test_input_identity_change_is_rejected_before_workspace_creation(tmp_path):
    planned, paths = plan(tmp_path)
    service, probe, *_ = executor(tmp_path, planned, paths)
    changed = MediaInfo(
        InputIdentity(
            planned.job.input_path,
            planned.media.input.size_bytes,
            planned.media.input.modified_ns,
            "1" * 64,
        ),
        planned.media.container_format,
        planned.media.duration_seconds,
        planned.media.streams,
        planned.media.primary_audio_stream_index,
    )
    probe.probe.return_value = changed

    with pytest.raises(
        InputChangedError,
        match="^Input changed between transcription planning and execution$",
    ):
        service.execute(planned)
    assert not paths.state_dir.exists()
    assert not paths.output_dir.exists()


@pytest.mark.parametrize(
    ("planned_fits", "available_memory"),
    [(False, 8 * GIB), (True, 2_303 * MIB)],
)
def test_insufficient_memory_is_rejected_before_input_is_reprobed(
    tmp_path, planned_fits, available_memory
):
    planned, paths = plan(tmp_path, fits=planned_fits)
    service, probe, inspector, decoder, transcriber = executor(
        tmp_path,
        planned,
        paths,
        available=resources(memory=available_memory),
    )
    with pytest.raises(
        ResourceAdmissionError,
        match="^Available memory is below the selected model's safe execution budget$",
    ):
        service.execute(planned)
    inspector.inspect.assert_called_once_with()
    probe.probe.assert_not_called()
    decoder.decode.assert_not_called()
    transcriber.transcribe.assert_not_called()


def test_reduced_cpu_capacity_requires_a_fresh_plan(tmp_path):
    planned, paths = plan(tmp_path)
    service, probe, _, _, _ = executor(
        tmp_path, planned, paths, available=resources(cpus=3)
    )
    with pytest.raises(
        ResourceAdmissionError,
        match="^Available CPU capacity changed; create a new transcription plan$",
    ):
        service.execute(planned)
    probe.probe.assert_not_called()


def test_resources_are_rechecked_after_normalization_before_model_load(tmp_path):
    planned, paths = plan(tmp_path, decode=DecodeStrategy.FFMPEG_NORMALIZE)
    service, _, inspector, decoder, transcriber = executor(tmp_path, planned, paths)
    inspector.inspect.side_effect = [resources(), resources(memory=2_303 * MIB)]

    with pytest.raises(ResourceAdmissionError):
        service.execute(planned)

    assert inspector.inspect.call_count == 2
    decoder.cleanup.assert_called_once_with(decoder.decode.return_value)
    transcriber.transcribe.assert_not_called()
    assert not planned.artifact.path.exists()


def test_transcription_failure_releases_placeholder_and_cleans_audio(tmp_path):
    planned, paths = plan(tmp_path)
    service, _, _, decoder, transcriber = executor(tmp_path, planned, paths)
    transcriber.transcribe.side_effect = TranscriptionError("engine failed")

    with pytest.raises(TranscriptionError, match="^engine failed$"):
        service.execute(planned)

    assert not planned.artifact.path.exists()
    decoder.cleanup.assert_called_once_with(decoder.decode.return_value)


def test_cleanup_failure_does_not_replace_successful_transcript(tmp_path):
    planned, paths = plan(tmp_path)
    service, _, _, decoder, _ = executor(tmp_path, planned, paths)
    decoder.cleanup.side_effect = OSError("cleanup failure")

    with pytest.raises(OSError, match="cleanup failure"):
        service.execute(planned)

    assert planned.artifact.path.exists()


def test_failed_artifact_cleanup_error_does_not_mask_engine_failure(tmp_path):
    planned, paths = plan(tmp_path)
    service, _, _, _, transcriber = executor(tmp_path, planned, paths)
    transcriber.transcribe.side_effect = TranscriptionError("engine failed")
    service.file_manager.delete_file = Mock(side_effect=OSError("cleanup failed"))

    with pytest.raises(TranscriptionError, match="^engine failed$"):
        service.execute(planned)
    service.file_manager.delete_file.assert_called_once_with(planned.artifact.path)


def test_execution_result_rejects_mismatched_job_artifact_or_transcript(tmp_path):
    planned, paths = plan(tmp_path)
    service, *_ = executor(tmp_path, planned, paths)
    result = service.execute(planned)
    wrong_artifact = Artifact(
        JobId("other"), result.artifact.kind, result.artifact.path
    )
    with pytest.raises(ValueError, match="^job and artifact IDs must match$"):
        type(result)(result.job, wrong_artifact, result.transcript)
    wrong_transcript = type(result.transcript)(
        job_id="other",
        source=result.transcript.source,
        profile=result.transcript.profile,
        provisional=result.transcript.provisional,
        decode_strategy=result.transcript.decode_strategy,
        engine=result.transcript.engine,
        detected_language=result.transcript.detected_language,
        language_probability=result.transcript.language_probability,
        segments=result.transcript.segments,
    )
    with pytest.raises(ValueError, match="^job and transcript IDs must match$"):
        type(result)(result.job, result.artifact, wrong_transcript)
