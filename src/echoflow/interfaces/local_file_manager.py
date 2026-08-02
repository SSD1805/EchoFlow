import os
import shutil
import tempfile
from pathlib import Path

from echoflow.core.errors import (
    StorageAlreadyExistsError,
    StorageError,
    StorageNotFoundError,
    StoragePermissionError,
)
from echoflow.interfaces.base_file_manager import FileMetadata

_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


class LocalFileManager:
    """Logger-free adapter for local filesystem behavior."""

    def save_file(self, content: bytes, file_path: str | Path) -> None:
        destination = Path(file_path).absolute()
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", delete=False, dir=destination.parent
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                temporary_file.write(content)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, destination)
        except Exception as exc:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise self._error("write", destination, exc) from exc

    def file_exists(self, file_path: str | Path) -> bool:
        return Path(file_path).is_file()

    def get_file_metadata(self, file_path: str | Path) -> FileMetadata:
        path = Path(file_path)
        try:
            stats = path.stat()
        except Exception as exc:
            raise self._error("read metadata for", path, exc) from exc
        return {
            "size": stats.st_size,
            "last_modified": stats.st_mtime,
            "last_accessed": stats.st_atime,
        }

    def delete_file(self, file_path: str | Path) -> None:
        path = Path(file_path)
        try:
            path.unlink(missing_ok=True)
        except Exception as exc:
            raise self._error("delete", path, exc) from exc

    def copy_file(self, source: str | Path, destination: str | Path) -> None:
        source_path = Path(source)
        destination_path = Path(destination)
        try:
            shutil.copy2(source_path, destination_path)
        except Exception as exc:
            error_path = source_path if not source_path.exists() else destination_path
            raise self._error("copy", error_path, exc) from exc

    def ensure_directory_exists(self, directory_path: str | Path) -> None:
        path = Path(directory_path)
        try:
            path.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            raise self._error("create directory", path, exc) from exc

    def reserve_directory(self, directory_path: str | Path) -> None:
        path = Path(directory_path)
        try:
            path.mkdir()
        except Exception as exc:
            raise self._error("reserve directory", path, exc) from exc

    def reserve_file(self, file_path: str | Path) -> None:
        path = Path(file_path)
        descriptor: int | None = None
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except Exception as exc:
            raise self._error("reserve file", path, exc) from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)

    def list_files(
        self,
        directory_path: str | Path,
        extensions: tuple[str, ...] | None = None,
    ) -> list[Path]:
        path = Path(directory_path)
        try:
            return sorted(
                candidate
                for candidate in path.iterdir()
                if candidate.is_file()
                and (not extensions or candidate.name.endswith(extensions))
            )
        except Exception as exc:
            raise self._error("list", path, exc) from exc

    def sanitize_filename(self, filename: str) -> str:
        sanitized = "".join(
            character if character.isalnum() or character in " ._-()" else "_"
            for character in filename
        )
        if sanitized in {"", ".", ".."}:
            return "_" * max(1, len(sanitized))
        sanitized = sanitized.rstrip(" .") or "_"
        if Path(sanitized).stem.upper() in _WINDOWS_RESERVED_NAMES:
            return f"_{sanitized}"
        return sanitized

    @staticmethod
    def _error(operation: str, path: Path, exc: Exception) -> StorageError:
        if isinstance(exc, FileExistsError):
            return StorageAlreadyExistsError(operation, path, cause=exc)
        if isinstance(exc, FileNotFoundError):
            return StorageNotFoundError(operation, path, cause=exc)
        if isinstance(exc, PermissionError):
            return StoragePermissionError(operation, path, cause=exc)
        return StorageError(operation, path, cause=exc)
