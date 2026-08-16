from __future__ import annotations

import argparse
import tempfile
import wave
from pathlib import Path

from echoflow.transcription.backend import FasterWhisperTranscriber
from echoflow.transcription.models import CpuEngineConfiguration

_SAMPLE_RATE_HZ = 16_000


def _write_silence(path: Path) -> None:
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(_SAMPLE_RATE_HZ)
        audio.writeframes(b"\x00\x00" * _SAMPLE_RATE_HZ)


def _configuration(model_cache: Path) -> CpuEngineConfiguration:
    return CpuEngineConfiguration(
        engine="faster-whisper",
        model="tiny",
        device="cpu",
        compute_type="int8",
        cpu_threads=2,
        beam_size=1,
        language="en",
        model_cache_path=model_cache,
    )


def verify_engine() -> None:
    with tempfile.TemporaryDirectory(prefix="echoflow-engine-") as temporary:
        root = Path(temporary).resolve()
        model_cache = root / "models"
        audio_path = root / "acceptance.wav"
        model_cache.mkdir()
        _write_silence(audio_path)

        configuration = _configuration(model_cache)
        transcriber = FasterWhisperTranscriber()

        downloaded_session = transcriber.open_session(
            configuration,
            allow_model_download=True,
        )
        downloaded_result = downloaded_session.transcribe(audio_path)

        local_session = transcriber.open_session(
            configuration,
            allow_model_download=False,
        )
        local_result = local_session.transcribe(audio_path)

        if downloaded_result.engine_version != local_result.engine_version:
            raise RuntimeError("engine version changed within one acceptance run")
        if not downloaded_result.engine_version.strip():
            raise RuntimeError("engine version was not reported")
        if not any(model_cache.iterdir()):
            raise RuntimeError("model download did not populate the private cache")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Download and execute the smallest configured faster-whisper model, then "
            "reopen it with network retrieval disabled."
        )
    )
    parser.parse_args()
    verify_engine()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
