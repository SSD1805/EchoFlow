from enum import StrEnum
from pathlib import Path


class ErrorCode(StrEnum):
    STORAGE = "storage_error"
    NOT_FOUND = "storage_not_found"
    PERMISSION = "storage_permission_denied"


class EchoFlowError(Exception):
    """Base for failures that can cross an application or CLI boundary safely."""

    code = ErrorCode.STORAGE
    exit_code = 1

    def __init__(self, public_message: str, *, cause: Exception | None = None):
        super().__init__(public_message)
        self.public_message = public_message
        self.cause = cause


class StorageError(EchoFlowError):
    def __init__(
        self, operation: str, path: str | Path, *, cause: Exception | None = None
    ):
        self.operation = operation
        self.path = Path(path)
        super().__init__(f"Could not {operation} local path: {self.path}", cause=cause)


class StorageNotFoundError(StorageError):
    code = ErrorCode.NOT_FOUND


class StoragePermissionError(StorageError):
    code = ErrorCode.PERMISSION
