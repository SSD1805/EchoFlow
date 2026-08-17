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

_ENGLISH_PHRASE = (
    "The quick brown fox jumps over the lazy dog. "
    "Echo Flow keeps local recordings private and recoverable."
)
_FRENCH_PHRASE = (
    "Bonjour. La musique française accompagne notre journée. "
    "Nous parlons français maintenant. Merci beaucoup."
)
_ENGLISH_WORDS = frozenset({"quick", "brown", "fox", "lazy", "dog"})
_FRENCH_WORDS = frozenset({"bonjour", "musique", "française", "français", "merci"})
_MIN_EXPECTED_WORDS = 4
_MIN_MIXED_WORDS = 2
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


def _synthesize(root: Path, name: str, *, voice: str, phrase: str) -> Path:
    synthesized = root / f"{name}-source.wav"
    canonical = root / f"{name}.wav"
    _run(
        [
            "espeak-ng",
            "-v",
            voice,
            "-s",
            "145",
            "-w",
            str(synthesized),
            phrase,
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
    return canonical


def _wrap_media(root: Path, audio: Path) -> Path:
    container = root / "known-speech-media.mp4"
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
            str(audio),
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
    return container


def _mixed_media(root: Path, english: Path) -> Path:
    french = _synthesize(
        root,
        "known-speech-french",
        voice="fr-fr",
        phrase=_FRENCH_PHRASE,
    )
    mixed = root / "known-speech-english-french.wav"
    _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-i",
            str(english),
            "-i",
            str(french),
            "-filter_complex",
            "[0:a][1:a]concat=n=2:v=0:a=1[out]",
            "-map",
            "[out]",
            "-c:a",
            "pcm_s16le",
            str(mixed),
        ]
    )
    return mixed


def _generate_media(root: Path) -> tuple[Path, Path, Path]:
    english = _synthesize(
        root,
        "known-speech-direct",
        voice="en-us",
        phrase=_ENGLISH_PHRASE,
    )
    return english, _wrap_media(root, english), _mixed_media(root, english)


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
    return set(re.findall(r"[^\W\d_]+", text.lower(), flags=re.UNICODE))


def _load_canonical(output_dir: Path) -> tuple[dict[str, Any], str]:
    raw_document = _one_artifact(output_dir, ".json").read_text(encoding="utf-8")
    document = json.loads(raw_document)
    if not isinstance(document, dict):
        raise RuntimeError("canonical transcript is not a JSON object")
    return document, raw_document


def _validate_known_speech(document: dict[str, Any]) -> set[str]:
    recognized_expected = _words(str(document.get("text", ""))) & _ENGLISH_WORDS
    if len(recognized_expected) < _MIN_EXPECTED_WORDS:
        raise RuntimeError(
            "known speech was not recognized reliably enough: "
            f"matched {sorted(recognized_expected)}"
        )
    return recognized_expected


def _validate_language_contract(document: dict[str, Any]) -> None:
    if document.get("schema_version") != 2:
        raise RuntimeError("unexpected canonical transcript schema version")
    engine = document.get("engine")
    attribution = document.get("language_attribution")
    if not isinstance(engine, dict) or not isinstance(attribution, dict):
        raise RuntimeError("canonical language provenance is incomplete")
    if engine.get("auto_language_mode") != "per_segment_v1":
        raise RuntimeError("canonical transcript omitted per-segment language policy")
    if attribution.get("provider") != "lingua":
        raise RuntimeError("canonical transcript recorded the wrong language provider")
    if not str(attribution.get("package_version", "")).strip():
        raise RuntimeError("canonical transcript omitted language provider version")

    segments = document.get("segments")
    if not isinstance(segments, list) or not segments:
        raise RuntimeError("known speech produced no canonical recognition segments")
    if any(not isinstance(segment, dict) for segment in segments):
        raise RuntimeError("canonical transcript contains malformed language segments")
    for segment in segments:
        assert isinstance(segment, dict)
        if "detected_language" not in segment or "language_spans" not in segment:
            raise RuntimeError("canonical segment omitted language evidence")


def _validate_provenance(
    document: dict[str, Any], *, expected_decode_strategy: str
) -> None:
    _validate_language_contract(document)
    if document.get("decode_strategy") != expected_decode_strategy:
        raise RuntimeError("canonical transcript recorded the wrong decode strategy")
    if document.get("detected_language") != "en":
        raise RuntimeError("known English speech was not detected as English")
    if document.get("detected_languages") != ["en"]:
        raise RuntimeError("known English speech recorded unexpected acoustic languages")

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
    if len(_words(txt) & _ENGLISH_WORDS) < _MIN_EXPECTED_WORDS:
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


def _validate_mixed_language(output_dir: Path) -> None:
    document, _ = _load_canonical(output_dir)
    _validate_language_contract(document)
    text_words = _words(str(document.get("text", "")))
    english_words = text_words & _ENGLISH_WORDS
    french_words = text_words & _FRENCH_WORDS
    if len(english_words) < _MIN_MIXED_WORDS:
        raise RuntimeError(
            "mixed-language speech lost too much English content: "
            f"matched {sorted(english_words)}"
        )
    if len(french_words) < _MIN_MIXED_WORDS:
        raise RuntimeError(
            "mixed-language speech lost too much French content: "
            f"matched {sorted(french_words)}"
        )

    languages: set[str] = set()
    for raw_segment in document.get("segments", []):
        if not isinstance(raw_segment, dict):
            continue
        for raw_span in raw_segment.get("language_spans", []):
            if isinstance(raw_span, dict):
                language = raw_span.get("language")
                if isinstance(language, str):
                    languages.add(language)
    if not {"en", "fr"}.issubset(languages):
        raise RuntimeError(
            "mixed-language transcript did not preserve English and French text spans: "
            f"found {sorted(languages)}"
        )


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
        direct_audio, media_container, mixed_audio = _generate_media(root)
        model_dir = root / "cache" / "models"

        direct_output = root / "output-direct"
        direct_env = _environment(root, direct_output)
        _initialize(direct_env)
        _transcribe(direct_audio, env=direct_env, allow_model_download=True)
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

        mixed_output = root / "output-mixed"
        mixed_env = _environment(root, mixed_output)
        _initialize(mixed_env)
        _transcribe(mixed_audio, env=mixed_env, allow_model_download=False)
        _validate_mixed_language(mixed_output)
        _validate_private_cleanup(root)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate known English and mixed English/French speech, run the real "
            "EchoFlow CLI with faster-whisper, prove offline cache reuse, real media "
            "normalization, and local language attribution."
        )
    )
    parser.parse_args()
    verify_engine()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
