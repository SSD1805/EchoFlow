import json
from pathlib import Path
from unittest.mock import Mock

import typer
from typer.testing import CliRunner

from echoflow.cli_library import register_library_commands
from echoflow.library.errors import TranscriptLibraryBuildError
from echoflow.library.service import LibraryRefreshReport


def _app(service: Mock) -> typer.Typer:
    app = typer.Typer()
    container = Mock()
    container.transcript_library.return_value = service
    register_library_commands(app, lambda context: container)
    return app


def _report(*, semantic_invalidated: bool = False) -> LibraryRefreshReport:
    return LibraryRefreshReport(
        backend_id="duckdb-bm25-v1",
        indexed_documents=4,
        added_document_ids=("new",),
        updated_document_ids=("changed",),
        removed_document_ids=("gone",),
        unchanged_document_ids=("same",),
        skipped_files=2,
        semantic_invalidated=semantic_invalidated,
        verified_all_tracked=True,
    )


def test_refresh_cli_passes_paths_and_verify_and_emits_json() -> None:
    service = Mock()
    service.refresh.return_value = _report(semantic_invalidated=True)

    result = CliRunner().invoke(
        _app(service),
        ["library", "refresh", "./imports", "--verify", "--json"],
    )

    assert result.exit_code == 0
    service.refresh.assert_called_once()
    (paths,) = service.refresh.call_args.args
    assert paths == (Path("imports"),)
    assert service.refresh.call_args.kwargs == {"verify": True}
    payload = json.loads(result.stdout)
    assert payload["changed"] is True
    assert payload["added_document_ids"] == ["new"]
    assert payload["updated_document_ids"] == ["changed"]
    assert payload["removed_document_ids"] == ["gone"]
    assert payload["unchanged_document_ids"] == ["same"]
    assert payload["semantic_invalidated"] is True
    assert payload["verified_all_tracked"] is True


def test_refresh_human_output_explains_delta_skip_and_semantic_invalidation() -> None:
    service = Mock()
    service.refresh.return_value = _report(semantic_invalidated=True)

    result = CliRunner().invoke(_app(service), ["library", "refresh", "--verify"])

    assert result.exit_code == 0
    assert "4 transcript(s)" in result.output
    assert "1 added" in result.output
    assert "1 updated" in result.output
    assert "1 removed" in result.output
    assert "1 unchanged" in result.output
    assert "Skipped 2" in result.output
    assert "Semantic embeddings were invalidated" in result.output
    assert "Re-hashed and validated" in result.output


def test_refresh_noop_human_output_does_not_claim_semantic_invalidation() -> None:
    service = Mock()
    service.refresh.return_value = LibraryRefreshReport(
        backend_id="duckdb-bm25-v1",
        indexed_documents=2,
        added_document_ids=(),
        updated_document_ids=(),
        removed_document_ids=(),
        unchanged_document_ids=("one", "two"),
        skipped_files=0,
        semantic_invalidated=False,
        verified_all_tracked=False,
    )

    result = CliRunner().invoke(_app(service), ["library", "refresh"])

    assert result.exit_code == 0
    assert "2 unchanged" in result.output
    assert "Semantic embeddings were invalidated" not in result.output
    service.refresh.assert_called_once_with((), verify=False)


def test_refresh_cli_reports_public_errors_and_masks_internal_details() -> None:
    runner = CliRunner()

    public = Mock()
    public.refresh.side_effect = TranscriptLibraryBuildError(
        "A tracked canonical transcript could not be refreshed safely"
    )
    public_result = runner.invoke(_app(public), ["library", "refresh"])

    internal = Mock()
    internal.refresh.side_effect = RuntimeError("secret /private/library.duckdb")
    internal_result = runner.invoke(_app(internal), ["library", "refresh"])

    assert public_result.exit_code == 2
    assert "tracked canonical transcript" in public_result.output
    assert internal_result.exit_code == 3
    assert "failed internally (RuntimeError)" in internal_result.output
    assert "/private/library.duckdb" not in internal_result.output
