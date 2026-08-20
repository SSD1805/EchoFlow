from types import SimpleNamespace
from typing import Any, cast

from echoflow.desktop.bridge import DesktopServices, handle_request
from echoflow.library.evidence import EvidenceAnchor
from echoflow.library.index import SearchQuery
from echoflow.library.research_state import (
    ResearchCollection,
    ResearchNote,
    ResearchTag,
)
from echoflow.library.research_workspace import ResearchNoteView
from echoflow.library.retrieval import RetrievalMode
from echoflow.library.workspace_metadata import SavedSearch, SavedSearchIntent


class _WorkspaceService:
    def __init__(self, *, canonical_sha256: str = "a" * 64) -> None:
        self.transcript_library = SimpleNamespace(
            documents=lambda: (
                SimpleNamespace(
                    document_id="interview-42",
                    canonical_sha256=canonical_sha256,
                ),
            )
        )
        self.last_add_note: dict[str, object] | None = None

    def notes(self, *, limit=1_000):
        assert limit == 200
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
            body="Follow up on governance.",
            anchor=anchor,
            tag_ids=("tag-3",),
            collection_ids=("collection-2",),
            created_at="2026-08-19T19:20:00+00:00",
            updated_at="2026-08-19T19:25:00+00:00",
        )
        return (
            ResearchNoteView(
                note=note,
                current=True,
                tags=("program",),
                collections=("Oral histories",),
            ),
        )

    def tags(self):
        return (ResearchTag(tag_id="tag-3", name="program"),)

    def collections(self):
        return (
            ResearchCollection(collection_id="collection-2", name="Oral histories"),
        )

    def saved_searches(self, *, limit=1_000):
        assert limit == 200
        return (
            SavedSearch(
                saved_search_id="search-9",
                name="Governance follow-up",
                description="Questions to revisit",
                intent=SavedSearchIntent(
                    query=SearchQuery("governance"),
                    mode=RetrievalMode.LEXICAL,
                    context_segments=1,
                ),
                created_at="2026-08-19T19:30:00+00:00",
                updated_at="2026-08-19T19:31:00+00:00",
            ),
        )

    def add_note(
        self,
        document_id,
        segment_ids,
        body,
        *,
        start_seconds=None,
        end_seconds=None,
    ):
        self.last_add_note = {
            "document_id": document_id,
            "segment_ids": segment_ids,
            "body": body,
            "start_seconds": start_seconds,
            "end_seconds": end_seconds,
        }
        anchor = EvidenceAnchor(
            document_id=document_id,
            source_sha256="b" * 64,
            canonical_sha256="a" * 64,
            canonical_path="/sensitive/canonical.json",
            source_path="/sensitive/interview.wav",
            segment_ids=segment_ids,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
        )
        note = ResearchNote(
            note_id="note-created",
            body=body,
            anchor=anchor,
            tag_ids=(),
            collection_ids=(),
            created_at="2026-08-19T21:44:00+00:00",
            updated_at="2026-08-19T21:44:00+00:00",
        )
        return ResearchNoteView(note=note, current=True, tags=(), collections=())


class _UnusedLocationService:
    pass


def _services(workspace: _WorkspaceService | None = None) -> DesktopServices:
    return DesktopServices(
        locations=cast(Any, _UnusedLocationService()),
        workspace=cast(Any, workspace or _WorkspaceService()),
    )


def _request(params=None):
    return {
        "protocol_version": 1,
        "request_id": "research-1",
        "method": "workspace.research.overview",
        "params": {} if params is None else params,
    }


def _create_request(**overrides):
    params = {
        "document_id": "interview-42",
        "canonical_sha256": "a" * 64,
        "segment_ids": ["segment-17"],
        "body": "Compare this passage with the follow-up interview.",
        "start_seconds": 862.1,
        "end_seconds": 870.4,
    }
    params.update(overrides)
    return {
        "protocol_version": 1,
        "request_id": "research-note-1",
        "method": "workspace.research.note.create",
        "params": params,
    }


def test_research_overview_returns_authoritative_human_state_without_paths():
    response = handle_request(_request(), _services())

    assert response["ok"] is True
    result = response["result"]
    assert result["notes"] == [
        {
            "note_id": "note-7",
            "body": "Follow up on governance.",
            "document_id": "interview-42",
            "canonical_sha256": "a" * 64,
            "segment_ids": ["segment-17"],
            "start_seconds": 862.1,
            "end_seconds": 870.4,
            "current": True,
            "tags": ["program"],
            "collections": ["Oral histories"],
            "created_at": "2026-08-19T19:20:00+00:00",
            "updated_at": "2026-08-19T19:25:00+00:00",
        }
    ]
    assert result["tags"] == [{"tag_id": "tag-3", "name": "program"}]
    assert result["collections"] == [
        {"collection_id": "collection-2", "name": "Oral histories"}
    ]
    assert result["saved_searches"] == [
        {
            "saved_search_id": "search-9",
            "name": "Governance follow-up",
            "description": "Questions to revisit",
            "query_text": "governance",
            "retrieval_mode": "lexical",
            "created_at": "2026-08-19T19:30:00+00:00",
            "updated_at": "2026-08-19T19:31:00+00:00",
        }
    ]
    assert "/sensitive" not in str(result)
    assert "canonical_path" not in str(result)
    assert "source_path" not in str(result)


def test_research_overview_rejects_unexpected_params():
    response = handle_request(_request({"sql": "SELECT * FROM notes"}), _services())

    assert response["ok"] is False
    assert response["error"]["code"] == "invalid_request"


def test_research_note_create_binds_mutation_to_verified_generation_without_paths():
    workspace = _WorkspaceService()

    response = handle_request(_create_request(), _services(workspace))

    assert response["ok"] is True
    assert workspace.last_add_note == {
        "document_id": "interview-42",
        "segment_ids": ("segment-17",),
        "body": "Compare this passage with the follow-up interview.",
        "start_seconds": 862.1,
        "end_seconds": 870.4,
    }
    result = response["result"]
    assert result["note_id"] == "note-created"
    assert result["canonical_sha256"] == "a" * 64
    assert result["segment_ids"] == ["segment-17"]
    assert "/sensitive" not in str(result)
    assert "canonical_path" not in str(result)
    assert "source_path" not in str(result)


def test_research_note_create_refuses_stale_generation_before_mutation():
    workspace = _WorkspaceService(canonical_sha256="c" * 64)

    response = handle_request(_create_request(), _services(workspace))

    assert response["ok"] is False
    assert "changed before the note could be saved" in response["error"]["message"]
    assert workspace.last_add_note is None


def test_research_note_create_rejects_unexpected_params():
    response = handle_request(
        _create_request(sql="SELECT * FROM notes"),
        _services(),
    )

    assert response["ok"] is False
    assert response["error"]["code"] == "invalid_request"
