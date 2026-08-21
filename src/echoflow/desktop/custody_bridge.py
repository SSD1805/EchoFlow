"""Narrow desktop adapter for custody-aware lifecycle operations.

The desktop may request plans and submit plan-bound confirmations. It never receives
filesystem paths and does not reimplement deletion or retention policy.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from echoflow.library.custody import (
    DeletionPlan,
    DeletionReceipt,
    DeletionScope,
    LibraryCustodyService,
    RetentionPlan,
    RetentionPolicy,
    RetentionReceipt,
)


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
    def unique_scopes(cls, values: tuple[DeletionScope, ...]) -> tuple[DeletionScope, ...]:
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
    documents = []
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
    """Dispatch bounded lifecycle operations after the outer bridge allowlist accepts them."""
    if method == "lifecycle.documents.list":
        _NoParams.model_validate(params)
        return _serialize_documents(service)
    if method == "lifecycle.deletion.plan":
        request = _DeletionPlanParams.model_validate(params)
        return _serialize_deletion_plan(
            service.plan_deletion(
                request.document_id,
                request.scopes,
                allow_source=request.allow_source,
            )
        )
    if method == "lifecycle.deletion.execute":
        request = _DeletionExecuteParams.model_validate(params)
        return _serialize_deletion_receipt(
            service.execute_deletion(
                request.document_id,
                request.scopes,
                confirmation_token=request.confirmation_token,
                allow_source=request.allow_source,
            )
        )
    if method == "lifecycle.retention.plan":
        request = _RetentionPlanParams.model_validate(params)
        return _serialize_retention_plan(
            service.plan_retention(
                RetentionPolicy(
                    execution_days=request.execution_days,
                    include_incomplete=request.include_incomplete,
                )
            )
        )
    if method == "lifecycle.retention.execute":
        request = _RetentionExecuteParams.model_validate(params)
        return _serialize_retention_receipt(
            service.execute_retention(
                RetentionPolicy(
                    execution_days=request.execution_days,
                    include_incomplete=request.include_incomplete,
                ),
                confirmation_token=request.confirmation_token,
            )
        )
    raise ValueError("Unsupported lifecycle desktop method")
