from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from echoflow.app.processing_center import (
    _requires_audio_stream_confirmation,
    _serialize_preflight,
)
from echoflow.media.models import MediaStream, StreamKind
from echoflow.runner.models import ProcessingProfile
from echoflow.workspace.models import JobId


def _plan():
    camera = MediaStream(
        index=1,
        kind=StreamKind.AUDIO,
        codec="aac",
        duration_seconds=42.0,
        sample_rate_hz=48_000,
        channels=2,
        title="Camera scratch",
        language="eng",
    )
    lav = MediaStream(
        index=3,
        kind=StreamKind.AUDIO,
        codec="pcm_s16le",
        duration_seconds=42.0,
        sample_rate_hz=48_000,
        channels=1,
        title="Lav microphone",
        language="eng",
        is_default=True,
    )
    video = MediaStream(index=0, kind=StreamKind.VIDEO, codec="h264")
    return SimpleNamespace(
        job=SimpleNamespace(
            job_id=JobId("planned-job"),
            input_path=Path("/private/recording.mkv"),
        ),
        media=SimpleNamespace(
            input=SimpleNamespace(sha256="a" * 64),
            container_format="matroska",
            duration_seconds=42.0,
            streams=(video, camera, lav),
            primary_audio_stream=camera,
        ),
        policy=SimpleNamespace(
            profile=ProcessingProfile.BALANCED,
            provisional=False,
            memory_budget_bytes=8_000,
        ),
        engine=SimpleNamespace(
            engine="faster-whisper",
            model="small",
            model_revision="revision-small",
            device="cpu",
            compute_type="int8",
            cpu_threads=4,
        ),
        decoder=SimpleNamespace(strategy=SimpleNamespace(value="ffmpeg-normalize")),
        enhancement=SimpleNamespace(enabled=False),
        resources=SimpleNamespace(
            total_disk_bytes=12_000,
            estimated_peak_memory_bytes=2_000,
            fits_memory_budget=True,
        ),
        warnings=(),
    )


def test_multitrack_preflight_requires_explicit_stream_until_index_is_requested():
    plan = cast(Any, _plan())

    assert _requires_audio_stream_confirmation(plan, None) is True
    assert _requires_audio_stream_confirmation(plan, 1) is False
    assert _requires_audio_stream_confirmation(plan, 3) is False


def test_preflight_serializes_bounded_human_track_metadata_without_paths():
    plan = cast(Any, _plan())

    result = _serialize_preflight(plan, audio_stream_selection_required=True)

    assert result["audio_stream_selection_required"] is True
    assert result["selected_audio_stream_index"] == 1
    assert result["audio_streams"] == [
        {
            "index": 1,
            "codec": "aac",
            "duration_seconds": 42.0,
            "sample_rate_hz": 48_000,
            "channels": 2,
            "title": "Camera scratch",
            "language": "eng",
        },
        {
            "index": 3,
            "codec": "pcm_s16le",
            "duration_seconds": 42.0,
            "sample_rate_hz": 48_000,
            "channels": 1,
            "title": "Lav microphone",
            "language": "eng",
            "is_default": True,
        },
    ]
    assert "/private" not in str(result)
