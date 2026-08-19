from typing import Any, cast

from echoflow.desktop.bridge import DesktopServices, handle_request
from echoflow.library.evidence import EvidenceAnchor
from echoflow.library.index import SearchQuery
from echoflow.library.research_state import ResearchCollection, ResearchNote, ResearchTag
from echoflow.library.research_workspace import ResearchNoteView
from echoflow.library.retrieval import RetrievalMode
from echoflow.library.workspace_metadata import SavedSearch, SavedSearchIntent


class _WorkspaceService:
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


class _UnusedLocationService:
    pass


def _services() -> DesktopServices:
    return DesktopServices(
        locations=cast(Any, _UnusedLocationService()),
        workspace=cast(Any, _WorkspaceService()),
    )


def _request(params=None):
    return {
        "protocol_version": 1,
        "request_id": "research-1",
        "method": "workspace.research.overview",
        "params": {} if params is None else params,
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
