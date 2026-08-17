from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class IndexedSegment:
    """One source-relative transcript segment copied into a rebuildable index."""

    segment_id: str
    start_seconds: float
    end_seconds: float
    text: str
    language: str | None = None
    speaker_ref: str | None = None

    def __post_init__(self) -> None:
        if not self.segment_id.strip():
            raise ValueError("segment_id cannot be empty")
        if self.start_seconds < 0 or self.end_seconds < self.start_seconds:
            raise ValueError("segment timestamps must be ordered and non-negative")
        if not self.text.strip():
            raise ValueError("segment text cannot be empty")
        if self.language is not None and not self.language.strip():
            raise ValueError("language cannot be empty")
        if self.speaker_ref is not None and not self.speaker_ref.strip():
            raise ValueError("speaker_ref cannot be empty")


@dataclass(frozen=True, slots=True)
class IndexedTranscript:
    """Database-neutral projection of one canonical transcript.

    This object is intentionally a projection rather than the canonical transcript
    schema itself. Index backends may store and optimize it however they want, but
    EchoFlow must be able to discard the backend and rebuild it from canonical
    artifacts.
    """

    document_id: str
    source_sha256: str
    transcript_schema_version: int
    detected_language: str | None
    segments: tuple[IndexedSegment, ...]

    def __post_init__(self) -> None:
        if not self.document_id.strip():
            raise ValueError("document_id cannot be empty")
        if len(self.source_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.source_sha256
        ):
            raise ValueError("source_sha256 must be a lowercase 64-character digest")
        if self.transcript_schema_version < 1:
            raise ValueError("transcript_schema_version must be positive")
        if self.detected_language is not None and not self.detected_language.strip():
            raise ValueError("detected_language cannot be empty")
        segment_ids = tuple(segment.segment_id for segment in self.segments)
        if len(segment_ids) != len(set(segment_ids)):
            raise ValueError("segment IDs must be unique within a document")


@dataclass(frozen=True, slots=True)
class TranscriptQuery:
    """Portable lexical query supported by every transcript-index backend."""

    text: str
    limit: int = 100

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("query text cannot be empty")
        if self.limit < 1:
            raise ValueError("query limit must be positive")


@dataclass(frozen=True, slots=True)
class TranscriptMatch:
    """Portable search result independent of backend ranking implementation."""

    document_id: str
    segment_id: str
    start_seconds: float
    end_seconds: float
    text: str
    score: float | None = None

    def __post_init__(self) -> None:
        if not self.document_id.strip():
            raise ValueError("document_id cannot be empty")
        if not self.segment_id.strip():
            raise ValueError("segment_id cannot be empty")
        if self.start_seconds < 0 or self.end_seconds < self.start_seconds:
            raise ValueError("match timestamps must be ordered and non-negative")
        if not self.text.strip():
            raise ValueError("match text cannot be empty")


@runtime_checkable
class TranscriptIndex(Protocol):
    """Application port for a rebuildable transcript-search index.

    Implementations may use DuckDB, SQLite, PostgreSQL, or another storage engine.
    The port deliberately exposes transcript-library behavior instead of SQL so the
    application never depends on a backend dialect or transaction API.
    """

    @property
    def backend_id(self) -> str:
        """Stable identifier used for diagnostics and provenance."""
        ...

    def upsert(self, transcript: IndexedTranscript) -> None:
        """Replace the indexed projection for one canonical transcript atomically."""
        ...

    def remove(self, document_id: str) -> None:
        """Remove one indexed document. Missing documents must be harmless."""
        ...

    def contains(self, document_id: str) -> bool:
        """Return whether the backend currently contains the document."""
        ...

    def search(self, query: TranscriptQuery) -> tuple[TranscriptMatch, ...]:
        """Return at most query.limit lexical matches."""
        ...

    def clear(self) -> None:
        """Discard all derived index state without touching canonical artifacts."""
        ...

    def close(self) -> None:
        """Release backend resources. Calling close repeatedly should be safe."""
        ...
