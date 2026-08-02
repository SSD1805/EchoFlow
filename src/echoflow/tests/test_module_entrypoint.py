import json
import os
import subprocess
import sys


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
        "STATE_DIR": str(tmp_path / "state"),
        "CACHE_DIR": str(tmp_path / "cache"),
        "OUTPUT_DIR": str(tmp_path / "output"),
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
