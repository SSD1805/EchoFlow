from dataclasses import FrozenInstanceError

import pytest

from echoflow.media.models import (
    InputIdentity,
    MediaInfo,
    MediaStream,
    MediaTemporalTag,
    StreamKind,
    TemporalTagKind,
    TemporalTagSource,
)


def identity(tmp_path) -> InputIdentity:
    return InputIdentity(
        path=tmp_path / "nested" / ".." / "recording.wav",
        size_bytes=12,
        modified_ns=34,
        sha256="a" * 64,
    )


def audio_stream(**overrides) -> MediaStream:
    values = {
        "index": 0,
        "kind": StreamKind.AUDIO,
        "codec": "pcm_s16le",
        "duration_seconds": 1.5,
        "sample_rate_hz": 16_000,
        "channels": 1,
        "channel_layout": "mono",
        "bit_rate_bps": 256_000,
    }
    values.update(overrides)
    return MediaStream(**values)


def test_input_identity_is_normalized_frozen_slotted_and_serializable(tmp_path):
    value = identity(tmp_path)
    assert value.path == (tmp_path / "recording.wav").resolve()
    assert value.to_dict() == {
        "path": str((tmp_path / "recording.wav").resolve()),
        "size_bytes": 12,
        "modified_ns": 34,
        "sha256": "a" * 64,
    }
    assert not hasattr(value, "__dict__")
    with pytest.raises(FrozenInstanceError):
        value.size_bytes = 13


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"size_bytes": 0}, "size_bytes must be positive"),
        ({"modified_ns": -1}, "modified_ns cannot be negative"),
        ({"sha256": "A" * 64}, "sha256 must be a lowercase 64-character digest"),
        ({"sha256": "a" * 63}, "sha256 must be a lowercase 64-character digest"),
    ],
)
def test_input_identity_rejects_invalid_wire_values(tmp_path, overrides, message):
    values = {
        "path": tmp_path / "input.wav",
        "size_bytes": 1,
        "modified_ns": 0,
        "sha256": "0" * 64,
    }
    values.update(overrides)
    with pytest.raises(ValueError, match=f"^{message}$"):
        InputIdentity(**values)


def test_media_stream_serialization_preserves_optional_audio_fields():
    stream = audio_stream()
    assert stream.to_dict() == {
        "index": 0,
        "kind": "audio",
        "codec": "pcm_s16le",
        "duration_seconds": 1.5,
        "sample_rate_hz": 16_000,
        "channels": 1,
        "channel_layout": "mono",
        "bit_rate_bps": 256_000,
    }
    assert [kind.value for kind in StreamKind] == [
        "audio",
        "video",
        "subtitle",
        "data",
        "attachment",
        "unknown",
    ]
    defaults = MediaStream(1, StreamKind.VIDEO, "h264")
    assert defaults.duration_seconds is None
    assert defaults.sample_rate_hz is None
    assert defaults.channels is None
    assert defaults.channel_layout is None
    assert defaults.bit_rate_bps is None
    assert not hasattr(stream, "__dict__")
    with pytest.raises(FrozenInstanceError):
        stream.codec = "aac"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"index": -1}, "stream index cannot be negative"),
        ({"codec": ""}, "stream codec cannot be empty"),
        (
            {"duration_seconds": -0.1},
            "stream duration must be finite and nonnegative",
        ),
        (
            {"duration_seconds": float("inf")},
            "stream duration must be finite and nonnegative",
        ),
        ({"sample_rate_hz": 0}, "sample_rate_hz must be positive"),
        ({"channels": 0}, "channels must be positive"),
        ({"bit_rate_bps": 0}, "bit_rate_bps must be positive"),
    ],
)
def test_media_stream_rejects_invalid_values(overrides, message):
    with pytest.raises(ValueError, match=f"^{message}$"):
        audio_stream(**overrides)


def test_temporal_tag_is_source_explicit_frozen_and_serializable():
    tag = MediaTemporalTag(
        TemporalTagKind.TIMECODE,
        " 10:00:00:00 ",
        TemporalTagSource.STREAM,
        stream_index=2,
    )

    assert tag.value == "10:00:00:00"
    assert tag.to_dict() == {
        "kind": "timecode",
        "value": "10:00:00:00",
        "source": "stream",
        "stream_index": 2,
    }
    assert not hasattr(tag, "__dict__")
    with pytest.raises(FrozenInstanceError):
        tag.value = "changed"


@pytest.mark.parametrize(
    ("tag", "message"),
    [
        (
            (TemporalTagKind.TIMECODE, " ", TemporalTagSource.FORMAT, None),
            "temporal tag value cannot be empty",
        ),
        (
            (TemporalTagKind.TIMECODE, "1", TemporalTagSource.FORMAT, 0),
            "format temporal tags cannot have a stream index",
        ),
        (
            (TemporalTagKind.CREATION_TIME, "1", TemporalTagSource.STREAM, None),
            "stream temporal tags require a nonnegative stream index",
        ),
        (
            (TemporalTagKind.CREATION_TIME, "1", TemporalTagSource.STREAM, -1),
            "stream temporal tags require a nonnegative stream index",
        ),
    ],
)
def test_temporal_tag_rejects_ambiguous_source_coordinates(tag, message):
    with pytest.raises(ValueError, match=f"^{message}$"):
        MediaTemporalTag(*tag)


def test_media_info_selects_primary_audio_and_serializes_all_streams(tmp_path):
    video = MediaStream(index=0, kind=StreamKind.VIDEO, codec="h264")
    audio = audio_stream(index=1)
    temporal = MediaTemporalTag(
        TemporalTagKind.CREATION_TIME,
        "2026-04-05T12:34:56Z",
        TemporalTagSource.FORMAT,
    )
    media = MediaInfo(
        input=identity(tmp_path),
        container_format="mov,mp4,m4a,3gp,3g2,mj2",
        duration_seconds=2.5,
        streams=(video, audio),
        primary_audio_stream_index=1,
        temporal_tags=(temporal,),
    )
    payload = media.to_dict()
    assert media.primary_audio_stream is audio
    assert payload["container_format"] == "mov,mp4,m4a,3gp,3g2,mj2"
    assert payload["duration_seconds"] == 2.5
    assert payload["primary_audio_stream_index"] == 1
    assert payload["streams"] == [video.to_dict(), audio.to_dict()]
    assert payload["temporal_tags"] == [temporal.to_dict()]
    assert payload["input"] == identity(tmp_path).to_dict()
    assert not hasattr(media, "__dict__")
    with pytest.raises(FrozenInstanceError):
        media.duration_seconds = 3


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"container_format": ""}, "container_format cannot be empty"),
        ({"duration_seconds": 0}, "duration_seconds must be finite and positive"),
        (
            {"duration_seconds": float("nan")},
            "duration_seconds must be finite and positive",
        ),
        ({"streams": ()}, "streams cannot be empty"),
        (
            {"primary_audio_stream_index": 7},
            "primary_audio_stream_index must select one audio stream",
        ),
    ],
)
def test_media_info_rejects_incomplete_or_inconsistent_values(
    tmp_path, overrides, message
):
    values = {
        "input": identity(tmp_path),
        "container_format": "wav",
        "duration_seconds": 1.0,
        "streams": (audio_stream(),),
        "primary_audio_stream_index": 0,
    }
    values.update(overrides)
    with pytest.raises(ValueError, match=f"^{message}$"):
        MediaInfo(**values)


def test_duplicate_primary_audio_stream_indices_are_rejected(tmp_path):
    with pytest.raises(
        ValueError,
        match="^primary_audio_stream_index must select one audio stream$",
    ):
        MediaInfo(
            input=identity(tmp_path),
            container_format="wav",
            duration_seconds=1,
            streams=(audio_stream(), audio_stream(codec="aac")),
            primary_audio_stream_index=0,
        )
