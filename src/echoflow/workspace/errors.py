from pathlib import Path

from echoflow.core.errors import EchoFlowError, ErrorCode


class InvalidInputError(EchoFlowError):
    code = ErrorCode.INVALID_INPUT
    exit_code = 2

    def __init__(self, path: Path):
        self.path = path
        super().__init__(f"Input is not a local file: {path}")


class UnsafePathError(EchoFlowError):
    code = ErrorCode.UNSAFE_PATH
    exit_code = 2


class JobCollisionError(EchoFlowError):
    code = ErrorCode.JOB_COLLISION

    def __init__(self, job_id: str, *, cause: Exception | None = None):
        self.job_id = job_id
        super().__init__(f"Job already exists: {job_id}", cause=cause)


class ArtifactCollisionError(EchoFlowError):
    code = ErrorCode.ARTIFACT_COLLISION

    def __init__(self, path: Path, *, cause: Exception | None = None):
        self.path = path
        super().__init__(f"Artifact already exists: {path.name}", cause=cause)
