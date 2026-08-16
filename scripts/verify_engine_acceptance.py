from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

_PHRASE = (
    "The quick brown fox jumps over the lazy dog. "
    "Echo Flow keeps local recordings private and recoverable."
)
_EXPECTED_WORDS = frozenset({"quick", "brown", "fox", "lazy", "dog"})
_MIN_EXPECTED_WORDS = 4
_TIMESTAMP_TOLERANCE_SECONDS = 0.5


def _run(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(  # noqa: S603
        command,
        check=False,
        env=env,
        text=True,
        capture_output=capture_output,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or "").strip() if capture_output else ""
        message = "acceptance subprocess failed"
        if detail:
            message = f"{message}: {detail}"
        raise RuntimeError(message)
    return completed


def _generate_media(root: Path) -> tuple[Path, Path]:
    synthesized = root / "known-speech-source.wav"
    canonical = root / "known-speech-direct.wav"
    container = root / "known-speech-media.mp4"

    _run(
        [
            "espeak-ng",
            "-v",
            "en-us",
            "-s",
            "145",
            "-w",
            str(synthesized),
            _PHRASE,
        ]
    )
    _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-i",
            str(synthesized),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(canonical),
        ]
    )
    _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=160x120:r=1",
            "-i",
            str(canonical),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-shortest",
            "-c:v",
            "mpeg4",
            "-c:a",
            "aac",
            str(container),
        ]
    )
    return canonical, container


def _environment(root: Path, output_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "ECHOFLOW_STATE_DIR": str(root / "state"),
            "ECHOFLOW_CACHE_DIR": str(root / "cache"),
            "ECHOFLOW_MODEL_DIR": str(root / "cache" / "models"),
            "ECHOFLOW_OUTPUT_DIR": str(output_dir),
            "ECHOFLOW_MAX_CPU_THREADS": "2",
            "ECHOFLOW_MIN_FREE_DISK_BYTES": "0",
            "ECHOFLOW_WARN_FREE_DISK_BYTES": "0",
        }
    )
    return env


def _initialize(env: dict[str, str]) -> None:
    completed = _run(
        [sys.executable, "-m", "echoflow", "init", "--json"],
        env=env,
        capture_output=True,
    )
    payload = json.loads(completed.stdout)
    if not isinstance(payload, dict):
        raise RuntimeError("EchoFlow init did not return a JSON object")


def _transcribe(
    input_path: Path,
    *,
    env: dict[str, str],
    allow_model_download: bool,
) -> dict[str, Any]:
    command = [
        sys.executable,
        "-m",
        "echoflow",
        "transcribe",
        str(input_path),
        "--profile",
        "screening",
        "--strategy",
        "tiny-cpu-int8",
        "--export",
        "txt",
        "--export",
        "srt",
        "--export",
        "vtt",
        "--json",
    ]
    if allow_model_download:
        command.append("--allow-model-download")
    completed = _run(command, env=env, capture_output=True)
    payload = json.loads(completed.stdout)
    if not isinstance(payload, dict):
        raise RuntimeError("EchoFlow transcribe did not return a JSON object")
    return payload


def _one_artifact(output_dir: Path, suffix: str) -> Path:
    matches = tuple(output_dir.glob(f"*{suffix}"))
    if len(matches) != 1:
        raise RuntimeError(
            f"expected one {suffix} artifact, found {len(matches)} in acceptance output"
        )
    return matches[0]


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", text.lower()))


def _load_canonical(output_dir: Path) -> tuple[dict[str, Any], str]:
    raw_document = _one_artifact(output_dir, ".json").read_text(encoding="utf-8")
    document = json.loads(raw_document)
    if not isinstance(document, dict):
        raise RuntimeError("canonical transcript is not a JSON object")
    return document, raw_document


def _validate_known_speech(document: dict[str, Any]) -> set[str]:
    text = str(document.get("text", "")).strip()
    recognized_expected = _words(text) & _EXPECTED_WORDS
    if len(recognized_expected) < _MIN_EXPECTED_WORDS:
        raise RuntimeError(
            "known speech was not recognized reliably enough: "
            f"matched {sorted(recognized_expected)}"
        )
    return recognized_expected


def _validate_provenance(
    document: dict[str, Any], *, expected_decode_strategy: str
) -> None:
    if document.get("schema_version") != 1:
        raise RuntimeError("unexpected canonical transcript schema version")
    if document.get("decode_strategy") != expected_decode_strategy:
        raise RuntimeError("canonical transcript recorded the wrong decode strategy")
    if document.get("detected_language") != "en":
        raise RuntimeError("known English speech was not detected as English")

    source = document.get("source")
    engine = document.get("engine")
    if not isinstance(source, dict) or not isinstance(engine, dict):
        raise RuntimeError("canonical provenance is incomplete")
    if engine.get("name") != "faster-whisper" or engine.get("model") != "tiny":
        raise RuntimeError("canonical transcript recorded the wrong engine or model")
    if engine.get("device") != "cpu" or engine.get("compute_type") != "int8":
        raise RuntimeError("canonical transcript recorded the wrong CPU configuration")
    if not str(engine.get("package_version", "")).strip():
        raise RuntimeError("canonical transcript omitted the engine package version")


def _validate_timestamps(document: dict[str, Any]) -> None:
    source = document.get("source")
    segments = document.get("segments")
    if not isinstance(source, dict):
        raise RuntimeError("canonical transcript source provenance is malformed")
    if not isinstance(segments, list) or not segments:
        raise RuntimeError("known speech produced no canonical recognition segments")

    duration_seconds = float(source.get("duration_seconds", 0.0))
    if duration_seconds <= 0:
        raise RuntimeError("canonical transcript recorded an invalid source duration")

    previous_start = 0.0
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            raise RuntimeError("canonical transcript contains a malformed segment")
        if segment.get("index") != index:
            raise RuntimeError("canonical segment indices are not contiguous")
        start = float(segment.get("start_seconds", -1.0))
        end = float(segment.get("end_seconds", -1.0))
        if start < 0 or end < start or start < previous_start:
            raise RuntimeError(
                "canonical segment timestamps are not finite and ordered"
            )
        if end > duration_seconds + _TIMESTAMP_TOLERANCE_SECONDS:
            raise RuntimeError("canonical segment timestamp exceeds source duration")
        previous_start = start


def _validate_privacy(raw_document: str, *, input_path: Path, model_dir: Path) -> None:
    sensitive_values = (str(input_path), input_path.name, str(model_dir))
    if any(value and value in raw_document for value in sensitive_values):
        raise RuntimeError(
            "canonical transcript leaked a local path or source filename"
        )


def _validate_exports(output_dir: Path) -> None:
    txt = _one_artifact(output_dir, ".txt").read_text(encoding="utf-8")
    srt = _one_artifact(output_dir, ".srt").read_text(encoding="utf-8")
    vtt = _one_artifact(output_dir, ".vtt").read_text(encoding="utf-8")
    if not txt.strip() or not srt.strip() or not vtt.strip():
        raise RuntimeError("one or more derived transcript exports are empty")
    if "-->" not in srt or "-->" not in vtt or not vtt.startswith("WEBVTT"):
        raise RuntimeError("subtitle exports do not contain timestamp cues")
    if len(_words(txt) & _EXPECTED_WORDS) < _MIN_EXPECTED_WORDS:
        raise RuntimeError(
            "plain-text export does not contain recognizable known speech"
        )


def _validate_transcript(
    output_dir: Path,
    *,
    input_path: Path,
    model_dir: Path,
    expected_decode_strategy: str,
) -> set[str]:
    document, raw_document = _load_canonical(output_dir)
    recognized_expected = _validate_known_speech(document)
    _validate_provenance(document, expected_decode_strategy=expected_decode_strategy)
    _validate_timestamps(document)
    _validate_privacy(raw_document, input_path=input_path, model_dir=model_dir)
    _validate_exports(output_dir)
    return recognized_expected


def _validate_private_cleanup(root: Path) -> None:
    state_dir = root / "state"
    leftovers = tuple(state_dir.rglob("*.wav")) if state_dir.exists() else ()
    if leftovers:
        raise RuntimeError(
            "successful execution left temporary decoded/segment WAV data"
        )


def verify_engine() -> None:
    with tempfile.TemporaryDirectory(prefix="echoflow-engine-") as temporary:
        root = Path(temporary).resolve()
        direct_audio, media_container = _generate_media(root)
        model_dir = root / "cache" / "models"

        direct_output = root / "output-direct"
        direct_env = _environment(root, direct_output)
        _initialize(direct_env)
        _transcribe(
            direct_audio,
            env=direct_env,
            allow_model_download=True,
        )
        direct_words = _validate_transcript(
            direct_output,
            input_path=direct_audio,
            model_dir=model_dir,
            expected_decode_strategy="direct",
        )
        if not model_dir.exists() or not any(model_dir.iterdir()):
            raise RuntimeError("model download did not populate the private cache")

        normalized_output = root / "output-normalized"
        normalized_env = _environment(root, normalized_output)
        _initialize(normalized_env)
        _transcribe(
            media_container,
            env=normalized_env,
            allow_model_download=False,
        )
        normalized_words = _validate_transcript(
            normalized_output,
            input_path=media_container,
            model_dir=model_dir,
            expected_decode_strategy="ffmpeg_normalize",
        )

        if len(direct_words & normalized_words) < 3:
            raise RuntimeError(
                "direct and normalized paths did not preserve enough recognizable speech"
            )
        _validate_private_cleanup(root)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate known speech, run it through EchoFlow's real CLI and smallest "
            "faster-whisper strategy, then prove offline cache reuse and the real "
            "FFmpeg-normalized media path."
        )
    )
    parser.parse_args()
    verify_engine()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
