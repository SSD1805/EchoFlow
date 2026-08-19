from types import SimpleNamespace
from unittest.mock import Mock

import typer
from typer.testing import CliRunner

from echoflow.cli_library import register_library_commands
from echoflow.library.index import SearchQuery
from echoflow.library.workspace_metadata import (
    NavigationItem,
    SavedSearch,
    SavedSearchIntent,
    WorkspaceNavigation,
)


def _saved() -> SavedSearch:
    return SavedSearch(
        saved_search_id="search-1",
        name="Housing",
        description="Chapter evidence",
        intent=SavedSearchIntent(
            query=SearchQuery("rent burden"),
            tags=("housing",),
            collections=("Chapter 1",),
            note_text="methods",
            with_notes=True,
        ),
        created_at="2026-08-19T00:00:00+00:00",
        updated_at="2026-08-19T01:00:00+00:00",
    )


def _app(workspace: Mock) -> typer.Typer:
    app = typer.Typer()
    container = Mock()
    container.research_workspace.return_value = workspace
    register_library_commands(app, lambda context: container)
    return app


def test_saved_search_human_list_show_save_run_and_delete_paths() -> None:
    workspace = Mock()
    saved = _saved()
    workspace.saved_searches.return_value = (saved,)
    workspace.saved_search.return_value = saved
    workspace.save_search.return_value = saved
    workspace.run_saved_search.return_value = SimpleNamespace(results=())
    app = _app(workspace)
    runner = CliRunner()

    listed = runner.invoke(app, ["library", "saved"])
    shown = runner.invoke(app, ["library", "saved", "show", "Housing"])
    created = runner.invoke(
        app,
        ["library", "saved", "save", "Housing", "rent burden"],
    )
    run = runner.invoke(app, ["library", "saved", "run", "Housing"])
    deleted = runner.invoke(app, ["library", "saved", "delete", "Housing"])

    assert listed.exit_code == shown.exit_code == 0
    assert created.exit_code == run.exit_code == deleted.exit_code == 0
    assert "EchoFlow saved searches" in listed.output
    assert "housing" in listed.output
    assert "Chapter 1" in listed.output
    assert "with notes" in listed.output
    assert "Saved 'Housing' as search-1." in created.output
    assert "0 current evidence result(s)" in run.output
    assert "Deleted saved search 'Housing' from durable user state." in deleted.output


def test_saved_search_human_navigation_renders_every_group() -> None:
    item = NavigationItem(
        object_id="tag-1",
        name="housing",
        usage_count=3,
        last_used_at="2026-08-19T01:00:00+00:00",
    )
    collection = NavigationItem(
        object_id="collection-1",
        name="Chapter 1",
        usage_count=2,
        last_used_at="2026-08-19T00:30:00+00:00",
    )
    workspace = Mock()
    workspace.workspace_navigation.return_value = WorkspaceNavigation(
        frequent_tags=(item,),
        recent_tags=(item,),
        frequent_collections=(collection,),
        recent_collections=(collection,),
    )

    result = CliRunner().invoke(
        _app(workspace),
        ["library", "navigation"],
    )

    assert result.exit_code == 0
    assert "EchoFlow workspace navigation" in result.output
    assert "frequent tag" in result.output
    assert "recent tag" in result.output
    assert "frequent collection" in result.output
    assert "recent collection" in result.output


def test_saved_search_missing_run_and_delete_fail_without_mutation() -> None:
    workspace = Mock()
    workspace.saved_search.return_value = None
    app = _app(workspace)
    runner = CliRunner()

    run = runner.invoke(app, ["library", "saved", "run", "missing"])
    deleted = runner.invoke(app, ["library", "saved", "delete", "missing"])

    assert run.exit_code == deleted.exit_code == 2
    assert "Saved search does not exist" in run.output
    assert "Saved search does not exist" in deleted.output
    workspace.run_saved_search.assert_not_called()
    workspace.delete_saved_search.assert_not_called()
