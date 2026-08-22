import json
from types import SimpleNamespace
from unittest.mock import Mock

import typer
from typer.testing import CliRunner

from scholion.cli_library import register_library_commands
from scholion.library.errors import ResearchStateError
from scholion.library.index import SearchOperator, SearchQuery, SearchSort
from scholion.library.research_workspace import ResearchQueryFilters
from scholion.library.retrieval import RetrievalMode
from scholion.library.workspace_metadata import (
    NavigationItem,
    SavedSearch,
    SavedSearchIntent,
    WorkspaceNavigation,
)


def _saved_search() -> SavedSearch:
    return SavedSearch(
        saved_search_id="search-housing",
        name="Housing chapter",
        description="Interview evidence for the housing chapter",
        intent=SavedSearchIntent(
            query=SearchQuery(
                "rent burden",
                phrase=True,
                operator=SearchOperator.ALL,
                speaker_refs=("speaker-02",),
                languages=("en",),
                document_ids=("job-1",),
                sort=SearchSort.TIMELINE,
                limit=17,
            ),
            mode=RetrievalMode.HYBRID,
            context_segments=2,
            tags=("housing",),
            collections=("Chapter 3",),
            note_text="methodology",
            with_notes=True,
        ),
        created_at="2026-08-19T01:00:00+00:00",
        updated_at="2026-08-19T02:00:00+00:00",
    )


def _navigation() -> WorkspaceNavigation:
    housing = NavigationItem(
        object_id="tag-housing",
        name="housing",
        usage_count=3,
        last_used_at="2026-08-19T02:00:00+00:00",
    )
    chapter = NavigationItem(
        object_id="collection-chapter-3",
        name="Chapter 3",
        usage_count=2,
        last_used_at="2026-08-19T01:30:00+00:00",
    )
    return WorkspaceNavigation(
        frequent_tags=(housing,),
        recent_tags=(housing,),
        frequent_collections=(chapter,),
        recent_collections=(chapter,),
    )


def _app(workspace: Mock) -> typer.Typer:
    app = typer.Typer()
    container = Mock()
    container.research_workspace.return_value = workspace
    register_library_commands(app, lambda context: container)
    return app


def test_saved_search_save_compiles_cli_options_into_typed_workspace_intent() -> None:
    workspace = Mock()
    workspace.save_search.return_value = _saved_search()

    result = CliRunner().invoke(
        _app(workspace),
        [
            "library",
            "saved",
            "save",
            "Housing chapter",
            "rent burden",
            "--description",
            "Interview evidence for the housing chapter",
            "--phrase",
            "--all-terms",
            "--speaker",
            "speaker-02",
            "--language",
            "en",
            "--transcript",
            "job-1",
            "--tag",
            "housing",
            "--collection",
            "Chapter 3",
            "--note-text",
            "methodology",
            "--with-notes",
            "--sort",
            "timeline",
            "--mode",
            "hybrid",
            "--limit",
            "17",
            "--context-segments",
            "2",
            "--json",
        ],
    )

    assert result.exit_code == 0
    call = workspace.save_search.call_args
    assert call.args[0] == "Housing chapter"
    query = call.args[1]
    assert query == SearchQuery(
        "rent burden",
        phrase=True,
        operator=SearchOperator.ALL,
        speaker_refs=("speaker-02",),
        languages=("en",),
        document_ids=("job-1",),
        sort=SearchSort.TIMELINE,
        limit=17,
    )
    assert call.kwargs["filters"] == ResearchQueryFilters(
        tags=("housing",),
        collections=("Chapter 3",),
        note_text="methodology",
        with_notes=True,
    )
    assert call.kwargs["mode"] is RetrievalMode.HYBRID
    assert call.kwargs["context_segments"] == 2
    assert call.kwargs["description"] == "Interview evidence for the housing chapter"
    payload = json.loads(result.stdout)
    assert payload["saved_search_id"] == "search-housing"
    assert payload["intent"]["query"]["text"] == "rent burden"
    assert payload["intent"]["research_filter"]["tags"] == ["housing"]


def test_saved_search_list_and_show_expose_typed_intent() -> None:
    workspace = Mock()
    saved = _saved_search()
    workspace.saved_searches.return_value = (saved,)
    workspace.saved_search.return_value = saved
    app = _app(workspace)
    runner = CliRunner()

    listed = runner.invoke(app, ["library", "saved", "--limit", "5", "--json"])
    shown = runner.invoke(
        app,
        ["library", "saved", "show", "Housing chapter", "--json"],
    )

    assert listed.exit_code == shown.exit_code == 0
    workspace.saved_searches.assert_called_once_with(limit=5)
    workspace.saved_search.assert_called_once_with("Housing chapter")
    assert json.loads(listed.stdout)[0]["intent"]["retrieval_mode"] == "hybrid"
    assert json.loads(shown.stdout)["intent"]["context_segments"] == 2


def test_saved_search_run_resolves_name_then_replays_stable_id() -> None:
    workspace = Mock()
    saved = _saved_search()
    workspace.saved_search.return_value = saved
    workspace.run_saved_search.return_value = SimpleNamespace(results=())

    result = CliRunner().invoke(
        _app(workspace),
        ["library", "saved", "run", "Housing chapter", "--json"],
    )

    assert result.exit_code == 0
    workspace.saved_search.assert_called_once_with("Housing chapter")
    workspace.run_saved_search.assert_called_once_with("search-housing")
    payload = json.loads(result.stdout)
    assert payload["saved_search"]["name"] == "Housing chapter"
    assert payload["result_count"] == 0
    assert payload["results"] == []


def test_saved_search_delete_is_explicit_durable_state_mutation() -> None:
    workspace = Mock()
    workspace.saved_search.return_value = _saved_search()

    result = CliRunner().invoke(
        _app(workspace),
        ["library", "saved", "delete", "Housing chapter"],
    )

    assert result.exit_code == 0
    workspace.delete_saved_search.assert_called_once_with("search-housing")
    assert "durable user state" in result.stdout


def test_navigation_json_is_a_derived_view_with_counts_and_recency() -> None:
    workspace = Mock()
    workspace.workspace_navigation.return_value = _navigation()

    result = CliRunner().invoke(
        _app(workspace),
        ["library", "navigation", "--limit", "7", "--json"],
    )

    assert result.exit_code == 0
    workspace.workspace_navigation.assert_called_once_with(limit=7)
    payload = json.loads(result.stdout)
    assert payload["frequent_tags"] == [
        {
            "last_used_at": "2026-08-19T02:00:00+00:00",
            "name": "housing",
            "object_id": "tag-housing",
            "usage_count": 3,
        }
    ]
    assert payload["recent_collections"][0]["name"] == "Chapter 3"


def test_saved_search_cli_reports_missing_public_and_internal_failures_safely() -> None:
    runner = CliRunner()

    missing = Mock()
    missing.saved_search.return_value = None
    missing_result = runner.invoke(
        _app(missing),
        ["library", "saved", "show", "missing"],
    )

    public = Mock()
    public.saved_searches.side_effect = ResearchStateError(
        "Saved-search state unavailable"
    )
    public_result = runner.invoke(_app(public), ["library", "saved"])

    internal = Mock()
    internal.workspace_navigation.side_effect = RuntimeError("private path /secret")
    internal_result = runner.invoke(_app(internal), ["library", "navigation"])

    assert missing_result.exit_code == 2
    assert "Saved search does not exist" in missing_result.output
    assert public_result.exit_code == 2
    assert "Saved-search state unavailable" in public_result.output
    assert internal_result.exit_code == 3
    assert "failed internally (RuntimeError)" in internal_result.output
    assert "/secret" not in internal_result.output
