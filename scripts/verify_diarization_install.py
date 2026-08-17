from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


def _wheel_from(dist_dir: Path) -> Path:
    wheels = tuple(sorted(dist_dir.glob("echoflow-*.whl")))
    if len(wheels) != 1:
        raise RuntimeError(
            f"expected exactly one EchoFlow wheel in {dist_dir}, found {len(wheels)}"
        )
    return wheels[0].resolve()


def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _run(command: list[str], *, cwd: Path, env: dict[str, str]) -> None:
    subprocess.run(command, cwd=cwd, env=env, check=True)  # noqa: S603


def verify_diarization_install(wheel: Path) -> None:
    """Prove the wheel's diarization extra installs without the ASR extra."""
    with tempfile.TemporaryDirectory(prefix="echoflow-diarization-dist-") as temporary:
        root = Path(temporary).resolve()
        venv_dir = root / "venv"
        work_dir = root / "work"
        work_dir.mkdir()
        venv.EnvBuilder(with_pip=True, clear=True).create(venv_dir)

        python = _venv_python(venv_dir)
        requirement = f"echoflow[diarization] @ {wheel.as_uri()}"
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        env["PYTHONNOUSERSITE"] = "1"
        env["PYANNOTE_METRICS_ENABLED"] = "0"

        _run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                requirement,
            ],
            cwd=work_dir,
            env=env,
        )
        _run(
            [
                str(python),
                "-c",
                (
                    "import echoflow, pyannote.audio, torch; "
                    "from importlib.metadata import version; "
                    "from importlib.util import find_spec; "
                    "assert find_spec('faster_whisper') is None; "
                    "print(version('echoflow')); "
                    "print(version('pyannote-audio')); "
                    "print(torch.__version__)"
                ),
            ],
            cwd=work_dir,
            env=env,
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify that the built EchoFlow wheel's diarization extra installs and "
            "imports outside the source checkout."
        )
    )
    parser.add_argument("dist_dir", type=Path)
    arguments = parser.parse_args()
    verify_diarization_install(_wheel_from(arguments.dist_dir.resolve()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
