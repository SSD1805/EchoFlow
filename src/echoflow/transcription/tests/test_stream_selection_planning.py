from dataclasses import replace
from unittest.mock import Mock

from echoflow.transcription.models import TranscriptSource
from echoflow.transcription.tests.test_planner import build_planner, media_info
from echoflow.transcription.tests.test_planner_resume import resume_settings
from echoflow.workspace.models import JobId


def multistream_media(source):
    base = media_info(source)
    first = base.primary_audio_stream
    second = replace(first, index=5)
    return replace(
        base,
        streams=(first, second),
        primary_audio_stream_index=first.index,
    )


def test_fresh_plan_binds_explicit_audio_stream_into_source_contract(tmp_path):
    source = tmp_path / "multitrack.mkv"
    source.write_bytes(b"audio")
    media = multistream_media(source)
    planner, _, _, _ = build_planner(tmp_path, media)

    plan = planner.plan(source, audio_stream_index=5)

    assert plan.media.primary_audio_stream_index == 5
    assert TranscriptSource.from_media(plan.media).audio_stream_index == 5


def test_resume_restores_checkpointed_audio_stream_instead_of_probe_default(tmp_path):
    source = tmp_path / "multitrack.mkv"
    source.write_bytes(b"audio")
    probed = multistream_media(source)
    checkpointed = replace(probed, primary_audio_stream_index=5)
    planner, _, _, _ = build_planner(tmp_path, probed)
    checkpoint_store = Mock()
    checkpoint_store.resume_settings.return_value = resume_settings(checkpointed)
    planner.checkpoint_store = checkpoint_store

    plan = planner.plan_resume(source, job_id=JobId("plan-1"))

    assert plan.media.primary_audio_stream_index == 5
    assert TranscriptSource.from_media(plan.media) == checkpoint_store.resume_settings.return_value.source
