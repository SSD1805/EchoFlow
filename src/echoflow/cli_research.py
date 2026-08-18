"""CLI presentation for durable notes and research projection diagnostics."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Annotated, cast

import typer
from rich.console import Console
from rich.table import Table

from echoflow.app.app_container import AppContainer
from echoflow.core.errors import EchoFlowError
from echoflow.library.research_projector import ResearchProjectionSyncReport
from echoflow.library.research_workspace import ResearchNoteView, ResearchWorkspaceService
from echoflow.media.time_coordinates import format_elapsed_timestamp

ContainerFactory = Callable[[typer.Context], AppContainer]


def _root_context(context: typer.Context) -> typer.Context:
    return cast("typer.Context", context.find_root())


def _handle_error(exc: Exception) -> None:
    if isinstance(exc, EchoFlowError):
        typer.echo(exc.public_message, err=True)
        raise typer.Exit(code=exc.exit_code) from None
    if isinstance(exc, ValueError):
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(
        f"EchoFlow research workspace failed internally ({type(exc).__name__})",
        err=True,
    )
    raise typer.Exit(code=3) from None


def _note_dict(view: ResearchNoteView) -> dict[str, object]:
    note = view.note
    anchor = note.anchor
    return {
        "note_id": note.note_id,
        "body": note.body,
        "created_at": note.created_at,
        "updated_at": note.updated_at,
        "current": view.current,
        "tags": list(view.tags),
        "collections": list(view.collections),
        "anchor": {
            "document_id": anchor.document_id,
            "source_sha256": anchor.source_sha256,
            "canonical_sha256": anchor.canonical_sha256,
            "canonical_path": anchor.canonical_path,
            "source_path": anchor.source_path,
            "segment_ids": list(anchor.segment_ids),
            "start_seconds": anchor.start_seconds,
            "end_seconds": anchor.end_seconds,
            "start_timestamp": format_elapsed_timestamp(anchor.start_seconds),
            "end_timestamp": format_elapsed_timestamp(anchor.end_seconds),
        },
    }


def _render_notes(notes: tuple[ResearchNoteView, ...]) -> None:
    table = Table(title=f"EchoFlow research notes: {len(notes)}")
    table.add_column("Note")
    table.add_column("Evidence")
    table.add_column("State")
    table.add_column("Tags / collections")
    table.add_column("Your note")
    for view in notes:
        note = view.note
        anchor = note.anchor
        evidence = (
            f"{anchor.document_id}\n"
            f"{format_elapsed_timestamp(anchor.start_seconds)}–"
            f"{format_elapsed_timestamp(anchor.end_seconds)}"
        )
        labels = []
        if view.tags:
            labels.append("# " + ", ".join(view.tags))
        if view.collections:
            labels.append("in " + ", ".join(view.collections))
        table.add_row(
            note.note_id,
            evidence,
            "current" if view.current else "older transcript generation",
            "\n".join(labels) or "—",
            note.body,
        )
    Console().print(table)


def _sync_dict(report: ResearchProjectionSyncReport) -> dict[str, object]:
    return {
        "before_sequence": report.before_sequence,
        "after_sequence": report.after_sequence,
        "authoritative_sequence": report.authoritative_sequence,
        "batches": report.batches,
        "rebuilt": report.rebuilt,
        "current": report.current,
    }


def _workspace(
    context: typer.Context, factory: ContainerFactory
) -> ResearchWorkspaceService:
    return factory(_root_context(context)).research_workspace()


def register_research_commands(
    library_app: typer.Typer,
    container_factory: ContainerFactory,
) -> None:
    notes_app = typer.Typer(
        help="Write and revisit durable notes anchored to canonical evidence.",
        invoke_without_command=True,
        no_args_is_help=False,
    )

    @notes_app.callback()
    def notes_root(
        context: typer.Context,
        transcript: str | None = typer.Option(None, "--transcript"),
        limit: int = typer.Option(100, "--limit", min=1, max=10_000),
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        if context.invoked_subcommand is not None:
            return
        try:
            notes = _workspace(context, container_factory).notes(
                document_id=transcript,
                limit=limit,
            )
        except Exception as exc:
            _handle_error(exc)
            return
        if json_output:
            typer.echo(json.dumps([_note_dict(note) for note in notes], sort_keys=True))
            return
        _render_notes(notes)

    @notes_app.command("add")
    def add_note(
        context: typer.Context,
        transcript_id: str = typer.Argument(..., metavar="TRANSCRIPT_ID"),
        segment_ids: Annotated[
            list[str] | None,
            typer.Argument(metavar="SEGMENT_ID..."),
        ] = None,
        body: str = typer.Option(..., "--body", help="Your note text."),
        tags: Annotated[list[str] | None, typer.Option("--tag")] = None,
        collections: Annotated[list[str] | None, typer.Option("--collection")] = None,
        start_seconds: float | None = typer.Option(None, "--start-seconds", min=0),
        end_seconds: float | None = typer.Option(None, "--end-seconds", min=0),
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        try:
            view = _workspace(context, container_factory).add_note(
                transcript_id,
                tuple(segment_ids or ()),
                body,
                tags=tuple(tags or ()),
                collections=tuple(collections or ()),
                start_seconds=start_seconds,
                end_seconds=end_seconds,
            )
        except Exception as exc:
            _handle_error(exc)
            return
        if json_output:
            typer.echo(json.dumps(_note_dict(view), sort_keys=True))
            return
        typer.echo(f"Saved {view.note.note_id}.")

    @notes_app.command("show")
    def show_note(
        context: typer.Context,
        note_id: str = typer.Argument(..., metavar="NOTE_ID"),
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        try:
            view = _workspace(context, container_factory).note(note_id)
        except Exception as exc:
            _handle_error(exc)
            return
        if view is None:
            typer.echo("Research note does not exist", err=True)
            raise typer.Exit(code=2)
        if json_output:
            typer.echo(json.dumps(_note_dict(view), sort_keys=True))
            return
        _render_notes((view,))

    @notes_app.command("edit")
    def edit_note(
        context: typer.Context,
        note_id: str = typer.Argument(..., metavar="NOTE_ID"),
        body: str = typer.Option(..., "--body", help="Replacement note text."),
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        try:
            view = _workspace(context, container_factory).update_note(note_id, body)
        except Exception as exc:
            _handle_error(exc)
            return
        if json_output:
            typer.echo(json.dumps(_note_dict(view), sort_keys=True))
            return
        typer.echo(f"Updated {view.note.note_id}.")

    @notes_app.command("delete")
    def delete_note(
        context: typer.Context,
        note_id: str = typer.Argument(..., metavar="NOTE_ID"),
    ) -> None:
        try:
            _workspace(context, container_factory).delete_note(note_id)
        except Exception as exc:
            _handle_error(exc)
            return
        typer.echo(f"Deleted {note_id} from durable user state.")

    @notes_app.command("set-tags")
    def set_tags(
        context: typer.Context,
        note_id: str = typer.Argument(..., metavar="NOTE_ID"),
        tags: Annotated[list[str] | None, typer.Option("--tag")] = None,
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        try:
            view = _workspace(context, container_factory).set_note_tags(
                note_id, tuple(tags or ())
            )
        except Exception as exc:
            _handle_error(exc)
            return
        if json_output:
            typer.echo(json.dumps(_note_dict(view), sort_keys=True))
            return
        typer.echo(f"Updated tags for {note_id}.")

    @notes_app.command("set-collections")
    def set_collections(
        context: typer.Context,
        note_id: str = typer.Argument(..., metavar="NOTE_ID"),
        collections: Annotated[list[str] | None, typer.Option("--collection")] = None,
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        try:
            view = _workspace(context, container_factory).set_note_collections(
                note_id, tuple(collections or ())
            )
        except Exception as exc:
            _handle_error(exc)
            return
        if json_output:
            typer.echo(json.dumps(_note_dict(view), sort_keys=True))
            return
        typer.echo(f"Updated collections for {note_id}.")

    research_app = typer.Typer(
        help="Inspect or repair the rebuildable research query projection.",
        invoke_without_command=True,
        no_args_is_help=False,
    )

    @research_app.callback()
    def research_root(
        context: typer.Context,
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        if context.invoked_subcommand is not None:
            return
        try:
            status = _workspace(context, container_factory).projection_status()
        except Exception as exc:
            _handle_error(exc)
            return
        payload = {
            "authoritative_sequence": status.authoritative_sequence,
            "projected_sequence": status.projected_sequence,
            "current": status.current,
        }
        if json_output:
            typer.echo(json.dumps(payload, sort_keys=True))
            return
        state = "current" if status.current else "catch-up needed"
        typer.echo(
            f"Research projection {state}: SQLite {status.authoritative_sequence}, "
            f"DuckDB {status.projected_sequence}."
        )

    @research_app.command("sync")
    def sync_research(
        context: typer.Context,
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        try:
            report = _workspace(context, container_factory).sync_projection()
        except Exception as exc:
            _handle_error(exc)
            return
        if json_output:
            typer.echo(json.dumps(_sync_dict(report), sort_keys=True))
            return
        typer.echo(
            f"Research projection current through sequence {report.after_sequence} "
            f"({report.batches} batch(es))."
        )

    @research_app.command("rebuild")
    def rebuild_research(
        context: typer.Context,
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        try:
            report = _workspace(context, container_factory).rebuild_projection()
        except Exception as exc:
            _handle_error(exc)
            return
        if json_output:
            typer.echo(json.dumps(_sync_dict(report), sort_keys=True))
            return
        typer.echo(
            f"Rebuilt research projection through sequence {report.after_sequence}."
        )

    library_app.add_typer(notes_app, name="notes")
    library_app.add_typer(research_app, name="research")
