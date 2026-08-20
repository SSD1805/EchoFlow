from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

import pytest

from echoflow.library.errors import ResearchStateError, TranscriptProjectionError
from echoflow.library.evidence import (
    EvidenceAnchor,
    EvidenceContextSegment,
    EvidenceLocation,
)
from echoflow.library.index import IndexedDocument, IndexedSegment, IndexedTranscript
from echoflow.library.research_anchor_review import (
    ResearchAnchorReviewService,
    ResearchAnchorStatus,
)
from echoflow.library.research_state import ResearchAnchorStateStore, ResearchNote
from echoflow.library.research_workspace import ResearchNoteView


def _anchor(*, canonical_digit: str = "b") -> EvidenceAnchor:
    return EvidenceAnchor(
        document_id="job-1",
        source_sha256="a" * 64,
        canonical_sha256=canonical_digit * 64,
        canonical_path=f"/private/{canonical_digit}.json",
        source_path="/private/source.wav",
        segment_ids=("segment-1",),
        start_seconds=2.1,
        end_seconds=2.9,
    )


def _note_view(
    *, current: bool = False, canonical_digit: str = "b"
) -> ResearchNoteView:
    note = ResearchNote(
        note_id="note-1",
        body="Interpretation",
        anchor=_anchor(canonical_digit=canonical_digit),
        tag_ids=(),
        collection_ids=(),
        created_at="2026-08-20T08:00:00+00:00",
        updated_at="2026-08-20T08:00:00+00:00",
    )
    return ResearchNoteView(note=note, current=current, tags=(), collections=())


def _document() -> IndexedDocument:
    return IndexedDocument(
        document_id="job-1",
        source_sha256="a" * 64,
        canonical_sha256="c" * 64,
        detected_language="en",
        canonical_path="/private/c.json",
        source_path="/private/source.wav",
        segment_count=1,
    )


def _indexed(
    *,
    document_id: str = "job-1",
    canonical_digit: str = "c",
    segments: tuple[IndexedSegment, ...] | None = None,
) -> IndexedTranscript:
    return IndexedTranscript(
        document_id=document_id,
        source_sha256="a" * 64,
        canonical_sha256=canonical_digit * 64,
        transcript_schema_version=1,
        detected_language="en",
        canonical_path="/private/c.json",
        source_path="/private/source.wav",
        source_size_bytes=100,
        source_modified_ns=1,
        canonical_size_bytes=100,
        canonical_modified_ns=1,
        segments=(
            (IndexedSegment("current-1", 2.0, 3.0, "Current evidence"),)
            if segments is None
            else segments
        ),
    )


def _evidence(anchor: EvidenceAnchor) -> EvidenceLocation:
    return EvidenceLocation(
        document_id=anchor.document_id,
        source_sha256=anchor.source_sha256,
        canonical_sha256=anchor.canonical_sha256,
        canonical_path=anchor.canonical_path,
        source_path=anchor.source_path,
        result_segment_ids=anchor.segment_ids,
        start_seconds=anchor.start_seconds,
        end_seconds=anchor.end_seconds,
        seek_seconds=anchor.start_seconds,
        result_speaker_refs=(),
        matched_words=(),
        context_segments=(
            EvidenceContextSegment(
                segment_id=anchor.segment_ids[0],
                start_seconds=anchor.start_seconds,
                end_seconds=anchor.end_seconds,
                text="Verified evidence",
                speaker_refs=(),
                words=(),
                is_result_segment=True,
                lexical_match=False,
            ),
        ),
    )


def _service() -> tuple[ResearchAnchorReviewService, Mock, Mock]:
    workspace = Mock()
    workspace.note.return_value = _note_view()
    workspace.transcript_library.documents.return_value = (_document(),)
    workspace.transcript_library.file_manager = Mock()
    workspace.evidence_locator.locate_anchor.side_effect = lambda anchor, **_: _evidence(
        anchor
    )
    workspace.evidence_locator.resolve_anchor.return_value = EvidenceAnchor(
        document_id="job-1",
        source_sha256="a" * 64,
        canonical_sha256="c" * 64,
        canonical_path="/private/c.json",
        source_path="/private/source.wav",
        segment_ids=("current-1",),
        start_seconds=2.1,
        end_seconds=2.9,
    )
    workspace.logger = None
    anchor_state = Mock(spec=ResearchAnchorStateStore)
    anchor_state.note_anchor_history.return_value = ()
    return ResearchAnchorReviewService(workspace, anchor_state), workspace, anchor_state


def test_for_workspace_rejects_non_sqlite_research_state() -> None:
    workspace = SimpleNamespace(state=SimpleNamespace())

    with pytest.raises(ResearchStateError, match="maintenance is unavailable"):
        ResearchAnchorReviewService.for_workspace(cast(Any, workspace))


def test_review_and_reanchor_reject_a_note_that_no_longer_exists() -> None:
    service, workspace, anchor_state = _service()
    workspace.note.return_value = None

    with pytest.raises(ResearchStateError, match="does not exist"):
        service.review("note-missing")
    with pytest.raises(ResearchStateError, match="does not exist"):
        service.reanchor_to_reviewed_current(
            "note-missing",
            expected_updated_at="v1",
            expected_candidate_sha256="c" * 64,
        )

    anchor_state.reanchor_note.assert_not_called()


def test_review_keeps_older_anchor_when_no_current_document_exists() -> None:
    service, workspace, _ = _service()
    workspace.transcript_library.documents.return_value = ()

    review = service.review("note-1")

    assert review.status is ResearchAnchorStatus.OLDER_VERIFIED
    assert review.anchored is not None
    assert review.candidate is None
    workspace.evidence_locator.resolve_anchor.assert_not_called()


def test_reanchor_rejects_when_no_safe_candidate_exists() -> None:
    service, workspace, anchor_state = _service()
    workspace.transcript_library.documents.return_value = ()

    with pytest.raises(ResearchStateError, match="No safe current-generation candidate"):
        service.reanchor_to_reviewed_current(
            "note-1",
            expected_updated_at=_note_view().note.updated_at,
            expected_candidate_sha256="c" * 64,
        )

    anchor_state.reanchor_note.assert_not_called()


def test_reanchor_fails_closed_when_authoritative_write_cannot_be_read_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, workspace, anchor_state = _service()
    candidate = workspace.evidence_locator.resolve_anchor.return_value
    workspace.note.side_effect = [_note_view(), None]
    monkeypatch.setattr(service, "_candidate_anchor", lambda note: candidate)

    with pytest.raises(ResearchStateError, match="could not be read back"):
        service.reanchor_to_reviewed_current(
            "note-1",
            expected_updated_at=_note_view().note.updated_at,
            expected_candidate_sha256="c" * 64,
        )

    anchor_state.reanchor_note.assert_called_once()


def test_reanchor_succeeds_without_operational_logger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, workspace, anchor_state = _service()
    original = _note_view()
    current = _note_view(current=True, canonical_digit="c")
    candidate = workspace.evidence_locator.resolve_anchor.return_value
    workspace.note.side_effect = [original, current]
    workspace.logger = None
    monkeypatch.setattr(service, "_candidate_anchor", lambda note: candidate)

    assert (
        service.reanchor_to_reviewed_current(
            "note-1",
            expected_updated_at=original.note.updated_at,
            expected_candidate_sha256="c" * 64,
        )
        == current
    )
    anchor_state.note_anchor_history.assert_not_called()


def test_candidate_rejects_changed_projection_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _, _ = _service()
    monkeypatch.setattr(
        "echoflow.library.research_anchor_review.load_indexed_transcript",
        lambda *args, **kwargs: _indexed(document_id="job-2"),
    )

    with pytest.raises(TranscriptProjectionError, match="changed while preparing"):
        service._candidate_anchor(_note_view().note)


def test_candidate_returns_none_when_current_generation_has_no_time_overlap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, workspace, _ = _service()
    monkeypatch.setattr(
        "echoflow.library.research_anchor_review.load_indexed_transcript",
        lambda *args, **kwargs: _indexed(
            segments=(IndexedSegment("later", 10.0, 11.0, "Later evidence"),)
        ),
    )

    assert service._candidate_anchor(_note_view().note) is None
    workspace.evidence_locator.resolve_anchor.assert_not_called()


def test_candidate_preview_converts_projection_failure_to_no_safe_preview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _, _ = _service()

    def fail(_: ResearchNote) -> EvidenceAnchor | None:
        raise TranscriptProjectionError("changed")

    monkeypatch.setattr(service, "_candidate_anchor", fail)

    assert service._candidate_evidence(_note_view().note, context_segments=1) is None
