import shutil
import subprocess
import wave
from pathlib import Path

import pytest

from scholion.media.models import StreamKind
from scholion.media.probe import FfprobeMediaProbe
from scholion.media.selection import AudioStreamSelector
from scholion.transcription.audio import FfmpegAudioDecoder
from scholion.transcription.models import DecodeConfiguration, DecodeStrategy


def _native_tool(name: str) -> str:
    executable = shutil.which(name)
    if executable is None:
        pytest.skip(f"{name} is not installed")
    return executable


def _make_multitrack_video(path: Path) -> None:
    ffmpeg = _native_tool("ffmpeg")
    command = [
        ffmpeg,
        "-nostdin",
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=64x64:r=1",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=16000:cl=mono",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=880:sample_rate=16000",
        "-t",
        "1.25",
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-map",
        "2:a:0",
        "-c:v",
        "mpeg4",
        "-c:a",
        "pcm_s16le",
        "-y",
        str(path),
    ]
    subprocess.run(command, check=True, capture_output=True)  # noqa: S603


def _pcm_payload(path: Path) -> bytes:
    with wave.open(str(path), "rb") as audio:
        assert audio.getframerate() == 16_000
        assert audio.getnchannels() == 1
        assert audio.getsampwidth() == 2
        return audio.readframes(audio.getnframes())


def test_real_ffmpeg_honors_explicit_audio_stream_selection(tmp_path):
    _native_tool("ffprobe")
    source = tmp_path / "two-track-interview.mkv"
    _make_multitrack_video(source)

    media = FfprobeMediaProbe().probe(source)
    audio_streams = tuple(
        stream for stream in media.streams if stream.kind is StreamKind.AUDIO
    )
    assert len(audio_streams) == 2
    assert media.primary_audio_stream_index == audio_streams[0].index

    selected = AudioStreamSelector().select(
        media,
        requested_index=audio_streams[1].index,
    )
    configuration = DecodeConfiguration(
        DecodeStrategy.FFMPEG_NORMALIZE,
        "pcm_s16le",
        16_000,
        1,
    )
    first_workspace = tmp_path / "first"
    second_workspace = tmp_path / "second"
    first_workspace.mkdir()
    second_workspace.mkdir()
    decoder = FfmpegAudioDecoder()

    first = decoder.decode(media, configuration, first_workspace)
    second = decoder.decode(selected, configuration, second_workspace)
    first_payload = _pcm_payload(first.path)
    second_payload = _pcm_payload(second.path)

    assert first_payload
    assert not any(first_payload)
    assert any(second_payload)
    assert selected.primary_audio_stream_index == audio_streams[1].index

    decoder.cleanup(first)
    decoder.cleanup(second)
    assert not first.path.exists()
    assert not second.path.exists()
    assert source.exists()
