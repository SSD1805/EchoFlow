from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, cast

import typer
from rich.console import Console
from rich.table import Table

from echoflow.app.app_container import AppContainer
from echoflow.cli_speakers import register_speaker_commands
from echoflow.core.errors import EchoFlowError
from echoflow.library.index import (
    IndexedDocument,
    SearchOperator,
    SearchQuery,
    SearchSort,
)
from echoflow.library.retrieval import RetrievalMode, SearchPassage, SearchResponse
from echoflow.library.semantic import EmbeddingProfile, SemanticState
from echoflow.library.service import (
    LibraryEvidenceReceipt,
    LibraryRebuildReport,
    SemanticRebuildReport,
)
from echoflow.media.time_coordinates import format_elapsed_timestamp

ContainerFactory = Callable[[typer.Context], AppContainer]


def _root_context(context: typer.Context) -> typer.Context:
    return cast("typer.Context", context.find_root())


def _document_dict(document: IndexedDocument) -> dict[str, object]:
    return {
        "document_id": document.document_id,
        "source_sha256": document.source_sha256,
        "canonical_sha256": document.canonical_sha256,
        "detected_language": document.detected_language,
        "canonical_path": document.canonical_path,
        "source_path": document.source_path,
        "segment_count": document.segment_count,
    }


def _profile_dict(profile: EmbeddingProfile) -> dict[str, object]:
    return {
        "profile_id": profile.profile_id,
        "provider": profile.provider,
        "model_id": profile.model_id,
        "resolved_revision": profile.resolved_revision,
        "dimensions": profile.dimensions,
        "normalization": profile.normalization,
        "pooling": profile.pooling,
        "distance_metric": profile.distance_metric,
        "query_prefix": profile.query_prefix,
        "passage_prefix": profile.passage_prefix,
        "chunking_profile_id": profile.chunking_profile_id,
        "embedding_schema_version": profile.embedding_schema_version,
    }


def _state_dict(state: SemanticState) -> dict[str, object]:
    return {
        "semantic_ready": True,
        "corpus_fingerprint": state.corpus_fingerprint,
        "chunk_count": state.chunk_count,
        "profile": _profile_dict(state.profile),
    }


def _passage_dict(passage: SearchPassage) -> dict[str, object]:
    return {
        "document_id": passage.document_id,
        "source_sha256": passage.source_sha256,
        "canonical_sha256": passage.canonical_sha256,
        "canonical_path": passage.canonical_path,
        "source_path": passage.source_path,
        "chunk_id": passage.chunk_id,
        "segment_ids": list(passage.segment_ids),
        "matched_segment_ids": list(passage.matched_segment_ids),
        "start_seconds": passage.start_seconds,
        "end_seconds": passage.end_seconds,
        "start_timestamp": format_elapsed_timestamp(passage.start_seconds),
        "end_timestamp": format_elapsed_timestamp(passage.end_seconds),
        "text": passage.text,
        "languages": list(passage.languages),
        "speaker_refs": list(passage.speaker_refs),
        "lexical_rank": passage.lexical_rank,
        "semantic_rank": passage.semantic_rank,
        "fused_rank": passage.fused_rank,
    }


def _response_dict(response: SearchResponse) -> dict[str, object]:
    query = response.query
    return {
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
        "retrieval": {
            "mode": response.mode.value,
            "lexical_backend_id": response.lexical_backend_id,
            "semantic_backend_id": response.semantic_backend_id,
            "semantic_profile": (
                None
                if response.semantic_profile is None
                else _profile_dict(response.semantic_profile)
            ),
            "fusion_profile": response.fusion_profile,
        },
        "result_count": len(response.results),
        "results": [_passage_dict(item) for item in response.results],
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
        ("Canonical SHA-256", document.canonical_sha256 or "rebuild library to record"),
        ("Current source integrity", receipt.source_integrity.value),
        ("Current source SHA-256", receipt.current_source_sha256 or "not available"),
        ("Canonical transcript", document.canonical_path),
        ("Search index", receipt.index_custody),
        ("Indexed segments", str(document.segment_count)),
    )
    for label, value in rows:
        table.add_row(label, value)
    console.print(table)


def _render_response(response: SearchResponse, console: Console) -> None:
    table = Table(
        title=(
            f"EchoFlow {response.mode.value} evidence search: "
            f"{len(response.results)} result(s)"
        )
    )
    table.add_column("Recording")
    table.add_column("Time", min_width=12, no_wrap=True)
    table.add_column("Speaker")
    table.add_column("Language")
    table.add_column("Ranks")
    table.add_column("Passage")
    for result in response.results:
        recording = (
            result.document_id
            if result.source_path is None
            else Path(result.source_path).name
        )
        ranks = (
            f"L:{result.lexical_rank or '-'} "
            f"S:{result.semantic_rank or '-'} "
            f"F:{result.fused_rank}"
        )
        time_range = (
            f"{format_elapsed_timestamp(result.start_seconds)}\n"
            f"{format_elapsed_timestamp(result.end_seconds)}"
        )
        table.add_row(
            recording,
            time_range,
            ", ".join(result.speaker_refs) or "unknown",
            ", ".join(result.languages) or "unknown",
            ranks,
            result.text,
        )
    console.print(table)


def _handle_error(exc: Exception) -> None:
    if isinstance(exc, EchoFlowError):
        typer.echo(exc.public_message, err=True)
        raise typer.Exit(code=exc.exit_code) from None
    if isinstance(exc, (ValueError, ModuleNotFoundError)):
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
        documents = (
            container_factory(_root_context(context)).transcript_library().documents()
        )
    except Exception as exc:
        _handle_error(exc)
        return
    if json_output:
        typer.echo(
            json.dumps([_document_dict(item) for item in documents], sort_keys=True)
        )
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
        report = (
            container_factory(_root_context(context))
            .transcript_library()
            .rebuild(paths)
        )
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


def _semantic_report_dict(report: SemanticRebuildReport) -> dict[str, object]:
    return {
        "lexical_backend_id": report.lexical_backend_id,
        "semantic_backend_id": report.semantic_backend_id,
        "embedding_profile_id": report.embedding_profile_id,
        "model_id": report.model_id,
        "resolved_revision": report.resolved_revision,
        "corpus_fingerprint": report.corpus_fingerprint,
        "indexed_documents": report.indexed_documents,
        "indexed_chunks": report.indexed_chunks,
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
        receipt = (
            container_factory(_root_context(context))
            .transcript_library()
            .inspect(document_id)
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
    mode: RetrievalMode,
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
        response = (
            container_factory(_root_context(context))
            .transcript_library()
            .retrieve(query, mode=mode)
        )
    except Exception as exc:
        _handle_error(exc)
        return
    if json_output:
        typer.echo(json.dumps(_response_dict(response), sort_keys=True))
        return
    _render_response(response, Console())


def _build_embeddings(
    context: typer.Context,
    model_path: Path,
    revision: str,
    paths: tuple[Path, ...],
    *,
    json_output: bool,
    container_factory: ContainerFactory,
) -> None:
    try:
        container = container_factory(_root_context(context))
        provider = container.semantic_embedding_provider(
            snapshot_path=model_path,
            resolved_revision=revision,
        )
        report = container.transcript_library().rebuild_semantic(provider, paths)
    except Exception as exc:
        _handle_error(exc)
        return
    if json_output:
        typer.echo(json.dumps(_semantic_report_dict(report), sort_keys=True))
        return
    typer.echo(
        f"Built {report.indexed_chunks} semantic chunk(s) across "
        f"{report.indexed_documents} transcript(s) with {report.model_id} "
        f"at revision {report.resolved_revision}."
    )


def _embedding_status(
    context: typer.Context,
    *,
    json_output: bool,
    container_factory: ContainerFactory,
) -> None:
    try:
        state = (
            container_factory(_root_context(context))
            .transcript_library()
            .semantic_state()
        )
    except Exception as exc:
        _handle_error(exc)
        return
    if json_output:
        document: dict[str, object] = (
            {"semantic_ready": False} if state is None else _state_dict(state)
        )
        typer.echo(json.dumps(document, sort_keys=True))
        return
    if state is None:
        typer.echo("Semantic embeddings have not been built.")
        return
    table = Table(title="EchoFlow semantic index")
    table.add_column("Setting")
    table.add_column("Value")
    table.add_row("Model", state.profile.model_id)
    table.add_row("Resolved revision", state.profile.resolved_revision)
    table.add_row("Dimensions", str(state.profile.dimensions))
    table.add_row("Normalization", state.profile.normalization)
    table.add_row("Pooling", state.profile.pooling)
    table.add_row("Distance metric", state.profile.distance_metric)
    table.add_row("Chunking", state.profile.chunking_profile_id)
    table.add_row("Chunks", str(state.chunk_count))
    table.add_row("Corpus fingerprint", state.corpus_fingerprint)
    Console().print(table)


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
        paths: Annotated[
            list[Path] | None,
            typer.Argument(
                metavar="[PATH]...",
                help="Optional canonical transcript file(s) or directories to include.",
            ),
        ] = None,
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
        phrase: bool = typer.Option(
            False, "--phrase", help="Require the exact phrase."
        ),
        all_terms: bool = typer.Option(
            False, "--all-terms", help="Require every lexical query term."
        ),
        speakers: Annotated[list[str] | None, typer.Option("--speaker")] = None,
        languages: Annotated[list[str] | None, typer.Option("--language")] = None,
        documents: Annotated[list[str] | None, typer.Option("--transcript")] = None,
        sort: Annotated[SearchSort, typer.Option("--sort")] = SearchSort.RELEVANCE,
        mode: Annotated[
            RetrievalMode,
            typer.Option(
                "--mode",
                help="Use lexical, semantic, or local hybrid retrieval.",
            ),
        ] = RetrievalMode.LEXICAL,
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
            mode=mode,
            limit=limit,
            json_output=json_output,
            container_factory=container_factory,
        )

    embeddings_app = typer.Typer(
        help="Build and inspect private rebuildable semantic embedding state.",
        invoke_without_command=True,
        no_args_is_help=False,
    )

    @embeddings_app.callback()
    def embeddings_root(
        context: typer.Context,
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        if context.invoked_subcommand is None:
            _embedding_status(
                context,
                json_output=json_output,
                container_factory=container_factory,
            )

    @embeddings_app.command("build")
    def build_embeddings(
        context: typer.Context,
        model_path: Annotated[
            Path,
            typer.Argument(
                metavar="MODEL_SNAPSHOT",
                help="Local immutable multilingual-e5-small snapshot directory.",
            ),
        ],
        revision: Annotated[
            str,
            typer.Option(
                "--revision",
                help="Immutable resolved model revision; must match snapshot dirname.",
            ),
        ],
        paths: Annotated[
            list[Path] | None,
            typer.Argument(
                metavar="[PATH]...",
                help="Optional canonical transcript file(s) or directories to include.",
            ),
        ] = None,
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        _build_embeddings(
            context,
            model_path,
            revision,
            tuple(paths or ()),
            json_output=json_output,
            container_factory=container_factory,
        )

    library_app.add_typer(embeddings_app, name="embeddings")
    register_speaker_commands(library_app, container_factory)
    app.add_typer(library_app, name="library")
