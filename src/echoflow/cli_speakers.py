"""CLI for durable human display names over anonymous speaker evidence."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import cast

import typer
from rich.console import Console
from rich.table import Table

from echoflow.app.app_container import AppContainer
from echoflow.core.errors import EchoFlowError
from echoflow.library.speaker_label_service import SpeakerRosterEntry
from echoflow.library.speaker_presentation import (
    SpeakerPresentationService,
    SpeakerPresentationSpan,
)
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
        f"EchoFlow speaker labels failed internally ({type(exc).__name__})",
        err=True,
    )
    raise typer.Exit(code=3) from None


def _roster_dict(entry: SpeakerRosterEntry) -> dict[str, object]:
    return {
        "speaker_ref": entry.speaker_ref,
        "display_label": entry.display_label,
        "display_name": entry.display_name,
    }


def _span_dict(span: SpeakerPresentationSpan) -> dict[str, object]:
    return {
        **span.to_dict(),
        "start_timestamp": format_elapsed_timestamp(span.start_seconds),
        "end_timestamp": format_elapsed_timestamp(span.end_seconds),
    }


def _render_roster(
    document_id: str,
    roster: tuple[SpeakerRosterEntry, ...],
    console: Console,
) -> None:
    table = Table(title=f"EchoFlow speakers: {document_id}")
    table.add_column("Evidence ref")
    table.add_column("Your label")
    table.add_column("Shown as")
    for entry in roster:
        table.add_row(
            entry.speaker_ref,
            entry.display_label or "not named",
            entry.display_name,
        )
    console.print(table)


def _render_transcript(
    document_id: str,
    spans: tuple[SpeakerPresentationSpan, ...],
    console: Console,
) -> None:
    table = Table(title=f"EchoFlow speaker transcript: {document_id}")
    table.add_column("Time", min_width=12, no_wrap=True)
    table.add_column("Speaker evidence")
    table.add_column("State")
    table.add_column("Transcript")
    for span in spans:
        time_range = (
            f"{format_elapsed_timestamp(span.start_seconds)}\n"
            f"{format_elapsed_timestamp(span.end_seconds)}"
        )
        speakers = (
            " + ".join(speaker.display_name for speaker in span.speakers) or "unknown"
        )
        table.add_row(time_range, speakers, span.kind.value, span.text)
    console.print(table)


def _presentation_service(container: AppContainer) -> SpeakerPresentationService:
    return SpeakerPresentationService(
        index=container.transcript_index(),
        label_store=container.speaker_label_store(),
        file_manager=container.file_manager(),
    )


def _list_speakers(
    context: typer.Context,
    transcript_id: str,
    *,
    json_output: bool,
    container_factory: ContainerFactory,
) -> None:
    try:
        roster = (
            container_factory(_root_context(context))
            .speaker_labels()
            .roster(transcript_id)
        )
    except Exception as exc:
        _handle_error(exc)
        return
    if json_output:
        typer.echo(json.dumps([_roster_dict(item) for item in roster], sort_keys=True))
        return
    _render_roster(transcript_id, roster, Console())


def _show_speaker_transcript(
    context: typer.Context,
    transcript_id: str,
    *,
    json_output: bool,
    container_factory: ContainerFactory,
) -> None:
    try:
        container = container_factory(_root_context(context))
        spans = _presentation_service(container).spans(transcript_id)
    except Exception as exc:
        _handle_error(exc)
        return
    if json_output:
        typer.echo(json.dumps([_span_dict(item) for item in spans], sort_keys=True))
        return
    _render_transcript(transcript_id, spans, Console())


def _name_speaker(
    context: typer.Context,
    transcript_id: str,
    speaker_ref: str,
    label: str,
    *,
    json_output: bool,
    container_factory: ContainerFactory,
) -> None:
    try:
        service = container_factory(_root_context(context)).speaker_labels()
        binding = service.set_label(
            transcript_id,
            speaker_ref=speaker_ref,
            label=label,
        )
    except Exception as exc:
        _handle_error(exc)
        return
    if json_output:
        typer.echo(json.dumps(binding.to_dict(), sort_keys=True))
        return
    typer.echo(
        f"{binding.speaker_ref} will be shown as "
        f"{binding.label} ({binding.speaker_ref})."
    )


def _forget_speaker_name(
    context: typer.Context,
    transcript_id: str,
    speaker_ref: str,
    *,
    json_output: bool,
    container_factory: ContainerFactory,
) -> None:
    try:
        removed = (
            container_factory(_root_context(context))
            .speaker_labels()
            .remove_label(transcript_id, speaker_ref=speaker_ref)
        )
    except Exception as exc:
        _handle_error(exc)
        return
    if json_output:
        typer.echo(
            json.dumps(
                {
                    "transcript_id": transcript_id,
                    "speaker_ref": speaker_ref,
                    "removed": removed,
                },
                sort_keys=True,
            )
        )
        return
    if removed:
        typer.echo(f"Forgot the display name for {speaker_ref}.")
    else:
        typer.echo(f"{speaker_ref} did not have a current display name.")


def register_speaker_commands(
    app: typer.Typer,
    container_factory: ContainerFactory,
) -> None:
    speakers_app = typer.Typer(
        help="Name and inspect anonymous transcript speaker evidence.",
        no_args_is_help=True,
    )

    @speakers_app.command("list")
    def list_speakers(
        context: typer.Context,
        transcript_id: str = typer.Argument(..., metavar="TRANSCRIPT_ID"),
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        _list_speakers(
            context,
            transcript_id,
            json_output=json_output,
            container_factory=container_factory,
        )

    @speakers_app.command("transcript")
    def speaker_transcript(
        context: typer.Context,
        transcript_id: str = typer.Argument(..., metavar="TRANSCRIPT_ID"),
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        _show_speaker_transcript(
            context,
            transcript_id,
            json_output=json_output,
            container_factory=container_factory,
        )

    @speakers_app.command("name")
    def name_speaker(
        context: typer.Context,
        transcript_id: str = typer.Argument(..., metavar="TRANSCRIPT_ID"),
        speaker_ref: str = typer.Argument(..., metavar="SPEAKER_REF"),
        label: str = typer.Argument(..., metavar="DISPLAY_LABEL"),
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        _name_speaker(
            context,
            transcript_id,
            speaker_ref,
            label,
            json_output=json_output,
            container_factory=container_factory,
        )

    @speakers_app.command("forget-name")
    def forget_speaker_name(
        context: typer.Context,
        transcript_id: str = typer.Argument(..., metavar="TRANSCRIPT_ID"),
        speaker_ref: str = typer.Argument(..., metavar="SPEAKER_REF"),
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        _forget_speaker_name(
            context,
            transcript_id,
            speaker_ref,
            json_output=json_output,
            container_factory=container_factory,
        )

    app.add_typer(speakers_app, name="speakers")
