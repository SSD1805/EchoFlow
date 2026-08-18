"""Durable user-authored research state and storage ports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from echoflow.library.evidence import EvidenceAnchor


@dataclass(frozen=True, slots=True)
class ResearchNote:
    """One durable user note anchored to exact canonical evidence."""

    note_id: str
    body: str
    anchor: EvidenceAnchor
    tag_ids: tuple[str, ...]
    collection_ids: tuple[str, ...]
    created_at: str
    updated_at: str

    def __post_init__(self) -> None:
        if not self.note_id.strip():
            raise ValueError("note_id cannot be empty")
        if not self.body.strip():
            raise ValueError("note body cannot be empty")
        if tuple(sorted(set(self.tag_ids))) != self.tag_ids:
            raise ValueError("note tag IDs must be sorted and deduplicated")
        if tuple(sorted(set(self.collection_ids))) != self.collection_ids:
            raise ValueError("note collection IDs must be sorted and deduplicated")
        if not self.created_at.strip() or not self.updated_at.strip():
            raise ValueError("note timestamps cannot be empty")


@dataclass(frozen=True, slots=True)
class ResearchTag:
    tag_id: str
    name: str

    def __post_init__(self) -> None:
        if not self.tag_id.strip() or not self.name.strip():
            raise ValueError("tag identity and name cannot be empty")


@dataclass(frozen=True, slots=True)
class ResearchCollection:
    collection_id: str
    name: str

    def __post_init__(self) -> None:
        if not self.collection_id.strip() or not self.name.strip():
            raise ValueError("collection identity and name cannot be empty")


@dataclass(frozen=True, slots=True)
class ResearchStateChange:
    """One monotonic outbox event that invalidates one projected note."""

    sequence_id: int
    note_id: str

    def __post_init__(self) -> None:
        if self.sequence_id < 1:
            raise ValueError("research state change sequence must be positive")
        if not self.note_id.strip():
            raise ValueError("research state change note ID cannot be empty")


@dataclass(frozen=True, slots=True)
class ResearchProjectionRecord:
    """Complete note state needed to rebuild the disposable query projection."""

    note_id: str
    body: str
    anchor: EvidenceAnchor
    tag_ids: tuple[str, ...]
    collection_ids: tuple[str, ...]
    updated_at: str

    def __post_init__(self) -> None:
        if not self.note_id.strip() or not self.body.strip():
            raise ValueError("projected note identity and body cannot be empty")
        if tuple(sorted(set(self.tag_ids))) != self.tag_ids:
            raise ValueError("projected tag IDs must be sorted and deduplicated")
        if tuple(sorted(set(self.collection_ids))) != self.collection_ids:
            raise ValueError("projected collection IDs must be sorted and deduplicated")
        if not self.updated_at.strip():
            raise ValueError("projected note updated_at cannot be empty")


@dataclass(frozen=True, slots=True)
class ResearchProjectionSnapshot:
    sequence_id: int
    records: tuple[ResearchProjectionRecord, ...]

    def __post_init__(self) -> None:
        if self.sequence_id < 0:
            raise ValueError("research snapshot sequence cannot be negative")


@runtime_checkable
class ResearchStateStore(Protocol):
    """Authoritative durable store for user-authored research knowledge."""

    def create_note(
        self,
        anchor: EvidenceAnchor,
        body: str,
        *,
        tags: tuple[str, ...] = (),
        collections: tuple[str, ...] = (),
        note_id: str | None = None,
    ) -> ResearchNote: ...

    def update_note(self, note_id: str, body: str) -> ResearchNote: ...

    def delete_note(self, note_id: str) -> None: ...

    def note(self, note_id: str) -> ResearchNote | None: ...

    def notes(
        self, *, document_id: str | None = None, limit: int = 1_000
    ) -> tuple[ResearchNote, ...]: ...

    def notes_by_ids(self, note_ids: tuple[str, ...]) -> tuple[ResearchNote, ...]: ...

    def set_note_tags(self, note_id: str, names: tuple[str, ...]) -> ResearchNote: ...

    def set_note_collections(
        self, note_id: str, names: tuple[str, ...]
    ) -> ResearchNote: ...

    def tags(self) -> tuple[ResearchTag, ...]: ...

    def collections(self) -> tuple[ResearchCollection, ...]: ...

    def resolve_tag_ids(self, names: tuple[str, ...]) -> tuple[str, ...] | None: ...

    def resolve_collection_ids(
        self, names: tuple[str, ...]
    ) -> tuple[str, ...] | None: ...

    def current_sequence(self) -> int: ...

    def oldest_change_sequence(self) -> int | None: ...

    def changes_after(
        self, sequence_id: int, *, limit: int
    ) -> tuple[ResearchStateChange, ...]: ...

    def projection_records(
        self, note_ids: tuple[str, ...]
    ) -> tuple[ResearchProjectionRecord, ...]: ...

    def projection_snapshot(self) -> ResearchProjectionSnapshot: ...

    def compact_changes(self, through_sequence: int, *, retain: int) -> None: ...
