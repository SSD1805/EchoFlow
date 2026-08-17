from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from echoflow.cli import app

_MODEL = "tiny"
_ENGLISH_TEXT = "The quick brown fox jumps over the lazy dog near the river bank."
_FRENCH_TEXT = "Bonjour tout le monde, ceci est un test français simple pour vérifier la langue."
_ENGLISH_WORDS = {
    "quick",
    "brown",
    "fox",
    "jumps",
    "lazy",
    "dog",
    "river",
    "bank",
}
_FRENCH_WORDS = {
    "bonjour",
    "monde",
    "test",
    "français",
    "simple",
    "vérifier",
    "langue",
}
_MIN_EXPECTED_WORDS = 3
_MIN_MIXED_WORDS = 2
_TIMESTAMP_TOLERANCE_SECONDS = 0.05


def _run(command: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )


def _generate_media(root: Path) -> tuple[Path, Path, Path]:
    english_raw = root / "english-raw.wav"
    french_raw = root / "french-raw.wav"
    direct_audio = root / "known.wav"
    french_audio = root / "french.wav"
    media_container = root / "known.m4a"
    mixed_audio = root / "mixed.wav"

    _run(["espeak-ng", "-v", "en-us", "-s", "135", "-w", str(english_raw), _ENGLISH_TEXT])
    _run(["espeak-ng", "-v", "fr-fr", "-s", "135", "-w", str(french_raw), _FRENCH_TEXT])
    for source, target in ((english_raw, direct_audio), (french_raw, french_audio)):
        _run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source),
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(target),
            ]
        )
    _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(direct_audio),
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(media_container),
        ]
    )
    _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(direct_audio),
            "-i",
            str(french_audio),
            "-filter_complex",
            "[0:a][1:a]concat=n=2:v=0:a=1[out]",
            "-map",
            "[out]",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(mixed_audio),
        ]
    )
    return direct_audio, media_container, mixed_audio


def _environment(root: Path, output_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "ECHOFLOW_APP_DATA_DIR": str(root / "state"),
            "ECHOFLOW_MODEL_DIR": str(root / "cache" / "models"),
            "ECHOFLOW_CACHE_DIR": str(root / "cache"),
            "ECHOFLOW_DEFAULT_OUTPUT_DIR": str(output_dir),
        }
    )
    return env


def _initialize(env: dict[str, str]) -> None:
    _run([sys.executable, "-m", "echoflow.cli", "init", "--json"], env=env)


def _transcribe(
    input_path: Path,
    *,
    env: dict[str, str],
    allow_model_download: bool,
) -> None:
    command = [
        sys.executable,
        "-m",
        "echoflow.cli",
        "transcribe",
        str(input_path),
        "--profile",
        "screening",
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
    _run(command, env=env)


def _one_artifact(output_dir: Path, suffix: str) -> Path:
    matches = tuple(output_dir.glob(f"*{suffix}"))
    if len(matches) != 1:
        raise RuntimeError(
            f"expected exactly one {suffix} artifact, found {len(matches)}"
        )
    return matches[0]


def _load_canonical(output_dir: Path) -> tuple[dict[str, Any], str]:
    path = _one_artifact(output_dir, ".json")
    raw = path.read_text(encoding="utf-8")
    document = json.loads(raw)
    if not isinstance(document, dict):
        raise RuntimeError("canonical transcript is not a JSON object")
    return document, raw


def _words(text: str) -> set[str]:
    return set(re.findall(r"[^\W\d_]+", text.casefold(), flags=re.UNICODE))


def _validate_known_speech(document: dict[str, Any]) -> set[str]:
    text = str(document.get("text", ""))
    words = _words(text)
    recognized = words & _ENGLISH_WORDS
    if len(recognized) < _MIN_EXPECTED_WORDS:
        raise RuntimeError(
            "real engine did not recover enough known speech; "
            f"matched {sorted(recognized)}"
        )
    return recognized


def _language_diagnostic(document: dict[str, Any]) -> str:
    spans: list[tuple[str | None, str]] = []
    for raw_segment in document.get("segments", []):
        if not isinstance(raw_segment, dict):
            continue
        segment_text = str(raw_segment.get("text", ""))
        for raw_span in raw_segment.get("language_spans", []):
            if not isinstance(raw_span, dict):
                continue
            try:
                start = int(raw_span.get("start_char", 0))
                end = int(raw_span.get("end_char", 0))
            except (TypeError, ValueError):
                continue
            spans.append((raw_span.get("language"), segment_text[start:end]))
    return (
        f"text={document.get('text', '')!r}; "
        f"detected_language={document.get('detected_language')!r}; "
        f"detected_languages={document.get('detected_languages')!r}; "
        f"spans={spans!r}"
    )


def _validate_language_provenance(document: dict[str, Any]) -> None:
    if document.get("schema_version") != 2:
        raise RuntimeError("unexpected canonical transcript schema version")
    engine = document.get("engine")
    attribution = document.get("language_attribution")
    if not isinstance(engine, dict) or not isinstance(attribution, dict):
        raise RuntimeError("canonical language provenance is incomplete")
    if engine.get("auto_language_mode") != "native_multilingual_v1":
        raise RuntimeError("canonical transcript omitted multilingual language policy")
    if attribution.get("provider") != "lingua":
        raise RuntimeError("canonical transcript recorded the wrong language provider")
    if not str(attribution.get("package_version", "")).strip():
        raise RuntimeError("canonical transcript omitted language provider version")


def _validate_language_segments(document: dict[str, Any]) -> None:
    segments = document.get("segments")
    if not isinstance(segments, list) or not segments:
        raise RuntimeError("known speech produced no canonical recognition segments")
    if any(not isinstance(segment, dict) for segment in segments):
        raise RuntimeError("canonical transcript contains malformed language segments")
    if not any(
        isinstance(segment, dict) and segment.get("language_spans")
        for segment in segments
    ):
        raise RuntimeError("canonical transcript contains no language-attributed spans")


def _validate_language_contract(document: dict[str, Any]) -> None:
    _validate_language_provenance(document)
    _validate_language_segments(document)


def _validate_provenance(
    document: dict[str, Any], *, expected_decode_strategy: str
) -> None:
    _validate_language_contract(document)
    if document.get("decode_strategy") != expected_decode_strategy:
        raise RuntimeError("canonical transcript recorded the wrong decode strategy")
    if document.get("detected_language") != "en":
        raise RuntimeError(
            "known English speech was not detected as English; "
            + _language_diagnostic(document)
        )
    if document.get("detected_languages") != ["en"]:
        raise RuntimeError(
            "known English speech recorded unexpected text languages; "
            + _language_diagnostic(document)
        )

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
            f"found {sorted(languages)}; "
            + _language_diagnostic(document)
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
        if direct_words != normalized_words:
            raise RuntimeError(
                "direct and normalized paths did not preserve the same known speech anchors"
            )

        mixed_output = root / "output-mixed"
        mixed_env = _environment(root, mixed_output)
        _initialize(mixed_env)
        _transcribe(mixed_audio, env=mixed_env, allow_model_download=False)
        _validate_mixed_language(mixed_output)

        _validate_private_cleanup(root)


def main() -> int:
    verify_engine()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
