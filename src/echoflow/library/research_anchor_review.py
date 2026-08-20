"""Review stale research anchors and deliberately bind notes to reviewed current evidence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from echoflow.core.errors import EchoFlowError
from echoflow.library.errors import ResearchStateError, TranscriptProjectionError
from echoflow.library.evidence import EvidenceAnchor
from echoflow.library.index import IndexedDocument, IndexedSegment
from echoflow.library.projection import load_indexed_transcript
from echoflow.library.research import LocatedCanonicalEvidence
from echoflow.library.research_state import ResearchAnchorHistoryEntry, ResearchNote
from echoflow.library.research_workspace import ResearchNoteView, ResearchWorkspaceService
from echoflow.library.sqlite_research_anchor_state import SqliteResearchAnchorStateStore


class ResearchAnchorStatus(StrEnum):
    CURRENT_VERIFIED = "current_verified"
    OLDER_VERIFIED = "older_verified"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ResearchAnchorReview:
    """Evidence review result; a candidate is preview only until explicitly confirmed."""

    note: ResearchNoteView
    status: ResearchAnchorStatus
    anchored: LocatedCanonicalEvidence | None
    candidate: LocatedCanonicalEvidence | None
    history: tuple[ResearchAnchorHistoryEntry, ...]


class ResearchAnchorReviewService:
    """Compose current library evidence with durable anchor history without auto-rebinding."""

    def __init__(
        self,
        workspace: ResearchWorkspaceService,
        anchor_state: SqliteResearchAnchorStateStore,
    ) -> None:
        self.workspace = workspace
        self.anchor_state = anchor_state

    @classmethod
    def for_workspace(
        cls, workspace: ResearchWorkspaceService
    ) -> ResearchAnchorReviewService:
        database_path = getattr(workspace.state, "database_path", None)
        if not isinstance(database_path, Path):
            raise ResearchStateError(
                "Research anchor maintenance is unavailable for this research-state backend"
            )
        return cls(workspace, SqliteResearchAnchorStateStore(database_path))

    def review(
        self,
        note_id: str,
        *,
        context_segments: int = 1,
    ) -> ResearchAnchorReview:
        note = self.workspace.note(note_id)
        if note is None:
            raise ResearchStateError("Research note does not exist")

        anchored: LocatedCanonicalEvidence | None = None
        try:
            anchored = self.workspace.navigation.locate_anchor(
                note.note.anchor,
                context_segments=context_segments,
            )
        except EchoFlowError:
            anchored = None

        if note.current and anchored is not None:
            status = ResearchAnchorStatus.CURRENT_VERIFIED
            candidate = None
        else:
            status = (
                ResearchAnchorStatus.OLDER_VERIFIED
                if anchored is not None
                else ResearchAnchorStatus.UNAVAILABLE
            )
            candidate = self._candidate_evidence(
                note.note,
                context_segments=context_segments,
            )

        history = self.anchor_state.note_anchor_history(note.note.note_id)
        self._log_review(note, status=status, candidate=candidate)
        return ResearchAnchorReview(
            note=note,
            status=status,
            anchored=anchored,
            candidate=candidate,
            history=history,
        )

    def reanchor_to_reviewed_current(
        self,
        note_id: str,
        *,
        expected_updated_at: str,
        expected_candidate_sha256: str,
    ) -> ResearchNoteView:
        note = self.workspace.note(note_id)
        if note is None:
            raise ResearchStateError("Research note does not exist")
        if note.current:
            raise ResearchStateError("Research note already cites current evidence")

        candidate = self._candidate_anchor(note.note)
        if candidate is None:
            raise ResearchStateError(
                "No safe current-generation candidate is available for this note"
            )
        if candidate.canonical_sha256 != expected_candidate_sha256:
            raise ResearchStateError(
                "Current transcript changed since the candidate was reviewed; review again before re-anchoring"
            )

        self.anchor_state.reanchor_note(
            note.note.note_id,
            candidate,
            expected_updated_at=expected_updated_at,
        )
        updated = self.workspace.note(note.note.note_id)
        if updated is None:
            raise ResearchStateError("Re-anchored research note could not be read back")
        if self.workspace.logger is not None:
            self.workspace.logger.info(
                "research_note_reanchored",
                note_id=updated.note.note_id,
                document_id=updated.note.anchor.document_id,
                canonical_sha256=updated.note.anchor.canonical_sha256,
                prior_canonical_sha256=note.note.anchor.canonical_sha256,
                history_count=len(
                    self.anchor_state.note_anchor_history(updated.note.note_id)
                ),
            )
        return updated

    def _candidate_evidence(
        self,
        note: ResearchNote,
        *,
        context_segments: int,
    ) -> LocatedCanonicalEvidence | None:
        try:
            anchor = self._candidate_anchor(note)
            if anchor is None:
                return None
            return self.workspace.navigation.locate_anchor(
                anchor,
                context_segments=context_segments,
            )
        except (EchoFlowError, OSError, ValueError):
            return None

    def _candidate_anchor(self, note: ResearchNote) -> EvidenceAnchor | None:
        document = self._current_document(note.anchor.document_id)
        if document is None or document.canonical_sha256 is None:
            return None
        if document.canonical_sha256 == note.anchor.canonical_sha256:
            return None
        if document.source_sha256 != note.anchor.source_sha256:
            return None

        indexed = load_indexed_transcript(
            Path(document.canonical_path),
            source_path=(
                None if document.source_path is None else Path(document.source_path)
            ),
            file_manager=self.workspace.transcript_library.file_manager,
        )
        if (
            indexed.document_id != document.document_id
            or indexed.source_sha256 != document.source_sha256
            or indexed.canonical_sha256 != document.canonical_sha256
        ):
            raise TranscriptProjectionError(
                "Current transcript changed while preparing re-anchor review"
            )

        selected = self._segments_for_time(
            indexed.segments,
            start_seconds=note.anchor.start_seconds,
            end_seconds=note.anchor.end_seconds,
        )
        if not selected:
            return None
        candidate_start = max(note.anchor.start_seconds, selected[0].start_seconds)
        candidate_end = min(note.anchor.end_seconds, selected[-1].end_seconds)
        if candidate_end < candidate_start:
            return None
        return self.workspace.evidence_locator.resolve_anchor(
            document,
            tuple(segment.segment_id for segment in selected),
            start_seconds=candidate_start,
            end_seconds=candidate_end,
        )

    def _current_document(self, document_id: str) -> IndexedDocument | None:
        return next(
            (
                document
                for document in self.workspace.transcript_library.documents()
                if document.document_id == document_id
            ),
            None,
        )

    @staticmethod
    def _segments_for_time(
        segments: tuple[IndexedSegment, ...],
        *,
        start_seconds: float,
        end_seconds: float,
    ) -> tuple[IndexedSegment, ...]:
        if end_seconds == start_seconds:
            return tuple(
                segment
                for segment in segments
                if segment.start_seconds <= start_seconds <= segment.end_seconds
            )
        return tuple(
            segment
            for segment in segments
            if segment.end_seconds > start_seconds
            and segment.start_seconds < end_seconds
        )

    def _log_review(
        self,
        note: ResearchNoteView,
        *,
        status: ResearchAnchorStatus,
        candidate: LocatedCanonicalEvidence | None,
    ) -> None:
        if self.workspace.logger is None:
            return
        self.workspace.logger.info(
            "research_note_anchor_reviewed",
            note_id=note.note.note_id,
            document_id=note.note.anchor.document_id,
            canonical_sha256=note.note.anchor.canonical_sha256,
            status=status.value,
            candidate_available=candidate is not None,
        )
