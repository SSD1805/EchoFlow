from echoflow.core.errors import EchoFlowError


class TranscriptLibraryError(EchoFlowError):
    """Safe application-boundary failure for local transcript-library operations."""


class TranscriptProjectionError(TranscriptLibraryError):
    exit_code = 2


class TranscriptLibraryBuildError(TranscriptLibraryError):
    exit_code = 2


class SemanticSearchUnavailableError(TranscriptLibraryError):
    """Semantic capability is absent, unbuilt, stale, or cannot load locally."""

    exit_code = 2


class SpeakerLabelStateError(TranscriptLibraryError):
    """User-authored speaker label state is invalid, stale, or unavailable."""

    exit_code = 2


class EvidenceNavigationError(TranscriptLibraryError):
    """A ranked result cannot be reconciled safely with canonical evidence."""

    exit_code = 2
