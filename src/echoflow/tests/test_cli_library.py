import json
from pathlib import Path
from unittest.mock import Mock

import typer
from typer.testing import CliRunner

from echoflow.cli_library import register_library_commands
from echoflow.library.errors import TranscriptLibraryError
from echoflow.library.evidence import (
    EvidenceContextSegment,
    EvidenceLocation,
    EvidenceWord,
)
from echoflow.library.index import (
    IndexedDocument,
    SearchOperator,
    SearchQuery,
    SearchSort,
)
from echoflow.library.research import (
    LocatedSearchPassage,
    ResearchSearchResponse,
    SpeakerDisplay,
)
from echoflow.library.research_workspace import (
    ResearchEvidenceView,
    ResearchQueryFilters,
    WorkspaceSearchPassage,
    WorkspaceSearchResponse,
)
from echoflow.library.retrieval import RetrievalMode, SearchPassage, SearchResponse
from echoflow.library.semantic import EmbeddingProfile, SemanticState
from echoflow.library.service import (
    LibraryEvidenceReceipt,
    LibraryRebuildReport,
    SemanticRebuildReport,
    SourceIntegrity,
)


def _document() -> IndexedDocument:
    root = Path.cwd() / "test-fixtures"
    return IndexedDocument(
        document_id="job-1",
        source_sha256="0" * 64,
        detected_language="en",
        canonical_path=str(root / "interview.json"),
        source_path=str(root / "interview.wav"),
        segment_count=3,
        canonical_sha256="1" * 64,
    )


def _profile() -> EmbeddingProfile:
    return EmbeddingProfile(
        profile_id="profile",
        provider="sentence-transformers",
        model_id="intfloat/multilingual-e5-small",
        resolved_revision="revision",
        dimensions=384,
        normalization="l2",
        pooling="mean",
        distance_metric="dot",
        query_prefix="query: ",
        passage_prefix="passage: ",
        chunking_profile_id="search-chunk-v1",
        snapshot_path="/private/revision",
    )


def _passage() -> SearchPassage:
    document = _document()
    return SearchPassage(
        document_id=document.document_id,
        source_sha256=document.source_sha256,
        canonical_sha256=document.canonical_sha256,
        canonical_path=document.canonical_path,
        source_path=document.source_path,
        chunk_id=None,
        segment_ids=("segment-000001",),
        matched_segment_ids=("segment-000001",),
        start_seconds=1.5,
        end_seconds=2.5,
        text="housing affordability matters",
        languages=("en",),
        speaker_refs=("speaker-02",),
        lexical_rank=1,
        semantic_rank=None,
        fused_rank=None,
    )


def _located(
    retrieval: SearchResponse | None = None,
    *,
    passage: SearchPassage | None = None,
) -> ResearchSearchResponse:
    retrieval = retrieval or SearchResponse(
        query=SearchQuery("housing"),
        mode=RetrievalMode.LEXICAL,
        lexical_backend_id="duckdb-bm25-v1",
        semantic_backend_id=None,
        semantic_profile=None,
        fusion_profile=None,
        results=(_passage(),),
    )
    passage = passage or retrieval.results[0]
    word = EvidenceWord(
        segment_id=passage.segment_ids[0],
        word_index=0,
        start_seconds=1.5,
        end_seconds=1.9,
        text="housing",
        speaker_ref="speaker-02",
        highlighted=True,
    )
    context = EvidenceContextSegment(
        segment_id=passage.segment_ids[0],
        start_seconds=passage.start_seconds,
        end_seconds=passage.end_seconds,
        text=passage.text,
        speaker_refs=("speaker-02",),
        words=(word,),
        is_result_segment=True,
        lexical_match=True,
    )
    evidence = EvidenceLocation(
        document_id=passage.document_id,
        source_sha256=passage.source_sha256,
        canonical_sha256=passage.canonical_sha256 or "1" * 64,
        canonical_path=passage.canonical_path,
        source_path=passage.source_path,
        result_segment_ids=passage.segment_ids,
        start_seconds=passage.start_seconds,
        end_seconds=passage.end_seconds,
        seek_seconds=1.5,
        result_speaker_refs=("speaker-02",),
        matched_words=(word,),
        context_segments=(context,),
    )
    return ResearchSearchResponse(
        retrieval=retrieval,
        results=(
            LocatedSearchPassage(
                passage=passage,
                evidence=evidence,
                speakers=(SpeakerDisplay("speaker-02", "Dr. Chen"),),
            ),
        ),
    )


def _workspace_response(
    navigation: ResearchSearchResponse | None = None,
    *,
    filters: ResearchQueryFilters | None = None,
) -> WorkspaceSearchResponse:
    navigation = navigation or _located()
    research = ResearchEvidenceView(
        note_ids=("note-1",),
        tags=("methodology",),
        collections=("Chapter 3",),
    )
    return WorkspaceSearchResponse(
        navigation=navigation,
        filters=filters or ResearchQueryFilters(),
        results=(WorkspaceSearchPassage(navigation.results[0], research),),
    )


def _app_with_library(
    library: Mock,
    *,
    workspace: Mock | None = None,
) -> tuple[typer.Typer, Mock]:
    app = typer.Typer()
    container = Mock()
    container.transcript_library.return_value = library
    container.research_workspace.return_value = workspace or Mock()
    container.semantic_embedding_provider.return_value = Mock()
    register_library_commands(app, lambda context: container)
    return app, container


def test_library_list_has_human_and_machine_readable_views() -> None:
    library = Mock()
    library.documents.return_value = (_document(),)
    app, _ = _app_with_library(library)
    runner = CliRunner()

    human = runner.invoke(app, ["library"])
    machine = runner.invoke(app, ["library", "--json"])

    assert human.exit_code == 0
    assert "interview.wav" in human.stdout
    assert "job-1" in human.stdout
    assert machine.exit_code == 0
    payload = json.loads(machine.stdout)
    assert payload[0]["source_sha256"] == "0" * 64
    assert payload[0]["canonical_sha256"] == "1" * 64
    assert payload[0]["segment_count"] == 3


def test_library_rebuild_reports_backend_and_skipped_files() -> None:
    library = Mock()
    library.rebuild.return_value = LibraryRebuildReport(
        backend_id="duckdb-bm25-v1",
        indexed_documents=2,
        skipped_files=1,
    )
    app, _ = _app_with_library(library)

    result = CliRunner().invoke(app, ["library", "rebuild", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "backend_id": "duckdb-bm25-v1",
        "indexed_documents": 2,
        "skipped_files": 1,
    }
    library.rebuild.assert_called_once_with(())


def test_library_rebuild_accepts_explicit_files_and_directories() -> None:
    library = Mock()
    library.rebuild.return_value = LibraryRebuildReport("duckdb-bm25-v1", 1, 0)
    app, _ = _app_with_library(library)

    result = CliRunner().invoke(
        app, ["library", "rebuild", "one.json", "transcripts"]
    )

    assert result.exit_code == 0
    assert "Indexed 1 transcript" in result.stdout
    assert library.rebuild.call_args.args[0] == (Path("one.json"), Path("transcripts"))


def test_library_show_explains_source_integrity_and_storage_custody() -> None:
    library = Mock()
    library.inspect.return_value = LibraryEvidenceReceipt(
        document=_document(),
        source_integrity=SourceIntegrity.MATCHES,
        current_source_sha256="0" * 64,
    )
    app, _ = _app_with_library(library)
    runner = CliRunner()

    human = runner.invoke(app, ["library", "show", "job-1"])
    machine = runner.invoke(app, ["library", "show", "job-1", "--json"])

    assert human.exit_code == 0
    assert "matches-recorded-source" in human.stdout
    assert "private-rebuildable-derived-state" in human.stdout
    payload = json.loads(machine.stdout)
    assert payload["source_handling"] == "read-only"
    assert payload["canonical_sha256"] == "1" * 64


def test_library_search_compiles_research_filters_to_workspace_contract() -> None:
    library = Mock()
    workspace = Mock()
    captured: list[tuple[SearchQuery, ResearchQueryFilters, RetrievalMode, int]] = []

    def capture(
        query: SearchQuery,
        *,
        filters: ResearchQueryFilters,
        mode: RetrievalMode,
        context_segments: int,
    ) -> WorkspaceSearchResponse:
        captured.append((query, filters, mode, context_segments))
        passage = SearchPassage(
            document_id="job-1",
            source_sha256="0" * 64,
            canonical_sha256="1" * 64,
            canonical_path="/canonical.json",
            source_path="/interview.wav",
            chunk_id="chunk-1",
            segment_ids=("segment-000001",),
            matched_segment_ids=("segment-000001",),
            start_seconds=1.5,
            end_seconds=4.0,
            text="housing affordability matters",
            languages=("en",),
            speaker_refs=("speaker-02",),
            lexical_rank=2,
            semantic_rank=1,
            fused_rank=1,
        )
        retrieval = SearchResponse(
            query=query,
            mode=mode,
            lexical_backend_id="duckdb-bm25-v1",
            semantic_backend_id="duckdb-exact-vector-v1",
            semantic_profile=_profile(),
            fusion_profile="rrf-k60-v1",
            results=(passage,),
        )
        resolved_filters = filters
        return _workspace_response(
            _located(retrieval, passage=passage),
            filters=resolved_filters,
        )

    workspace.search.side_effect = capture
    app, _ = _app_with_library(library, workspace=workspace)
    result = CliRunner().invoke(
        app,
        [
            "library",
            "search",
            "housing affordability",
            "--phrase",
            "--all-terms",
            "--speaker",
            "speaker-02",
            "--language",
            "en",
            "--transcript",
            "job-1",
            "--tag",
            "methodology",
            "--collection",
            "Chapter 3",
            "--note-text",
            "survey evidence",
            "--with-notes",
            "--sort",
            "timeline",
            "--mode",
            "hybrid",
            "--limit",
            "25",
            "--context-segments",
            "2",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["retrieval"]["mode"] == "hybrid"
    assert payload["results"][0]["speaker_display_labels"] == {"speaker-02": "Dr. Chen"}
    assert payload["results"][0]["research_state"] == {
        "collections": ["Chapter 3"],
        "note_count": 1,
        "note_ids": ["note-1"],
        "tags": ["methodology"],
    }
    assert payload["results"][0]["evidence_location"]["seek_seconds"] == 1.5
    query, filters, mode, context_segments = captured[0]
    assert mode is RetrievalMode.HYBRID
    assert context_segments == 2
    assert query.text == "housing affordability"
    assert query.phrase is True
    assert query.operator is SearchOperator.ALL
    assert query.speaker_refs == ("speaker-02",)
    assert query.languages == ("en",)
    assert query.document_ids == ("job-1",)
    assert query.sort is SearchSort.TIMELINE
    assert query.limit == 25
    assert filters.tags == ("methodology",)
    assert filters.collections == ("Chapter 3",)
    assert filters.note_text == "survey evidence"
    assert filters.with_notes is True


def test_library_search_human_view_shows_research_and_speaker_state() -> None:
    library = Mock()
    workspace = Mock()
    workspace.search.return_value = _workspace_response()
    app, _ = _app_with_library(library, workspace=workspace)

    result = CliRunner().invoke(app, ["library", "search", "housing"])

    assert result.exit_code == 0
    assert "interview" in result.stdout
    assert "00:00:01.500" in result.stdout
    assert "Dr. Chen" in result.stdout
    assert "speaker-02" in result.stdout
    assert "1 note" in result.stdout
    assert "methodology" in result.stdout
    assert "Chapter 3" in result.stdout
    assert "housing" in result.stdout


def test_embedding_build_and_status_expose_provenance_without_model_path(
    tmp_path: Path,
) -> None:
    revision = "a" * 40
    snapshot = tmp_path / revision
    snapshot.mkdir()
    library = Mock()
    library.rebuild_semantic.return_value = SemanticRebuildReport(
        lexical_backend_id="duckdb-bm25-v1",
        semantic_backend_id="duckdb-exact-vector-v1",
        embedding_profile_id="profile",
        model_id="intfloat/multilingual-e5-small",
        resolved_revision=revision,
        corpus_fingerprint="f" * 64,
        indexed_documents=2,
        indexed_chunks=5,
        skipped_files=0,
    )
    library.semantic_state.return_value = SemanticState(_profile(), "f" * 64, 5)
    app, container = _app_with_library(library)
    runner = CliRunner()

    built = runner.invoke(
        app,
        [
            "library",
            "embeddings",
            "build",
            str(snapshot),
            "--revision",
            revision,
            "--json",
        ],
    )
    status = runner.invoke(app, ["library", "embeddings", "--json"])

    assert built.exit_code == 0
    payload = json.loads(built.stdout)
    assert payload["indexed_chunks"] == 5
    assert payload["model_id"] == "intfloat/multilingual-e5-small"
    container.semantic_embedding_provider.assert_called_once_with(
        snapshot_path=snapshot,
        resolved_revision=revision,
    )
    library.rebuild_semantic.assert_called_once()
    status_payload = json.loads(status.stdout)
    assert status_payload["semantic_ready"] is True
    assert status_payload["profile"]["dimensions"] == 384
    assert "snapshot_path" not in status_payload["profile"]


def test_library_errors_are_safe_at_cli_boundary() -> None:
    library = Mock()
    library.documents.side_effect = TranscriptLibraryError("Library unavailable")
    app, _ = _app_with_library(library)

    result = CliRunner().invoke(app, ["library"])

    assert result.exit_code == 1
    assert "Library unavailable" in result.stderr
