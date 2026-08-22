from pathlib import Path

from scholion.core.errors import ErrorCode, ScholionError


class InvalidInputError(ScholionError):
    code = ErrorCode.INVALID_INPUT
    exit_code = 2

    def __init__(self, path: Path):
        self.path = path
        super().__init__("Input is not a readable local file")


class UnsafePathError(ScholionError):
    code = ErrorCode.UNSAFE_PATH
    exit_code = 2


class JobCollisionError(ScholionError):
    code = ErrorCode.JOB_COLLISION

    def __init__(self, job_id: str, *, cause: Exception | None = None):
        self.job_id = job_id
        super().__init__(f"Job already exists: {job_id}", cause=cause)


class JobNotFoundError(ScholionError):
    code = ErrorCode.NOT_FOUND
    exit_code = 2

    def __init__(self, job_id: str):
        self.job_id = job_id
        super().__init__("Interrupted job was not found in private Scholion state")


class ArtifactCollisionError(ScholionError):
    code = ErrorCode.ARTIFACT_COLLISION

    def __init__(self, path: Path, *, cause: Exception | None = None):
        self.path = path
        super().__init__("Artifact path is already occupied", cause=cause)
