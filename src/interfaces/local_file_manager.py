import os
import shutil
import tempfile
from pathlib import Path

from src.core.errors import (
    StorageError,
    StorageNotFoundError,
    StoragePermissionError,
)
from src.interfaces.base_file_manager import FileMetadata


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
        return sanitized

    @staticmethod
    def _error(operation: str, path: Path, exc: Exception) -> StorageError:
        if isinstance(exc, FileNotFoundError):
            return StorageNotFoundError(operation, path, cause=exc)
        if isinstance(exc, PermissionError):
            return StoragePermissionError(operation, path, cause=exc)
        return StorageError(operation, path, cause=exc)
