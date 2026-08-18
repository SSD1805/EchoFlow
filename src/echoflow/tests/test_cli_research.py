import json
from unittest.mock import Mock

import typer
from typer.testing import CliRunner

from echoflow.cli_library import register_library_commands
from echoflow.library.evidence import EvidenceAnchor
from echoflow.library.research_projection import ResearchProjectionStatus
from echoflow.library.research_projector import ResearchProjectionSyncReport
from echoflow.library.research_state import ResearchNote
from echoflow.library.research_workspace import ResearchNoteView


def _note_view() -> ResearchNoteView:
    anchor = EvidenceAnchor(
        document_id="job-1",
        source_sha256="0" * 64,
        canonical_sha256="1" * 64,
        canonical_path="/private/interview.json",
        source_path="/private/interview.wav",
        segment_ids=("segment-000042",),
        start_seconds=42.0,
        end_seconds=45.0,
    )
    note = ResearchNote(
        note_id="note-1",
        body="Check this against the 2024 survey.",
        anchor=anchor,
        tag_ids=("tag-1",),
        collection_ids=("collection-1",),
        created_at="2026-08-18T11:00:00+00:00",
        updated_at="2026-08-18T11:00:00+00:00",
    )
    return ResearchNoteView(
        note=note,
        current=True,
        tags=("methodology",),
        collections=("Chapter 3",),
    )


def _app(workspace: Mock) -> typer.Typer:
    app = typer.Typer()
    container = Mock()
    container.research_workspace.return_value = workspace
    register_library_commands(app, lambda context: container)
    return app


def test_notes_list_json_exposes_durable_anchor_and_user_labels() -> None:
    workspace = Mock()
    workspace.notes.return_value = (_note_view(),)
    app = _app(workspace)

    result = CliRunner().invoke(app, ["library", "notes", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload[0]["note_id"] == "note-1"
    assert payload[0]["tags"] == ["methodology"]
    assert payload[0]["collections"] == ["Chapter 3"]
    assert payload[0]["anchor"]["segment_ids"] == ["segment-000042"]
    assert payload[0]["anchor"]["start_timestamp"] == "00:00:42.000"


def test_notes_add_passes_evidence_and_labels_to_workspace() -> None:
    workspace = Mock()
    workspace.add_note.return_value = _note_view()
    app = _app(workspace)

    result = CliRunner().invoke(
        app,
        [
            "library",
            "notes",
            "add",
            "job-1",
            "segment-000042",
            "--body",
            "Check this against the 2024 survey.",
            "--tag",
            "methodology",
            "--collection",
            "Chapter 3",
            "--json",
        ],
    )

    assert result.exit_code == 0
    workspace.add_note.assert_called_once_with(
        "job-1",
        ("segment-000042",),
        "Check this against the 2024 survey.",
        tags=("methodology",),
        collections=("Chapter 3",),
        start_seconds=None,
        end_seconds=None,
    )
    assert json.loads(result.stdout)["current"] is True


def test_notes_edit_tag_collection_and_delete_are_explicit_mutations() -> None:
    workspace = Mock()
    workspace.update_note.return_value = _note_view()
    workspace.set_note_tags.return_value = _note_view()
    workspace.set_note_collections.return_value = _note_view()
    app = _app(workspace)
    runner = CliRunner()

    edited = runner.invoke(
        app,
        ["library", "notes", "edit", "note-1", "--body", "Replacement"],
    )
    tagged = runner.invoke(
        app,
        ["library", "notes", "set-tags", "note-1", "--tag", "housing"],
    )
    collected = runner.invoke(
        app,
        [
            "library",
            "notes",
            "set-collections",
            "note-1",
            "--collection",
            "Chapter 4",
        ],
    )
    deleted = runner.invoke(app, ["library", "notes", "delete", "note-1"])

    assert edited.exit_code == 0
    assert tagged.exit_code == 0
    assert collected.exit_code == 0
    assert deleted.exit_code == 0
    workspace.update_note.assert_called_once_with("note-1", "Replacement")
    workspace.set_note_tags.assert_called_once_with("note-1", ("housing",))
    workspace.set_note_collections.assert_called_once_with("note-1", ("Chapter 4",))
    workspace.delete_note.assert_called_once_with("note-1")


def test_research_status_and_sync_expose_projection_watermark() -> None:
    workspace = Mock()
    workspace.projection_status.return_value = ResearchProjectionStatus(12, 10)
    workspace.sync_projection.return_value = ResearchProjectionSyncReport(
        before_sequence=10,
        after_sequence=12,
        authoritative_sequence=12,
        batches=1,
        rebuilt=False,
    )
    app = _app(workspace)
    runner = CliRunner()

    status = runner.invoke(app, ["library", "research", "--json"])
    sync = runner.invoke(app, ["library", "research", "sync", "--json"])

    assert status.exit_code == 0
    assert json.loads(status.stdout) == {
        "authoritative_sequence": 12,
        "current": False,
        "projected_sequence": 10,
    }
    assert sync.exit_code == 0
    assert json.loads(sync.stdout)["current"] is True
    assert json.loads(sync.stdout)["after_sequence"] == 12
