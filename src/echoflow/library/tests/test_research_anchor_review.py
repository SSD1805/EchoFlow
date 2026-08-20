from unittest.mock import Mock

import pytest

from echoflow.library.errors import EvidenceNavigationError, ResearchStateError
from echoflow.library.evidence import EvidenceAnchor, EvidenceContextSegment, EvidenceLocation
from echoflow.library.index import IndexedDocument, IndexedSegment, IndexedTranscript
from echoflow.library.research import LocatedCanonicalEvidence
from echoflow.library.research_anchor_review import (
    ResearchAnchorReviewService,
    ResearchAnchorStatus,
)
from echoflow.library.research_state import ResearchAnchorStateStore, ResearchNote
from echoflow.library.research_workspace import ResearchNoteView


def _anchor(*, canonical_digit: str = "b", segment_id: str = "old-1") -> EvidenceAnchor:
    return EvidenceAnchor(
        document_id="job-1",
        source_sha256="a" * 64,
        canonical_sha256=canonical_digit * 64,
        canonical_path=f"/private/{canonical_digit}.json",
        source_path="/private/source.wav",
        segment_ids=(segment_id,),
        start_seconds=2.1,
        end_seconds=2.9,
    )


def _note_view(*, current: bool = False, canonical_digit: str = "b") -> ResearchNoteView:
    return ResearchNoteView(
        note=ResearchNote(
            note_id="note-1",
            body="Interpretation",
            anchor=_anchor(canonical_digit=canonical_digit),
            tag_ids=(),
            collection_ids=(),
            created_at="2026-08-20T08:00:00+00:00",
            updated_at="2026-08-20T08:00:00+00:00",
        ),
        current=current,
        tags=(),
        collections=(),
    )


def _document(*, source_digit: str = "a") -> IndexedDocument:
    return IndexedDocument(
        document_id="job-1",
        source_sha256=source_digit * 64,
        canonical_sha256="c" * 64,
        detected_language="en",
        canonical_path="/private/c.json",
        source_path="/private/source.wav",
        segment_count=2,
    )


def _indexed() -> IndexedTranscript:
    return IndexedTranscript(
        document_id="job-1",
        source_sha256="a" * 64,
        canonical_sha256="c" * 64,
        transcript_schema_version=1,
        detected_language="en",
        canonical_path="/private/c.json",
        source_path="/private/source.wav",
        source_size_bytes=100,
        source_modified_ns=1,
        canonical_size_bytes=100,
        canonical_modified_ns=1,
        segments=(
            IndexedSegment("current-1", 2.0, 2.5, "Current first half"),
            IndexedSegment("current-2", 2.5, 3.0, "Current second half"),
        ),
    )


def _located(anchor: EvidenceAnchor, text: str) -> LocatedCanonicalEvidence:
    return LocatedCanonicalEvidence(
        evidence=EvidenceLocation(
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
                    text=text,
                    speaker_refs=(),
                    words=(),
                    is_result_segment=True,
                    lexical_match=False,
                ),
            ),
        ),
        speakers=(),
    )


def _service(monkeypatch: pytest.MonkeyPatch) -> tuple[ResearchAnchorReviewService, Mock, Mock]:
    workspace = Mock()
    workspace.note.return_value = _note_view()
    workspace.transcript_library.documents.return_value = (_document(),)
    workspace.transcript_library.file_manager = Mock()
    candidate = EvidenceAnchor(
        document_id="job-1",
        source_sha256="a" * 64,
        canonical_sha256="c" * 64,
        canonical_path="/private/c.json",
        source_path="/private/source.wav",
        segment_ids=("current-1", "current-2"),
        start_seconds=2.1,
        end_seconds=2.9,
    )
    workspace.evidence_locator.resolve_anchor.return_value = candidate
    workspace.navigation.locate_anchor.side_effect = lambda anchor, **_: _located(
        anchor, "Old evidence" if anchor.canonical_sha256.startswith("b") else "Current evidence"
    )
    workspace.logger = Mock()
    anchor_state = Mock(spec=ResearchAnchorStateStore)
    anchor_state.note_anchor_history.return_value = ()
    monkeypatch.setattr(
        "echoflow.library.research_anchor_review.load_indexed_transcript",
        lambda *args, **kwargs: _indexed(),
    )
    return ResearchAnchorReviewService(workspace, anchor_state), workspace, anchor_state


def test_review_distinguishes_verified_older_evidence_and_previews_current_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, workspace, _ = _service(monkeypatch)

    review = service.review("note-1", context_segments=2)

    assert review.status is ResearchAnchorStatus.OLDER_VERIFIED
    assert review.anchored is not None
    assert review.anchored.evidence.canonical_sha256 == "b" * 64
    assert review.candidate is not None
    assert review.candidate.evidence.canonical_sha256 == "c" * 64
    workspace.evidence_locator.resolve_anchor.assert_called_once()
    assert workspace.navigation.locate_anchor.call_count == 2


def test_review_can_report_unavailable_stored_anchor_without_hiding_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, workspace, _ = _service(monkeypatch)

    def locate(anchor: EvidenceAnchor, **_: object) -> LocatedCanonicalEvidence:
        if anchor.canonical_sha256 == "b" * 64:
            raise EvidenceNavigationError("Stored generation missing")
        return _located(anchor, "Current evidence")

    workspace.navigation.locate_anchor.side_effect = locate

    review = service.review("note-1")

    assert review.status is ResearchAnchorStatus.UNAVAILABLE
    assert review.anchored is None
    assert review.candidate is not None


def test_review_current_verified_anchor_never_fabricates_reanchor_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, workspace, _ = _service(monkeypatch)
    current = _note_view(current=True, canonical_digit="c")
    workspace.note.return_value = current
    workspace.navigation.locate_anchor.side_effect = None
    workspace.navigation.locate_anchor.return_value = _located(current.note.anchor, "Current")

    review = service.review("note-1")

    assert review.status is ResearchAnchorStatus.CURRENT_VERIFIED
    assert review.candidate is None
    workspace.evidence_locator.resolve_anchor.assert_not_called()


def test_reanchor_binds_confirmation_to_candidate_sha_and_reloads_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, workspace, anchor_state = _service(monkeypatch)
    original = workspace.note.return_value
    current = _note_view(current=True, canonical_digit="c")

    def mutate(*_: object, **__: object) -> None:
        workspace.note.return_value = current

    anchor_state.reanchor_note.side_effect = mutate

    updated = service.reanchor_to_reviewed_current(
        "note-1",
        expected_updated_at=original.note.updated_at,
        expected_candidate_sha256="c" * 64,
    )

    assert updated == current
    anchor_state.reanchor_note.assert_called_once()
    call = anchor_state.reanchor_note.call_args
    assert call.args[0] == "note-1"
    assert call.args[1].canonical_sha256 == "c" * 64
    assert call.kwargs["expected_updated_at"] == original.note.updated_at


def test_reanchor_rejects_changed_candidate_and_current_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, workspace, anchor_state = _service(monkeypatch)

    with pytest.raises(ResearchStateError, match="changed since the candidate was reviewed"):
        service.reanchor_to_reviewed_current(
            "note-1",
            expected_updated_at="2026-08-20T08:00:00+00:00",
            expected_candidate_sha256="d" * 64,
        )
    anchor_state.reanchor_note.assert_not_called()

    workspace.note.return_value = _note_view(current=True, canonical_digit="c")
    with pytest.raises(ResearchStateError, match="already cites current"):
        service.reanchor_to_reviewed_current(
            "note-1",
            expected_updated_at="2026-08-20T08:00:00+00:00",
            expected_candidate_sha256="c" * 64,
        )


def test_candidate_requires_same_source_and_time_overlap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, workspace, _ = _service(monkeypatch)
    workspace.transcript_library.documents.return_value = (_document(source_digit="f"),)
    assert service._candidate_anchor(_note_view().note) is None

    segments = _indexed().segments
    assert [item.segment_id for item in service._segments_for_time(segments, start_seconds=2.1, end_seconds=2.9)] == [
        "current-1",
        "current-2",
    ]
    assert [item.segment_id for item in service._segments_for_time(segments, start_seconds=2.5, end_seconds=2.5)] == [
        "current-1",
        "current-2",
    ]
    assert service._segments_for_time(segments, start_seconds=4.0, end_seconds=5.0) == ()
