from unittest.mock import Mock

import pytest
import typer
from typer.testing import CliRunner

from scholion.cli_library import register_library_commands
from scholion.library.errors import ResearchStateError


def _app(workspace: Mock) -> typer.Typer:
    app = typer.Typer()
    container = Mock()
    container.research_workspace.return_value = workspace
    register_library_commands(app, lambda context: container)
    return app


@pytest.mark.parametrize(
    ("method_name", "arguments", "forbidden_success"),
    (
        (
            "add_note",
            [
                "library",
                "notes",
                "add",
                "job-1",
                "segment-000042",
                "--body",
                "body",
            ],
            "Saved",
        ),
        (
            "note",
            ["library", "notes", "show", "note-1"],
            "Research Notes",
        ),
        (
            "update_note",
            ["library", "notes", "edit", "note-1", "--body", "replacement"],
            "Updated note-1",
        ),
        (
            "delete_note",
            ["library", "notes", "delete", "note-1"],
            "Deleted note-1",
        ),
        (
            "set_note_tags",
            ["library", "notes", "set-tags", "note-1", "--tag", "methodology"],
            "Updated tags",
        ),
        (
            "set_note_collections",
            [
                "library",
                "notes",
                "set-collections",
                "note-1",
                "--collection",
                "Chapter 3",
            ],
            "Updated collections",
        ),
        (
            "projection_status",
            ["library", "research"],
            "Research projection current",
        ),
        (
            "sync_projection",
            ["library", "research", "sync"],
            "current through sequence",
        ),
        (
            "rebuild_projection",
            ["library", "research", "rebuild"],
            "Rebuilt research projection",
        ),
    ),
)
def test_research_commands_surface_public_state_errors_without_false_success(
    method_name: str,
    arguments: list[str],
    forbidden_success: str,
) -> None:
    workspace = Mock()
    method = getattr(workspace, method_name)
    method.side_effect = ResearchStateError("Research state is unavailable")

    result = CliRunner().invoke(_app(workspace), arguments)

    assert result.exit_code == 2
    assert "Research state is unavailable" in result.output
    assert forbidden_success not in result.output
    method.assert_called_once()
