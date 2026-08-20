"""Materialize the checked-in Tauri icon from its base64 source.

This helper exists only to keep the repository text-only through connector workflows.
Normal development and packaged builds consume ``frontend/src-tauri/icons/icon.png``
directly and do not run this script.
"""

from __future__ import annotations

import base64
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "frontend" / "src-tauri" / "icons" / "icon.png.base64"
TARGET = ROOT / "frontend" / "src-tauri" / "icons" / "icon.png"


def main() -> int:
    TARGET.write_bytes(base64.b64decode(SOURCE.read_text(encoding="utf-8").strip()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
