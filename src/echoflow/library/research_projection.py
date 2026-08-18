"""Disposable research-state projection contracts used for fast evidence filtering."""

from dataclasses import dataclass  # noqa: I001
from typing import Protocol, runtime_checkable

from echoflow.library.research_state import ResearchProjectionRecord


type EvidenceScopeKey = tuple[str, str, str]


@dataclass(frozen=True, slots=True)
class ResearchProjectionFilter:
    """Resolved query constraints over projected user-authored research state."""

    tag_ids: tuple[str, ...] = ()
    collection_ids: tuple[str, ...] = ()
    document_ids: tuple[str, ...] = ()
    note_text: str | None = None
    require_notes: bool = False

    def __post_init__(self) -> None:
        for name, values in (
            ("tag_ids", self.tag_ids),
            ("collection_ids", self.collection_ids),
            ("document_ids", self.document_ids),
        ):
            if any(not value.strip() for value in values):
                raise ValueError(f"{name} cannot contain empty values")
            if tuple(sorted(set(values))) != values:
                raise ValueError(f"{name} must be sorted and deduplicated")
        if self.note_text is not None and not self.note_text.strip():
            raise ValueError("note_text cannot be blank")

    @property
    def active(self) -> bool:
        return bool(
            self.require_notes
            or self.tag_ids
            or self.collection_ids
            or self.document_ids
            or self.note_text is not None
        )


@dataclass(frozen=True, slots=True)
class ProjectedEvidenceSummary:
    """Rebuildable user-state metadata attached to one canonical evidence segment."""

    note_ids: tuple[str, ...] = ()
    tag_ids: tuple[str, ...] = ()
    collection_ids: tuple[str, ...] = ()

    @property
    def note_count(self) -> int:
        return len(self.note_ids)


@dataclass(frozen=True, slots=True)
class ResearchProjectionStatus:
    authoritative_sequence: int
    projected_sequence: int

    def __post_init__(self) -> None:
        if self.authoritative_sequence < 0 or self.projected_sequence < 0:
            raise ValueError("research projection sequences cannot be negative")

    @property
    def current(self) -> bool:
        return self.authoritative_sequence == self.projected_sequence


@runtime_checkable
class ResearchProjectionIndex(Protocol):
    """Disposable query projection derived entirely from durable research state."""

    @property
    def backend_id(self) -> str: ...

    def projected_through_sequence(self) -> int: ...

    def rebuild(
        self,
        records: tuple[ResearchProjectionRecord, ...],
        *,
        through_sequence: int,
    ) -> None: ...

    def apply(
        self,
        records: tuple[ResearchProjectionRecord, ...],
        *,
        deleted_note_ids: tuple[str, ...],
        through_sequence: int,
    ) -> None: ...

    def matching_note_ids(
        self, filters: ResearchProjectionFilter
    ) -> tuple[str, ...]: ...

    def matching_evidence(
        self, filters: ResearchProjectionFilter
    ) -> tuple[EvidenceScopeKey, ...]: ...

    def summaries(
        self, keys: tuple[EvidenceScopeKey, ...]
    ) -> dict[EvidenceScopeKey, ProjectedEvidenceSummary]: ...

    def clear(self) -> None: ...

    def close(self) -> None: ...
