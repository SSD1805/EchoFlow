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
