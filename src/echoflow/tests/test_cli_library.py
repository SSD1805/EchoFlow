import json
from pathlib import Path
from unittest.mock import Mock

import typer
from typer.testing import CliRunner

from echoflow.cli_library import register_library_commands
from echoflow.library.errors import TranscriptLibraryError
from echoflow.library.index import (
    IndexedDocument,
    SearchOperator,
    SearchSort,
    TranscriptMatch,
)
from echoflow.library.service import (
    LibraryEvidenceReceipt,
    LibraryRebuildReport,
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
    )


def _match() -> TranscriptMatch:
    document = _document()
    return TranscriptMatch(
        document_id=document.document_id,
        source_sha256=document.source_sha256,
        canonical_path=document.canonical_path,
        source_path=document.source_path,
        segment_id="segment-000001",
        start_seconds=1.5,
        end_seconds=2.5,
        text="housing affordability matters",
        language="en",
        speaker_ref="speaker-02",
        score=2.75,
    )


def _app_with_library(library: Mock) -> typer.Typer:
    app = typer.Typer()
    container = Mock()
    container.transcript_library.return_value = library
    register_library_commands(app, lambda context: container)
    return app


def test_library_list_has_human_and_machine_readable_views() -> None:
    library = Mock()
    library.documents.return_value = (_document(),)
    app = _app_with_library(library)
    runner = CliRunner()

    human = runner.invoke(app, ["library"])
    machine = runner.invoke(app, ["library", "--json"])

    assert human.exit_code == 0
    assert "interview.wav" in human.stdout
    assert "job-1" in human.stdout
    assert machine.exit_code == 0
    payload = json.loads(machine.stdout)
    assert payload[0]["source_sha256"] == "0" * 64
    assert payload[0]["segment_count"] == 3


def test_library_rebuild_reports_backend_and_skipped_files() -> None:
    library = Mock()
    library.rebuild.return_value = LibraryRebuildReport(
        backend_id="duckdb-bm25-v1",
        indexed_documents=2,
        skipped_files=1,
    )
    app = _app_with_library(library)
    runner = CliRunner()

    result = runner.invoke(app, ["library", "rebuild", "--json"])

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
    app = _app_with_library(library)
    runner = CliRunner()

    result = runner.invoke(app, ["library", "rebuild", "one.json", "transcripts"])

    assert result.exit_code == 0
    assert "Indexed 1 transcript" in result.stdout
    paths = library.rebuild.call_args.args[0]
    assert paths == (Path("one.json"), Path("transcripts"))


def test_library_show_explains_source_integrity_and_storage_custody() -> None:
    library = Mock()
    library.inspect.return_value = LibraryEvidenceReceipt(
        document=_document(),
        source_integrity=SourceIntegrity.MATCHES,
        current_source_sha256="0" * 64,
    )
    app = _app_with_library(library)
    runner = CliRunner()

    human = runner.invoke(app, ["library", "show", "job-1"])
    machine = runner.invoke(app, ["library", "show", "job-1", "--json"])

    assert human.exit_code == 0
    assert "matches-recorded-source" in human.stdout
    assert "read-only" in human.stdout
    assert "private-rebuildable-derived-state" in human.stdout
    payload = json.loads(machine.stdout)
    assert payload["source_handling"] == "read-only"
    assert payload["source_integrity"] == "matches-recorded-source"
    assert payload["canonical_path"].endswith("interview.json")


def test_library_search_compiles_cli_options_to_typed_query() -> None:
    library = Mock()
    library.search.return_value = (_match(),)
    app = _app_with_library(library)
    runner = CliRunner()

    result = runner.invoke(
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
            "--sort",
            "timeline",
            "--limit",
            "25",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload[0]["segment_id"] == "segment-000001"
    assert payload[0]["start_seconds"] == 1.5
    query = library.search.call_args.args[0]
    assert query.text == "housing affordability"
    assert query.phrase is True
    assert query.operator is SearchOperator.ALL
    assert query.speaker_refs == ("speaker-02",)
    assert query.languages == ("en",)
    assert query.document_ids == ("job-1",)
    assert query.sort is SearchSort.TIMELINE
    assert query.limit == 25


def test_library_search_human_view_keeps_passage_and_timestamp_visible() -> None:
    library = Mock()
    library.search.return_value = (_match(),)
    app = _app_with_library(library)
    result = CliRunner().invoke(app, ["library", "search", "housing"])

    assert result.exit_code == 0
    assert "interview.wav" in result.stdout
    assert "1.50-2.50s" in result.stdout
    assert "speaker-02" in result.stdout
    assert "housing" in result.stdout
    assert "affordability" in result.stdout
    assert "matters" in result.stdout


def test_library_errors_are_safe_at_cli_boundary() -> None:
    library = Mock()
    library.documents.side_effect = TranscriptLibraryError("Library unavailable")
    app = _app_with_library(library)

    result = CliRunner().invoke(app, ["library"])

    assert result.exit_code == 1
    assert "Library unavailable" in result.stderr
