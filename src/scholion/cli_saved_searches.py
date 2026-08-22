"""CLI for durable saved searches and disposable workspace navigation views."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, cast

import typer
from rich.console import Console
from rich.table import Table

from scholion.app.app_container import AppContainer
from scholion.core.errors import ScholionError
from scholion.library.index import SearchOperator, SearchQuery, SearchSort
from scholion.library.research_workspace import (
    ResearchQueryFilters,
    ResearchWorkspaceService,
    WorkspaceSearchResponse,
)
from scholion.library.retrieval import RetrievalMode
from scholion.library.workspace_metadata import (
    NavigationItem,
    SavedSearch,
    WorkspaceNavigation,
)
from scholion.media.time_coordinates import format_elapsed_timestamp

ContainerFactory = Callable[[typer.Context], AppContainer]


def _root_context(context: typer.Context) -> typer.Context:
    return cast("typer.Context", context.find_root())


def _workspace(
    context: typer.Context,
    container_factory: ContainerFactory,
) -> ResearchWorkspaceService:
    return container_factory(_root_context(context)).research_workspace()


def _handle_error(exc: Exception) -> None:
    if isinstance(exc, ScholionError):
        typer.echo(exc.public_message, err=True)
        raise typer.Exit(code=exc.exit_code) from None
    if isinstance(exc, (ValueError, ModuleNotFoundError)):
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(
        f"Scholion saved-search workspace failed internally ({type(exc).__name__})",
        err=True,
    )
    raise typer.Exit(code=3) from None


def _saved_search_dict(saved: SavedSearch) -> dict[str, object]:
    intent = saved.intent
    query = intent.query
    return {
        "saved_search_id": saved.saved_search_id,
        "name": saved.name,
        "description": saved.description,
        "created_at": saved.created_at,
        "updated_at": saved.updated_at,
        "intent": {
            "query": {
                "text": query.text,
                "phrase": query.phrase,
                "operator": query.operator.value,
                "speaker_refs": list(query.speaker_refs),
                "languages": list(query.languages),
                "document_ids": list(query.document_ids),
                "sort": query.sort.value,
                "limit": query.limit,
            },
            "research_filter": {
                "tags": list(intent.tags),
                "collections": list(intent.collections),
                "note_text": intent.note_text,
                "with_notes": intent.with_notes,
            },
            "retrieval_mode": intent.mode.value,
            "context_segments": intent.context_segments,
        },
    }


def _navigation_item_dict(item: NavigationItem) -> dict[str, object]:
    return {
        "object_id": item.object_id,
        "name": item.name,
        "usage_count": item.usage_count,
        "last_used_at": item.last_used_at,
    }


def _navigation_dict(navigation: WorkspaceNavigation) -> dict[str, object]:
    return {
        "frequent_tags": [
            _navigation_item_dict(item) for item in navigation.frequent_tags
        ],
        "recent_tags": [_navigation_item_dict(item) for item in navigation.recent_tags],
        "frequent_collections": [
            _navigation_item_dict(item) for item in navigation.frequent_collections
        ],
        "recent_collections": [
            _navigation_item_dict(item) for item in navigation.recent_collections
        ],
    }


def _run_response_dict(
    saved: SavedSearch,
    response: WorkspaceSearchResponse,
) -> dict[str, object]:
    return {
        "saved_search": _saved_search_dict(saved),
        "result_count": len(response.results),
        "results": [
            {
                "document_id": item.located.passage.document_id,
                "source_sha256": item.located.passage.source_sha256,
                "canonical_sha256": item.located.passage.canonical_sha256,
                "canonical_path": item.located.passage.canonical_path,
                "source_path": item.located.passage.source_path,
                "segment_ids": list(item.located.passage.segment_ids),
                "start_seconds": item.located.passage.start_seconds,
                "end_seconds": item.located.passage.end_seconds,
                "seek_seconds": item.located.evidence.seek_seconds,
                "text": item.located.passage.text,
                "speaker_refs": list(item.located.passage.speaker_refs),
                "speaker_display_labels": {
                    speaker.speaker_ref: speaker.display_label
                    for speaker in item.located.speakers
                    if speaker.display_label is not None
                },
                "research_state": {
                    "note_ids": list(item.research.note_ids),
                    "tags": list(item.research.tags),
                    "collections": list(item.research.collections),
                },
            }
            for item in response.results
        ],
    }


def _render_saved_searches(saved_searches: tuple[SavedSearch, ...]) -> None:
    table = Table(title=f"Scholion saved searches: {len(saved_searches)}")
    table.add_column("Name")
    table.add_column("ID")
    table.add_column("Query")
    table.add_column("Mode")
    table.add_column("Research filters")
    table.add_column("Updated")
    for saved in saved_searches:
        intent = saved.intent
        filters: list[str] = []
        if intent.tags:
            filters.append("# " + ", ".join(intent.tags))
        if intent.collections:
            filters.append("in " + ", ".join(intent.collections))
        if intent.note_text is not None:
            filters.append(f"note: {intent.note_text}")
        if intent.with_notes:
            filters.append("with notes")
        table.add_row(
            saved.name,
            saved.saved_search_id,
            intent.query.text,
            intent.mode.value,
            "\n".join(filters) or "—",
            saved.updated_at,
        )
    Console().print(table)


def _render_run(saved: SavedSearch, response: WorkspaceSearchResponse) -> None:
    table = Table(
        title=f"{saved.name}: {len(response.results)} current evidence result(s)"
    )
    table.add_column("Recording", min_width=14)
    table.add_column("Evidence time", min_width=12)
    table.add_column("Research", min_width=10)
    table.add_column("Passage")
    for item in response.results:
        passage = item.located.passage
        recording = (
            passage.document_id
            if passage.source_path is None
            else Path(passage.source_path).name
        )
        research: list[str] = []
        if item.research.note_count:
            research.append(f"{item.research.note_count} note(s)")
        if item.research.tags:
            research.append("# " + ", ".join(item.research.tags))
        if item.research.collections:
            research.append("in " + ", ".join(item.research.collections))
        table.add_row(
            recording,
            format_elapsed_timestamp(item.located.evidence.seek_seconds),
            "\n".join(research) or "—",
            passage.text,
        )
    Console().print(table)


def _render_navigation(navigation: WorkspaceNavigation) -> None:
    table = Table(title="Scholion workspace navigation")
    table.add_column("View")
    table.add_column("Name")
    table.add_column("Uses", justify="right")
    table.add_column("Last used")
    groups = (
        ("frequent tag", navigation.frequent_tags),
        ("recent tag", navigation.recent_tags),
        ("frequent collection", navigation.frequent_collections),
        ("recent collection", navigation.recent_collections),
    )
    for label, items in groups:
        for item in items:
            table.add_row(label, item.name, str(item.usage_count), item.last_used_at)
    Console().print(table)


def _list_saved(
    context: typer.Context,
    container_factory: ContainerFactory,
    *,
    limit: int,
    json_output: bool,
) -> None:
    if context.invoked_subcommand is not None:
        return
    try:
        saved = _workspace(context, container_factory).saved_searches(limit=limit)
    except Exception as exc:
        _handle_error(exc)
        return
    if json_output:
        typer.echo(
            json.dumps([_saved_search_dict(item) for item in saved], sort_keys=True)
        )
        return
    _render_saved_searches(saved)


def _show_saved(
    context: typer.Context,
    container_factory: ContainerFactory,
    identifier: str,
    *,
    json_output: bool,
) -> None:
    try:
        saved = _workspace(context, container_factory).saved_search(identifier)
    except Exception as exc:
        _handle_error(exc)
        return
    if saved is None:
        typer.echo("Saved search does not exist", err=True)
        raise typer.Exit(code=2)
    if json_output:
        typer.echo(json.dumps(_saved_search_dict(saved), sort_keys=True))
        return
    _render_saved_searches((saved,))


def _save_search(
    context: typer.Context,
    container_factory: ContainerFactory,
    name: str,
    text: str,
    *,
    description: str | None,
    phrase: bool,
    all_terms: bool,
    speakers: tuple[str, ...],
    languages: tuple[str, ...],
    documents: tuple[str, ...],
    tags: tuple[str, ...],
    collections: tuple[str, ...],
    note_text: str | None,
    with_notes: bool,
    sort: SearchSort,
    mode: RetrievalMode,
    limit: int,
    context_segments: int,
    json_output: bool,
) -> None:
    try:
        saved = _workspace(context, container_factory).save_search(
            name,
            SearchQuery(
                text=text,
                phrase=phrase,
                operator=SearchOperator.ALL if all_terms else SearchOperator.ANY,
                speaker_refs=speakers,
                languages=languages,
                document_ids=documents,
                sort=sort,
                limit=limit,
            ),
            filters=ResearchQueryFilters(
                tags=tags,
                collections=collections,
                note_text=note_text,
                with_notes=with_notes,
            ),
            mode=mode,
            context_segments=context_segments,
            description=description,
        )
    except Exception as exc:
        _handle_error(exc)
        return
    if json_output:
        typer.echo(json.dumps(_saved_search_dict(saved), sort_keys=True))
        return
    typer.echo(f"Saved {saved.name!r} as {saved.saved_search_id}.")


def _run_saved(
    context: typer.Context,
    container_factory: ContainerFactory,
    identifier: str,
    *,
    json_output: bool,
) -> None:
    try:
        workspace = _workspace(context, container_factory)
        saved = workspace.saved_search(identifier)
        if saved is None:
            typer.echo("Saved search does not exist", err=True)
            raise typer.Exit(code=2)
        response = workspace.run_saved_search(saved.saved_search_id)
    except typer.Exit:
        raise
    except Exception as exc:
        _handle_error(exc)
        return
    if json_output:
        typer.echo(json.dumps(_run_response_dict(saved, response), sort_keys=True))
        return
    _render_run(saved, response)


def _delete_saved(
    context: typer.Context,
    container_factory: ContainerFactory,
    identifier: str,
) -> None:
    try:
        workspace = _workspace(context, container_factory)
        saved = workspace.saved_search(identifier)
        if saved is None:
            typer.echo("Saved search does not exist", err=True)
            raise typer.Exit(code=2)
        workspace.delete_saved_search(saved.saved_search_id)
    except typer.Exit:
        raise
    except Exception as exc:
        _handle_error(exc)
        return
    typer.echo(f"Deleted saved search {saved.name!r} from durable user state.")


def _show_navigation(
    context: typer.Context,
    container_factory: ContainerFactory,
    *,
    limit: int,
    json_output: bool,
) -> None:
    try:
        navigation = _workspace(context, container_factory).workspace_navigation(
            limit=limit
        )
    except Exception as exc:
        _handle_error(exc)
        return
    if json_output:
        typer.echo(json.dumps(_navigation_dict(navigation), sort_keys=True))
        return
    _render_navigation(navigation)


def register_saved_search_commands(
    library_app: typer.Typer,
    container_factory: ContainerFactory,
) -> None:
    """Register durable saved searches and derived navigation on ``library``."""
    saved_app = typer.Typer(
        help="Save and replay typed research searches.",
        invoke_without_command=True,
        no_args_is_help=False,
    )

    @saved_app.callback()
    def saved_root(
        context: typer.Context,
        limit: int = typer.Option(100, "--limit", min=1, max=10_000),
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        _list_saved(
            context,
            container_factory,
            limit=limit,
            json_output=json_output,
        )

    @saved_app.command("save")
    def save_search(
        context: typer.Context,
        name: str = typer.Argument(..., metavar="NAME"),
        text: str = typer.Argument(..., metavar="QUERY"),
        description: str | None = typer.Option(None, "--description"),
        phrase: bool = typer.Option(False, "--phrase"),
        all_terms: bool = typer.Option(False, "--all-terms"),
        speakers: Annotated[list[str] | None, typer.Option("--speaker")] = None,
        languages: Annotated[list[str] | None, typer.Option("--language")] = None,
        documents: Annotated[list[str] | None, typer.Option("--transcript")] = None,
        tags: Annotated[list[str] | None, typer.Option("--tag")] = None,
        collections: Annotated[list[str] | None, typer.Option("--collection")] = None,
        note_text: str | None = typer.Option(None, "--note-text"),
        with_notes: bool = typer.Option(False, "--with-notes"),
        sort: Annotated[SearchSort, typer.Option("--sort")] = SearchSort.RELEVANCE,
        mode: Annotated[RetrievalMode, typer.Option("--mode")] = RetrievalMode.LEXICAL,
        limit: int = typer.Option(100, "--limit", min=1, max=1_000),
        context_segments: int = typer.Option(
            0,
            "--context-segments",
            min=0,
            max=10,
        ),
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        _save_search(
            context,
            container_factory,
            name,
            text,
            description=description,
            phrase=phrase,
            all_terms=all_terms,
            speakers=tuple(speakers or ()),
            languages=tuple(languages or ()),
            documents=tuple(documents or ()),
            tags=tuple(tags or ()),
            collections=tuple(collections or ()),
            note_text=note_text,
            with_notes=with_notes,
            sort=sort,
            mode=mode,
            limit=limit,
            context_segments=context_segments,
            json_output=json_output,
        )

    @saved_app.command("show")
    def show_saved(
        context: typer.Context,
        identifier: str = typer.Argument(..., metavar="ID_OR_NAME"),
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        _show_saved(
            context,
            container_factory,
            identifier,
            json_output=json_output,
        )

    @saved_app.command("run")
    def run_saved(
        context: typer.Context,
        identifier: str = typer.Argument(..., metavar="ID_OR_NAME"),
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        _run_saved(
            context,
            container_factory,
            identifier,
            json_output=json_output,
        )

    @saved_app.command("delete")
    def delete_saved(
        context: typer.Context,
        identifier: str = typer.Argument(..., metavar="ID_OR_NAME"),
    ) -> None:
        _delete_saved(context, container_factory, identifier)

    @library_app.command("navigation")
    def navigation(
        context: typer.Context,
        limit: int = typer.Option(10, "--limit", min=1, max=100),
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        _show_navigation(
            context,
            container_factory,
            limit=limit,
            json_output=json_output,
        )

    library_app.add_typer(saved_app, name="saved")
