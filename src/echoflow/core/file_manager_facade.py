from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Protocol, TypeVar

from echoflow.core.errors import EchoFlowError
from echoflow.core.ilogger import ILogger
from echoflow.core.privacy import PathDisclosure, path_log_context
from echoflow.interfaces.base_file_manager import FileManager, FileMetadata

T = TypeVar("T")


class ExecutionTracker(Protocol):
    def track_execution(self, operation_name: str) -> AbstractContextManager[None]: ...
    def get_metric(self, operation_name: str) -> float | None: ...


class FileManagerFacade:
    """Application boundary that owns file-operation timing and logging."""

    def __init__(
        self,
        file_manager: FileManager,
        logger: ILogger,
        tracker: ExecutionTracker,
        path_disclosure: PathDisclosure = PathDisclosure.REDACT,
    ):
        self.file_manager = file_manager
        self.logger = logger
        self.tracker = tracker
        self.path_disclosure = path_disclosure

    def _execute(self, operation: str, action: Callable[[], T], **context: object) -> T:
        try:
            with self.tracker.track_execution(operation):
                result = action()
        except EchoFlowError as exc:
            self.logger.error(
                "File operation failed",
                operation=operation,
                error_code=exc.code.value,
                exception_type=type(exc).__name__,
                **context,
            )
            raise
        self.logger.info(
            "File operation completed",
            operation=operation,
            duration_seconds=self.tracker.get_metric(operation),
            **context,
        )
        return result

    def save_file(
        self, content: bytes, file_path: str | Path, *, private: bool = False
    ) -> None:
        if private:
            action = lambda: self.file_manager.save_file(
                content, file_path, private=True
            )
        else:
            action = lambda: self.file_manager.save_file(content, file_path)
        self._execute(
            "save_file",
            action,
            private=private,
            **path_log_context(self.path_disclosure, path=file_path),
        )

    def read_file(self, file_path: str | Path) -> bytes:
        return self._execute(
            "read_file",
            lambda: self.file_manager.read_file(file_path),
            **path_log_context(self.path_disclosure, path=file_path),
        )

    def file_exists(self, file_path: str | Path) -> bool:
        return self._execute(
            "file_exists",
            lambda: self.file_manager.file_exists(file_path),
            **path_log_context(self.path_disclosure, path=file_path),
        )

    def get_file_metadata(self, file_path: str | Path) -> FileMetadata:
        return self._execute(
            "get_file_metadata",
            lambda: self.file_manager.get_file_metadata(file_path),
            **path_log_context(self.path_disclosure, path=file_path),
        )

    def delete_file(self, file_path: str | Path) -> None:
        self._execute(
            "delete_file",
            lambda: self.file_manager.delete_file(file_path),
            **path_log_context(self.path_disclosure, path=file_path),
        )

    def copy_file(self, source: str | Path, destination: str | Path) -> None:
        self._execute(
            "copy_file",
            lambda: self.file_manager.copy_file(source, destination),
            **path_log_context(
                self.path_disclosure, source=source, destination=destination
            ),
        )

    def ensure_directory_exists(
        self, directory_path: str | Path, *, private: bool = False
    ) -> None:
        self._execute(
            "ensure_directory_exists",
            lambda: self.file_manager.ensure_directory_exists(
                directory_path, private=private
            ),
            private=private,
            **path_log_context(self.path_disclosure, path=directory_path),
        )

    def reserve_directory(
        self, directory_path: str | Path, *, private: bool = False
    ) -> None:
        self._execute(
            "reserve_directory",
            lambda: self.file_manager.reserve_directory(
                directory_path, private=private
            ),
            private=private,
            **path_log_context(self.path_disclosure, path=directory_path),
        )

    def reserve_file(self, file_path: str | Path) -> None:
        self._execute(
            "reserve_file",
            lambda: self.file_manager.reserve_file(file_path),
            **path_log_context(self.path_disclosure, path=file_path),
        )

    def list_files(
        self,
        directory_path: str | Path,
        extensions: tuple[str, ...] | None = None,
    ) -> list[Path]:
        return self._execute(
            "list_files",
            lambda: self.file_manager.list_files(directory_path, extensions),
            **path_log_context(self.path_disclosure, path=directory_path),
            extensions=extensions,
        )

    def sanitize_filename(self, filename: str) -> str:
        return self._execute(
            "sanitize_filename", lambda: self.file_manager.sanitize_filename(filename)
        )
