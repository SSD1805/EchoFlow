"""CLI for custody-aware deletion, retention, and library maintenance registration."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Annotated, cast

import typer
from rich.console import Console
from rich.table import Table

from echoflow.app.app_container import AppContainer
from echoflow.cli_refresh import register_refresh_command
from echoflow.core.errors import EchoFlowError
from echoflow.library.custody import (
    DeletionAction,
    DeletionPlan,
    DeletionReceipt,
    DeletionScope,
    LibraryCustodyService,
    RetentionCandidate,
    RetentionPlan,
    RetentionPolicy,
    RetentionReceipt,
)

ContainerFactory = Callable[[typer.Context], AppContainer]


def _root_context(context: typer.Context) -> typer.Context:
    return cast("typer.Context", context.find_root())


def _service(
    context: typer.Context,
    container_factory: ContainerFactory,
) -> LibraryCustodyService:
    return container_factory(_root_context(context)).library_custody()


def _action_dict(action: DeletionAction) -> dict[str, object]:
    return {
        "target": action.target.value,
        "object_id": action.object_id,
        "description": action.description,
        "path": action.path,
    }


def _deletion_plan_dict(plan: DeletionPlan) -> dict[str, object]:
    return {
        "document_id": plan.document_id,
        "canonical_sha256": plan.canonical_sha256,
        "requested_scopes": [item.value for item in plan.requested_scopes],
        "effective_scopes": [item.value for item in plan.effective_scopes],
        "actions": [_action_dict(item) for item in plan.actions],
        "preserved_note_ids": list(plan.preserved_note_ids),
        "affected_saved_search_ids": list(plan.affected_saved_search_ids),
        "confirmation_token": plan.confirmation_token,
        "secure_erasure_guaranteed": False,
        "executed": False,
    }


def _deletion_receipt_dict(receipt: DeletionReceipt) -> dict[str, object]:
    return {
        "document_id": receipt.document_id,
        "confirmation_token": receipt.confirmation_token,
        "executed_targets": [item.value for item in receipt.executed_targets],
        "preserved_note_ids": list(receipt.preserved_note_ids),
        "affected_saved_search_ids": list(receipt.affected_saved_search_ids),
        "secure_erasure_guaranteed": False,
        "executed": True,
    }


def _candidate_dict(candidate: RetentionCandidate) -> dict[str, object]:
    return {
        "job_id": candidate.job_id,
        "status": candidate.status.value,
        "updated_at": candidate.updated_at,
        "workspace_path": candidate.workspace_path,
        "resume_capability_lost": candidate.resume_capability_lost,
    }


def _retention_plan_dict(plan: RetentionPlan) -> dict[str, object]:
    return {
        "policy": {
            "execution_days": plan.policy.execution_days,
            "include_incomplete": plan.policy.include_incomplete,
        },
        "candidates": [_candidate_dict(item) for item in plan.candidates],
        "confirmation_token": plan.confirmation_token,
        "preserves_canonical_transcripts": True,
        "preserves_research_knowledge": True,
        "preserves_lifecycle_manifests": True,
        "executed": False,
    }


def _retention_receipt_dict(receipt: RetentionReceipt) -> dict[str, object]:
    return {
        "confirmation_token": receipt.confirmation_token,
        "discarded_job_ids": list(receipt.discarded_job_ids),
        "preserves_canonical_transcripts": True,
        "preserves_research_knowledge": True,
        "preserves_lifecycle_manifests": True,
        "executed": True,
    }


def _render_deletion_plan(plan: DeletionPlan) -> None:
    table = Table(title=f"EchoFlow deletion plan: {plan.document_id}")
    table.add_column("Target")
    table.add_column("Action")
    table.add_column("Path")
    for action in plan.actions:
        table.add_row(
            action.target.value,
            action.description,
            action.path or "private database state",
        )
    Console().print(table)
    typer.echo(
        "Requested scopes: " + ", ".join(item.value for item in plan.requested_scopes)
    )
    if plan.effective_scopes != plan.requested_scopes:
        typer.echo(
            "Effective scopes: "
            + ", ".join(item.value for item in plan.effective_scopes)
        )
    if plan.preserved_note_ids:
        typer.echo(
            f"Preserved attached notes: {len(plan.preserved_note_ids)} "
            "(they remain as historical anchors if canonical evidence is removed)."
        )
    if plan.affected_saved_search_ids:
        typer.echo(
            f"Document-scoped saved searches affected: "
            f"{len(plan.affected_saved_search_ids)}."
        )
    typer.echo("Secure erasure is not guaranteed by this operation.")
    typer.echo(f"Confirmation token: {plan.confirmation_token}")
    typer.echo(
        "No changes made. Re-run the same command with --confirm TOKEN to apply."
    )


def _render_deletion_receipt(receipt: DeletionReceipt) -> None:
    targets = ", ".join(item.value for item in receipt.executed_targets) or "none"
    typer.echo(f"Deletion applied for {receipt.document_id}: {targets}.")
    if receipt.preserved_note_ids:
        typer.echo(f"Preserved {len(receipt.preserved_note_ids)} attached note(s).")
    typer.echo("No secure-erasure guarantee is made.")


def _render_retention_plan(plan: RetentionPlan) -> None:
    table = Table(title="EchoFlow private execution-state retention plan")
    table.add_column("Job")
    table.add_column("Status")
    table.add_column("Updated")
    table.add_column("Resume lost?")
    table.add_column("Private workspace")
    for item in plan.candidates:
        table.add_row(
            item.job_id,
            item.status.value,
            item.updated_at,
            "yes" if item.resume_capability_lost else "no",
            item.workspace_path,
        )
    Console().print(table)
    typer.echo(
        "This policy deletes only private job workspaces. Canonical transcripts, "
        "research knowledge, and lifecycle manifests are preserved."
    )
    typer.echo(f"Confirmation token: {plan.confirmation_token}")
    typer.echo(
        "No changes made. Re-run the same command with --confirm TOKEN to apply."
    )


def _render_retention_receipt(receipt: RetentionReceipt) -> None:
    typer.echo(
        f"Deleted {len(receipt.discarded_job_ids)} private execution workspace(s). "
        "Canonical evidence and user-authored research state were preserved."
    )


def _handle_error(exc: Exception) -> None:
    if isinstance(exc, EchoFlowError):
        typer.echo(exc.public_message, err=True)
        raise typer.Exit(code=exc.exit_code) from None
    if isinstance(exc, ValueError):
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(
        f"EchoFlow custody operation failed internally ({type(exc).__name__})",
        err=True,
    )
    raise typer.Exit(code=3) from None


def _delete(
    context: typer.Context,
    container_factory: ContainerFactory,
    document_id: str,
    *,
    scopes: tuple[DeletionScope, ...],
    allow_source: bool,
    confirm: str | None,
    json_output: bool,
) -> None:
    try:
        service = _service(context, container_factory)
        if confirm is None:
            plan = service.plan_deletion(
                document_id,
                scopes,
                allow_source=allow_source,
            )
            if json_output:
                typer.echo(json.dumps(_deletion_plan_dict(plan), sort_keys=True))
                return
            _render_deletion_plan(plan)
            return
        receipt = service.execute_deletion(
            document_id,
            scopes,
            confirmation_token=confirm,
            allow_source=allow_source,
        )
    except Exception as exc:
        _handle_error(exc)
        return
    if json_output:
        typer.echo(json.dumps(_deletion_receipt_dict(receipt), sort_keys=True))
        return
    _render_deletion_receipt(receipt)


def _retention(
    context: typer.Context,
    container_factory: ContainerFactory,
    *,
    execution_days: int,
    include_incomplete: bool,
    confirm: str | None,
    json_output: bool,
) -> None:
    try:
        service = _service(context, container_factory)
        policy = RetentionPolicy(
            execution_days=execution_days,
            include_incomplete=include_incomplete,
        )
        if confirm is None:
            plan = service.plan_retention(policy)
            if json_output:
                typer.echo(json.dumps(_retention_plan_dict(plan), sort_keys=True))
                return
            _render_retention_plan(plan)
            return
        receipt = service.execute_retention(
            policy,
            confirmation_token=confirm,
        )
    except Exception as exc:
        _handle_error(exc)
        return
    if json_output:
        typer.echo(json.dumps(_retention_receipt_dict(receipt), sort_keys=True))
        return
    _render_retention_receipt(receipt)


def register_custody_commands(
    library_app: typer.Typer,
    container_factory: ContainerFactory,
) -> None:
    """Register custody controls and adjacent library maintenance commands."""

    @library_app.command("delete")
    def delete_transcript(
        context: typer.Context,
        document_id: str = typer.Argument(..., metavar="TRANSCRIPT_ID"),
        scopes: Annotated[
            list[DeletionScope] | None,
            typer.Option(
                "--scope",
                help=(
                    "Custody scope. Repeat to combine. canonical-transcript expands "
                    "to library-view, derived-artifacts, and execution-state."
                ),
            ),
        ] = None,
        allow_source: bool = typer.Option(
            False,
            "--allow-source",
            help=(
                "Permit an explicitly requested source-recording deletion only when "
                "the current source still matches transcription provenance."
            ),
        ),
        confirm: str | None = typer.Option(
            None,
            "--confirm",
            help="Apply only if this exact plan-bound token still matches.",
        ),
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        _delete(
            context,
            container_factory,
            document_id,
            scopes=tuple(scopes or (DeletionScope.LIBRARY_VIEW,)),
            allow_source=allow_source,
            confirm=confirm,
            json_output=json_output,
        )

    @library_app.command("retention")
    def retention(
        context: typer.Context,
        execution_days: int = typer.Option(
            30,
            "--execution-days",
            min=0,
            max=36_500,
            help="Delete terminal private job workspaces at least this many days old.",
        ),
        include_incomplete: bool = typer.Option(
            False,
            "--include-incomplete",
            help=(
                "Also include failed/interrupted workspaces, which removes resume "
                "capability. Running jobs are never eligible."
            ),
        ),
        confirm: str | None = typer.Option(
            None,
            "--confirm",
            help="Apply only if this exact retention plan token still matches.",
        ),
        json_output: bool = typer.Option(False, "--json"),
    ) -> None:
        _retention(
            context,
            container_factory,
            execution_days=execution_days,
            include_incomplete=include_incomplete,
            confirm=confirm,
            json_output=json_output,
        )

    register_refresh_command(library_app, container_factory)
