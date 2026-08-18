"""Synchronize authoritative research state into its disposable query projection."""

from __future__ import annotations

from dataclasses import dataclass

from echoflow.library.errors import ResearchProjectionError
from echoflow.library.research_projection import (
    ResearchProjectionIndex,
    ResearchProjectionStatus,
)
from echoflow.library.research_state import ResearchStateStore

_DEFAULT_BATCH_SIZE = 500
_DEFAULT_RETAINED_CHANGES = 2_048
_MAX_SYNC_BATCHES = 1_000


@dataclass(frozen=True, slots=True)
class ResearchProjectionSyncReport:
    before_sequence: int
    after_sequence: int
    authoritative_sequence: int
    batches: int
    rebuilt: bool

    @property
    def current(self) -> bool:
        return self.after_sequence == self.authoritative_sequence


class ResearchStateProjector:
    """Idempotently replay note changes into the fast DuckDB projection."""

    def __init__(
        self,
        store: ResearchStateStore,
        projection: ResearchProjectionIndex,
        *,
        batch_size: int = _DEFAULT_BATCH_SIZE,
        retained_changes: int = _DEFAULT_RETAINED_CHANGES,
    ) -> None:
        if batch_size < 1 or batch_size > 10_000:
            raise ValueError("research projection batch_size must be between 1 and 10000")
        if retained_changes < 0:
            raise ValueError("retained_changes cannot be negative")
        self.store = store
        self.projection = projection
        self.batch_size = batch_size
        self.retained_changes = retained_changes

    def status(self) -> ResearchProjectionStatus:
        return ResearchProjectionStatus(
            authoritative_sequence=self.store.current_sequence(),
            projected_sequence=self.projection.projected_through_sequence(),
        )

    def sync(self) -> ResearchProjectionSyncReport:
        before = self.projection.projected_through_sequence()
        authoritative = self.store.current_sequence()
        if before > authoritative:
            raise ResearchProjectionError(
                "Research projection is ahead of authoritative user state"
            )
        if before == authoritative:
            return ResearchProjectionSyncReport(
                before_sequence=before,
                after_sequence=before,
                authoritative_sequence=authoritative,
                batches=0,
                rebuilt=False,
            )

        oldest = self.store.oldest_change_sequence()
        if oldest is None or before < oldest - 1:
            return self.rebuild(before_sequence=before)

        projected = before
        batches = 0
        while batches < _MAX_SYNC_BATCHES:
            changes = self.store.changes_after(projected, limit=self.batch_size)
            if not changes:
                authoritative = self.store.current_sequence()
                if projected == authoritative:
                    break
                return self.rebuild(before_sequence=before)
            note_ids = tuple(sorted({change.note_id for change in changes}))
            records = self.store.projection_records(note_ids)
            present_ids = {record.note_id for record in records}
            deleted = tuple(note_id for note_id in note_ids if note_id not in present_ids)
            through = changes[-1].sequence_id
            self.projection.apply(
                records,
                deleted_note_ids=deleted,
                through_sequence=through,
            )
            projected = through
            batches += 1
            authoritative = self.store.current_sequence()
            if projected == authoritative:
                break
        else:
            raise ResearchProjectionError(
                "Research projection did not converge within its bounded sync budget"
            )

        authoritative = self.store.current_sequence()
        if projected != authoritative:
            raise ResearchProjectionError(
                "Research projection stopped before authoritative state was reached"
            )
        self.store.compact_changes(
            projected,
            retain=self.retained_changes,
        )
        return ResearchProjectionSyncReport(
            before_sequence=before,
            after_sequence=projected,
            authoritative_sequence=authoritative,
            batches=batches,
            rebuilt=False,
        )

    def rebuild(self, *, before_sequence: int | None = None) -> ResearchProjectionSyncReport:
        before = (
            self.projection.projected_through_sequence()
            if before_sequence is None
            else before_sequence
        )
        snapshot = self.store.projection_snapshot()
        self.projection.rebuild(
            snapshot.records,
            through_sequence=snapshot.sequence_id,
        )
        self.store.compact_changes(
            snapshot.sequence_id,
            retain=self.retained_changes,
        )
        return ResearchProjectionSyncReport(
            before_sequence=before,
            after_sequence=snapshot.sequence_id,
            authoritative_sequence=snapshot.sequence_id,
            batches=1,
            rebuilt=True,
        )
