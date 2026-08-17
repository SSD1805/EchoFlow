from __future__ import annotations

import shutil
import subprocess
import wave
from pathlib import Path

from echoflow.media.errors import MediaToolUnavailableError
from echoflow.transcription.audio import DecodedAudio
from echoflow.transcription.enhancement_models import (
    EnhancedAudio,
    EnhancementConfiguration,
    EnhancementMode,
    EnhancementProvenance,
)
from echoflow.transcription.errors import AudioEnhancementError

_PROVIDER = "ffmpeg-afftdn"
_PARAMETERS = (
    ("noise_floor_db", "-50"),
    ("noise_reduction_db", "12"),
)
_FILTER = "afftdn=nf=-50:nr=12"


def ffmpeg_afftdn_configuration() -> EnhancementConfiguration:
    """Return EchoFlow's versioned deterministic v1 denoising contract."""
    return EnhancementConfiguration(
        mode=EnhancementMode.ON,
        provider=_PROVIDER,
        parameters=_PARAMETERS,
    )


class FfmpegAfftdnEnhancer:
    """Apply FFmpeg's local frequency-domain denoiser to canonical PCM audio."""

    def __init__(self, timeout_seconds: float = 3_600.0):
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.timeout_seconds = timeout_seconds

    def enhance(
        self,
        audio: DecodedAudio,
        configuration: EnhancementConfiguration,
        workspace_dir: Path,
    ) -> EnhancedAudio:
        self._validate_configuration(configuration)
        executable = shutil.which("ffmpeg")
        if executable is None:
            raise MediaToolUnavailableError(
                "FFmpeg is required for local speech noise suppression"
            )
        provider_version = self._ffmpeg_version(executable)
        destination = (workspace_dir / "enhanced.wav").resolve(strict=False)
        command = [
            executable,
            "-nostdin",
            "-v",
            "error",
            "-protocol_whitelist",
            "file",
            "-i",
            str(audio.path),
            "-map",
            "0:a:0",
            "-vn",
            "-sn",
            "-dn",
            "-af",
            _FILTER,
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
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
            raise AudioEnhancementError("Audio noise suppression timed out", cause=exc) from exc
        except OSError as exc:
            destination.unlink(missing_ok=True)
            raise MediaToolUnavailableError(
                "FFmpeg could not execute local speech noise suppression", cause=exc
            ) from exc
        if completed.returncode != 0:
            destination.unlink(missing_ok=True)
            raise AudioEnhancementError("Local speech noise suppression failed")
        self._validate_output(audio.path, destination)
        return EnhancedAudio(
            path=destination,
            provenance=EnhancementProvenance(
                provider=_PROVIDER,
                provider_version=provider_version,
                operation="noise_suppression",
                parameters=_PARAMETERS,
            ),
        )

    @staticmethod
    def cleanup(audio: EnhancedAudio) -> None:
        if audio.temporary:
            audio.path.unlink(missing_ok=True)

    @staticmethod
    def _validate_configuration(configuration: EnhancementConfiguration) -> None:
        if configuration.mode is not EnhancementMode.ON:
            raise ValueError("enhancer requires enabled enhancement configuration")
        if configuration.provider != _PROVIDER:
            raise ValueError("unsupported enhancement provider")
        if configuration.parameters != _PARAMETERS:
            raise ValueError("unsupported ffmpeg-afftdn parameter contract")
        if configuration.model_id is not None or configuration.model_revision is not None:
            raise ValueError("ffmpeg-afftdn does not use a model")

    @staticmethod
    def _ffmpeg_version(executable: str) -> str:
        try:
            completed = subprocess.run(  # noqa: S603
                [executable, "-version"],
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=10.0,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise MediaToolUnavailableError(
                "FFmpeg version could not be verified for enhancement provenance",
                cause=exc,
            ) from exc
        first_line = completed.stdout.splitlines()[0].strip() if completed.stdout else ""
        if completed.returncode != 0 or not first_line:
            raise MediaToolUnavailableError(
                "FFmpeg version could not be verified for enhancement provenance"
            )
        return first_line

    @staticmethod
    def _wave_identity(path: Path) -> tuple[int, int, int, int]:
        try:
            with wave.open(str(path), "rb") as stream:
                return (
                    stream.getnchannels(),
                    stream.getsampwidth(),
                    stream.getframerate(),
                    stream.getnframes(),
                )
        except (OSError, wave.Error) as exc:
            raise AudioEnhancementError(
                "Enhanced audio could not be validated", cause=exc
            ) from exc

    @classmethod
    def _validate_output(cls, source: Path, destination: Path) -> None:
        try:
            size = destination.stat().st_size
        except OSError as exc:
            destination.unlink(missing_ok=True)
            raise AudioEnhancementError(
                "Enhanced audio could not be validated", cause=exc
            ) from exc
        if size <= 44:
            destination.unlink(missing_ok=True)
            raise AudioEnhancementError("Enhanced audio contains no usable samples")
        try:
            if cls._wave_identity(source) != cls._wave_identity(destination):
                raise AudioEnhancementError(
                    "Enhancement changed the canonical audio timeline contract"
                )
        except AudioEnhancementError:
            destination.unlink(missing_ok=True)
            raise
