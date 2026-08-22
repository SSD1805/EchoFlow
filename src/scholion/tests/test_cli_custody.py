import json
from unittest.mock import Mock

import typer
from typer.testing import CliRunner

from scholion.cli_library import register_library_commands
from scholion.library.custody import (
    DeletionAction,
    DeletionPlan,
    DeletionReceipt,
    DeletionScope,
    DeletionTarget,
    RetentionCandidate,
    RetentionPlan,
    RetentionPolicy,
    RetentionReceipt,
)
from scholion.library.errors import CustodyOperationError
from scholion.workspace.lifecycle import JobStatus


def _app(service: Mock) -> typer.Typer:
    app = typer.Typer()
    container = Mock()
    container.library_custody.return_value = service
    register_library_commands(app, lambda context: container)
    return app


def _deletion_plan() -> DeletionPlan:
    return DeletionPlan(
        document_id="job-1",
        canonical_sha256="a" * 64,
        requested_scopes=(DeletionScope.CANONICAL_TRANSCRIPT,),
        effective_scopes=(
            DeletionScope.LIBRARY_VIEW,
            DeletionScope.DERIVED_ARTIFACTS,
            DeletionScope.EXECUTION_STATE,
            DeletionScope.CANONICAL_TRANSCRIPT,
        ),
        actions=(
            DeletionAction(
                target=DeletionTarget.LEXICAL_INDEX,
                object_id="job-1",
                description="remove from index",
            ),
            DeletionAction(
                target=DeletionTarget.CANONICAL_TRANSCRIPT,
                object_id="a" * 64,
                description="delete canonical evidence",
                path="/output/interview.json",
            ),
        ),
        preserved_note_ids=("note-1",),
        affected_saved_search_ids=("search-1",),
        confirmation_token="delete:job-1:aaaaaaaaaaaa:token",
    )


def _retention_plan() -> RetentionPlan:
    return RetentionPlan(
        policy=RetentionPolicy(execution_days=30, include_incomplete=True),
        candidates=(
            RetentionCandidate(
                job_id="job-1",
                status=JobStatus.INTERRUPTED,
                updated_at="2026-07-01T00:00:00+00:00",
                workspace_path="/private/jobs/job-1",
                resume_capability_lost=True,
            ),
        ),
        confirmation_token="retention:token",
    )


def test_delete_defaults_to_dry_run_library_view_and_json() -> None:
    service = Mock()
    plan = _deletion_plan()
    service.plan_deletion.return_value = plan

    result = CliRunner().invoke(
        _app(service),
        ["library", "delete", "job-1", "--json"],
    )

    assert result.exit_code == 0
    service.plan_deletion.assert_called_once_with(
        "job-1",
        (DeletionScope.LIBRARY_VIEW,),
        allow_source=False,
    )
    payload = json.loads(result.stdout)
    assert payload["executed"] is False
    assert payload["secure_erasure_guaranteed"] is False
    assert payload["preserved_note_ids"] == ["note-1"]
    assert payload["affected_saved_search_ids"] == ["search-1"]


def test_delete_human_plan_explains_preservation_and_confirmation() -> None:
    service = Mock()
    service.plan_deletion.return_value = _deletion_plan()

    result = CliRunner().invoke(
        _app(service),
        [
            "library",
            "delete",
            "job-1",
            "--scope",
            "canonical-transcript",
        ],
    )

    assert result.exit_code == 0
    assert "Preserved attached notes: 1" in result.output
    assert "Secure erasure is not guaranteed" in result.output
    assert "Confirmation token:" in result.output
    assert "No changes made" in result.output


def test_delete_confirm_executes_exact_typed_scopes_and_source_switch() -> None:
    service = Mock()
    service.execute_deletion.return_value = DeletionReceipt(
        document_id="job-1",
        confirmation_token="delete:token",
        executed_targets=(
            DeletionTarget.RESEARCH_NOTE,
            DeletionTarget.SOURCE_RECORDING,
        ),
        preserved_note_ids=(),
        affected_saved_search_ids=(),
    )

    result = CliRunner().invoke(
        _app(service),
        [
            "library",
            "delete",
            "job-1",
            "--scope",
            "research-notes",
            "--scope",
            "source-recording",
            "--allow-source",
            "--confirm",
            "delete:token",
            "--json",
        ],
    )

    assert result.exit_code == 0
    service.execute_deletion.assert_called_once_with(
        "job-1",
        (
            DeletionScope.RESEARCH_NOTES,
            DeletionScope.SOURCE_RECORDING,
        ),
        confirmation_token="delete:token",
        allow_source=True,
    )
    payload = json.loads(result.stdout)
    assert payload["executed"] is True
    assert payload["executed_targets"] == [
        "research-note",
        "source-recording",
    ]


def test_retention_dry_run_and_apply_share_typed_policy() -> None:
    service = Mock()
    service.plan_retention.return_value = _retention_plan()
    service.execute_retention.return_value = RetentionReceipt(
        confirmation_token="retention:token",
        discarded_job_ids=("job-1",),
    )
    app = _app(service)
    runner = CliRunner()

    planned = runner.invoke(
        app,
        [
            "library",
            "retention",
            "--execution-days",
            "30",
            "--include-incomplete",
            "--json",
        ],
    )
    applied = runner.invoke(
        app,
        [
            "library",
            "retention",
            "--execution-days",
            "30",
            "--include-incomplete",
            "--confirm",
            "retention:token",
            "--json",
        ],
    )

    assert planned.exit_code == applied.exit_code == 0
    service.plan_retention.assert_called_once_with(
        RetentionPolicy(execution_days=30, include_incomplete=True)
    )
    service.execute_retention.assert_called_once_with(
        RetentionPolicy(execution_days=30, include_incomplete=True),
        confirmation_token="retention:token",
    )
    plan_payload = json.loads(planned.stdout)
    assert plan_payload["candidates"][0]["resume_capability_lost"] is True
    assert plan_payload["preserves_canonical_transcripts"] is True
    assert json.loads(applied.stdout)["discarded_job_ids"] == ["job-1"]


def test_retention_human_plan_states_the_custody_boundary() -> None:
    service = Mock()
    service.plan_retention.return_value = _retention_plan()

    result = CliRunner().invoke(
        _app(service),
        ["library", "retention", "--include-incomplete"],
    )

    assert result.exit_code == 0
    assert "deletes only private job workspaces" in result.output
    assert "lifecycle manifests are preserved" in result.output
    assert "Resume lost?" in result.output


def test_custody_cli_reports_public_errors_and_masks_internal_details() -> None:
    runner = CliRunner()

    public = Mock()
    public.plan_deletion.side_effect = CustodyOperationError(
        "Deletion plan changed; review again"
    )
    public_result = runner.invoke(
        _app(public),
        ["library", "delete", "job-1"],
    )

    internal = Mock()
    internal.plan_retention.side_effect = RuntimeError("secret /private/path")
    internal_result = runner.invoke(
        _app(internal),
        ["library", "retention"],
    )

    assert public_result.exit_code == 2
    assert "Deletion plan changed; review again" in public_result.output
    assert internal_result.exit_code == 3
    assert "failed internally (RuntimeError)" in internal_result.output
    assert "/private/path" not in internal_result.output
