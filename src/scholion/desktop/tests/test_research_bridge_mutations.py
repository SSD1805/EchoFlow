from typing import Any, cast

from scholion.desktop.bridge import DesktopServices, handle_request
from scholion.library.evidence import EvidenceAnchor
from scholion.library.research_state import ResearchNote
from scholion.library.research_workspace import ResearchNoteView


class _Workspace:
    def __init__(self) -> None:
        self.last_replace: dict[str, object] | None = None
        self.last_delete: dict[str, object] | None = None

    @staticmethod
    def _view(*, body: str, updated_at: str) -> ResearchNoteView:
        anchor = EvidenceAnchor(
            document_id="interview-42",
            source_sha256="b" * 64,
            canonical_sha256="a" * 64,
            canonical_path="/sensitive/canonical.json",
            source_path="/sensitive/interview.wav",
            segment_ids=("segment-17",),
            start_seconds=862.1,
            end_seconds=870.4,
        )
        note = ResearchNote(
            note_id="note-7",
            body=body,
            anchor=anchor,
            tag_ids=("tag-1", "tag-2"),
            collection_ids=("collection-1",),
            created_at="2026-08-19T19:20:00+00:00",
            updated_at=updated_at,
        )
        return ResearchNoteView(
            note=note,
            current=True,
            tags=("follow-up", "program"),
            collections=("Oral histories",),
        )

    def replace_note(
        self,
        note_id,
        body,
        *,
        tags,
        collections,
        expected_updated_at=None,
    ):
        self.last_replace = {
            "note_id": note_id,
            "body": body,
            "tags": tags,
            "collections": collections,
            "expected_updated_at": expected_updated_at,
        }
        return self._view(body=body, updated_at="2026-08-19T22:01:00+00:00")

    def delete_note(self, note_id, *, expected_updated_at=None):
        self.last_delete = {
            "note_id": note_id,
            "expected_updated_at": expected_updated_at,
        }


class _UnusedLocationService:
    pass


def _services(workspace: _Workspace) -> DesktopServices:
    return DesktopServices(
        locations=cast(Any, _UnusedLocationService()),
        workspace=cast(Any, workspace),
        research_search=cast(Any, object()),
        processing=cast(Any, object()),
    )


def _request(method: str, params: dict[str, object]) -> dict[str, object]:
    return {
        "protocol_version": 1,
        "request_id": "mutation-1",
        "method": method,
        "params": params,
    }


def test_note_update_replaces_human_state_without_exposing_paths() -> None:
    workspace = _Workspace()
    response = handle_request(
        _request(
            "workspace.research.note.update",
            {
                "note_id": "note-7",
                "expected_updated_at": "2026-08-19T19:25:00+00:00",
                "body": "Compare this passage with the follow-up interview.",
                "tags": ["program", "follow-up"],
                "collections": ["Oral histories"],
            },
        ),
        _services(workspace),
    )

    assert response["ok"] is True
    assert workspace.last_replace == {
        "note_id": "note-7",
        "body": "Compare this passage with the follow-up interview.",
        "tags": ("follow-up", "program"),
        "collections": ("Oral histories",),
        "expected_updated_at": "2026-08-19T19:25:00+00:00",
    }
    result = response["result"]
    assert result["body"] == "Compare this passage with the follow-up interview."
    assert result["canonical_sha256"] == "a" * 64
    assert "/sensitive" not in str(result)
    assert "source_path" not in str(result)
    assert "canonical_path" not in str(result)


def test_note_delete_is_version_bound_and_returns_only_safe_identity() -> None:
    workspace = _Workspace()
    response = handle_request(
        _request(
            "workspace.research.note.delete",
            {
                "note_id": "note-7",
                "expected_updated_at": "2026-08-19T19:25:00+00:00",
            },
        ),
        _services(workspace),
    )

    assert response["ok"] is True
    assert workspace.last_delete == {
        "note_id": "note-7",
        "expected_updated_at": "2026-08-19T19:25:00+00:00",
    }
    assert response["result"] == {"note_id": "note-7", "deleted": True}


def test_note_mutations_reject_unexpected_sql_shaped_parameters() -> None:
    workspace = _Workspace()
    update = handle_request(
        _request(
            "workspace.research.note.update",
            {
                "note_id": "note-7",
                "expected_updated_at": "2026-08-19T19:25:00+00:00",
                "body": "Updated",
                "tags": [],
                "collections": [],
                "sql": "UPDATE notes SET body = 'oops'",
            },
        ),
        _services(workspace),
    )
    delete = handle_request(
        _request(
            "workspace.research.note.delete",
            {
                "note_id": "note-7",
                "expected_updated_at": "2026-08-19T19:25:00+00:00",
                "sql": "DELETE FROM notes",
            },
        ),
        _services(workspace),
    )

    assert update["ok"] is False
    assert update["error"]["code"] == "invalid_request"
    assert delete["ok"] is False
    assert delete["error"]["code"] == "invalid_request"
    assert workspace.last_replace is None
    assert workspace.last_delete is None
