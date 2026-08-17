import json
import os
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from echoflow.core.file_manager_facade import FileManagerFacade
from echoflow.core.performance_tracker import PerformanceTracker
from echoflow.interfaces.local_file_manager import LocalFileManager
from echoflow.media.models import InputIdentity, MediaInfo, MediaStream, StreamKind
from echoflow.runner.models import ProcessingProfile
from echoflow.transcription.checkpoint import LocalCheckpointStore
from echoflow.transcription.enhancement import ffmpeg_afftdn_configuration
from echoflow.transcription.enhancement_models import EnhancementConfiguration
from echoflow.transcription.errors import CheckpointError
from echoflow.transcription.models import (
    AudioSegmentWindow,
    CpuEngineConfiguration,
    DecodeConfiguration,
    DecodeStrategy,
    EngineTranscript,
    RecognizedSegment,
    SegmentationConfiguration,
)
from echoflow.workspace.models import Job, JobId, WorkspacePaths

MIB = 1024**2


def context(tmp_path, *, profile=ProcessingProfile.BALANCED):
    source = tmp_path / "participant-secret-name.wav"
    source.write_bytes(b"audio")
    paths = WorkspacePaths(
        tmp_path / "state",
        tmp_path / "cache",
        tmp_path / "cache" / "models",
        tmp_path / "output",
    )
    workspace = paths.jobs_dir / "job-1"
    workspace.mkdir(parents=True)
    job = Job(JobId("job-1"), source, workspace, paths.output_dir)
    media = MediaInfo(
        InputIdentity(
            source.resolve(),
            source.stat().st_size,
            source.stat().st_mtime_ns,
            "a" * 64,
        ),
        "wav",
        2.0,
        (MediaStream(0, StreamKind.AUDIO, "pcm_s16le", 2.0, 16_000, 1),),
        0,
    )
    plan = Mock()
    plan.schema_version = 1
    plan.media = media
    plan.policy = SimpleNamespace(profile=profile, provisional=False)
    plan.engine = CpuEngineConfiguration(
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
    plan.decoder = DecodeConfiguration(DecodeStrategy.DIRECT, "pcm_s16le", 16_000, 1)
    plan.enhancement = EnhancementConfiguration()
    plan.segmentation = SegmentationConfiguration(segment_duration_seconds=1)
    plan.resources = SimpleNamespace(
        model_cache_bytes=750 * MIB,
        estimated_peak_memory_bytes=2_304 * MIB,
    )
    windows = (
        AudioSegmentWindow(0, 0, 16_000, 16_000),
        AudioSegmentWindow(1, 16_000, 32_000, 16_000),
    )
    facade = FileManagerFacade(LocalFileManager(), Mock(), PerformanceTracker())
    return LocalCheckpointStore(facade), job, plan, windows, source


def result(text, *, language="en"):
    return EngineTranscript(
        (
            RecognizedSegment(
                0,
                0.0,
                1.0,
                text,
                -0.2,
                0.1,
                detected_language=language,
                language_probability=0.98,
            ),
        ),
        language,
        0.98,
        "1.2.1",
    )


def test_manifest_is_private_local_and_omits_source_and_model_paths(tmp_path):
    store, job, plan, windows, source = context(tmp_path)

    store.initialize(job, plan, windows)

    manifest = job.workspace_dir / "checkpoints" / "manifest.json"
    document = manifest.read_text()
    assert manifest.is_file()
    assert str(source) not in document
    assert source.name not in document
    assert str(plan.engine.model_cache_path) not in document
    assert "model_cache_path" not in document
    contract = json.loads(document)["contract"]
    assert contract["source"]["sha256"] == "a" * 64
    assert contract["enhancement"]["mode"] == "off"
    if os.name != "nt":
        assert manifest.stat().st_mode & 0o777 == 0o600
        assert manifest.parent.stat().st_mode & 0o777 == 0o700


def test_manifest_restores_original_execution_settings_without_local_paths(tmp_path):
    store, job, plan, windows, _ = context(tmp_path)
    store.initialize(job, plan, windows)

    settings = store.resume_settings(job)

    assert settings.profile is ProcessingProfile.BALANCED
    assert settings.engine.model == "small"
    assert settings.engine.cpu_threads == 4
    assert settings.engine.model_revision == "revision-1"
    assert settings.decoder == plan.decoder
    assert settings.enhancement == plan.enhancement
    assert settings.segmentation == plan.segmentation
    assert settings.model_cache_bytes == 750 * MIB
    assert settings.estimated_peak_memory_bytes == 2_304 * MIB
    restored_engine = settings.engine.configuration(tmp_path / "new-model-cache")
    assert restored_engine.model_cache_path == (tmp_path / "new-model-cache").resolve()


def test_completed_segment_round_trips_with_detected_language(tmp_path):
    store, job, plan, windows, _ = context(tmp_path)
    store.initialize(job, plan, windows)
    store.save_segment(job, plan, windows, windows[0], result("sensitive words"))

    restored = store.restore(job, plan, windows)

    assert len(restored.completed) == 1
    assert restored.completed[0][0] == windows[0]
    restored_result = restored.completed[0][1]
    assert restored_result.segments[0].text == "sensitive words"
    assert restored_result.segments[0].detected_language == "en"
    assert restored_result.segments[0].language_probability == 0.98
    assert restored.engine_version == "1.2.1"


def test_contract_change_refuses_resume(tmp_path):
    store, job, plan, windows, _ = context(tmp_path)
    store.initialize(job, plan, windows)
    plan.policy = SimpleNamespace(profile=ProcessingProfile.ACCURACY, provisional=False)

    with pytest.raises(
        CheckpointError,
        match="^Private checkpoint does not match the current transcription contract$",
    ):
        store.restore(job, plan, windows)


def test_enhancement_change_refuses_resume(tmp_path):
    store, job, plan, windows, _ = context(tmp_path)
    store.initialize(job, plan, windows)
    plan.enhancement = ffmpeg_afftdn_configuration()

    with pytest.raises(
        CheckpointError,
        match="^Private checkpoint does not match the current transcription contract$",
    ):
        store.restore(job, plan, windows)


def test_tampered_segment_payload_fails_integrity_check(tmp_path):
    store, job, plan, windows, _ = context(tmp_path)
    store.initialize(job, plan, windows)
    store.save_segment(job, plan, windows, windows[0], result("original"))
    checkpoint = job.workspace_dir / "checkpoints" / "audio-000000.json"
    document = json.loads(checkpoint.read_text())
    document["result"]["segments"][0]["text"] = "tampered"
    checkpoint.write_text(json.dumps(document))

    with pytest.raises(
        CheckpointError,
        match="^Private segment checkpoint integrity check failed$",
    ):
        store.restore(job, plan, windows)


def test_noncontiguous_completed_prefix_is_rejected(tmp_path):
    store, job, plan, windows, _ = context(tmp_path)
    store.initialize(job, plan, windows)
    store.save_segment(job, plan, windows, windows[1], result("second"))

    with pytest.raises(
        CheckpointError,
        match="^Completed private checkpoints are not a contiguous prefix$",
    ):
        store.restore(job, plan, windows)


def test_checkpoint_size_bound_is_enforced_before_json_parse(tmp_path):
    store, job, plan, windows, _ = context(tmp_path)
    store.initialize(job, plan, windows)
    bounded = LocalCheckpointStore(store.file_manager, max_checkpoint_bytes=2)

    with pytest.raises(
        CheckpointError,
        match="^Private checkpoint file size is outside safe bounds$",
    ):
        bounded.restore(job, plan, windows)


def test_clear_removes_sensitive_checkpoint_payloads_after_completion(tmp_path):
    store, job, plan, windows, _ = context(tmp_path)
    store.initialize(job, plan, windows)
    store.save_segment(job, plan, windows, windows[0], result("delete me"))

    store.clear(job)

    assert list((job.workspace_dir / "checkpoints").iterdir()) == []
