from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    required = (repo_root / "pyproject.toml", repo_root / "uv.lock")
    missing = [path.name for path in required if not path.is_file()]
    if missing:
        names = ", ".join(missing)
        raise SystemExit(f"Scholion checkout is incomplete; missing: {names}")

    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit(
            "uv is required to prepare the Scholion development environment"
        )

    subprocess.run(  # noqa: S603 - executable is resolved locally; argv is fixed
        [
            uv,
            "sync",
            "--locked",
            "--all-groups",
            "--extra",
            "transcription",
        ],
        cwd=repo_root,
        check=True,
    )
    subprocess.run(  # noqa: S603 - executable is resolved locally; argv is fixed
        [uv, "run", "poodle", "--help"],
        cwd=repo_root,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    print("Scholion development environment ready; Poodle is available.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
