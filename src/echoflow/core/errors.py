from enum import StrEnum
from pathlib import Path


class ErrorCode(StrEnum):
    INTERNAL = "internal_error"
    CONFIGURATION = "configuration_error"
    STORAGE = "storage_error"
    NOT_FOUND = "storage_not_found"
    PERMISSION = "storage_permission_denied"
    ALREADY_EXISTS = "storage_already_exists"
    INVALID_INPUT = "invalid_input"
    UNSAFE_PATH = "unsafe_path"
    JOB_COLLISION = "job_collision"
    ARTIFACT_COLLISION = "artifact_collision"
    MEDIA_TOOL_UNAVAILABLE = "media_tool_unavailable"
    MEDIA_PROBE = "media_probe_failed"
    UNSUPPORTED_MEDIA = "unsupported_media"
    INPUT_CHANGED = "input_changed"
    AUDIO_DECODE = "audio_decode_failed"
    RESOURCE_ADMISSION = "resource_admission_failed"
    TRANSCRIPTION_DEPENDENCY = "transcription_dependency_unavailable"
    MODEL_UNAVAILABLE = "transcription_model_unavailable"
    TRANSCRIPTION = "transcription_failed"
    DIARIZATION_DEPENDENCY = "diarization_dependency_unavailable"
    DIARIZATION_MODEL_UNAVAILABLE = "diarization_model_unavailable"
    DIARIZATION = "diarization_failed"


class EchoFlowError(Exception):
    """Base for failures that can cross an application or CLI boundary safely."""

    code = ErrorCode.INTERNAL
    exit_code = 1

    def __init__(self, public_message: str, *, cause: Exception | None = None):
        super().__init__(public_message)
        self.public_message = public_message
        self.cause = cause


class ConfigurationError(EchoFlowError):
    code = ErrorCode.CONFIGURATION
    exit_code = 2


class StorageError(EchoFlowError):
    code = ErrorCode.STORAGE

    def __init__(
        self, operation: str, path: str | Path, *, cause: Exception | None = None
    ):
        self.operation = operation
        self.path = Path(path)
        super().__init__(f"Could not {operation} local path", cause=cause)


class StorageNotFoundError(StorageError):
    code = ErrorCode.NOT_FOUND


class StoragePermissionError(StorageError):
    code = ErrorCode.PERMISSION


class StorageAlreadyExistsError(StorageError):
    code = ErrorCode.ALREADY_EXISTS
