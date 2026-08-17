from dataclasses import replace
from unittest.mock import Mock

import pytest

from echoflow.runner.models import ProcessingProfile
from echoflow.transcription.checkpoint import ResumeEngineSettings, ResumeSettings
from echoflow.transcription.errors import CheckpointError, ResourceAdmissionError
from echoflow.transcription.models import (
    DecodeConfiguration,
    DecodeStrategy,
    SegmentationConfiguration,
    TranscriptSource,
)
from echoflow.transcription.tests.test_planner import (
    GIB,
    MIB,
    build_planner,
    media_info,
    runner_resources,
)
from echoflow.workspace.models import JobId


def resume_settings(media):
    return ResumeSettings(
        source=TranscriptSource.from_media(media),
        profile=ProcessingProfile.ACCURACY,
        provisional=False,
        engine=ResumeEngineSettings(
            engine="faster-whisper",
            model="medium",
            device="cpu",
            compute_type="int8",
            cpu_threads=2,
            beam_size=5,
            language=None,
            model_revision="immutable-revision",
        ),
        decoder=DecodeConfiguration(
            DecodeStrategy.FFMPEG_NORMALIZE,
            "pcm_s16le",
            16_000,
            1,
        ),
        segmentation=SegmentationConfiguration(segment_duration_seconds=300),
        model_cache_bytes=2_500 * MIB,
        estimated_peak_memory_bytes=4_352 * MIB,
    )


def test_resume_restores_original_engine_contract_on_a_stronger_machine(tmp_path):
    source = tmp_path / "interview.m4a"
    source.write_bytes(b"audio")
    media = media_info(source)
    planner, paths, _, inspector = build_planner(
        tmp_path, media, runner_resources(8 * GIB)
    )
    checkpoint_store = Mock()
    checkpoint_store.resume_settings.return_value = resume_settings(media)
    planner.checkpoint_store = checkpoint_store

    plan = planner.plan_resume(source, job_id=JobId("plan-1"))

    assert plan.job.job_id == JobId("plan-1")
    assert plan.policy.profile is ProcessingProfile.ACCURACY
    assert plan.policy.cpu_threads == 2
    assert plan.engine.model == "medium"
    assert plan.engine.cpu_threads == 2
    assert plan.engine.model_revision == "immutable-revision"
    assert plan.engine.model_cache_path == paths.model_dir / "faster-whisper"
    assert plan.segmentation.segment_duration_seconds == 300
    assert plan.resources.model_cache_bytes == 2_500 * MIB
    assert plan.resources.estimated_peak_memory_bytes == 4_352 * MIB
    assert plan.resources.fits_memory_budget is True
    assert plan.warnings == ("paths_are_unreserved", "resume_contract_restored")
    checkpoint_store.resume_settings.assert_called_once_with(plan.job)
    inspector.inspect.assert_called_once_with()


def test_resume_rejects_same_job_id_with_different_source_identity(tmp_path):
    source = tmp_path / "interview.m4a"
    source.write_bytes(b"audio")
    media = media_info(source)
    planner, _, _, inspector = build_planner(tmp_path, media)
    settings = resume_settings(media)
    checkpoint_store = Mock()
    checkpoint_store.resume_settings.return_value = replace(
        settings,
        source=replace(settings.source, sha256="b" * 64),
    )
    planner.checkpoint_store = checkpoint_store

    with pytest.raises(
        CheckpointError,
        match="^Input does not match the interrupted job checkpoint$",
    ):
        planner.plan_resume(source, job_id=JobId("plan-1"))

    inspector.inspect.assert_not_called()


def test_resume_refuses_when_current_cpu_is_below_original_requirement(tmp_path):
    source = tmp_path / "interview.m4a"
    source.write_bytes(b"audio")
    media = media_info(source)
    constrained = replace(
        runner_resources(8 * GIB),
        physical_cpus=1,
        affinity_cpus=1,
        effective_cpus=1,
    )
    planner, _, _, _ = build_planner(tmp_path, media, constrained)
    checkpoint_store = Mock()
    checkpoint_store.resume_settings.return_value = resume_settings(media)
    planner.checkpoint_store = checkpoint_store

    with pytest.raises(
        ResourceAdmissionError,
        match="^Current CPU capacity is below the interrupted job requirement$",
    ):
        planner.plan_resume(source, job_id=JobId("plan-1"))


def test_resume_refuses_when_current_memory_is_below_original_requirement(tmp_path):
    source = tmp_path / "interview.m4a"
    source.write_bytes(b"audio")
    media = media_info(source)
    planner, _, _, _ = build_planner(tmp_path, media, runner_resources(3 * GIB))
    checkpoint_store = Mock()
    checkpoint_store.resume_settings.return_value = resume_settings(media)
    planner.checkpoint_store = checkpoint_store

    with pytest.raises(
        ResourceAdmissionError,
        match="^Current memory budget is below the interrupted job requirement$",
    ):
        planner.plan_resume(source, job_id=JobId("plan-1"))