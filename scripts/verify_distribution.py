from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import venv
import wave
import zipfile
from email import policy
from email.parser import BytesParser
from pathlib import Path

_EXPECTED_LICENSE_EXPRESSION = "AGPL-3.0-only"


def _wheel_from(dist_dir: Path) -> Path:
    wheels = tuple(sorted(dist_dir.glob("echoflow-*.whl")))
    if len(wheels) != 1:
        raise RuntimeError(
            f"expected exactly one EchoFlow wheel in {dist_dir}, found {len(wheels)}"
        )
    return wheels[0].resolve()


def _inspect_wheel(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        names = tuple(archive.namelist())
        leaked_tests = tuple(
            name
            for name in names
            if "/tests/" in name or Path(name).name.startswith("test_")
        )
        if leaked_tests:
            raise RuntimeError(
                "built wheel contains test files: " + ", ".join(leaked_tests)
            )

        metadata_names = tuple(
            name for name in names if name.endswith(".dist-info/METADATA")
        )
        entry_point_names = tuple(
            name for name in names if name.endswith(".dist-info/entry_points.txt")
        )
        license_names = tuple(
            name for name in names if name.endswith(".dist-info/licenses/LICENSE")
        )
        if len(metadata_names) != 1 or len(entry_point_names) != 1:
            raise RuntimeError("built wheel is missing canonical distribution metadata")
        if len(license_names) != 1:
            raise RuntimeError("built wheel does not contain the EchoFlow license file")

        metadata = BytesParser(policy=policy.default).parsebytes(
            archive.read(metadata_names[0])
        )
        if metadata.get("License-Expression") != _EXPECTED_LICENSE_EXPRESSION:
            raise RuntimeError(
                "built wheel has unexpected license expression: "
                f"{metadata.get('License-Expression')!r}"
            )
        extras = set(metadata.get_all("Provides-Extra", []))
        requirements = tuple(metadata.get_all("Requires-Dist", []))
        if "transcription" not in extras:
            raise RuntimeError("built wheel does not expose the transcription extra")
        if not any(
            requirement.startswith("faster-whisper") and "transcription" in requirement
            for requirement in requirements
        ):
            raise RuntimeError(
                "built wheel does not bind faster-whisper to the transcription extra"
            )

        entry_points = archive.read(entry_point_names[0]).decode("utf-8")
        if "echoflow = echoflow.cli:app" not in entry_points:
            raise RuntimeError(
                "built wheel does not expose the echoflow console command"
            )


def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _console_script(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "echoflow.exe"
    return venv_dir / "bin" / "echoflow"


def _run(command: list[str], *, cwd: Path, env: dict[str, str]) -> None:
    subprocess.run(command, cwd=cwd, env=env, check=True)  # noqa: S603


def _write_acceptance_wave(path: Path) -> None:
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16_000)
        audio.writeframes(b"\x00\x00" * 16_000)


def _verify_clean_install(wheel: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="echoflow-dist-") as temporary:
        root = Path(temporary).resolve()
        venv_dir = root / "venv"
        work_dir = root / "work"
        work_dir.mkdir()
        venv.EnvBuilder(with_pip=True, clear=True).create(venv_dir)

        python = _venv_python(venv_dir)
        console = _console_script(venv_dir)
        requirement = f"echoflow[transcription] @ {wheel.as_uri()}"
        sample_audio = work_dir / "acceptance.wav"
        _write_acceptance_wave(sample_audio)

        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        env["PYTHONNOUSERSITE"] = "1"
        env["ECHOFLOW_STATE_DIR"] = str(root / "state")
        env["ECHOFLOW_CACHE_DIR"] = str(root / "cache")
        env["ECHOFLOW_MODEL_DIR"] = str(root / "cache" / "models")
        env["ECHOFLOW_OUTPUT_DIR"] = str(root / "output")
        env["ECHOFLOW_MIN_FREE_DISK_BYTES"] = "0"
        env["ECHOFLOW_WARN_FREE_DISK_BYTES"] = "0"

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
                    "import echoflow, faster_whisper; "
                    "from importlib.metadata import version; "
                    "print(version('echoflow')); "
                    "print(faster_whisper.__version__)"
                ),
            ],
            cwd=work_dir,
            env=env,
        )
        _run([str(console), "--help"], cwd=work_dir, env=env)
        _run([str(python), "-m", "echoflow", "--help"], cwd=work_dir, env=env)
        _run([str(console), "init", "--json"], cwd=work_dir, env=env)
        _run([str(console), "doctor", "--json"], cwd=work_dir, env=env)
        _run([str(console), "runner", "--json"], cwd=work_dir, env=env)
        _run([str(console), "strategies", "--json"], cwd=work_dir, env=env)
        _run(
            [
                str(console),
                "transcribe",
                str(sample_audio),
                "--dry-run",
                "--profile",
                "screening",
                "--json",
            ],
            cwd=work_dir,
            env=env,
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify that a built EchoFlow wheel works without the source checkout."
    )
    parser.add_argument("dist_dir", type=Path)
    arguments = parser.parse_args()

    wheel = _wheel_from(arguments.dist_dir.resolve())
    _inspect_wheel(wheel)
    _verify_clean_install(wheel)
    return 0


if __name__ == "__main__":
    sys.exit(main())
