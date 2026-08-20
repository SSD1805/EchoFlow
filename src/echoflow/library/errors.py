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


class TranscriptToolingError(TranscriptLibraryError):
    """Transcript inspection, speaker management, or publication failed safely."""

    exit_code = 2


class EvidenceNavigationError(TranscriptLibraryError):
    """A ranked result cannot be reconciled safely with canonical evidence."""

    exit_code = 2


class ResearchStateError(TranscriptLibraryError):
    """Durable user-authored research state is invalid or unavailable."""

    exit_code = 2


class ResearchProjectionError(TranscriptLibraryError):
    """Disposable research-state projection cannot be reconciled safely."""

    exit_code = 2


class CustodyOperationError(TranscriptLibraryError):
    """A deletion or retention request cannot be executed safely as planned."""

    exit_code = 2


class LibraryLocationError(TranscriptLibraryError):
    """Durable library-location state or discovery policy is invalid or unavailable."""

    exit_code = 2
