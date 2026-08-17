import json
import os
import shutil
import subprocess
import sys
import wave

import pytest


def run_module(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "echoflow", *arguments],
        capture_output=True,
        check=False,
        text=True,
    )


def test_module_entrypoint_exposes_cli_help() -> None:
    result = run_module("--help")

    assert result.returncode == 0
    assert "Local-first audio processing and transcription" in result.stdout
    assert "doctor" in result.stdout


def test_module_entrypoint_rejects_unknown_commands() -> None:
    result = run_module("not-a-command")

    assert result.returncode == 2
    assert "No such command" in result.stderr
    assert "not-a-command" in result.stderr


def test_real_init_json_keeps_logs_on_standard_error(tmp_path) -> None:
    environment = {
        **os.environ,
        "ECHOFLOW_STATE_DIR": str(tmp_path / "state"),
        "ECHOFLOW_CACHE_DIR": str(tmp_path / "cache"),
        "ECHOFLOW_OUTPUT_DIR": str(tmp_path / "output"),
    }
    result = subprocess.run(
        [sys.executable, "-m", "echoflow", "init", "--json"],
        capture_output=True,
        check=False,
        text=True,
        env=environment,
    )
    payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert payload["output_dir"] == str(tmp_path / "output")
    assert "File operation completed" not in result.stdout
    assert "File operation completed" in result.stderr
    assert str(tmp_path) not in result.stderr


@pytest.mark.skipif(shutil.which("ffprobe") is None, reason="ffprobe is unavailable")
def test_real_dry_run_probes_media_then_refuses_unmanaged_model_without_writes(
    tmp_path,
) -> None:
    source = tmp_path / "incoming" / "participant-001.wav"
    source.parent.mkdir()
    with wave.open(str(source), "wb") as recording:
        recording.setnchannels(1)
        recording.setsampwidth(2)
        recording.setframerate(16_000)
        recording.writeframes(b"\0\0" * 4_000)

    state = tmp_path / "state"
    cache = tmp_path / "cache"
    output = tmp_path / "output"
    environment = {
        **os.environ,
        "ECHOFLOW_STATE_DIR": str(state),
        "ECHOFLOW_CACHE_DIR": str(cache),
        "ECHOFLOW_OUTPUT_DIR": str(output),
        "ECHOFLOW_FFPROBE_TIMEOUT_SECONDS": "10",
    }
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "echoflow",
            "transcribe",
            str(source),
            "--dry-run",
            "--profile",
            "screening",
            "--json",
        ],
        capture_output=True,
        check=False,
        text=True,
        env=environment,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert "echoflow models install tiny" in result.stderr
    assert "participant-001" not in result.stderr
    assert str(tmp_path) not in result.stderr
    assert not state.exists()
    assert not cache.exists()
    assert not output.exists()