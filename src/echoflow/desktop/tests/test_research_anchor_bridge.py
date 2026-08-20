from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

import echoflow.desktop.bridge as desktop_bridge
import echoflow.desktop.research_anchor_bridge as anchor_bridge
from echoflow.desktop.bridge import DesktopServices, handle_request
from echoflow.library.evidence import (
    EvidenceAnchor,
    EvidenceContextSegment,
    EvidenceLocation,
)
from echoflow.library.research import LocatedCanonicalEvidence
from echoflow.library.research_anchor_review import (
    ResearchAnchorReview,
    ResearchAnchorStatus,
)
from echoflow.library.research_state import ResearchAnchorHistoryEntry, ResearchNote
from echoflow.library.research_workspace import ResearchNoteView


def _anchor(*, canonical_digit: str = "b") -> EvidenceAnchor:
    return EvidenceAnchor(
        document_id="job-1",
        source_sha256="a" * 64,
        canonical_sha256=canonical_digit * 64,
        canonical_path=f"/secret/{canonical_digit}.json",
        source_path="/secret/source.wav",
        segment_ids=("segment-1",),
        start_seconds=4.0,
        end_seconds=5.0,
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
                    segment_id="segment-1",
                    start_seconds=4.0,
                    end_seconds=5.0,
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


def _review() -> ResearchAnchorReview:
    old = _anchor()
    current = _anchor(canonical_digit="c")
    note = ResearchNote(
        note_id="note-1",
        body="Interpretation",
        anchor=old,
        tag_ids=(),
        collection_ids=(),
        created_at="2026-08-20T08:00:00+00:00",
        updated_at="2026-08-20T08:00:00+00:00",
    )
    return ResearchAnchorReview(
        note=ResearchNoteView(note=note, current=False, tags=(), collections=()),
        status=ResearchAnchorStatus.OLDER_VERIFIED,
        anchored=_located(old, "Stored evidence"),
        candidate=_located(current, "Current candidate"),
        history=(
            ResearchAnchorHistoryEntry(
                note_id="note-1",
                revision=1,
                anchor=_anchor(canonical_digit="1"),
                replaced_at="2026-08-19T08:00:00+00:00",
            ),
        ),
    )


def _services() -> DesktopServices:
    return DesktopServices(
        locations=cast(Any, SimpleNamespace()),
        workspace=cast(Any, SimpleNamespace()),
        processing=cast(Any, object()),
    )


def _request(method: str, params: dict[str, object]) -> dict[str, object]:
    return {
        "protocol_version": 1,
        "request_id": "anchor-1",
        "method": method,
        "params": params,
    }


def test_anchor_methods_are_explicitly_allowlisted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def dispatch(method: str, params: dict[str, object], workspace: object) -> object:
        calls.append((method, params))
        return {"accepted": True}

    monkeypatch.setattr(desktop_bridge, "dispatch_research_anchor", dispatch)

    review = handle_request(
        _request("workspace.research.note.anchor.review", {"note_id": "note-1"}),
        _services(),
    )
    reanchor = handle_request(
        _request(
            "workspace.research.note.anchor.reanchor",
            {
                "note_id": "note-1",
                "expected_updated_at": "2026-08-20T08:00:00+00:00",
                "expected_candidate_sha256": "c" * 64,
            },
        ),
        _services(),
    )

    assert review["ok"] is True
    assert reanchor["ok"] is True
    assert [item[0] for item in calls] == [
        "workspace.research.note.anchor.review",
        "workspace.research.note.anchor.reanchor",
    ]


def test_anchor_review_serializer_never_exposes_authoritative_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = Mock()
    service.review.return_value = _review()
    monkeypatch.setattr(
        anchor_bridge.ResearchAnchorReviewService,
        "for_workspace",
        classmethod(lambda cls, workspace: service),
    )

    result = anchor_bridge.dispatch_research_anchor(
        "workspace.research.note.anchor.review",
        {"note_id": "note-1", "context_segments": 1},
        cast(Any, SimpleNamespace()),
    )

    assert result["status"] == "older_verified"
    assert result["anchored"]["text"] == "Stored evidence"  # type: ignore[index]
    assert result["candidate"]["text"] == "Current candidate"  # type: ignore[index]
    assert result["history"][0]["canonical_sha256"] == "1" * 64  # type: ignore[index]
    assert "/secret" not in str(result)
    assert "canonical_path" not in str(result)
    assert "source_path" not in str(result)
    assert "source_sha256" not in str(result)


def test_anchor_bridge_rejects_extra_or_malformed_confirmation_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        anchor_bridge.ResearchAnchorReviewService,
        "for_workspace",
        classmethod(lambda cls, workspace: Mock()),
    )

    with pytest.raises(ValidationError):
        anchor_bridge.dispatch_research_anchor(
            "workspace.research.note.anchor.review",
            {"note_id": "note-1", "sql": "SELECT * FROM notes"},
            cast(Any, SimpleNamespace()),
        )
    with pytest.raises(ValidationError):
        anchor_bridge.dispatch_research_anchor(
            "workspace.research.note.anchor.reanchor",
            {
                "note_id": "note-1",
                "expected_updated_at": "v1",
                "expected_candidate_sha256": "not-a-sha",
            },
            cast(Any, SimpleNamespace()),
        )
