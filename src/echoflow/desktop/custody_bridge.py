"""Trusted-host bridge for custody-aware lifecycle operations.

The webview may request plans and submit plan-bound confirmations through a fixed Tauri
command. It never receives filesystem paths and cannot choose a Python module, SQL query,
or arbitrary local file operation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from echoflow.app.app_container import AppContainer
from echoflow.core.errors import EchoFlowError
from echoflow.desktop.host_protocol import (
    failure_response,
    run_stdio_bridge,
    success_response,
)
from echoflow.library.custody import (
    DeletionPlan,
    DeletionReceipt,
    DeletionScope,
    LibraryCustodyService,
    RetentionPlan,
    RetentionPolicy,
    RetentionReceipt,
)

LifecycleMethod = Literal[
    "lifecycle.documents.list",
    "lifecycle.deletion.plan",
    "lifecycle.deletion.execute",
    "lifecycle.retention.plan",
    "lifecycle.retention.execute",
]


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: Literal[1]
    request_id: str = Field(min_length=1, max_length=128)
    method: LifecycleMethod
    params: dict[str, object] = Field(default_factory=dict)


class _NoParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _DeletionPlanParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1, max_length=1_024)
    scopes: tuple[DeletionScope, ...] = Field(min_length=1, max_length=16)
    allow_source: bool = False

    @field_validator("document_id")
    @classmethod
    def strip_document_id(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("document_id cannot be blank")
        return stripped

    @field_validator("scopes")
    @classmethod
    def unique_scopes(
        cls, values: tuple[DeletionScope, ...]
    ) -> tuple[DeletionScope, ...]:
        if len(values) != len(set(values)):
            raise ValueError("deletion scopes cannot repeat")
        return values


class _DeletionExecuteParams(_DeletionPlanParams):
    confirmation_token: str = Field(min_length=1, max_length=4_096)

    @field_validator("confirmation_token")
    @classmethod
    def strip_confirmation_token(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("confirmation_token cannot be blank")
        return stripped


class _RetentionPlanParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execution_days: int = Field(default=30, ge=0, le=36_500)
    include_incomplete: bool = False


class _RetentionExecuteParams(_RetentionPlanParams):
    confirmation_token: str = Field(min_length=1, max_length=4_096)

    @field_validator("confirmation_token")
    @classmethod
    def strip_confirmation_token(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("confirmation_token cannot be blank")
        return stripped


def _serialize_documents(service: LibraryCustodyService) -> list[dict[str, object]]:
    documents: list[dict[str, object]] = []
    for document in service.transcript_library.documents():
        source_name = Path(document.source_path).name if document.source_path else None
        documents.append(
            {
                "document_id": document.document_id,
                "canonical_sha256": document.canonical_sha256,
                "source_name": source_name,
                "segment_count": document.segment_count,
                "detected_language": document.detected_language,
                "deletion_ready": document.canonical_sha256 is not None,
            }
        )
    return sorted(documents, key=lambda item: str(item["document_id"]))


def _serialize_deletion_plan(plan: DeletionPlan) -> dict[str, object]:
    return {
        "document_id": plan.document_id,
        "canonical_sha256": plan.canonical_sha256,
        "requested_scopes": [scope.value for scope in plan.requested_scopes],
        "effective_scopes": [scope.value for scope in plan.effective_scopes],
        "actions": [
            {
                "target": action.target.value,
                "description": action.description,
            }
            for action in plan.actions
        ],
        "preserved_note_count": len(plan.preserved_note_ids),
        "affected_saved_search_count": len(plan.affected_saved_search_ids),
        "confirmation_token": plan.confirmation_token,
    }


def _serialize_deletion_receipt(receipt: DeletionReceipt) -> dict[str, object]:
    return {
        "document_id": receipt.document_id,
        "executed_targets": [target.value for target in receipt.executed_targets],
        "preserved_note_count": len(receipt.preserved_note_ids),
        "affected_saved_search_count": len(receipt.affected_saved_search_ids),
    }


def _serialize_retention_plan(plan: RetentionPlan) -> dict[str, object]:
    return {
        "policy": {
            "execution_days": plan.policy.execution_days,
            "include_incomplete": plan.policy.include_incomplete,
        },
        "candidates": [
            {
                "job_id": candidate.job_id,
                "status": candidate.status.value,
                "updated_at": candidate.updated_at,
                "resume_capability_lost": candidate.resume_capability_lost,
            }
            for candidate in plan.candidates
        ],
        "confirmation_token": plan.confirmation_token,
    }


def _serialize_retention_receipt(receipt: RetentionReceipt) -> dict[str, object]:
    return {"discarded_job_ids": list(receipt.discarded_job_ids)}


def dispatch_custody(
    method: str,
    params: dict[str, object],
    service: LibraryCustodyService,
) -> object:
    """Dispatch only the lifecycle methods named by the closed request schema."""
    if method == "lifecycle.documents.list":
        _NoParams.model_validate(params)
        return _serialize_documents(service)
    if method == "lifecycle.deletion.plan":
        deletion_plan = _DeletionPlanParams.model_validate(params)
        return _serialize_deletion_plan(
            service.plan_deletion(
                deletion_plan.document_id,
                deletion_plan.scopes,
                allow_source=deletion_plan.allow_source,
            )
        )
    if method == "lifecycle.deletion.execute":
        deletion_execute = _DeletionExecuteParams.model_validate(params)
        return _serialize_deletion_receipt(
            service.execute_deletion(
                deletion_execute.document_id,
                deletion_execute.scopes,
                confirmation_token=deletion_execute.confirmation_token,
                allow_source=deletion_execute.allow_source,
            )
        )
    if method == "lifecycle.retention.plan":
        retention_plan = _RetentionPlanParams.model_validate(params)
        return _serialize_retention_plan(
            service.plan_retention(
                RetentionPolicy(
                    execution_days=retention_plan.execution_days,
                    include_incomplete=retention_plan.include_incomplete,
                )
            )
        )
    if method == "lifecycle.retention.execute":
        retention_execute = _RetentionExecuteParams.model_validate(params)
        return _serialize_retention_receipt(
            service.execute_retention(
                RetentionPolicy(
                    execution_days=retention_execute.execution_days,
                    include_incomplete=retention_execute.include_incomplete,
                ),
                confirmation_token=retention_execute.confirmation_token,
            )
        )
    raise ValueError("Unsupported lifecycle desktop method")


def handle_request(
    payload: object, service: LibraryCustodyService
) -> dict[str, object]:
    request_id = "unknown"
    if isinstance(payload, dict) and isinstance(payload.get("request_id"), str):
        request_id = payload["request_id"][:128]
    try:
        request = _Request.model_validate(payload)
        return success_response(
            request.request_id,
            dispatch_custody(request.method, request.params, service),
        )
    except ValidationError:
        return failure_response(
            request_id,
            code="invalid_request",
            message="Lifecycle request is invalid or incompatible",
        )
    except EchoFlowError as exc:
        return failure_response(
            request_id,
            code=exc.code.value,
            message=exc.public_message,
        )
    except ValueError:
        return failure_response(
            request_id,
            code="invalid_request",
            message="Lifecycle request is invalid",
        )
    except Exception:
        return failure_response(
            request_id,
            code="internal_error",
            message="EchoFlow could not complete the local lifecycle request",
        )


def main() -> int:
    return run_stdio_bridge(
        lambda payload: handle_request(payload, AppContainer().library_custody()),
        oversized_message="Lifecycle request exceeded the safe size limit",
        invalid_json_message="Lifecycle request was not valid JSON",
    )


if __name__ == "__main__":
    raise SystemExit(main())
