import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from scholion.media.errors import AudioDecodeError, MediaToolUnavailableError
from scholion.media.models import InputIdentity, MediaInfo, MediaStream, StreamKind
from scholion.transcription.audio import DecodedAudio, FfmpegAudioDecoder
from scholion.transcription.models import DecodeConfiguration, DecodeStrategy


def media(source: Path, *, stream_index: int = 2) -> MediaInfo:
    return MediaInfo(
        InputIdentity(
            source,
            source.stat().st_size,
            source.stat().st_mtime_ns,
            "0" * 64,
        ),
        "mov,mp4,m4a,3gp,3g2,mj2",
        2.0,
        (
            MediaStream(0, StreamKind.VIDEO, "h264", 2.0),
            MediaStream(stream_index, StreamKind.AUDIO, "aac", 2.0, 48_000, 2),
        ),
        stream_index,
    )


def normalized() -> DecodeConfiguration:
    return DecodeConfiguration(DecodeStrategy.FFMPEG_NORMALIZE, "pcm_s16le", 16_000, 1)


def test_direct_audio_returns_original_without_resolving_ffmpeg(tmp_path):
    source = tmp_path / "ready.wav"
    source.write_bytes(b"RIFFaudio")
    decoder = FfmpegAudioDecoder()
    with patch("scholion.transcription.audio.shutil.which") as which:
        result = decoder.decode(
            media(source),
            DecodeConfiguration(DecodeStrategy.DIRECT, "pcm_s16le", 16_000, 1),
            tmp_path / "workspace",
        )
    assert result == DecodedAudio(source.resolve(), temporary=False)
    which.assert_not_called()
    decoder.cleanup(result)
    assert source.exists()


def test_video_container_maps_only_selected_audio_to_private_wav(tmp_path):
    source = tmp_path / "interview.mp4"
    source.write_bytes(b"video-and-audio")
    workspace = tmp_path / "private-job"
    workspace.mkdir()

    def run(command, **kwargs):
        Path(command[-1]).write_bytes(b"RIFF" + b"\0" * 64)
        return SimpleNamespace(returncode=0)

    with (
        patch("scholion.transcription.audio.shutil.which", return_value="ffmpeg"),
        patch("scholion.transcription.audio.subprocess.run", side_effect=run) as call,
    ):
        result = FfmpegAudioDecoder(timeout_seconds=12.5).decode(
            media(source, stream_index=2), normalized(), workspace
        )

    assert result.path == workspace / "normalized.wav"
    assert result.temporary is True
    command = call.call_args.args[0]
    assert command == [
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-protocol_whitelist",
        "file",
        "-i",
        str(source.resolve()),
        "-map",
        "0:2",
        "-vn",
        "-sn",
        "-dn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        "-f",
        "wav",
        "-n",
        str(workspace / "normalized.wav"),
    ]
    assert call.call_args.kwargs == {
        "check": False,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "timeout": 12.5,
    }
    FfmpegAudioDecoder.cleanup(result)
    assert not result.path.exists()


def test_decoder_requires_positive_timeout():
    with pytest.raises(ValueError, match="^timeout_seconds must be positive$"):
        FfmpegAudioDecoder(0)


def test_normalization_requires_ffmpeg(tmp_path):
    source = tmp_path / "audio.m4a"
    source.write_bytes(b"audio")
    with (
        patch("scholion.transcription.audio.shutil.which", return_value=None),
        pytest.raises(MediaToolUnavailableError, match="^FFmpeg is required"),
    ):
        FfmpegAudioDecoder().decode(media(source), normalized(), tmp_path)


@pytest.mark.parametrize(
    ("effect", "error_type", "message"),
    [
        (
            subprocess.TimeoutExpired("ffmpeg", 1),
            AudioDecodeError,
            "Audio extraction timed out",
        ),
        (OSError("missing dll"), MediaToolUnavailableError, "FFmpeg could not"),
    ],
)
def test_native_process_failures_are_typed_and_remove_partial_output(
    tmp_path, effect, error_type, message
):
    source = tmp_path / "audio.m4a"
    source.write_bytes(b"audio")
    partial = tmp_path / "normalized.wav"

    def run(*_args, **_kwargs):
        partial.write_bytes(b"partial")
        raise effect

    with (
        patch("scholion.transcription.audio.shutil.which", return_value="ffmpeg"),
        patch("scholion.transcription.audio.subprocess.run", side_effect=run),
        pytest.raises(error_type, match=f"^{message}"),
    ):
        FfmpegAudioDecoder().decode(media(source), normalized(), tmp_path)
    assert not partial.exists()


@pytest.mark.parametrize("returncode", [1, 255])
def test_nonzero_ffmpeg_exit_removes_output_and_hides_native_details(
    tmp_path, returncode
):
    source = tmp_path / "audio.m4a"
    source.write_bytes(b"audio")
    destination = tmp_path / "normalized.wav"

    def run(*_args, **_kwargs):
        destination.write_bytes(b"partial")
        return SimpleNamespace(returncode=returncode)

    with (
        patch("scholion.transcription.audio.shutil.which", return_value="ffmpeg"),
        patch("scholion.transcription.audio.subprocess.run", side_effect=run),
        pytest.raises(
            AudioDecodeError,
            match="^The selected audio stream could not be normalized$",
        ),
    ):
        FfmpegAudioDecoder().decode(media(source), normalized(), tmp_path)
    assert not destination.exists()


@pytest.mark.parametrize("payload", [b"", b"RIFF" + b"\0" * 40])
def test_header_only_or_empty_normalized_audio_is_rejected(tmp_path, payload):
    source = tmp_path / "audio.m4a"
    source.write_bytes(b"audio")
    destination = tmp_path / "normalized.wav"

    def run(*_args, **_kwargs):
        destination.write_bytes(payload)
        return SimpleNamespace(returncode=0)

    with (
        patch("scholion.transcription.audio.shutil.which", return_value="ffmpeg"),
        patch("scholion.transcription.audio.subprocess.run", side_effect=run),
        pytest.raises(
            AudioDecodeError, match="^Normalized audio contains no usable samples$"
        ),
    ):
        FfmpegAudioDecoder().decode(media(source), normalized(), tmp_path)
    assert not destination.exists()


def test_missing_normalized_output_is_typed(tmp_path):
    source = tmp_path / "audio.m4a"
    source.write_bytes(b"audio")
    with (
        patch("scholion.transcription.audio.shutil.which", return_value="ffmpeg"),
        patch(
            "scholion.transcription.audio.subprocess.run",
            return_value=SimpleNamespace(returncode=0),
        ),
        pytest.raises(
            AudioDecodeError, match="^Normalized audio could not be validated$"
        ),
    ):
        FfmpegAudioDecoder().decode(media(source), normalized(), tmp_path)


def test_decoded_audio_normalizes_path_and_is_slotted(tmp_path):
    audio = DecodedAudio(tmp_path / "nested/../audio.wav", True)
    assert audio.path == (tmp_path / "audio.wav").resolve()
    assert not hasattr(audio, "__dict__")
