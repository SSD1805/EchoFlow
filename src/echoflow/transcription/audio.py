"""Canonical-audio extraction and normalization for transcription execution.

The planner decides whether the selected audio stream is already canonical. If not,
``FfmpegAudioDecoder`` extracts only that stream and writes a private normalized WAV
using the immutable ``DecodeConfiguration``. Downstream segmentation therefore sees
one predictable PCM representation regardless of whether the source was WAV, MP3,
M4A, or an audio-bearing video container.

Normalization changes representation, not EchoFlow's public timestamp basis. Segment
windows are measured from frame zero of this canonical audio and the assembler maps
engine-local timestamps back onto that one source-relative recording timeline.
"""

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from echoflow.media.errors import AudioDecodeError, MediaToolUnavailableError
from echoflow.media.models import MediaInfo
from echoflow.transcription.models import DecodeConfiguration, DecodeStrategy


@dataclass(frozen=True, slots=True)
class DecodedAudio:
    """Canonical audio made available to segmentation for one job."""

    path: Path
    temporary: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", self.path.expanduser().resolve(strict=False))


class FfmpegAudioDecoder:
    """Extract the selected stream into EchoFlow's planned canonical audio format.

    ``DIRECT`` returns an already-canonical source without copying it. The normalize
    path invokes FFmpeg with file-only protocol access, maps exactly the selected
    audio stream, drops video/subtitle/data streams, and writes the planned codec,
    sample rate, and channel count to a private WAV in the job workspace.
    """

    def __init__(self, timeout_seconds: float = 3_600.0):
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.timeout_seconds = timeout_seconds

    def decode(
        self,
        media: MediaInfo,
        configuration: DecodeConfiguration,
        workspace_dir: Path,
    ) -> DecodedAudio:
        if configuration.strategy is DecodeStrategy.DIRECT:
            return DecodedAudio(media.input.path, temporary=False)

        executable = shutil.which("ffmpeg")
        if executable is None:
            raise MediaToolUnavailableError(
                "FFmpeg is required to extract and normalize this recording's audio"
            )
        destination = (workspace_dir / "normalized.wav").resolve(strict=False)
        command = [
            executable,
            "-nostdin",
            "-v",
            "error",
            "-protocol_whitelist",
            "file",
            "-i",
            str(media.input.path),
            "-map",
            f"0:{media.primary_audio_stream_index}",
            "-vn",
            "-sn",
            "-dn",
            "-ac",
            str(configuration.channels),
            "-ar",
            str(configuration.sample_rate_hz),
            "-c:a",
            configuration.output_codec,
            "-f",
            "wav",
            "-n",
            str(destination),
        ]
        try:
            completed = subprocess.run(  # noqa: S603
                command,
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            destination.unlink(missing_ok=True)
            raise AudioDecodeError("Audio extraction timed out", cause=exc) from exc
        except OSError as exc:
            destination.unlink(missing_ok=True)
            raise MediaToolUnavailableError(
                "FFmpeg could not be executed", cause=exc
            ) from exc
        if completed.returncode != 0:
            destination.unlink(missing_ok=True)
            raise AudioDecodeError("The selected audio stream could not be normalized")
        try:
            size = destination.stat().st_size
        except OSError as exc:
            destination.unlink(missing_ok=True)
            raise AudioDecodeError(
                "Normalized audio could not be validated", cause=exc
            ) from exc
        if size <= 44:
            destination.unlink(missing_ok=True)
            raise AudioDecodeError("Normalized audio contains no usable samples")
        return DecodedAudio(destination, temporary=True)

    @staticmethod
    def cleanup(audio: DecodedAudio) -> None:
        if audio.temporary:
            audio.path.unlink(missing_ok=True)
