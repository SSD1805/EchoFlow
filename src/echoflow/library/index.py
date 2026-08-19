from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable


def _validate_sha256(name: str, value: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{name} must be a lowercase 64-character digest")


class SearchOperator(StrEnum):
    ANY = "any"
    ALL = "all"


class SearchSort(StrEnum):
    RELEVANCE = "relevance"
    TIMELINE = "timeline"


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
    """Database-neutral projection of one canonical transcript."""

    document_id: str
    source_sha256: str
    transcript_schema_version: int
    detected_language: str | None
    canonical_path: str
    source_path: str | None
    source_size_bytes: int
    source_modified_ns: int
    segments: tuple[IndexedSegment, ...]
    canonical_sha256: str | None = None
    canonical_size_bytes: int | None = None
    canonical_modified_ns: int | None = None

    def __post_init__(self) -> None:
        if not self.document_id.strip():
            raise ValueError("document_id cannot be empty")
        _validate_sha256("source_sha256", self.source_sha256)
        if self.canonical_sha256 is not None:
            _validate_sha256("canonical_sha256", self.canonical_sha256)
        if self.transcript_schema_version < 1:
            raise ValueError("transcript_schema_version must be positive")
        if self.detected_language is not None and not self.detected_language.strip():
            raise ValueError("detected_language cannot be empty")
        if not self.canonical_path.strip():
            raise ValueError("canonical_path cannot be empty")
        if self.source_path is not None and not self.source_path.strip():
            raise ValueError("source_path cannot be empty")
        if self.source_size_bytes < 1:
            raise ValueError("source_size_bytes must be positive")
        if self.source_modified_ns < 0:
            raise ValueError("source_modified_ns cannot be negative")
        self._validate_canonical_signature()
        segment_ids = tuple(segment.segment_id for segment in self.segments)
        if len(segment_ids) != len(set(segment_ids)):
            raise ValueError("segment IDs must be unique within a document")

    def _validate_canonical_signature(self) -> None:
        if (self.canonical_size_bytes is None) != (self.canonical_modified_ns is None):
            raise ValueError(
                "canonical size and modified time must either both be set or both be absent"
            )
        if self.canonical_size_bytes is not None and self.canonical_size_bytes < 1:
            raise ValueError("canonical_size_bytes must be positive")
        if self.canonical_modified_ns is not None and self.canonical_modified_ns < 0:
            raise ValueError("canonical_modified_ns cannot be negative")


@dataclass(frozen=True, slots=True)
class IndexedDocument:
    document_id: str
    source_sha256: str
    detected_language: str | None
    canonical_path: str
    source_path: str | None
    segment_count: int
    canonical_sha256: str | None = None
    canonical_size_bytes: int | None = None
    canonical_modified_ns: int | None = None


@dataclass(frozen=True, slots=True)
class SearchQuery:
    """Stable application query contract shared by CLI, UI, and index adapters."""

    text: str
    phrase: bool = False
    operator: SearchOperator = SearchOperator.ANY
    speaker_refs: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    document_ids: tuple[str, ...] = ()
    sort: SearchSort = SearchSort.RELEVANCE
    limit: int = 100
    evidence_scope: tuple[tuple[str, str, str], ...] | None = None

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("query text cannot be empty")
        if self.limit < 1 or self.limit > 1_000:
            raise ValueError("query limit must be between 1 and 1000")
        for name, values in (
            ("speaker_refs", self.speaker_refs),
            ("languages", self.languages),
            ("document_ids", self.document_ids),
        ):
            if any(not value.strip() for value in values):
                raise ValueError(f"{name} cannot contain empty values")
            if len(values) != len(set(values)):
                raise ValueError(f"{name} cannot contain duplicates")
        self._validate_evidence_scope()

    def _validate_evidence_scope(self) -> None:
        if self.evidence_scope is None:
            return
        if len(self.evidence_scope) != len(set(self.evidence_scope)):
            raise ValueError("evidence_scope cannot contain duplicates")
        for document_id, canonical_sha256, segment_id in self.evidence_scope:
            if not document_id.strip() or not segment_id.strip():
                raise ValueError("evidence_scope identities cannot be empty")
            _validate_sha256("evidence_scope canonical_sha256", canonical_sha256)


@dataclass(frozen=True, slots=True)
class TranscriptMatch:
    """Evidence-bearing lexical result independent of backend implementation."""

    document_id: str
    source_sha256: str
    canonical_path: str
    source_path: str | None
    segment_id: str
    start_seconds: float
    end_seconds: float
    text: str
    language: str | None
    speaker_ref: str | None
    score: float

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
    """Application port for disposable, rebuildable transcript search state."""

    @property
    def backend_id(self) -> str: ...

    def rebuild(self, transcripts: tuple[IndexedTranscript, ...]) -> None:
        """Replace the complete derived index atomically."""
        ...

    def apply_delta(
        self,
        *,
        upserts: tuple[IndexedTranscript, ...],
        removals: tuple[str, ...],
    ) -> None:
        """Apply one incremental corpus delta atomically."""
        ...

    def upsert(self, transcript: IndexedTranscript) -> None: ...

    def remove(self, document_id: str) -> None: ...

    def contains(self, document_id: str) -> bool: ...

    def documents(self) -> tuple[IndexedDocument, ...]: ...

    def search(self, query: SearchQuery) -> tuple[TranscriptMatch, ...]: ...

    def clear(self) -> None: ...

    def close(self) -> None: ...
