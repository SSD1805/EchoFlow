"""CLI presentation for unified transcript and research-workspace discovery."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, cast

import typer
from rich.console import Console
from rich.table import Table

from echoflow.app.app_container import AppContainer
from echoflow.core.errors import EchoFlowError
from echoflow.library.research_workspace import (
    ResearchNoteView,
    WorkspaceDiscoveryResponse,
    WorkspaceSearchPassage,
)
from echoflow.library.retrieval import RetrievalMode
from echoflow.media.time_coordinates import format_elapsed_timestamp

ContainerFactory = Callable[[typer.Context], AppContainer]


def _root_context(context: typer.Context) -> typer.Context:
    return cast("typer.Context", context.find_root())


def _handle_error(exc: Exception) -> None:
    if isinstance(exc, EchoFlowError):
        typer.echo(exc.public_message, err=True)
        raise typer.Exit(code=exc.exit_code) from None
    if isinstance(exc, (ValueError, ModuleNotFoundError)):
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(
        f"EchoFlow library discovery failed internally ({type(exc).__name__})",
        err=True,
    )
    raise typer.Exit(code=3) from None


def _transcript_dict(result: WorkspaceSearchPassage) -> dict[str, object]:
    located = result.located
    passage = located.passage
    evidence = located.evidence
    return {
        "document_id": passage.document_id,
        "source_sha256": passage.source_sha256,
        "canonical_sha256": passage.canonical_sha256,
        "canonical_path": passage.canonical_path,
        "source_path": passage.source_path,
        "segment_ids": list(passage.segment_ids),
        "start_seconds": passage.start_seconds,
        "end_seconds": passage.end_seconds,
        "start_timestamp": format_elapsed_timestamp(passage.start_seconds),
        "end_timestamp": format_elapsed_timestamp(passage.end_seconds),
        "seek_seconds": evidence.seek_seconds,
        "seek_timestamp": format_elapsed_timestamp(evidence.seek_seconds),
        "text": passage.text,
        "languages": list(passage.languages),
        "speaker_refs": list(passage.speaker_refs),
        "speaker_display_labels": {
            item.speaker_ref: item.display_label
            for item in located.speakers
            if item.display_label is not None
        },
        "lexical_rank": passage.lexical_rank,
        "semantic_rank": passage.semantic_rank,
        "fused_rank": passage.fused_rank,
        "research_state": {
            "note_ids": list(result.research.note_ids),
            "note_count": result.research.note_count,
            "tags": list(result.research.tags),
            "collections": list(result.research.collections),
        },
    }


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
            "segment_ids": list(anchor.segment_ids),
            "start_seconds": anchor.start_seconds,
            "end_seconds": anchor.end_seconds,
            "start_timestamp": format_elapsed_timestamp(anchor.start_seconds),
            "end_timestamp": format_elapsed_timestamp(anchor.end_seconds),
        },
    }


def _response_dict(response: WorkspaceDiscoveryResponse) -> dict[str, object]:
    retrieval = response.transcripts.navigation.retrieval
    return {
        "query": response.query,
        "total_count": response.total_count,
        "groups": {
            "transcripts": {
                "count": len(response.transcripts.results),
                "retrieval_mode": retrieval.mode.value,
                "results": [
                    _transcript_dict(item) for item in response.transcripts.results
                ],
            },
            "notes": {
                "count": len(response.notes),
                "results": [_note_dict(item) for item in response.notes],
            },
            "tags": {
                "count": len(response.tags),
                "results": [
                    {"tag_id": item.tag_id, "name": item.name}
                    for item in response.tags
                ],
            },
            "collections": {
                "count": len(response.collections),
                "results": [
                    {"collection_id": item.collection_id, "name": item.name}
                    for item in response.collections
                ],
            },
        },
    }


def _research_summary(result: WorkspaceSearchPassage) -> str:
    details: list[str] = []
    if result.research.note_count:
        suffix = "note" if result.research.note_count == 1 else "notes"
        details.append(f"{result.research.note_count} {suffix}")
    if result.research.tags:
        details.append("# " + ", ".join(result.research.tags))
    if result.research.collections:
        details.append("in " + ", ".join(result.research.collections))
    return "\n".join(details) or "—"


def _passage_text(result: WorkspaceSearchPassage) -> str:
    context = result.located.evidence.context_segments
    if not context:
        return result.located.passage.text
    return "\n".join(
        ("› " if segment.is_result_segment else "  ") + segment.text
        for segment in context
    )


def _render_transcripts(
    results: tuple[WorkspaceSearchPassage, ...], console: Console
) -> None:
    table = Table(title=f"Transcript evidence ({len(results)})")
    table.add_column("Evidence", min_width=20)
    table.add_column("Research", min_width=10)
    table.add_column("Passage")
    for result in results:
        located = result.located
        passage = located.passage
        recording = (
            passage.document_id
            if passage.source_path is None
            else Path(passage.source_path).name
        )
        speakers = ", ".join(item.display_name for item in located.speakers) or "unknown"
        evidence = (
            f"{recording}\n"
            f"{format_elapsed_timestamp(located.evidence.seek_seconds)}\n"
            f"{speakers}"
        )
        table.add_row(evidence, _research_summary(result), _passage_text(result))
    console.print(table)


def _render_notes(notes: tuple[ResearchNoteView, ...], console: Console) -> None:
    table = Table(title=f"Your notes ({len(notes)})")
    table.add_column("Evidence", min_width=20)
    table.add_column("Labels", min_width=10)
    table.add_column("Your note")
    for view in notes:
        note = view.note
        anchor = note.anchor
        evidence = (
            f"{anchor.document_id}\n"
            f"{format_elapsed_timestamp(anchor.start_seconds)}\n"
            f"{'current' if view.current else 'older transcript generation'}"
        )
        labels: list[str] = []
        if view.tags:
            labels.append("# " + ", ".join(view.tags))
        if view.collections:
            labels.append("in " + ", ".join(view.collections))
        table.add_row(evidence, "\n".join(labels) or "—", note.body)
    console.print(table)


def _render_named_group(
    title: str,
    names: tuple[str, ...],
    console: Console,
) -> None:
    table = Table(title=f"{title} ({len(names)})")
    table.add_column(title[:-1] if title.endswith("s") else title)
    for name in names:
        table.add_row(name)
    console.print(table)


def _render_response(response: WorkspaceDiscoveryResponse) -> None:
    console = Console()
    console.print(
        f"EchoFlow library discovery for {response.query!r}: "
        f"{response.total_count} grouped result(s)"
    )
    _render_transcripts(response.transcripts.results, console)
    _render_notes(response.notes, console)
    _render_named_group("Tags", tuple(item.name for item in response.tags), console)
    _render_named_group(
        "Collections",
        tuple(item.name for item in response.collections),
        console,
    )


def _find_library(
    context: typer.Context,
    text: str,
    *,
    mode: RetrievalMode,
    limit: int,
    context_segments: int,
    json_output: bool,
    container_factory: ContainerFactory,
) -> None:
    try:
        response = (
            container_factory(_root_context(context))
            .research_workspace()
            .discover(
                text,
                mode=mode,
                limit=limit,
                context_segments=context_segments,
            )
        )
    except Exception as exc:
        _handle_error(exc)
        return
    if json_output:
        typer.echo(json.dumps(_response_dict(response), sort_keys=True))
        return
    _render_response(response)


def register_discovery_command(
    library_app: typer.Typer,
    container_factory: ContainerFactory,
) -> None:
    """Register the one-box grouped discovery surface on the library CLI."""

    @library_app.command("find")
    def find_library(
        context: typer.Context,
        text: str = typer.Argument(..., metavar="QUERY"),
        mode: Annotated[
            RetrievalMode,
            typer.Option(
                "--mode",
                help=(
                    "Choose lexical, semantic, or hybrid retrieval for transcript "
                    "evidence. Notes and labels remain deterministic local text lookup."
                ),
            ),
        ] = RetrievalMode.LEXICAL,
        limit: int = typer.Option(
            20,
            "--limit",
            min=1,
            max=100,
            help="Maximum results to return in each discovery group.",
        ),
        context_segments: int = typer.Option(
            0,
            "--context-segments",
            min=0,
            max=10,
            help="Canonical context segments around transcript evidence results.",
        ),
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        _find_library(
            context,
            text,
            mode=mode,
            limit=limit,
            context_segments=context_segments,
            json_output=json_output,
            container_factory=container_factory,
        )
