from __future__ import annotations

import csv
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Protocol

_PRIVATE_DIRECTORY_MODE = 0o700
_PRIVATE_FILE_MODE = 0o600
_WINDOWS_ACL_TIMEOUT_SECONDS = 10.0
_SID_PATTERN = re.compile(r"S-\d-\d+(?:-\d+)+\Z")


class PrivateStoragePolicy(Protocol):
    """Platform-specific enforcement behind one private-storage contract."""

    def protect_directory(self, path: Path) -> None: ...
    def protect_file(self, path: Path) -> None: ...


class PosixPrivateStoragePolicy:
    """Enforce and verify owner-only POSIX mode bits."""

    def protect_directory(self, path: Path) -> None:
        self._protect(path, _PRIVATE_DIRECTORY_MODE)

    def protect_file(self, path: Path) -> None:
        self._protect(path, _PRIVATE_FILE_MODE)

    @staticmethod
    def _protect(path: Path, expected_mode: int) -> None:
        path.chmod(expected_mode)
        actual_mode = stat.S_IMODE(path.stat().st_mode)
        if actual_mode != expected_mode:
            raise PermissionError("Private POSIX permissions could not be verified")


class WindowsPrivateStoragePolicy:
    """Protect private paths with a DACL scoped to the current user SID."""

    def __init__(self) -> None:
        self._user_sid: str | None = None

    def protect_directory(self, path: Path) -> None:
        self._protect(path, inherit_to_children=True)

    def protect_file(self, path: Path) -> None:
        self._protect(path, inherit_to_children=False)

    def _protect(self, path: Path, *, inherit_to_children: bool) -> None:
        sid = self._current_user_sid()
        icacls = self._system_executable("icacls.exe")
        self._run([icacls, str(path), "/reset", "/Q"])
        self._run([icacls, str(path), "/inheritance:r", "/Q"])
        inheritance = "(OI)(CI)" if inherit_to_children else ""
        self._run(
            [icacls, str(path), "/grant:r", f"*{sid}:{inheritance}F", "/Q"]
        )
        self._run([icacls, str(path), "/verify", "/Q"])

    def _current_user_sid(self) -> str:
        if self._user_sid is not None:
            return self._user_sid

        whoami = self._system_executable("whoami.exe")
        completed = self._run([whoami, "/user", "/fo", "csv", "/nh"])
        row = next(csv.reader([completed.stdout.strip()]), [])
        if len(row) < 2 or _SID_PATTERN.fullmatch(row[1].strip()) is None:
            raise PermissionError("Windows user SID could not be verified")
        self._user_sid = row[1].strip()
        return self._user_sid

    @staticmethod
    def _system_executable(name: str) -> str:
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        executable = Path(system_root) / "System32" / name
        if not executable.is_file():
            raise PermissionError("Required Windows ACL utility is unavailable")
        return str(executable)

    @staticmethod
    def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(  # noqa: S603
                command,
                capture_output=True,
                check=True,
                text=True,
                timeout=_WINDOWS_ACL_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
            raise PermissionError("Windows private ACL enforcement failed") from exc


def default_private_storage_policy() -> PrivateStoragePolicy:
    if os.name == "nt":
        return WindowsPrivateStoragePolicy()
    return PosixPrivateStoragePolicy()
