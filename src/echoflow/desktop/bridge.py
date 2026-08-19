"""Versioned stdin/stdout bridge used by the local Tauri desktop host.

The bridge intentionally exposes a small allowlist of application operations. It does not
provide arbitrary shell, filesystem, SQL, or database access to the frontend.
"""

from __future__ import annotations

import json
import sys
from contextlib import redirect_stdout
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from echoflow.app.app_container import AppContainer
from echoflow.core.errors import EchoFlowError
from echoflow.library.locations import (
    LibraryLocationKind,
    LibraryLocationService,
    RecordingProcessingPolicy,
)

_PROTOCOL_VERSION = 1
_MAX_REQUEST_BYTES = 128 * 1024


class _DesktopRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: Literal[1]
    request_id: str = Field(min_length=1, max_length=128)
    method: Literal[
        "locations.list",
        "locations.add",
        "recordings.discover",
        "transcripts.refresh",
    ]
    params: dict[str, object] = Field(default_factory=dict)


class _NoParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _AddLocationParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=32_768)
    kind: LibraryLocationKind
    processing_policy: RecordingProcessingPolicy = RecordingProcessingPolicy.MANUAL


class _RefreshParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verify: bool = False


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


def _dispatch(request: _DesktopRequest, service: LibraryLocationService) -> object:
    if request.method == "locations.list":
        _NoParams.model_validate(request.params)
        return [item.to_dict() for item in service.locations()]

    if request.method == "locations.add":
        params = _AddLocationParams.model_validate(request.params)
        location = service.add(
            params.path,
            kind=params.kind,
            processing_policy=params.processing_policy,
        )
        return location.to_dict()

    if request.method == "recordings.discover":
        _NoParams.model_validate(request.params)
        report = service.discover_recordings()
        return {
            "recordings": [
                {
                    "path": item.path,
                    "size_bytes": item.size_bytes,
                    "location_ids": list(item.location_ids),
                    "automatic_processing_requested": item.automatic_processing_requested,
                }
                for item in report.recordings
            ],
            "unavailable_location_ids": list(report.unavailable_location_ids),
        }

    params = _RefreshParams.model_validate(request.params)
    report = service.refresh_transcript_locations(verify=params.verify)
    return {
        "backend_id": report.refresh.backend_id,
        "indexed_documents": report.refresh.indexed_documents,
        "added_document_ids": list(report.refresh.added_document_ids),
        "updated_document_ids": list(report.refresh.updated_document_ids),
        "removed_document_ids": list(report.refresh.removed_document_ids),
        "unchanged_document_ids": list(report.refresh.unchanged_document_ids),
        "skipped_files": report.refresh.skipped_files,
        "semantic_invalidated": report.refresh.semantic_invalidated,
        "verified_all_tracked": report.refresh.verified_all_tracked,
        "unavailable_location_ids": list(report.unavailable_location_ids),
    }


def handle_request(payload: object, service: LibraryLocationService) -> dict[str, object]:
    request_id = "unknown"
    if isinstance(payload, dict) and isinstance(payload.get("request_id"), str):
        request_id = payload["request_id"][:128]
    try:
        request = _DesktopRequest.model_validate(payload)
        return _success(request.request_id, _dispatch(request, service))
    except ValidationError:
        return _failure(
            request_id,
            code="invalid_request",
            message="The desktop request was invalid or incompatible",
        )
    except EchoFlowError as exc:
        return _failure(
            request_id,
            code=exc.code.value,
            message=exc.public_message,
        )
    except Exception:
        return _failure(
            request_id,
            code="internal_error",
            message="EchoFlow could not complete the local desktop request",
        )


def main() -> int:
    raw = sys.stdin.buffer.read(_MAX_REQUEST_BYTES + 1)
    if len(raw) > _MAX_REQUEST_BYTES:
        response = _failure(
            "unknown",
            code="invalid_request",
            message="The desktop request exceeded the safe size limit",
        )
    else:
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            response = _failure(
                "unknown",
                code="invalid_request",
                message="The desktop request was not valid JSON",
            )
        else:
            with redirect_stdout(sys.stderr):
                service = AppContainer().library_locations()
                response = handle_request(payload, service)
    sys.stdout.write(json.dumps(response, separators=(",", ":")))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
