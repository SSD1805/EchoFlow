import json
from unittest.mock import Mock

import typer
from typer.testing import CliRunner

from echoflow.cli_library import register_library_commands
from echoflow.library.errors import ResearchStateError
from echoflow.library.evidence import EvidenceAnchor
from echoflow.library.research_projection import ResearchProjectionStatus
from echoflow.library.research_projector import ResearchProjectionSyncReport
from echoflow.library.research_state import ResearchNote
from echoflow.library.research_workspace import ResearchNoteView, ResearchQueryFilters


def _note_view(*, current: bool = True) -> ResearchNoteView:
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
        current=current,
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


def test_notes_list_human_view_forwards_filters_and_marks_stale_evidence() -> None:
    workspace = Mock()
    workspace.notes.return_value = (_note_view(current=False),)
    app = _app(workspace)

    result = CliRunner().invoke(
        app,
        [
            "library",
            "notes",
            "--transcript",
            "job-1",
            "--text",
            "survey",
            "--tag",
            "methodology",
            "--collection",
            "Chapter 3",
            "--limit",
            "5",
        ],
    )

    assert result.exit_code == 0
    workspace.notes.assert_called_once_with(
        document_id="job-1",
        filters=ResearchQueryFilters(
            tags=("methodology",),
            collections=("Chapter 3",),
            note_text="survey",
        ),
        limit=5,
    )
    assert "note-1" in result.stdout
    assert "older transcript generation" in result.stdout
    assert "methodology" in result.stdout
    assert "Chapter 3" in result.stdout


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


def test_notes_add_human_view_preserves_optional_time_anchor() -> None:
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
            "--start-seconds",
            "42.25",
            "--end-seconds",
            "44.75",
        ],
    )

    assert result.exit_code == 0
    workspace.add_note.assert_called_once_with(
        "job-1",
        ("segment-000042",),
        "Check this against the 2024 survey.",
        tags=(),
        collections=(),
        start_seconds=42.25,
        end_seconds=44.75,
    )
    assert result.stdout.strip() == "Saved note-1."


def test_notes_show_reports_missing_note_without_rendering_fake_content() -> None:
    workspace = Mock()
    workspace.note.return_value = None
    app = _app(workspace)

    result = CliRunner().invoke(app, ["library", "notes", "show", "missing"])

    assert result.exit_code == 2
    assert "Research note does not exist" in result.output
    assert "note-1" not in result.output


def test_notes_show_json_reads_authoritative_note_view() -> None:
    workspace = Mock()
    workspace.note.return_value = _note_view(current=False)
    app = _app(workspace)

    result = CliRunner().invoke(
        app, ["library", "notes", "show", "note-1", "--json"]
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["note_id"] == "note-1"
    assert payload["body"] == "Check this against the 2024 survey."
    assert payload["current"] is False
    workspace.note.assert_called_once_with("note-1")


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
    assert edited.stdout.strip() == "Updated note-1."
    assert tagged.stdout.strip() == "Updated tags for note-1."
    assert collected.stdout.strip() == "Updated collections for note-1."
    assert deleted.stdout.strip() == "Deleted note-1 from durable user state."
    workspace.update_note.assert_called_once_with("note-1", "Replacement")
    workspace.set_note_tags.assert_called_once_with("note-1", ("housing",))
    workspace.set_note_collections.assert_called_once_with("note-1", ("Chapter 4",))
    workspace.delete_note.assert_called_once_with("note-1")


def test_note_mutation_json_outputs_return_authoritative_view() -> None:
    workspace = Mock()
    workspace.update_note.return_value = _note_view()
    workspace.set_note_tags.return_value = _note_view()
    workspace.set_note_collections.return_value = _note_view()
    app = _app(workspace)
    runner = CliRunner()

    results = (
        runner.invoke(
            app,
            [
                "library",
                "notes",
                "edit",
                "note-1",
                "--body",
                "Replacement",
                "--json",
            ],
        ),
        runner.invoke(
            app,
            [
                "library",
                "notes",
                "set-tags",
                "note-1",
                "--tag",
                "housing",
                "--json",
            ],
        ),
        runner.invoke(
            app,
            [
                "library",
                "notes",
                "set-collections",
                "note-1",
                "--collection",
                "Chapter 4",
                "--json",
            ],
        ),
    )

    assert all(result.exit_code == 0 for result in results)
    assert [json.loads(result.stdout)["note_id"] for result in results] == [
        "note-1",
        "note-1",
        "note-1",
    ]


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


def test_research_human_status_sync_and_rebuild_explain_projection_state() -> None:
    workspace = Mock()
    workspace.projection_status.return_value = ResearchProjectionStatus(12, 12)
    workspace.sync_projection.return_value = ResearchProjectionSyncReport(
        before_sequence=10,
        after_sequence=12,
        authoritative_sequence=12,
        batches=2,
        rebuilt=False,
    )
    workspace.rebuild_projection.return_value = ResearchProjectionSyncReport(
        before_sequence=0,
        after_sequence=12,
        authoritative_sequence=12,
        batches=1,
        rebuilt=True,
    )
    app = _app(workspace)
    runner = CliRunner()

    status = runner.invoke(app, ["library", "research"])
    sync = runner.invoke(app, ["library", "research", "sync"])
    rebuild = runner.invoke(app, ["library", "research", "rebuild"])

    assert status.exit_code == sync.exit_code == rebuild.exit_code == 0
    assert "Research projection current: SQLite 12, DuckDB 12." in status.stdout
    assert "current through sequence 12 (2 batch(es))" in sync.stdout
    assert "Rebuilt research projection through sequence 12." in rebuild.stdout


def test_research_rebuild_json_reports_rebuild_receipt() -> None:
    workspace = Mock()
    workspace.rebuild_projection.return_value = ResearchProjectionSyncReport(
        before_sequence=7,
        after_sequence=12,
        authoritative_sequence=12,
        batches=1,
        rebuilt=True,
    )
    app = _app(workspace)

    result = CliRunner().invoke(
        app, ["library", "research", "rebuild", "--json"]
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "after_sequence": 12,
        "authoritative_sequence": 12,
        "batches": 1,
        "before_sequence": 7,
        "current": True,
        "rebuilt": True,
    }


def test_research_cli_preserves_public_errors_and_masks_internal_failures() -> None:
    runner = CliRunner()

    public_workspace = Mock()
    public_workspace.notes.side_effect = ResearchStateError("Research state is unavailable")
    public_result = runner.invoke(_app(public_workspace), ["library", "notes"])

    value_workspace = Mock()
    value_workspace.notes.side_effect = ValueError("invalid research filter")
    value_result = runner.invoke(_app(value_workspace), ["library", "notes"])

    internal_workspace = Mock()
    internal_workspace.notes.side_effect = RuntimeError("sensitive implementation detail")
    internal_result = runner.invoke(_app(internal_workspace), ["library", "notes"])

    assert public_result.exit_code == 2
    assert "Research state is unavailable" in public_result.output
    assert value_result.exit_code == 2
    assert "invalid research filter" in value_result.output
    assert internal_result.exit_code == 3
    assert "failed internally (RuntimeError)" in internal_result.output
    assert "sensitive implementation detail" not in internal_result.output
