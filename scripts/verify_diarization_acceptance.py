from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from echoflow.transcription.diarization import PyannoteSpeakerDiarizer


def _validate_result(*, audio_path: Path, result) -> None:
    if not result.turns:
        raise RuntimeError("real diarization acceptance produced no speaker turns")
    if result.provenance.telemetry_enabled:
        raise RuntimeError("diarization acceptance unexpectedly enabled telemetry")
    if result.provenance.provider != "pyannote.audio":
        raise RuntimeError("diarization acceptance returned unexpected provenance")
    for turn in result.turns:
        if not turn.speaker_ref.startswith("speaker-"):
            raise RuntimeError("diarization acceptance returned a non-anonymous label")
        if turn.start_seconds < 0 or turn.end_seconds <= turn.start_seconds:
            raise RuntimeError("diarization acceptance returned an invalid turn")
    print(
        f"accepted {audio_path.name}: {len(result.turns)} turns, "
        f"{len({turn.speaker_ref for turn in result.turns})} speakers"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run gated real pyannote Community-1 inference and prove local-cache "
            "reopen semantics."
        )
    )
    parser.add_argument("audio_path", type=Path)
    parser.add_argument("--cache-dir", type=Path, required=True)
    arguments = parser.parse_args()

    audio_path = arguments.audio_path.expanduser().resolve(strict=True)
    cache_dir = arguments.cache_dir.expanduser().resolve(strict=False)
    if not os.environ.get("HF_TOKEN") and not os.environ.get("HUGGING_FACE_HUB_TOKEN"):
        raise RuntimeError(
            "real diarization acceptance requires an authenticated Hugging Face token"
        )

    diarizer = PyannoteSpeakerDiarizer(model_cache_path=cache_dir)
    downloaded = diarizer.diarize(audio_path, allow_model_download=True)
    _validate_result(audio_path=audio_path, result=downloaded)

    cached = diarizer.diarize(audio_path, allow_model_download=False)
    _validate_result(audio_path=audio_path, result=cached)
    return 0


if __name__ == "__main__":
    sys.exit(main())
