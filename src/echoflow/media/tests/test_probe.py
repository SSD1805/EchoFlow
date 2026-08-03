import hashlib
import json
import subprocess

import pytest

from echoflow.media import probe as probe_module
from echoflow.media.errors import (
    InputChangedError,
    MediaProbeError,
    MediaToolUnavailableError,
    UnsupportedMediaError,
)
from echoflow.media.models import InputIdentity, StreamKind
from echoflow.media.probe import FfprobeMediaProbe


def payload(*, duration="1.250", streams=None):
    return {
        "streams": streams
        or [
            {
                "index": 0,
                "codec_name": "pcm_s16le",
                "codec_type": "audio",
                "sample_rate": "16000",
                "channels": 1,
                "channel_layout": "mono",
                "duration": "1.250",
                "bit_rate": "256000",
            }
        ],
        "format": {"format_name": "wav", "duration": duration},
    }


def install_completed_probe(monkeypatch, response, *, returncode=0):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            command,
            returncode,
            stdout=response if isinstance(response, str) else json.dumps(response),
            stderr="private ffprobe detail",
        )

    def fake_which(name):
        captured["lookup"] = name
        return "/tools/ffprobe"

    monkeypatch.setattr(probe_module.shutil, "which", fake_which)
    monkeypatch.setattr(probe_module.subprocess, "run", fake_run)
    return captured


def test_probe_fingerprints_and_parses_local_media_without_network_protocols(
    monkeypatch, tmp_path
):
    source = tmp_path / "interview.wav"
    source.write_bytes(b"audio-content")
    captured = install_completed_probe(monkeypatch, payload())

    result = FfprobeMediaProbe(timeout_seconds=3).probe(source)

    assert result.input.path == source.resolve()
    assert result.input.size_bytes == len(b"audio-content")
    assert result.input.modified_ns == source.stat().st_mtime_ns
    assert result.input.sha256 == hashlib.sha256(b"audio-content").hexdigest()
    assert result.container_format == "wav"
    assert result.duration_seconds == 1.25
    assert result.primary_audio_stream.codec == "pcm_s16le"
    assert result.primary_audio_stream.sample_rate_hz == 16_000
    assert result.primary_audio_stream.channels == 1
    assert result.primary_audio_stream.channel_layout == "mono"
    assert result.primary_audio_stream.bit_rate_bps == 256_000
    assert captured["lookup"] == "ffprobe"
    assert captured["command"] == [
        "/tools/ffprobe",
        "-v",
        "error",
        "-protocol_whitelist",
        "file",
        "-show_entries",
        "format=format_name,duration:stream=index,codec_type,codec_name,duration,"
        "sample_rate,channels,channel_layout,bit_rate",
        "-of",
        "json",
        str(source.resolve()),
    ]
    assert captured["kwargs"] == {
        "capture_output": True,
        "check": False,
        "text": True,
        "timeout": 3,
    }


def test_probe_preserves_all_streams_and_uses_first_audio_as_primary(
    monkeypatch, tmp_path
):
    source = tmp_path / "session.mkv"
    source.write_bytes(b"media")
    streams = [
        {"index": 0, "codec_type": "video", "codec_name": "h264"},
        {"index": 2, "codec_type": "audio", "codec_name": "aac"},
        {"index": 3, "codec_type": "audio", "codec_name": "opus"},
        {"index": 4, "codec_type": "future", "codec_name": "unknown"},
    ]
    install_completed_probe(monkeypatch, payload(streams=streams))

    result = FfprobeMediaProbe().probe(source)

    assert [stream.index for stream in result.streams] == [0, 2, 3, 4]
    assert result.primary_audio_stream_index == 2
    assert result.streams[-1].kind is StreamKind.UNKNOWN
    assert result.streams[0].channel_layout is None
    assert result.streams[1].codec == "aac"
    assert result.streams[1].channels is None


def test_probe_security_limits_and_defaults_are_stable():
    probe = FfprobeMediaProbe()
    assert probe_module._HASH_BLOCK_SIZE == 1_048_576
    assert probe_module._MAX_PROBE_OUTPUT_BYTES == 1_048_576
    assert probe_module._FFPROBE_ENTRIES == (
        "format=format_name,duration:stream=index,codec_type,codec_name,duration,"
        "sample_rate,channels,channel_layout,bit_rate"
    )
    assert probe.timeout_seconds == 10.0
    assert probe.max_output_bytes == 1_048_576


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("N/A", None),
        ("", None),
        (True, None),
        (False, None),
        ("invalid", None),
        (-1, None),
        (0, None),
        (1, 1),
        ("2", 2),
    ],
)
def test_optional_integer_parser_has_exact_boundaries(value, expected):
    assert probe_module._optional_int(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("N/A", None),
        ("", None),
        (True, None),
        (False, None),
        ("invalid", None),
        (-1, None),
        (float("inf"), None),
        (0, 0.0),
        (0.5, 0.5),
        ("1", 1.0),
    ],
)
def test_optional_float_parser_has_exact_boundaries(value, expected):
    assert probe_module._optional_float(value) == expected


def test_stream_duration_is_used_when_container_duration_is_unavailable(tmp_path):
    identity = InputIdentity(tmp_path / "audio", 1, 0, "0" * 64)
    result = FfprobeMediaProbe._parse(payload(duration="N/A"), identity)
    assert result.duration_seconds == 1.25


def test_subsecond_stream_duration_is_preserved_as_fallback(tmp_path):
    identity = InputIdentity(tmp_path / "audio", 1, 0, "0" * 64)
    document = payload(duration="N/A")
    document["streams"][0]["duration"] = "0.5"
    result = FfprobeMediaProbe._parse(document, identity)
    assert result.duration_seconds == 0.5


def test_subsecond_container_duration_is_not_replaced_by_stream_duration(tmp_path):
    identity = InputIdentity(tmp_path / "audio", 1, 0, "0" * 64)
    document = payload(duration="0.5")
    document["streams"][0]["duration"] = "0.75"
    result = FfprobeMediaProbe._parse(document, identity)
    assert result.duration_seconds == 0.5


def test_zero_container_duration_falls_back_to_positive_stream_duration(tmp_path):
    identity = InputIdentity(tmp_path / "audio", 1, 0, "0" * 64)
    document = payload(duration="0")
    document["streams"][0]["duration"] = "0.5"
    result = FfprobeMediaProbe._parse(document, identity)
    assert result.duration_seconds == 0.5


@pytest.mark.parametrize("duration", [None, "N/A", "0", "nan", "inf", "-1"])
def test_missing_nonpositive_or_nonfinite_duration_is_rejected(tmp_path, duration):
    identity = InputIdentity(tmp_path / "audio", 1, 0, "0" * 64)
    document = payload(duration=duration)
    document["streams"][0]["duration"] = "0"
    with pytest.raises(
        UnsupportedMediaError,
        match="^Input audio duration could not be determined$",
    ):
        FfprobeMediaProbe._parse(document, identity)


def test_missing_stream_duration_is_rejected_with_typed_error(tmp_path):
    identity = InputIdentity(tmp_path / "audio", 1, 0, "0" * 64)
    document = payload(duration="N/A")
    document["streams"][0].pop("duration")
    with pytest.raises(
        UnsupportedMediaError,
        match="^Input audio duration could not be determined$",
    ):
        FfprobeMediaProbe._parse(document, identity)


def test_optional_invalid_numeric_fields_are_omitted(tmp_path):
    identity = InputIdentity(tmp_path / "audio", 1, 0, "0" * 64)
    document = payload()
    document["streams"][0].update(
        sample_rate=True,
        channels="zero",
        bit_rate="-2",
        duration="not-a-number",
    )
    stream = FfprobeMediaProbe._parse(document, identity).primary_audio_stream
    assert stream.sample_rate_hz is None
    assert stream.channels is None
    assert stream.bit_rate_bps is None
    assert stream.duration_seconds is None


def test_missing_ffprobe_is_a_typed_dependency_failure(monkeypatch, tmp_path):
    source = tmp_path / "audio.wav"
    source.write_bytes(b"audio")
    monkeypatch.setattr(probe_module.shutil, "which", lambda name: None)
    with pytest.raises(MediaToolUnavailableError) as error:
        FfprobeMediaProbe().probe(source)
    assert error.value.exit_code == 1
    assert str(error.value) == "FFprobe is required to inspect audio input"


def test_empty_input_is_rejected_before_executable_lookup(monkeypatch, tmp_path):
    source = tmp_path / "empty.wav"
    source.touch()
    lookup = pytest.MonkeyPatch()
    lookup.setattr(probe_module.shutil, "which", lambda name: pytest.fail("lookup"))
    try:
        with pytest.raises(UnsupportedMediaError, match="^Input file is empty$"):
            FfprobeMediaProbe().probe(source)
    finally:
        lookup.undo()


def test_one_byte_input_is_not_misclassified_as_empty(monkeypatch, tmp_path):
    source = tmp_path / "one-byte.wav"
    source.write_bytes(b"x")
    install_completed_probe(monkeypatch, payload())
    assert FfprobeMediaProbe().probe(source).input.size_bytes == 1


def test_missing_input_metadata_is_a_typed_probe_failure(tmp_path):
    with pytest.raises(MediaProbeError, match="^Input metadata could not be read$"):
        FfprobeMediaProbe().probe(tmp_path / "missing.wav")


def test_probe_timeout_hides_command_detail(monkeypatch, tmp_path):
    source = tmp_path / "audio.wav"
    source.write_bytes(b"audio")
    monkeypatch.setattr(probe_module.shutil, "which", lambda name: "/tools/ffprobe")

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 2)

    monkeypatch.setattr(probe_module.subprocess, "run", timeout)
    with pytest.raises(MediaProbeError) as error:
        FfprobeMediaProbe().probe(source)
    assert str(error.value) == "Media inspection timed out"
    assert str(source) not in str(error.value)


def test_probe_execution_failure_is_typed(monkeypatch, tmp_path):
    source = tmp_path / "audio.wav"
    source.write_bytes(b"audio")
    monkeypatch.setattr(probe_module.shutil, "which", lambda name: "/tools/ffprobe")

    def unavailable(*args, **kwargs):
        raise OSError("private")

    monkeypatch.setattr(probe_module.subprocess, "run", unavailable)
    with pytest.raises(
        MediaToolUnavailableError, match="^FFprobe could not be executed$"
    ):
        FfprobeMediaProbe().probe(source)


def test_probe_decode_failure_is_typed(monkeypatch, tmp_path):
    source = tmp_path / "audio.wav"
    source.write_bytes(b"audio")
    monkeypatch.setattr(probe_module.shutil, "which", lambda name: "/tools/ffprobe")

    def invalid_text(*args, **kwargs):
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid")

    monkeypatch.setattr(probe_module.subprocess, "run", invalid_text)
    with pytest.raises(MediaProbeError, match="^FFprobe returned invalid metadata$"):
        FfprobeMediaProbe().probe(source)


def test_nonzero_probe_result_does_not_expose_ffprobe_stderr(monkeypatch, tmp_path):
    source = tmp_path / "not-media.txt"
    source.write_text("private")
    install_completed_probe(monkeypatch, "", returncode=1)
    with pytest.raises(UnsupportedMediaError) as error:
        FfprobeMediaProbe().probe(source)
    assert str(error.value) == "Input could not be inspected as supported local media"
    assert "private ffprobe detail" not in str(error.value)


@pytest.mark.parametrize("response", ["not-json", "[]"])
def test_invalid_probe_json_is_typed(monkeypatch, tmp_path, response):
    source = tmp_path / "audio.wav"
    source.write_bytes(b"audio")
    install_completed_probe(monkeypatch, response)
    with pytest.raises(MediaProbeError, match="^FFprobe returned invalid metadata$"):
        FfprobeMediaProbe().probe(source)


def test_probe_output_is_bounded_before_json_parsing(monkeypatch, tmp_path):
    source = tmp_path / "audio.wav"
    source.write_bytes(b"audio")
    install_completed_probe(monkeypatch, "{}")
    with pytest.raises(
        MediaProbeError,
        match="^Media metadata exceeded the safe inspection limit$",
    ):
        FfprobeMediaProbe(max_output_bytes=1).probe(source)


def test_probe_output_exactly_at_limit_is_allowed(monkeypatch, tmp_path):
    source = tmp_path / "audio.wav"
    source.write_bytes(b"audio")
    install_completed_probe(monkeypatch, "{}")
    probe = FfprobeMediaProbe(max_output_bytes=2)
    assert probe._run("/tools/ffprobe", source) == {}


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ({}, "FFprobe metadata is incomplete"),
        ({"streams": [], "format": []}, "FFprobe metadata is incomplete"),
        (
            {"streams": ["invalid"], "format": {}},
            "FFprobe stream metadata is invalid",
        ),
        (
            {"streams": [{"index": None}], "format": {}},
            "FFprobe stream index is invalid",
        ),
        (
            {"streams": [{"index": True}], "format": {}},
            "FFprobe stream index is invalid",
        ),
        (
            {"streams": [{"index": -1}], "format": {}},
            "FFprobe stream metadata failed validation",
        ),
    ],
)
def test_incomplete_stream_metadata_is_rejected(tmp_path, document, message):
    identity = InputIdentity(tmp_path / "audio", 1, 0, "0" * 64)
    with pytest.raises(MediaProbeError, match=f"^{message}$"):
        FfprobeMediaProbe._parse(document, identity)


def test_media_without_audio_is_rejected(tmp_path):
    identity = InputIdentity(tmp_path / "video", 1, 0, "0" * 64)
    document = payload(streams=[{"index": 0, "codec_type": "video"}])
    with pytest.raises(UnsupportedMediaError, match="^Input contains no audio stream$"):
        FfprobeMediaProbe._parse(document, identity)


def test_missing_codec_and_container_use_explicit_unknown_values(tmp_path):
    identity = InputIdentity(tmp_path / "audio", 1, 0, "0" * 64)
    document = payload()
    document["streams"][0].pop("codec_name")
    document["format"].pop("format_name")
    result = FfprobeMediaProbe._parse(document, identity)
    assert result.primary_audio_stream.codec == "unknown"
    assert result.container_format == "unknown"


def test_duplicate_audio_indexes_are_wrapped_as_probe_validation_error(tmp_path):
    identity = InputIdentity(tmp_path / "audio", 1, 0, "0" * 64)
    document = payload(
        streams=[
            {"index": 0, "codec_type": "audio", "codec_name": "aac"},
            {"index": 0, "codec_type": "audio", "codec_name": "opus"},
        ]
    )
    with pytest.raises(MediaProbeError, match="^FFprobe metadata failed validation$"):
        FfprobeMediaProbe._parse(document, identity)


def test_input_change_between_probe_and_fingerprint_is_rejected(monkeypatch, tmp_path):
    source = tmp_path / "audio.wav"
    source.write_bytes(b"audio")
    install_completed_probe(monkeypatch, payload())
    snapshots = iter([(5, 1, 2, 3), (6, 2, 2, 3)])
    monkeypatch.setattr(probe_module, "_snapshot", lambda path: next(snapshots))
    monkeypatch.setattr(probe_module, "_fingerprint", lambda path: "0" * 64)
    with pytest.raises(
        InputChangedError, match="^Input changed while it was being inspected$"
    ):
        FfprobeMediaProbe().probe(source)


def test_fingerprint_read_failure_is_typed(monkeypatch, tmp_path):
    source = tmp_path / "audio.wav"
    source.write_bytes(b"audio")
    install_completed_probe(monkeypatch, payload())

    def failed(path):
        raise OSError("private")

    monkeypatch.setattr(probe_module, "_fingerprint", failed)
    with pytest.raises(MediaProbeError, match="^Input could not be fingerprinted$"):
        FfprobeMediaProbe().probe(source)


@pytest.mark.parametrize(
    "kwargs",
    [{"timeout_seconds": 0}, {"timeout_seconds": -1}, {"max_output_bytes": 0}],
)
def test_probe_limits_must_be_positive(kwargs):
    expected = (
        "timeout_seconds must be positive"
        if kwargs.get("timeout_seconds", 1) <= 0
        else "max_output_bytes must be positive"
    )
    with pytest.raises(ValueError, match=f"^{expected}$"):
        FfprobeMediaProbe(**kwargs)


def test_positive_probe_limit_lower_bound_is_accepted():
    probe = FfprobeMediaProbe(timeout_seconds=0.1, max_output_bytes=1)
    assert probe.timeout_seconds == 0.1
    assert probe.max_output_bytes == 1
