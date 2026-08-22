from pathlib import Path

import pytest

from scholion.media.errors import UnsupportedMediaError
from scholion.media.models import InputIdentity, MediaInfo, MediaStream, StreamKind
from scholion.media.selection import AudioStreamSelector


def media() -> MediaInfo:
    return MediaInfo(
        input=InputIdentity(Path("recording.mkv"), 100, 1, "a" * 64),
        container_format="matroska,webm",
        duration_seconds=30.0,
        streams=(
            MediaStream(0, StreamKind.VIDEO, "h264", 30.0),
            MediaStream(2, StreamKind.AUDIO, "aac", 30.0, 48_000, 2),
            MediaStream(5, StreamKind.AUDIO, "aac", 30.0, 48_000, 2),
        ),
        primary_audio_stream_index=2,
    )


def test_default_selection_is_first_audio_stream() -> None:
    source = media()

    selected = AudioStreamSelector().select(source)

    assert selected is source
    assert selected.primary_audio_stream_index == 2


def test_explicit_selection_returns_same_media_with_requested_audio_stream() -> None:
    source = media()

    selected = AudioStreamSelector().select(source, requested_index=5)

    assert selected is not source
    assert selected.primary_audio_stream_index == 5
    assert selected.primary_audio_stream.index == 5
    assert source.primary_audio_stream_index == 2


@pytest.mark.parametrize("requested_index", [-1, 0, 3, 99])
def test_selection_rejects_non_audio_or_missing_stream(requested_index: int) -> None:
    with pytest.raises(
        UnsupportedMediaError,
        match="^Requested audio stream is not available$",
    ):
        AudioStreamSelector().select(media(), requested_index=requested_index)
