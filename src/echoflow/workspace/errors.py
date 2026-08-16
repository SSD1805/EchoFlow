from pathlib import Path

from echoflow.core.errors import EchoFlowError, ErrorCode


class InvalidInputError(EchoFlowError):
    code = ErrorCode.INVALID_INPUT
    exit_code = 2

    def __init__(self, path: Path):
        self.path = path
        super().__init__("Input is not a readable local file")


class UnsafePathError(EchoFlowError):
    code = ErrorCode.UNSAFE_PATH
    exit_code = 2


class JobCollisionError(EchoFlowError):
    code = ErrorCode.JOB_COLLISION

    def __init__(self, job_id: str, *, cause: Exception | None = None):
        self.job_id = job_id
        super().__init__(f"Job already exists: {job_id}", cause=cause)


class JobNotFoundError(EchoFlowError):
    code = ErrorCode.NOT_FOUND
    exit_code = 2

    def __init__(self, job_id: str):
        self.job_id = job_id
        super().__init__("Interrupted job was not found in private EchoFlow state")


class ArtifactCollisionError(EchoFlowError):
    code = ErrorCode.ARTIFACT_COLLISION

    def __init__(self, path: Path, *, cause: Exception | None = None):
        self.path = path
        super().__init__("Artifact path is already occupied", cause=cause)
