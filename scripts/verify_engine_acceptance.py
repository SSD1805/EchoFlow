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
_MIN_ENHANCED_WORDS = 3
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


def _json_command(command: list[str], *, env: dict[str, str]) -> dict[str, Any]:
    completed = _run(command, env=env, capture_output=True)
    payload = json.loads(completed.stdout)
    if not isinstance(payload, dict):
        raise RuntimeError("acceptance command did not return a JSON object")
    return payload


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


def _mixed_audio(root: Path, english: Path) -> Path:
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


def _environment(root: Path, output_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "SCHOLION_STATE_DIR": str(root / "state"),
            "SCHOLION_CACHE_DIR": str(root / "cache"),
            "SCHOLION_MODEL_DIR": str(root / "cache" / "models"),
            "SCHOLION_OUTPUT_DIR": str(output_dir),
            "SCHOLION_MAX_CPU_THREADS": "2",
            "SCHOLION_MIN_FREE_DISK_BYTES": "0",
            "SCHOLION_WARN_FREE_DISK_BYTES": "0",
        }
    )
    return env


def _initialize(env: dict[str, str]) -> None:
    payload = _json_command(
        [sys.executable, "-m", "scholion", "init", "--json"], env=env
    )
    if not payload:
        raise RuntimeError("Scholion init returned no directory state")


def _install_tiny(env: dict[str, str]) -> str:
    manifest = _json_command(
        [
            sys.executable,
            "-m",
            "scholion",
            "models",
            "install",
            "tiny",
            "--json",
        ],
        env=env,
    )
    if manifest.get("model_id") != "tiny":
        raise RuntimeError("model management installed the wrong model")
    revision = str(manifest.get("resolved_revision", "")).strip()
    if not revision:
        raise RuntimeError("managed model omitted immutable resolved revision")
    if not str(manifest.get("verification", "")).strip():
        raise RuntimeError("managed model omitted verification evidence")
    return revision


def _transcribe(
    input_path: Path,
    *,
    env: dict[str, str],
    enhance: bool = False,
) -> dict[str, Any]:
    command = [
        sys.executable,
        "-m",
        "scholion",
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
    if enhance:
        command.append("--enhance")
    return _json_command(command, env=env)


def _one_artifact(output_dir: Path, suffix: str) -> Path:
    matches = tuple(output_dir.glob(f"*{suffix}"))
    if len(matches) != 1:
        raise RuntimeError(f"expected one {suffix} artifact, found {len(matches)}")
    return matches[0]


def _words(text: str) -> set[str]:
    return set(re.findall(r"[^\W\d_]+", text.lower(), flags=re.UNICODE))


def _load_canonical(output_dir: Path) -> tuple[dict[str, Any], str]:
    raw_document = _one_artifact(output_dir, ".json").read_text(encoding="utf-8")
    document = json.loads(raw_document)
    if not isinstance(document, dict):
        raise RuntimeError("canonical transcript is not a JSON object")
    return document, raw_document


def _validate_engine_contract(
    document: dict[str, Any], *, expected_revision: str
) -> None:
    engine = document.get("engine")
    if not isinstance(engine, dict):
        raise RuntimeError("canonical engine provenance is malformed")
    if engine.get("name") != "faster-whisper" or engine.get("model") != "tiny":
        raise RuntimeError("canonical transcript recorded wrong engine/model")
    if engine.get("model_revision") != expected_revision:
        raise RuntimeError("canonical transcript did not preserve managed revision")
    if engine.get("device") != "cpu" or engine.get("compute_type") != "int8":
        raise RuntimeError("canonical transcript recorded wrong CPU configuration")
    if "auto_language_mode" in engine:
        raise RuntimeError("legacy language-mode compatibility field survived")


def _validate_language_contract(document: dict[str, Any]) -> None:
    attribution = document.get("language_attribution")
    if not isinstance(attribution, dict) or attribution.get("provider") != "lingua":
        raise RuntimeError("canonical transcript omitted local language provenance")


def _validate_enhancement_contract(
    document: dict[str, Any], *, expect_enhancement: bool
) -> None:
    enhancement = document.get("enhancement")
    if not expect_enhancement:
        if enhancement is not None:
            raise RuntimeError("raw run unexpectedly recorded enhancement provenance")
        return
    if not isinstance(enhancement, dict):
        raise RuntimeError("enhanced run omitted enhancement provenance")
    if enhancement.get("provider") != "ffmpeg-afftdn":
        raise RuntimeError("enhanced run recorded wrong provider")
    if enhancement.get("operation") != "noise_suppression":
        raise RuntimeError("enhanced run recorded wrong operation")
    if not str(enhancement.get("provider_version", "")).strip():
        raise RuntimeError("enhanced run omitted FFmpeg version")


def _validate_contract(
    document: dict[str, Any],
    *,
    expected_decode_strategy: str,
    expected_revision: str,
    expect_enhancement: bool,
) -> None:
    if document.get("schema_version") != 1:
        raise RuntimeError("unexpected canonical transcript schema version")
    if document.get("decode_strategy") != expected_decode_strategy:
        raise RuntimeError("canonical transcript recorded wrong decode strategy")
    _validate_engine_contract(document, expected_revision=expected_revision)
    _validate_language_contract(document)
    _validate_enhancement_contract(document, expect_enhancement=expect_enhancement)


def _validate_timestamps(document: dict[str, Any]) -> None:
    source = document.get("source")
    segments = document.get("segments")
    if not isinstance(source, dict) or not isinstance(segments, list) or not segments:
        raise RuntimeError("canonical transcript source/segments are malformed")
    duration_seconds = float(source.get("duration_seconds", 0.0))
    previous_start = 0.0
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict) or segment.get("index") != index:
            raise RuntimeError("canonical segment indices are not contiguous")
        start = float(segment.get("start_seconds", -1.0))
        end = float(segment.get("end_seconds", -1.0))
        if start < 0 or end < start or start < previous_start:
            raise RuntimeError("canonical segment timestamps are not ordered")
        if end > duration_seconds + _TIMESTAMP_TOLERANCE_SECONDS:
            raise RuntimeError("canonical segment timestamp exceeds source duration")
        previous_start = start


def _validate_privacy(raw_document: str, *, input_path: Path, model_dir: Path) -> None:
    for value in (str(input_path), input_path.name, str(model_dir)):
        if value and value in raw_document:
            raise RuntimeError("canonical transcript leaked local path/source filename")


def _validate_exports(output_dir: Path) -> None:
    txt = _one_artifact(output_dir, ".txt").read_text(encoding="utf-8")
    srt = _one_artifact(output_dir, ".srt").read_text(encoding="utf-8")
    vtt = _one_artifact(output_dir, ".vtt").read_text(encoding="utf-8")
    if not txt.strip() or not srt.strip() or not vtt.strip():
        raise RuntimeError("one or more derived exports are empty")
    if "-->" not in srt or "-->" not in vtt or not vtt.startswith("WEBVTT"):
        raise RuntimeError("subtitle exports do not contain timestamp cues")


def _validate_english(
    output_dir: Path,
    *,
    input_path: Path,
    model_dir: Path,
    expected_revision: str,
    expected_decode_strategy: str,
    expect_enhancement: bool = False,
    minimum_expected_words: int = _MIN_EXPECTED_WORDS,
) -> set[str]:
    document, raw_document = _load_canonical(output_dir)
    recognized = _words(str(document.get("text", ""))) & _ENGLISH_WORDS
    if len(recognized) < minimum_expected_words:
        raise RuntimeError(
            f"known speech recognition too weak: matched {sorted(recognized)}"
        )
    _validate_contract(
        document,
        expected_decode_strategy=expected_decode_strategy,
        expected_revision=expected_revision,
        expect_enhancement=expect_enhancement,
    )
    _validate_timestamps(document)
    _validate_privacy(raw_document, input_path=input_path, model_dir=model_dir)
    _validate_exports(output_dir)
    return recognized


def _validate_mixed_language(output_dir: Path, *, expected_revision: str) -> None:
    document, _ = _load_canonical(output_dir)
    _validate_contract(
        document,
        expected_decode_strategy="direct",
        expected_revision=expected_revision,
        expect_enhancement=False,
    )
    words = _words(str(document.get("text", "")))
    if len(words & _ENGLISH_WORDS) < _MIN_MIXED_WORDS:
        raise RuntimeError("mixed-language run lost too much English content")
    if len(words & _FRENCH_WORDS) < _MIN_MIXED_WORDS:
        raise RuntimeError("mixed-language run lost too much French content")

    languages: set[str] = set()
    for raw_segment in document.get("segments", []):
        if not isinstance(raw_segment, dict):
            continue
        for raw_span in raw_segment.get("language_spans", []):
            if isinstance(raw_span, dict) and isinstance(raw_span.get("language"), str):
                languages.add(str(raw_span["language"]))
    if not {"en", "fr"}.issubset(languages):
        raise RuntimeError(
            f"mixed-language transcript lost language evidence: {sorted(languages)}"
        )


def _validate_private_cleanup(root: Path) -> None:
    state_dir = root / "state"
    leftovers = tuple(state_dir.rglob("*.wav")) if state_dir.exists() else ()
    if leftovers:
        raise RuntimeError("successful execution left private temporary WAV data")


def verify_engine() -> None:
    with tempfile.TemporaryDirectory(prefix="scholion-engine-") as temporary:
        root = Path(temporary).resolve()
        model_dir = root / "cache" / "models"
        english = _synthesize(
            root,
            "known-speech-direct",
            voice="en-us",
            phrase=_ENGLISH_PHRASE,
        )
        media_container = _wrap_media(root, english)
        mixed = _mixed_audio(root, english)

        setup_env = _environment(root, root / "output-setup")
        _initialize(setup_env)
        revision = _install_tiny(setup_env)

        direct_output = root / "output-direct"
        direct_env = _environment(root, direct_output)
        _transcribe(english, env=direct_env)
        direct_words = _validate_english(
            direct_output,
            input_path=english,
            model_dir=model_dir,
            expected_revision=revision,
            expected_decode_strategy="direct",
        )

        normalized_output = root / "output-normalized"
        normalized_env = _environment(root, normalized_output)
        _transcribe(media_container, env=normalized_env)
        normalized_words = _validate_english(
            normalized_output,
            input_path=media_container,
            model_dir=model_dir,
            expected_revision=revision,
            expected_decode_strategy="ffmpeg_normalize",
        )
        if len(direct_words & normalized_words) < _MIN_EXPECTED_WORDS:
            raise RuntimeError(
                "normalization changed known-speech recognition too much"
            )

        mixed_output = root / "output-mixed"
        mixed_env = _environment(root, mixed_output)
        _transcribe(mixed, env=mixed_env)
        _validate_mixed_language(mixed_output, expected_revision=revision)

        enhanced_output = root / "output-enhanced"
        enhanced_env = _environment(root, enhanced_output)
        _transcribe(english, env=enhanced_env, enhance=True)
        _validate_english(
            enhanced_output,
            input_path=english,
            model_dir=model_dir,
            expected_revision=revision,
            expected_decode_strategy="direct",
            expect_enhancement=True,
            minimum_expected_words=_MIN_ENHANCED_WORDS,
        )

        if not model_dir.is_dir() or not any(model_dir.iterdir()):
            raise RuntimeError("managed model install did not populate private cache")
        _validate_private_cleanup(root)


if __name__ == "__main__":
    for executable in ("ffmpeg", "ffprobe", "espeak-ng"):
        if shutil.which(executable) is None:
            raise SystemExit(
                f"required acceptance executable unavailable: {executable}"
            )
    verify_engine()
