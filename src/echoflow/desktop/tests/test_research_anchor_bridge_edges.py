from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

import echoflow.desktop.research_anchor_bridge as anchor_bridge


def _install_service(monkeypatch: pytest.MonkeyPatch, service: Mock) -> None:
    monkeypatch.setattr(
        anchor_bridge.ResearchAnchorReviewService,
        "for_workspace",
        classmethod(lambda cls, workspace: service),
    )


def test_reanchor_bridge_serializes_authoritative_updated_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = Mock()
    service.reanchor_to_reviewed_current.return_value = SimpleNamespace(
        note=SimpleNamespace(
            note_id="note-1",
            updated_at="2026-08-20T09:00:00+00:00",
            anchor=SimpleNamespace(canonical_sha256="c" * 64),
        ),
        current=True,
    )
    _install_service(monkeypatch, service)

    result = anchor_bridge.dispatch_research_anchor(
        "workspace.research.note.anchor.reanchor",
        {
            "note_id": "note-1",
            "expected_updated_at": "2026-08-20T08:00:00+00:00",
            "expected_candidate_sha256": "c" * 64,
        },
        cast(Any, SimpleNamespace()),
    )

    assert result == {
        "note_id": "note-1",
        "updated_at": "2026-08-20T09:00:00+00:00",
        "canonical_sha256": "c" * 64,
        "current": True,
    }
    service.reanchor_to_reviewed_current.assert_called_once_with(
        "note-1",
        expected_updated_at="2026-08-20T08:00:00+00:00",
        expected_candidate_sha256="c" * 64,
    )


def test_anchor_bridge_validates_blank_identity_before_service_construction() -> None:
    with pytest.raises(ValidationError):
        anchor_bridge.dispatch_research_anchor(
            "workspace.research.note.anchor.review",
            {"note_id": "   "},
            cast(Any, SimpleNamespace()),
        )

    with pytest.raises(ValidationError):
        anchor_bridge.dispatch_research_anchor(
            "workspace.research.note.anchor.reanchor",
            {
                "note_id": "note-1",
                "expected_updated_at": "   ",
                "expected_candidate_sha256": "c" * 64,
            },
            cast(Any, SimpleNamespace()),
        )


def test_anchor_bridge_handles_empty_evidence_and_rejects_unknown_method() -> None:
    assert anchor_bridge._serialize_evidence(None) is None

    with pytest.raises(ValueError, match="Unsupported research anchor desktop method"):
        anchor_bridge.dispatch_research_anchor(
            "workspace.research.note.anchor.unknown",
            {},
            cast(Any, SimpleNamespace()),
        )
