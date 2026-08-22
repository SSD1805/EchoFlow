import shutil
import subprocess
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from scholion.media.errors import MediaToolUnavailableError
from scholion.transcription.audio import DecodedAudio
from scholion.transcription.enhancement import (
    FfmpegAfftdnEnhancer,
    ffmpeg_afftdn_configuration,
)
from scholion.transcription.enhancement_models import (
    EnhancementConfiguration,
    EnhancementMode,
)
from scholion.transcription.errors import AudioEnhancementError


def _write_wave(path: Path, *, frames: int = 160) -> None:
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16_000)
        stream.writeframes(b"\x00\x00" * frames)


def test_afftdn_configuration_is_explicit_and_model_free() -> None:
    configuration = ffmpeg_afftdn_configuration()

    assert configuration.mode is EnhancementMode.ON
    assert configuration.provider == "ffmpeg-afftdn"
    assert configuration.parameters == (
        ("noise_floor_db", "-50"),
        ("noise_reduction_db", "12"),
    )
    assert configuration.model_id is None
    assert configuration.model_revision is None


def test_enhancer_fails_closed_when_ffmpeg_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.wav"
    _write_wave(source)
    monkeypatch.setattr(
        "scholion.transcription.enhancement.shutil.which", lambda _: None
    )

    with pytest.raises(MediaToolUnavailableError, match="noise suppression"):
        FfmpegAfftdnEnhancer().enhance(
            DecodedAudio(source, temporary=False),
            ffmpeg_afftdn_configuration(),
            tmp_path,
        )


def test_enhancer_applies_fixed_filter_and_preserves_timeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.wav"
    _write_wave(source)
    commands: list[list[str]] = []
    monkeypatch.setattr(
        "scholion.transcription.enhancement.shutil.which", lambda _: "/usr/bin/ffmpeg"
    )

    def fake_run(command: list[str], **_: object) -> SimpleNamespace:
        commands.append(command)
        if command[1] == "-version":
            return SimpleNamespace(returncode=0, stdout="ffmpeg version test-1\n")
        shutil.copyfile(source, Path(command[-1]))
        return SimpleNamespace(returncode=0, stdout=None)

    monkeypatch.setattr("scholion.transcription.enhancement.subprocess.run", fake_run)

    result = FfmpegAfftdnEnhancer().enhance(
        DecodedAudio(source, temporary=False),
        ffmpeg_afftdn_configuration(),
        tmp_path,
    )

    assert result.path == (tmp_path / "enhanced.wav").resolve()
    assert result.provenance.provider == "ffmpeg-afftdn"
    assert result.provenance.provider_version == "ffmpeg version test-1"
    assert result.provenance.operation == "noise_suppression"
    assert commands[1][commands[1].index("-af") + 1] == "afftdn=nf=-50:nr=12"


def test_enhancer_rejects_parameter_mutation(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    _write_wave(source)
    mutated = EnhancementConfiguration(
        mode=EnhancementMode.ON,
        provider="ffmpeg-afftdn",
        parameters=(("noise_floor_db", "-40"), ("noise_reduction_db", "12")),
    )

    with pytest.raises(ValueError, match="parameter contract"):
        FfmpegAfftdnEnhancer().enhance(
            DecodedAudio(source, temporary=False), mutated, tmp_path
        )


def test_enhancer_removes_output_when_timeline_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.wav"
    _write_wave(source, frames=160)
    monkeypatch.setattr(
        "scholion.transcription.enhancement.shutil.which", lambda _: "/usr/bin/ffmpeg"
    )

    def fake_run(command: list[str], **_: object) -> SimpleNamespace:
        if command[1] == "-version":
            return SimpleNamespace(returncode=0, stdout="ffmpeg version test-1\n")
        _write_wave(Path(command[-1]), frames=159)
        return SimpleNamespace(returncode=0, stdout=None)

    monkeypatch.setattr("scholion.transcription.enhancement.subprocess.run", fake_run)

    with pytest.raises(AudioEnhancementError, match="timeline contract"):
        FfmpegAfftdnEnhancer().enhance(
            DecodedAudio(source, temporary=False),
            ffmpeg_afftdn_configuration(),
            tmp_path,
        )

    assert not (tmp_path / "enhanced.wav").exists()


def test_enhancer_cleans_partial_output_when_filter_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.wav"
    _write_wave(source)
    monkeypatch.setattr(
        "scholion.transcription.enhancement.shutil.which", lambda _: "/usr/bin/ffmpeg"
    )

    def fake_run(command: list[str], **_: object) -> SimpleNamespace:
        if command[1] == "-version":
            return SimpleNamespace(returncode=0, stdout="ffmpeg version test-1\n")
        Path(command[-1]).write_bytes(b"partial")
        return SimpleNamespace(returncode=1, stdout=None)

    monkeypatch.setattr("scholion.transcription.enhancement.subprocess.run", fake_run)

    with pytest.raises(AudioEnhancementError, match="failed"):
        FfmpegAfftdnEnhancer().enhance(
            DecodedAudio(source, temporary=False),
            ffmpeg_afftdn_configuration(),
            tmp_path,
        )

    assert not (tmp_path / "enhanced.wav").exists()


def test_version_probe_timeout_is_dependency_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.wav"
    _write_wave(source)
    monkeypatch.setattr(
        "scholion.transcription.enhancement.shutil.which", lambda _: "/usr/bin/ffmpeg"
    )

    def fake_run(command: list[str], **_: object) -> SimpleNamespace:
        if command[1] == "-version":
            raise subprocess.TimeoutExpired(command, 10)
        return SimpleNamespace(returncode=0, stdout=None)

    monkeypatch.setattr("scholion.transcription.enhancement.subprocess.run", fake_run)

    with pytest.raises(MediaToolUnavailableError, match="version"):
        FfmpegAfftdnEnhancer().enhance(
            DecodedAudio(source, temporary=False),
            ffmpeg_afftdn_configuration(),
            tmp_path,
        )
