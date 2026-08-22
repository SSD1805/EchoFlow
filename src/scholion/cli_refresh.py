"""CLI for incremental transcript-library reconciliation."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, cast

import typer

from scholion.app.app_container import AppContainer
from scholion.core.errors import ScholionError
from scholion.library.service import LibraryRefreshReport

ContainerFactory = Callable[[typer.Context], AppContainer]


def _root_context(context: typer.Context) -> typer.Context:
    return cast("typer.Context", context.find_root())


def _report_dict(report: LibraryRefreshReport) -> dict[str, object]:
    return {
        "backend_id": report.backend_id,
        "indexed_documents": report.indexed_documents,
        "added_document_ids": list(report.added_document_ids),
        "updated_document_ids": list(report.updated_document_ids),
        "removed_document_ids": list(report.removed_document_ids),
        "unchanged_document_ids": list(report.unchanged_document_ids),
        "added_documents": len(report.added_document_ids),
        "updated_documents": len(report.updated_document_ids),
        "removed_documents": len(report.removed_document_ids),
        "unchanged_documents": len(report.unchanged_document_ids),
        "skipped_files": report.skipped_files,
        "semantic_invalidated": report.semantic_invalidated,
        "verified_all_tracked": report.verified_all_tracked,
        "changed": report.changed,
    }


def _handle_error(exc: Exception) -> None:
    if isinstance(exc, ScholionError):
        typer.echo(exc.public_message, err=True)
        raise typer.Exit(code=exc.exit_code) from None
    if isinstance(exc, ValueError):
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(
        f"Scholion library refresh failed internally ({type(exc).__name__})",
        err=True,
    )
    raise typer.Exit(code=3) from None


def _render_report(report: LibraryRefreshReport) -> None:
    typer.echo(
        f"Library current with {report.indexed_documents} transcript(s): "
        f"{len(report.added_document_ids)} added, "
        f"{len(report.updated_document_ids)} updated, "
        f"{len(report.removed_document_ids)} removed, "
        f"{len(report.unchanged_document_ids)} unchanged."
    )
    if report.skipped_files:
        typer.echo(
            f"Skipped {report.skipped_files} unrelated or invalid untracked JSON file(s)."
        )
    if report.semantic_invalidated:
        typer.echo(
            "Semantic embeddings were invalidated because indexed evidence changed; "
            "rebuild embeddings before semantic or hybrid search."
        )
    if report.verified_all_tracked:
        typer.echo(
            "Re-hashed and validated every tracked canonical transcript during this refresh."
        )


def _refresh(
    context: typer.Context,
    container_factory: ContainerFactory,
    paths: tuple[Path, ...],
    *,
    verify: bool,
    json_output: bool,
) -> None:
    try:
        report = (
            container_factory(_root_context(context))
            .transcript_library()
            .refresh(paths, verify=verify)
        )
    except Exception as exc:
        _handle_error(exc)
        return
    if json_output:
        typer.echo(json.dumps(_report_dict(report), sort_keys=True))
        return
    _render_report(report)


def register_refresh_command(
    library_app: typer.Typer,
    container_factory: ContainerFactory,
) -> None:
    """Register fast incremental library reconciliation."""

    @library_app.command("refresh")
    def refresh_library(
        context: typer.Context,
        paths: Annotated[
            list[Path] | None,
            typer.Argument(
                metavar="[PATH]...",
                help=(
                    "Optional canonical transcript file(s) or directories to discover "
                    "in addition to tracked and configured library paths."
                ),
            ),
        ] = None,
        verify: bool = typer.Option(
            False,
            "--verify",
            help=(
                "Re-hash and validate every tracked canonical transcript instead of "
                "using the stored size/mtime fast path; unchanged generations are "
                "still not rewritten."
            ),
        ),
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        _refresh(
            context,
            container_factory,
            tuple(paths or ()),
            verify=verify,
            json_output=json_output,
        )
