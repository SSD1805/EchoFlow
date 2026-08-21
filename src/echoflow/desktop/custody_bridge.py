"""Trusted-host bridge for custody-aware lifecycle operations.

The webview may request plans and submit plan-bound confirmations through a fixed Tauri
command. It never receives filesystem paths and cannot choose a Python module, SQL query,
or arbitrary local file operation.
"""

from __future__ import annotations

import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from echoflow.app.app_container import AppContainer
from echoflow.core.errors import EchoFlowError
from echoflow.library.custody import (
    DeletionPlan,
    DeletionReceipt,
    DeletionScope,
    LibraryCustodyService,
    RetentionPlan,
    RetentionPolicy,
    RetentionReceipt,
)

_PROTOCOL_VERSION = 1
_MAX_REQUEST_BYTES = 128 * 1024
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
    """Dispatch only the lifecycle methods named by the closed request schema."""
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


def _success(request_id: str, result: object) -> dict[str, object]:
    return {
        "protocol_version": _PROTOCOL_VERSION,
        "request_id": request_id,
        "ok": True,
        "result": result,
        "error": None,
    }


def _failure(request_id: str, *, code: str, message: str) -> dict[str, object]:
    return {
        "protocol_version": _PROTOCOL_VERSION,
        "request_id": request_id,
        "ok": False,
        "result": None,
        "error": {"code": code, "message": message},
    }


def handle_request(payload: object, service: LibraryCustodyService) -> dict[str, object]:
    request_id = "unknown"
    if isinstance(payload, dict) and isinstance(payload.get("request_id"), str):
        request_id = payload["request_id"][:128]
    try:
        request = _Request.model_validate(payload)
        return _success(
            request.request_id,
            dispatch_custody(request.method, request.params, service),
        )
    except ValidationError:
        return _failure(
            request_id,
            code="invalid_request",
            message="Lifecycle request is invalid or incompatible",
        )
    except EchoFlowError as exc:
        return _failure(
            request_id,
            code=exc.code.value,
            message=exc.public_message,
        )
    except ValueError:
        return _failure(
            request_id,
            code="invalid_request",
            message="Lifecycle request is invalid",
        )
    except Exception:
        return _failure(
            request_id,
            code="internal_error",
            message="EchoFlow could not complete the local lifecycle request",
        )


def main() -> int:
    raw = sys.stdin.buffer.read(_MAX_REQUEST_BYTES + 1)
    if len(raw) > _MAX_REQUEST_BYTES:
        response = _failure(
            "unknown",
            code="invalid_request",
            message="Lifecycle request exceeded the safe size limit",
        )
    else:
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            response = _failure(
                "unknown",
                code="invalid_request",
                message="Lifecycle request was not valid JSON",
            )
        else:
            with redirect_stdout(sys.stderr):
                container = AppContainer()
                response = handle_request(payload, container.library_custody())
    sys.stdout.write(json.dumps(response, sort_keys=True))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
