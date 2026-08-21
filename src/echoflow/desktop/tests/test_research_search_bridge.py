from unittest.mock import Mock

import pytest

from echoflow.desktop.bridge import DesktopServices, handle_request
from echoflow.library.evidence import EvidenceContextSegment, EvidenceLocation
from echoflow.library.index import SearchOperator, SearchQuery, SearchSort
from echoflow.library.research import LocatedSearchPassage, ResearchSearchResponse
from echoflow.library.research_workspace import (
    ResearchEvidenceView,
    ResearchQueryFilters,
    WorkspaceSearchPassage,
    WorkspaceSearchResponse,
)
from echoflow.library.retrieval import RetrievalMode, SearchPassage, SearchResponse
from echoflow.library.workspace_metadata import SavedSearch, SavedSearchIntent


def _params() -> dict[str, object]:
    return {
        "query_text": "governance reform",
        "phrase": False,
        "operator": "all",
        "speaker_refs": ["speaker-1"],
        "languages": ["en"],
        "document_ids": ["interview-42"],
        "sort": "timeline",
        "limit": 25,
        "retrieval_mode": "lexical",
        "context_segments": 2,
        "tags": ["governance"],
        "collections": ["Oral histories"],
        "note_text": "follow up",
        "with_notes": True,
    }


def _workspace_response() -> WorkspaceSearchResponse:
    query = SearchQuery(
        "governance reform",
        operator=SearchOperator.ALL,
        speaker_refs=("speaker-1",),
        languages=("en",),
        document_ids=("interview-42",),
        sort=SearchSort.TIMELINE,
        limit=25,
    )
    passage = SearchPassage(
        document_id="interview-42",
        source_sha256="a" * 64,
        canonical_sha256="b" * 64,
        canonical_path="/private/canonical/interview-42.json",
        source_path="/private/recordings/interview-42.wav",
        chunk_id=None,
        segment_ids=("segment-1",),
        matched_segment_ids=("segment-1",),
        start_seconds=12.0,
        end_seconds=14.0,
        text="Governance reform evidence",
        languages=("en",),
        speaker_refs=("speaker-1",),
        lexical_rank=1,
        semantic_rank=None,
        fused_rank=None,
    )
    context = EvidenceContextSegment(
        segment_id="segment-1",
        start_seconds=12.0,
        end_seconds=14.0,
        text="Governance reform evidence",
        speaker_refs=("speaker-1",),
        words=(),
        is_result_segment=True,
        lexical_match=True,
    )
    evidence = EvidenceLocation(
        document_id="interview-42",
        source_sha256="a" * 64,
        canonical_sha256="b" * 64,
        canonical_path="/private/canonical/interview-42.json",
        source_path="/private/recordings/interview-42.wav",
        result_segment_ids=("segment-1",),
        start_seconds=12.0,
        end_seconds=14.0,
        seek_seconds=12.0,
        result_speaker_refs=("speaker-1",),
        matched_words=(),
        context_segments=(context,),
    )
    located = LocatedSearchPassage(passage=passage, evidence=evidence, speakers=())
    item = WorkspaceSearchPassage(
        located=located,
        research=ResearchEvidenceView(
            note_ids=("note-1",),
            tags=("governance",),
            collections=("Oral histories",),
        ),
    )
    retrieval = SearchResponse(
        query=query,
        mode=RetrievalMode.LEXICAL,
        lexical_backend_id="duckdb-bm25-v1",
        semantic_backend_id=None,
        semantic_profile=None,
        fusion_profile=None,
        results=(passage,),
    )
    navigation = ResearchSearchResponse(retrieval=retrieval, results=(located,))
    return WorkspaceSearchResponse(
        navigation=navigation,
        filters=ResearchQueryFilters(
            tags=("governance",),
            collections=("Oral histories",),
            note_text="follow up",
            with_notes=True,
        ),
        results=(item,),
    )


def _saved_search() -> SavedSearch:
    return SavedSearch(
        saved_search_id="search-1",
        name="Governance",
        description="Questions to revisit",
        intent=SavedSearchIntent(
            query=SearchQuery(
                "governance reform",
                operator=SearchOperator.ALL,
                speaker_refs=("speaker-1",),
                languages=("en",),
                document_ids=("interview-42",),
                sort=SearchSort.TIMELINE,
                limit=25,
            ),
            mode=RetrievalMode.LEXICAL,
            context_segments=2,
            tags=("governance",),
            collections=("Oral histories",),
            note_text="follow up",
            with_notes=True,
        ),
        created_at="2026-08-20T12:00:00+00:00",
        updated_at="2026-08-20T12:01:00+00:00",
    )


def _services() -> tuple[DesktopServices, Mock]:
    workspace = Mock()
    workspace.search.return_value = _workspace_response()
    workspace.saved_searches.return_value = ()
    workspace.logger = None
    return (
        DesktopServices(locations=Mock(), workspace=workspace, processing=Mock()),
        workspace,
    )


def _request(method: str, params: dict[str, object]) -> dict[str, object]:
    return {
        "protocol_version": 1,
        "request_id": "request-1",
        "method": method,
        "params": params,
    }


def test_typed_search_round_trips_intent_without_exposing_private_paths() -> None:
    services, workspace = _services()

    response = handle_request(
        _request("workspace.research.search.execute", {"intent": _params()}),
        services,
    )

    assert response["ok"] is True
    result = response["result"]
    assert isinstance(result, dict)
    intent = result["intent"]
    assert isinstance(intent, dict)
    assert intent["operator"] == "all"
    assert intent["speaker_refs"] == ["speaker-1"]
    assert intent["languages"] == ["en"]
    assert intent["document_ids"] == ["interview-42"]
    assert intent["tags"] == ["governance"]
    assert intent["collections"] == ["Oral histories"]
    assert intent["note_text"] == "follow up"
    assert intent["with_notes"] is True
    rendered = repr(result)
    assert "/private/canonical" not in rendered
    assert "/private/recordings" not in rendered
    assert "canonical_path" not in rendered
    assert "source_path" not in rendered

    call = workspace.search.call_args
    query = call.args[0]
    assert query.operator is SearchOperator.ALL
    assert query.sort is SearchSort.TIMELINE
    assert query.speaker_refs == ("speaker-1",)
    assert query.languages == ("en",)
    assert query.document_ids == ("interview-42",)
    assert call.kwargs["mode"] is RetrievalMode.LEXICAL
    assert call.kwargs["context_segments"] == 2
    assert call.kwargs["filters"].tags == ("governance",)


def test_typed_search_rejects_extra_fields_before_workspace_execution() -> None:
    services, workspace = _services()
    intent = _params()
    intent["sql"] = "select * from notes"

    response = handle_request(
        _request("workspace.research.search.execute", {"intent": intent}),
        services,
    )

    assert response["ok"] is False
    assert response["error"] == {
        "code": "invalid_request",
        "message": "The desktop request was invalid or incompatible",
    }
    workspace.search.assert_not_called()


def test_saved_search_list_and_inspection_return_full_typed_intent() -> None:
    services, workspace = _services()
    saved = _saved_search()
    workspace.saved_searches.return_value = (saved,)
    workspace.saved_search.return_value = saved

    listed = handle_request(
        _request("workspace.research.search.saved.list", {"limit": 25}),
        services,
    )
    inspected = handle_request(
        _request(
            "workspace.research.search.saved.inspect",
            {"saved_search_id": "search-1"},
        ),
        services,
    )

    assert listed["ok"] is True
    assert workspace.saved_searches.call_args.kwargs["limit"] == 25
    list_result = listed["result"]
    assert isinstance(list_result, list)
    assert list_result[0]["saved_search_id"] == "search-1"
    assert list_result[0]["intent"]["tags"] == ["governance"]

    assert inspected["ok"] is True
    result = inspected["result"]
    assert isinstance(result, dict)
    intent = result["intent"]
    assert isinstance(intent, dict)
    assert intent["operator"] == "all"
    assert intent["retrieval_mode"] == "lexical"
    assert intent["context_segments"] == 2
    assert intent["tags"] == ["governance"]
    assert intent["with_notes"] is True


def test_saved_search_replace_is_version_bound_and_carries_full_intent() -> None:
    services, workspace = _services()
    current = SavedSearch(
        saved_search_id="search-1",
        name="Old name",
        description=None,
        intent=SavedSearchIntent(query=SearchQuery("old query")),
        created_at="2026-08-20T12:00:00+00:00",
        updated_at="2026-08-20T12:01:00+00:00",
    )
    updated = _saved_search()
    workspace.saved_search.return_value = current
    workspace.metadata = Mock()
    workspace.metadata.update_saved_search.return_value = updated

    response = handle_request(
        _request(
            "workspace.research.search.saved.replace",
            {
                "saved_search_id": "search-1",
                "expected_updated_at": current.updated_at,
                "name": "Governance",
                "description": "Questions to revisit",
                "intent": _params(),
            },
        ),
        services,
    )

    assert response["ok"] is True
    call = workspace.metadata.update_saved_search.call_args
    assert call.args[0] == "search-1"
    assert call.kwargs["expected_updated_at"] == current.updated_at
    persisted = call.kwargs["intent"]
    assert persisted.query.text == "governance reform"
    assert persisted.query.operator is SearchOperator.ALL
    assert persisted.query.document_ids == ("interview-42",)
    assert persisted.tags == ("governance",)
    assert persisted.collections == ("Oral histories",)
    assert persisted.note_text == "follow up"
    assert persisted.with_notes


def test_saved_search_run_replays_current_authority_and_never_serializes_paths() -> None:
    services, workspace = _services()
    saved = _saved_search()
    workspace.saved_search.return_value = saved
    workspace.run_saved_search.return_value = _workspace_response()

    response = handle_request(
        _request(
            "workspace.research.search.saved.run",
            {"saved_search_id": saved.saved_search_id},
        ),
        services,
    )

    assert response["ok"] is True
    workspace.run_saved_search.assert_called_once_with(saved.saved_search_id)
    result = response["result"]
    assert isinstance(result, dict)
    assert result["intent"]["query_text"] == "governance reform"
    assert result["evidence"][0]["canonical_sha256"] == "b" * 64
    assert result["evidence"][0]["text"] == "Governance reform evidence"
    rendered = repr(result)
    assert "/private/canonical" not in rendered
    assert "/private/recordings" not in rendered
    assert "canonical_path" not in rendered
    assert "source_path" not in rendered


def test_saved_search_delete_passes_optimistic_version() -> None:
    services, workspace = _services()
    saved = _saved_search()

    response = handle_request(
        _request(
            "workspace.research.search.saved.delete",
            {
                "saved_search_id": saved.saved_search_id,
                "expected_updated_at": saved.updated_at,
            },
        ),
        services,
    )

    assert response["ok"] is True
    workspace.delete_saved_search.assert_called_once_with(
        saved.saved_search_id,
        expected_updated_at=saved.updated_at,
    )
    assert response["result"] == {
        "saved_search_id": saved.saved_search_id,
        "deleted": True,
    }


@pytest.mark.parametrize(
    "method",
    [
        "workspace.research.search.execute",
        "workspace.research.search.saved.list",
        "workspace.research.search.saved.create",
        "workspace.research.search.saved.inspect",
        "workspace.research.search.saved.replace",
        "workspace.research.search.saved.run",
        "workspace.research.search.saved.delete",
    ],
)
def test_typed_search_methods_are_explicitly_allowlisted(method: str) -> None:
    services, _ = _services()
    params: dict[str, object]
    if method == "workspace.research.search.execute":
        params = {"intent": _params()}
    elif method == "workspace.research.search.saved.list":
        params = {"limit": 20}
    elif method == "workspace.research.search.saved.create":
        params = {"name": "Governance", "description": None, "intent": _params()}
    elif method in {
        "workspace.research.search.saved.inspect",
        "workspace.research.search.saved.run",
    }:
        services.workspace.saved_search.return_value = None
        params = {"saved_search_id": "search-1"}
    elif method == "workspace.research.search.saved.delete":
        params = {
            "saved_search_id": "search-1",
            "expected_updated_at": "v1",
        }
    else:
        services.workspace.saved_search.return_value = None
        params = {
            "saved_search_id": "search-1",
            "expected_updated_at": "v1",
            "name": "Governance",
            "description": None,
            "intent": _params(),
        }

    response = handle_request(_request(method, params), services)

    assert response["error"] != {
        "code": "invalid_request",
        "message": "The desktop request was invalid or incompatible",
    }
