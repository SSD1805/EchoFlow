from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import cast

import typer
from rich.console import Console
from rich.table import Table

from echoflow.app.app_container import AppContainer
from echoflow.core.errors import EchoFlowError
from echoflow.library.index import (
    IndexedDocument,
    SearchOperator,
    SearchQuery,
    SearchSort,
    TranscriptMatch,
)
from echoflow.library.service import LibraryEvidenceReceipt, LibraryRebuildReport

ContainerFactory = Callable[[typer.Context], AppContainer]


def _root_context(context: typer.Context) -> typer.Context:
    return cast("typer.Context", context.find_root())


def _document_dict(document: IndexedDocument) -> dict[str, object]:
    return {
        "document_id": document.document_id,
        "source_sha256": document.source_sha256,
        "detected_language": document.detected_language,
        "canonical_path": document.canonical_path,
        "source_path": document.source_path,
        "segment_count": document.segment_count,
    }


def _match_dict(match: TranscriptMatch) -> dict[str, object]:
    return {
        "document_id": match.document_id,
        "source_sha256": match.source_sha256,
        "canonical_path": match.canonical_path,
        "source_path": match.source_path,
        "segment_id": match.segment_id,
        "start_seconds": match.start_seconds,
        "end_seconds": match.end_seconds,
        "text": match.text,
        "language": match.language,
        "speaker_ref": match.speaker_ref,
        "score": match.score,
    }


def _receipt_dict(receipt: LibraryEvidenceReceipt) -> dict[str, object]:
    return {
        **_document_dict(receipt.document),
        "source_integrity": receipt.source_integrity.value,
        "current_source_sha256": receipt.current_source_sha256,
        "source_handling": receipt.source_handling,
        "index_custody": receipt.index_custody,
    }


def _render_documents(documents: tuple[IndexedDocument, ...], console: Console) -> None:
    table = Table(title="EchoFlow transcript library")
    table.add_column("Transcript")
    table.add_column("Recording")
    table.add_column("Language")
    table.add_column("Segments")
    table.add_column("Canonical transcript")
    for document in documents:
        recording = (
            "unknown"
            if document.source_path is None
            else Path(document.source_path).name
        )
        table.add_row(
            document.document_id,
            recording,
            document.detected_language or "mixed/unknown",
            str(document.segment_count),
            document.canonical_path,
        )
    console.print(table)


def _render_receipt(receipt: LibraryEvidenceReceipt, console: Console) -> None:
    document = receipt.document
    table = Table(title=f"EchoFlow transcript evidence: {document.document_id}")
    table.add_column("What")
    table.add_column("Evidence")
    rows = (
        ("Original recording", document.source_path or "path unavailable"),
        ("EchoFlow source handling", receipt.source_handling),
        ("Recorded source SHA-256", document.source_sha256),
        ("Current source integrity", receipt.source_integrity.value),
        ("Current source SHA-256", receipt.current_source_sha256 or "not available"),
        ("Canonical transcript", document.canonical_path),
        ("Search index", receipt.index_custody),
        ("Indexed segments", str(document.segment_count)),
    )
    for label, value in rows:
        table.add_row(label, value)
    console.print(table)


def _render_matches(matches: tuple[TranscriptMatch, ...], console: Console) -> None:
    table = Table(title=f"EchoFlow evidence search: {len(matches)} result(s)")
    table.add_column("Recording")
    table.add_column("Time")
    table.add_column("Speaker")
    table.add_column("Language")
    table.add_column("Score")
    table.add_column("Passage")
    for match in matches:
        recording = (
            match.document_id
            if match.source_path is None
            else Path(match.source_path).name
        )
        table.add_row(
            recording,
            f"{match.start_seconds:.2f}-{match.end_seconds:.2f}s",
            match.speaker_ref or "unknown",
            match.language or "unknown",
            f"{match.score:.3f}",
            match.text,
        )
    console.print(table)


def _handle_error(exc: Exception) -> None:
    if isinstance(exc, EchoFlowError):
        typer.echo(exc.public_message, err=True)
        raise typer.Exit(code=exc.exit_code) from None
    if isinstance(exc, ValueError):
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(
        f"EchoFlow transcript library failed internally ({type(exc).__name__})",
        err=True,
    )
    raise typer.Exit(code=3) from None


def _list_library(
    context: typer.Context,
    *,
    json_output: bool,
    container_factory: ContainerFactory,
) -> None:
    try:
        documents = container_factory(_root_context(context)).transcript_library().documents()
    except Exception as exc:
        _handle_error(exc)
        return
    if json_output:
        typer.echo(json.dumps([_document_dict(item) for item in documents], sort_keys=True))
        return
    _render_documents(documents, Console())


def _rebuild_library(
    context: typer.Context,
    paths: tuple[Path, ...],
    *,
    json_output: bool,
    container_factory: ContainerFactory,
) -> None:
    try:
        report = container_factory(_root_context(context)).transcript_library().rebuild(paths)
    except Exception as exc:
        _handle_error(exc)
        return
    if json_output:
        typer.echo(json.dumps(_report_dict(report), sort_keys=True))
        return
    typer.echo(
        f"Indexed {report.indexed_documents} transcript(s) with {report.backend_id}; "
        f"skipped {report.skipped_files} non-transcript JSON file(s)."
    )


def _report_dict(report: LibraryRebuildReport) -> dict[str, object]:
    return {
        "backend_id": report.backend_id,
        "indexed_documents": report.indexed_documents,
        "skipped_files": report.skipped_files,
    }


def _show_transcript(
    context: typer.Context,
    document_id: str,
    *,
    json_output: bool,
    container_factory: ContainerFactory,
) -> None:
    try:
        receipt = container_factory(_root_context(context)).transcript_library().inspect(
            document_id
        )
    except Exception as exc:
        _handle_error(exc)
        return
    if json_output:
        typer.echo(json.dumps(_receipt_dict(receipt), sort_keys=True))
        return
    _render_receipt(receipt, Console())


def _search_library(
    context: typer.Context,
    text: str,
    *,
    phrase: bool,
    all_terms: bool,
    speakers: tuple[str, ...],
    languages: tuple[str, ...],
    documents: tuple[str, ...],
    sort: SearchSort,
    limit: int,
    json_output: bool,
    container_factory: ContainerFactory,
) -> None:
    try:
        query = SearchQuery(
            text=text,
            phrase=phrase,
            operator=SearchOperator.ALL if all_terms else SearchOperator.ANY,
            speaker_refs=speakers,
            languages=languages,
            document_ids=documents,
            sort=sort,
            limit=limit,
        )
        matches = container_factory(_root_context(context)).transcript_library().search(query)
    except Exception as exc:
        _handle_error(exc)
        return
    if json_output:
        typer.echo(json.dumps([_match_dict(item) for item in matches], sort_keys=True))
        return
    _render_matches(matches, Console())


def register_library_commands(
    app: typer.Typer, container_factory: ContainerFactory
) -> None:
    library_app = typer.Typer(
        help="Search and inspect the rebuildable local transcript library.",
        invoke_without_command=True,
        no_args_is_help=False,
    )

    @library_app.callback()
    def library_root(
        context: typer.Context,
        json_output: bool = typer.Option(
            False, "--json", help="Emit machine-readable library records."
        ),
    ) -> None:
        if context.invoked_subcommand is None:
            _list_library(
                context,
                json_output=json_output,
                container_factory=container_factory,
            )

    @library_app.command("rebuild")
    def rebuild_library(
        context: typer.Context,
        paths: list[Path] | None = typer.Argument(
            None,
            metavar="[PATH]...",
            help="Optional canonical transcript file(s) or directories to include.",
        ),
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        _rebuild_library(
            context,
            tuple(paths or ()),
            json_output=json_output,
            container_factory=container_factory,
        )

    @library_app.command("show")
    def show_transcript(
        context: typer.Context,
        document_id: str = typer.Argument(..., metavar="TRANSCRIPT_ID"),
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        _show_transcript(
            context,
            document_id,
            json_output=json_output,
            container_factory=container_factory,
        )

    @library_app.command("search")
    def search_library(
        context: typer.Context,
        text: str = typer.Argument(..., metavar="QUERY"),
        phrase: bool = typer.Option(False, "--phrase", help="Require the exact phrase."),
        all_terms: bool = typer.Option(
            False, "--all-terms", help="Require every lexical query term."
        ),
        speakers: list[str] | None = typer.Option(None, "--speaker"),
        languages: list[str] | None = typer.Option(None, "--language"),
        documents: list[str] | None = typer.Option(None, "--transcript"),
        sort: SearchSort = typer.Option(SearchSort.RELEVANCE, "--sort"),
        limit: int = typer.Option(100, "--limit", min=1, max=1_000),
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        _search_library(
            context,
            text,
            phrase=phrase,
            all_terms=all_terms,
            speakers=tuple(speakers or ()),
            languages=tuple(languages or ()),
            documents=tuple(documents or ()),
            sort=sort,
            limit=limit,
            json_output=json_output,
            container_factory=container_factory,
        )

    app.add_typer(library_app, name="library")
