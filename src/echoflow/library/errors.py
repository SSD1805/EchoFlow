from echoflow.core.errors import EchoFlowError


class TranscriptLibraryError(EchoFlowError):
    """Safe application-boundary failure for local transcript-library operations."""


class TranscriptProjectionError(TranscriptLibraryError):
    exit_code = 2


class TranscriptLibraryBuildError(TranscriptLibraryError):
    exit_code = 2
