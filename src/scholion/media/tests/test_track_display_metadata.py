import pytest

from scholion.media import probe as probe_module
from scholion.media.models import InputIdentity, MediaStream, StreamKind
from scholion.media.probe import FfprobeMediaProbe


def _identity(tmp_path) -> InputIdentity:
    return InputIdentity(tmp_path / "recording.mkv", 5, 0, "a" * 64)


def _base_payload(*, multitrack: bool = True) -> dict[str, object]:
    streams: list[dict[str, object]] = [
        {
            "index": 0,
            "codec_type": "audio",
            "codec_name": "aac",
            "duration": "10.0",
            "sample_rate": "48000",
            "channels": 2,
        }
    ]
    if multitrack:
        streams.append(
            {
                "index": 3,
                "codec_type": "audio",
                "codec_name": "pcm_s16le",
                "duration": "10.0",
                "sample_rate": "48000",
                "channels": 1,
            }
        )
    return {
        "streams": streams,
        "format": {"format_name": "matroska", "duration": "10.0"},
    }


def _display_payload() -> dict[str, object]:
    return {
        "streams": [
            {
                "index": 0,
                "tags": {"title": "  Camera scratch  ", "language": "eng"},
                "disposition": {"default": 0},
            },
            {
                "index": 3,
                "tags": {"title": "Lav microphone", "language": "eng"},
                "disposition": {"default": 1},
            },
        ]
    }


def test_parse_binds_display_metadata_by_exact_stream_index_including_zero(tmp_path):
    display = probe_module._display_stream_lookup(_display_payload())

    media = FfprobeMediaProbe._parse(
        _base_payload(),
        _identity(tmp_path),
        display_lookup=display,
    )

    first, second = media.streams
    assert first.index == 0
    assert first.title == "Camera scratch"
    assert first.language == "eng"
    assert first.is_default is False
    assert second.index == 3
    assert second.title == "Lav microphone"
    assert second.language == "eng"
    assert second.is_default is True
    assert second.to_dict()["is_default"] is True


def test_multitrack_probe_runs_one_extra_bounded_display_query(monkeypatch, tmp_path):
    source = tmp_path / "recording.mkv"
    source.write_bytes(b"media")
    calls: list[str] = []

    def fake_run(self, executable, path, *, entries):
        del self, executable
        assert path == source.resolve()
        calls.append(entries)
        if entries == probe_module._FFPROBE_TRACK_DISPLAY_ENTRIES:
            return _display_payload()
        return _base_payload()

    monkeypatch.setattr(probe_module.shutil, "which", lambda name: "/tools/ffprobe")
    monkeypatch.setattr(FfprobeMediaProbe, "_run", fake_run)

    media = FfprobeMediaProbe().probe(source)

    assert calls == [
        probe_module._FFPROBE_ENTRIES,
        probe_module._FFPROBE_TRACK_DISPLAY_ENTRIES,
    ]
    assert media.streams[1].title == "Lav microphone"


def test_single_track_probe_does_not_request_display_metadata(monkeypatch, tmp_path):
    source = tmp_path / "recording.m4a"
    source.write_bytes(b"media")
    calls: list[str] = []

    def fake_run(self, executable, path, *, entries):
        del self, executable
        assert path == source.resolve()
        calls.append(entries)
        return _base_payload(multitrack=False)

    monkeypatch.setattr(probe_module.shutil, "which", lambda name: "/tools/ffprobe")
    monkeypatch.setattr(FfprobeMediaProbe, "_run", fake_run)

    FfprobeMediaProbe().probe(source)

    assert calls == [probe_module._FFPROBE_ENTRIES]


def test_display_lookup_and_multitrack_detection_fail_closed_on_malformed_values():
    assert probe_module._display_stream_lookup({"streams": "not-a-list"}) == {}
    assert probe_module._display_stream_lookup(
        {"streams": [{"index": True}, {"index": "bad"}, {"index": 2}]}
    ) == {2: {"index": 2}}
    assert probe_module._multiple_audio_streams({"streams": []}) is False
    assert (
        probe_module._multiple_audio_streams(
            {
                "streams": [
                    {"codec_type": "audio"},
                    {"codec_type": "video"},
                    {"codec_type": "audio"},
                ]
            }
        )
        is True
    )


def test_stream_display_metadata_is_normalized_bounded_and_typed():
    stream = MediaStream(
        1,
        StreamKind.AUDIO,
        "aac",
        title="  Interview microphone  ",
        language=" eng ",
        is_default=True,
    )
    assert stream.title == "Interview microphone"
    assert stream.language == "eng"
    assert stream.is_default is True

    with pytest.raises(ValueError, match="^title exceeds safe display length$"):
        MediaStream(1, StreamKind.AUDIO, "aac", title="x" * 201)
    with pytest.raises(ValueError, match="^language exceeds safe display length$"):
        MediaStream(1, StreamKind.AUDIO, "aac", language="x" * 65)
    with pytest.raises(ValueError, match="^is_default must be boolean$"):
        MediaStream(1, StreamKind.AUDIO, "aac", is_default=1)  # type: ignore[arg-type]
