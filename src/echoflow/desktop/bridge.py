"""Versioned stdin/stdout bridge used by the local Tauri desktop host.

The bridge intentionally exposes a small allowlist of application operations. It does not
provide arbitrary shell, filesystem, SQL, or database access to the frontend.
"""

from __future__ import annotations

import json
import sys
from contextlib import redirect_stdout
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from echoflow.app.app_container import AppContainer
from echoflow.core.errors import EchoFlowError
from echoflow.library.evidence import EvidenceContextSegment, EvidenceWord
from echoflow.library.locations import (
    LibraryLocationKind,
    LibraryLocationService,
    RecordingProcessingPolicy,
)
from echoflow.library.research_workspace import (
    ResearchNoteView,
    ResearchWorkspaceService,
    WorkspaceDiscoveryResponse,
)

_PROTOCOL_VERSION = 1
_MAX_REQUEST_BYTES = 128 * 1024


@dataclass(frozen=True, slots=True)
class DesktopServices:
    """Application services deliberately exposed to the desktop adapter."""

    locations: LibraryLocationService
    workspace: ResearchWorkspaceService


class _DesktopRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: Literal[1]
    request_id: str = Field(min_length=1, max_length=128)
    method: Literal[
        "locations.list",
        "locations.add",
        "recordings.discover",
        "transcripts.refresh",
        "workspace.discover",
        "workspace.research.overview",
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


class _DiscoverParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=4_096)
    limit: int = Field(default=20, ge=1, le=100)
    context_segments: int = Field(default=1, ge=0, le=10)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("search text cannot be blank")
        return stripped


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


def _serialize_word(word: EvidenceWord) -> dict[str, object]:
    return {
        "segment_id": word.segment_id,
        "word_index": word.word_index,
        "start_seconds": word.start_seconds,
        "end_seconds": word.end_seconds,
        "text": word.text,
        "speaker_ref": word.speaker_ref,
        "highlighted": word.highlighted,
    }


def _serialize_context_segment(segment: EvidenceContextSegment) -> dict[str, object]:
    return {
        "segment_id": segment.segment_id,
        "start_seconds": segment.start_seconds,
        "end_seconds": segment.end_seconds,
        "text": segment.text,
        "speaker_refs": list(segment.speaker_refs),
        "words": [_serialize_word(word) for word in segment.words],
        "is_result_segment": segment.is_result_segment,
        "lexical_match": segment.lexical_match,
    }


def _serialize_note(item: ResearchNoteView) -> dict[str, object]:
    return {
        "note_id": item.note.note_id,
        "body": item.note.body,
        "document_id": item.note.anchor.document_id,
        "canonical_sha256": item.note.anchor.canonical_sha256,
        "segment_ids": list(item.note.anchor.segment_ids),
        "start_seconds": item.note.anchor.start_seconds,
        "end_seconds": item.note.anchor.end_seconds,
        "current": item.current,
        "tags": list(item.tags),
        "collections": list(item.collections),
        "created_at": item.note.created_at,
        "updated_at": item.note.updated_at,
    }


def _serialize_discovery(report: WorkspaceDiscoveryResponse) -> dict[str, object]:
    return {
        "query": report.query,
        "total_count": report.total_count,
        "evidence": [
            {
                "document_id": item.located.evidence.document_id,
                "source_sha256": item.located.evidence.source_sha256,
                "canonical_sha256": item.located.evidence.canonical_sha256,
                "segment_ids": list(item.located.evidence.result_segment_ids),
                "text": item.located.passage.text,
                "start_seconds": item.located.evidence.start_seconds,
                "end_seconds": item.located.evidence.end_seconds,
                "seek_seconds": item.located.evidence.seek_seconds,
                "languages": list(item.located.passage.languages),
                "speakers": [
                    {
                        "speaker_ref": speaker.speaker_ref,
                        "display_label": speaker.display_label,
                    }
                    for speaker in item.located.speakers
                ],
                "matched_words": [
                    _serialize_word(word)
                    for word in item.located.evidence.matched_words
                ],
                "context_segments": [
                    _serialize_context_segment(segment)
                    for segment in item.located.evidence.context_segments
                ],
                "note_count": item.research.note_count,
                "tags": list(item.research.tags),
                "collections": list(item.research.collections),
            }
            for item in report.transcripts.results
        ],
        "notes": [_serialize_note(item) for item in report.notes],
        "tags": [{"tag_id": item.tag_id, "name": item.name} for item in report.tags],
        "collections": [
            {"collection_id": item.collection_id, "name": item.name}
            for item in report.collections
        ],
    }


def _serialize_research_overview(workspace: ResearchWorkspaceService) -> dict[str, object]:
    saved_searches = workspace.saved_searches(limit=200)
    return {
        "notes": [_serialize_note(item) for item in workspace.notes(limit=200)],
        "tags": [
            {"tag_id": item.tag_id, "name": item.name} for item in workspace.tags()
        ],
        "collections": [
            {"collection_id": item.collection_id, "name": item.name}
            for item in workspace.collections()
        ],
        "saved_searches": [
            {
                "saved_search_id": item.saved_search_id,
                "name": item.name,
                "description": item.description,
                "query_text": item.intent.query.text,
                "retrieval_mode": item.intent.mode.value,
                "updated_at": item.updated_at,
            }
            for item in saved_searches
        ],
    }


def _dispatch(request: _DesktopRequest, services: DesktopServices) -> object:
    if request.method == "locations.list":
        _NoParams.model_validate(request.params)
        return [item.to_dict() for item in services.locations.locations()]

    if request.method == "locations.add":
        add_params = _AddLocationParams.model_validate(request.params)
        location = services.locations.add(
            add_params.path,
            kind=add_params.kind,
            processing_policy=add_params.processing_policy,
        )
        return location.to_dict()

    if request.method == "recordings.discover":
        _NoParams.model_validate(request.params)
        discovery_report = services.locations.discover_recordings()
        return {
            "recordings": [
                {
                    "path": item.path,
                    "size_bytes": item.size_bytes,
                    "location_ids": list(item.location_ids),
                    "automatic_processing_requested": item.automatic_processing_requested,
                }
                for item in discovery_report.recordings
            ],
            "unavailable_location_ids": list(discovery_report.unavailable_location_ids),
        }

    if request.method == "workspace.discover":
        discover_params = _DiscoverParams.model_validate(request.params)
        discovery = services.workspace.discover(
            discover_params.text,
            limit=discover_params.limit,
            context_segments=discover_params.context_segments,
        )
        return _serialize_discovery(discovery)

    if request.method == "workspace.research.overview":
        _NoParams.model_validate(request.params)
        return _serialize_research_overview(services.workspace)

    refresh_params = _RefreshParams.model_validate(request.params)
    refresh_report = services.locations.refresh_transcript_locations(
        verify=refresh_params.verify
    )
    return {
        "backend_id": refresh_report.refresh.backend_id,
        "indexed_documents": refresh_report.refresh.indexed_documents,
        "added_document_ids": list(refresh_report.refresh.added_document_ids),
        "updated_document_ids": list(refresh_report.refresh.updated_document_ids),
        "removed_document_ids": list(refresh_report.refresh.removed_document_ids),
        "unchanged_document_ids": list(refresh_report.refresh.unchanged_document_ids),
        "skipped_files": refresh_report.refresh.skipped_files,
        "semantic_invalidated": refresh_report.refresh.semantic_invalidated,
        "verified_all_tracked": refresh_report.refresh.verified_all_tracked,
        "unavailable_location_ids": list(refresh_report.unavailable_location_ids),
    }


def handle_request(payload: object, services: DesktopServices) -> dict[str, object]:
    request_id = "unknown"
    if isinstance(payload, dict) and isinstance(payload.get("request_id"), str):
        request_id = payload["request_id"][:128]
    try:
        request = _DesktopRequest.model_validate(payload)
        return _success(request.request_id, _dispatch(request, services))
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
                container = AppContainer()
                services = DesktopServices(
                    locations=container.library_locations(),
                    workspace=container.research_workspace(),
                )
                response = handle_request(payload, services)
    sys.stdout.write(json.dumps(response, separators=(",", ":")))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
