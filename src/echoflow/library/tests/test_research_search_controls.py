from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from echoflow.library.errors import ResearchStateError
from echoflow.library.index import SearchOperator, SearchQuery, SearchSort
from echoflow.library.research_search_controls import (
    ResearchSearchControlService,
    ResearchSearchIntent,
)
from echoflow.library.research_workspace import ResearchQueryFilters
from echoflow.library.retrieval import RetrievalMode
from echoflow.library.workspace_metadata import SavedSearch, SavedSearchIntent


def _query(*, text: str = "governance") -> SearchQuery:
    return SearchQuery(
        text,
        phrase=False,
        operator=SearchOperator.ALL,
        speaker_refs=("speaker-1",),
        languages=("en",),
        document_ids=("interview-42",),
        sort=SearchSort.TIMELINE,
        limit=25,
    )


def _intent() -> ResearchSearchIntent:
    return ResearchSearchIntent(
        query=_query(),
        filters=ResearchQueryFilters(
            tags=("governance",),
            collections=("Oral histories",),
            note_text="follow up",
            with_notes=True,
        ),
        mode=RetrievalMode.HYBRID,
        context_segments=2,
    )


def _saved(intent: SavedSearchIntent | None = None) -> SavedSearch:
    return SavedSearch(
        saved_search_id="search-1",
        name="Governance",
        description="Reusable question",
        intent=intent or _intent().to_saved_intent(),
        created_at="2026-08-20T12:00:00+00:00",
        updated_at="2026-08-20T12:01:00+00:00",
    )


def test_intent_rejects_runtime_evidence_scope_and_invalid_context() -> None:
    scoped = SearchQuery(
        "governance",
        evidence_scope=(("job-1", "a" * 64, "segment-1"),),
    )
    with pytest.raises(ValueError, match="derived evidence scope"):
        ResearchSearchIntent(query=scoped)
    with pytest.raises(ValueError, match="context_segments"):
        ResearchSearchIntent(query=_query(), context_segments=11)


def test_saved_intent_round_trip_preserves_every_user_authored_control() -> None:
    intent = _intent()

    restored = ResearchSearchIntent.from_saved_intent(intent.to_saved_intent())

    assert restored == intent
    assert restored.query.evidence_scope is None


def test_search_delegates_complete_intent_to_workspace_authority() -> None:
    workspace = Mock()
    expected = SimpleNamespace(results=())
    workspace.search.return_value = expected
    service = ResearchSearchControlService(workspace)
    intent = _intent()

    assert service.search(intent) is expected
    workspace.search.assert_called_once_with(
        intent.query,
        filters=intent.filters,
        mode=RetrievalMode.HYBRID,
        context_segments=2,
    )


def test_create_saved_search_delegates_typed_intent_without_flattening() -> None:
    workspace = Mock()
    saved = _saved()
    workspace.save_search.return_value = saved
    service = ResearchSearchControlService(workspace)
    intent = _intent()

    assert (
        service.create_saved_search(
            "Governance",
            intent,
            description="Reusable question",
            saved_search_id="search-1",
        )
        == saved
    )
    workspace.save_search.assert_called_once_with(
        "Governance",
        intent.query,
        filters=intent.filters,
        mode=RetrievalMode.HYBRID,
        context_segments=2,
        description="Reusable question",
        saved_search_id="search-1",
    )


def test_replace_saved_search_updates_display_and_intent_atomically() -> None:
    workspace = Mock()
    current = _saved()
    updated = _saved(_intent().to_saved_intent())
    workspace.saved_search.return_value = current
    workspace.metadata = Mock()
    workspace.metadata.update_saved_search.return_value = updated
    workspace.logger = Mock()
    service = ResearchSearchControlService(workspace)
    intent = _intent()

    result = service.replace_saved_search(
        "search-1",
        name="Governance updated",
        description=None,
        intent=intent,
        expected_updated_at=current.updated_at,
    )

    assert result is updated
    workspace.metadata.update_saved_search.assert_called_once_with(
        "search-1",
        name="Governance updated",
        description=None,
        intent=intent.to_saved_intent(),
        expected_updated_at=current.updated_at,
    )
    event = workspace.logger.info.call_args
    assert event.args == ("research_saved_search_updated",)
    assert event.kwargs["retrieval_mode"] == "hybrid"
    assert event.kwargs["speaker_filter_count"] == 1
    assert event.kwargs["language_filter_count"] == 1
    assert event.kwargs["document_filter_count"] == 1
    assert "governance" not in repr(event)
    assert "follow up" not in repr(event)


def test_replace_saved_search_fails_closed_without_authoritative_state() -> None:
    workspace = Mock()
    workspace.saved_search.return_value = None
    service = ResearchSearchControlService(workspace)

    with pytest.raises(ResearchStateError, match="does not exist"):
        service.replace_saved_search(
            "missing",
            name="Missing",
            description=None,
            intent=_intent(),
            expected_updated_at="v1",
        )

    workspace.saved_search.return_value = _saved()
    workspace.metadata = None
    with pytest.raises(ResearchStateError, match="not configured"):
        service.replace_saved_search(
            "search-1",
            name="Governance",
            description=None,
            intent=_intent(),
            expected_updated_at="v1",
        )
