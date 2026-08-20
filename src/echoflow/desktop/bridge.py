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
from echoflow.library.errors import ResearchStateError
from echoflow.library.evidence import EvidenceContextSegment, EvidenceWord
from echoflow.library.index import SearchQuery
from echoflow.library.locations import (
    LibraryLocationKind,
    LibraryLocationService,
    RecordingProcessingPolicy,
)
from echoflow.library.research_workspace import (
    ResearchNoteEvidenceView,
    ResearchNoteView,
    ResearchQueryFilters,
    ResearchWorkspaceService,
    WorkspaceDiscoveryResponse,
    WorkspaceSearchPassage,
    WorkspaceSearchResponse,
)
from echoflow.library.workspace_metadata import SavedSearch

_PROTOCOL_VERSION = 1
_MAX_REQUEST_BYTES = 128 * 1024
_DESKTOP_DEFAULT_SEARCH_LIMIT = 20
_DESKTOP_DEFAULT_CONTEXT_SEGMENTS = 1
_DESKTOP_RESEARCH_LIST_LIMIT = 200


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
        "workspace.research.notes.filter",
        "workspace.research.note.create",
        "workspace.research.note.update",
        "workspace.research.note.delete",
        "workspace.research.note.evidence",
        "workspace.research.saved_search.create",
        "workspace.research.saved_search.update",
        "workspace.research.saved_search.delete",
        "workspace.research.saved_search.run",
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


def _normalize_research_labels(values: tuple[str, ...]) -> tuple[str, ...]:
    normalized: dict[str, str] = {}
    for raw in values:
        value = raw.strip()
        if not value:
            raise ValueError("research labels cannot be blank")
        if len(value) > 200:
            raise ValueError("research labels cannot exceed 200 characters")
        if any(character in value for character in ("\r", "\n", "\x00")):
            raise ValueError("research labels contain unsupported control characters")
        normalized.setdefault(value.casefold(), value)
    return tuple(normalized[key] for key in sorted(normalized))


class _CreateResearchNoteParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1, max_length=1_024)
    canonical_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_ids: tuple[str, ...] = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1, max_length=50_000)
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(ge=0)

    @field_validator("document_id", "body")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value cannot be blank")
        return stripped

    @field_validator("segment_ids")
    @classmethod
    def validate_segment_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("segment IDs cannot be blank")
        if len(normalized) != len(set(normalized)):
            raise ValueError("segment IDs cannot repeat")
        return normalized


class _UpdateResearchNoteParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note_id: str = Field(min_length=1, max_length=200)
    expected_updated_at: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=50_000)
    tags: tuple[str, ...] = Field(default=(), max_length=100)
    collections: tuple[str, ...] = Field(default=(), max_length=100)

    @field_validator("note_id", "expected_updated_at", "body")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value cannot be blank")
        return stripped

    @field_validator("tags", "collections")
    @classmethod
    def validate_labels(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _normalize_research_labels(values)


class _FilterResearchNotesParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tags: tuple[str, ...] = Field(default=(), max_length=100)
    collections: tuple[str, ...] = Field(default=(), max_length=100)

    @field_validator("tags", "collections")
    @classmethod
    def validate_labels(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _normalize_research_labels(values)


class _DeleteResearchNoteParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note_id: str = Field(min_length=1, max_length=200)
    expected_updated_at: str = Field(min_length=1, max_length=200)

    @field_validator("note_id", "expected_updated_at")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value cannot be blank")
        return stripped


class _OpenResearchNoteEvidenceParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note_id: str = Field(min_length=1, max_length=200)
    context_segments: int = Field(default=1, ge=0, le=10)

    @field_validator("note_id")
    @classmethod
    def strip_note_id(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("note_id cannot be blank")
        return stripped


class _CreateSavedSearchParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    query_text: str = Field(min_length=1, max_length=4_096)
    description: str | None = Field(default=None, max_length=4_000)

    @field_validator("name", "query_text")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value cannot be blank")
        return stripped

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class _UpdateSavedSearchParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    saved_search_id: str = Field(min_length=1, max_length=200)
    expected_updated_at: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4_000)

    @field_validator("saved_search_id", "expected_updated_at", "name")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value cannot be blank")
        return stripped

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class _DeleteSavedSearchParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    saved_search_id: str = Field(min_length=1, max_length=200)
    expected_updated_at: str = Field(min_length=1, max_length=200)

    @field_validator("saved_search_id", "expected_updated_at")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value cannot be blank")
        return stripped


class _RunSavedSearchParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    saved_search_id: str = Field(min_length=1, max_length=200)

    @field_validator("saved_search_id")
    @classmethod
    def strip_saved_search_id(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("saved_search_id cannot be blank")
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


def _serialize_workspace_passage(item: WorkspaceSearchPassage) -> dict[str, object]:
    return {
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
            _serialize_word(word) for word in item.located.evidence.matched_words
        ],
        "context_segments": [
            _serialize_context_segment(segment)
            for segment in item.located.evidence.context_segments
        ],
        "note_count": item.research.note_count,
        "tags": list(item.research.tags),
        "collections": list(item.research.collections),
    }


def _serialize_discovery(report: WorkspaceDiscoveryResponse) -> dict[str, object]:
    return {
        "query": report.query,
        "total_count": report.total_count,
        "evidence": [
            _serialize_workspace_passage(item) for item in report.transcripts.results
        ],
        "notes": [_serialize_note(item) for item in report.notes],
        "tags": [{"tag_id": item.tag_id, "name": item.name} for item in report.tags],
        "collections": [
            {"collection_id": item.collection_id, "name": item.name}
            for item in report.collections
        ],
    }


def _serialize_saved_search(item: SavedSearch) -> dict[str, object]:
    return {
        "saved_search_id": item.saved_search_id,
        "name": item.name,
        "description": item.description,
        "query_text": item.intent.query.text,
        "retrieval_mode": item.intent.mode.value,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def _serialize_research_overview(
    workspace: ResearchWorkspaceService,
) -> dict[str, object]:
    saved_searches = workspace.saved_searches(limit=_DESKTOP_RESEARCH_LIST_LIMIT)
    return {
        "notes": [
            _serialize_note(item)
            for item in workspace.notes(limit=_DESKTOP_RESEARCH_LIST_LIMIT)
        ],
        "tags": [
            {"tag_id": item.tag_id, "name": item.name} for item in workspace.tags()
        ],
        "collections": [
            {"collection_id": item.collection_id, "name": item.name}
            for item in workspace.collections()
        ],
        "saved_searches": [_serialize_saved_search(item) for item in saved_searches],
    }


def _serialize_note_evidence(item: ResearchNoteEvidenceView) -> dict[str, object]:
    evidence = item.located.evidence
    result_ids = set(evidence.result_segment_ids)
    text = " ".join(
        segment.text
        for segment in evidence.context_segments
        if segment.segment_id in result_ids
    )
    return {
        "note_id": item.note.note.note_id,
        "current": item.note.current,
        "evidence": {
            "document_id": evidence.document_id,
            "source_sha256": evidence.source_sha256,
            "canonical_sha256": evidence.canonical_sha256,
            "segment_ids": list(evidence.result_segment_ids),
            "text": text,
            "start_seconds": evidence.start_seconds,
            "end_seconds": evidence.end_seconds,
            "seek_seconds": evidence.seek_seconds,
            "languages": [],
            "speakers": [
                {
                    "speaker_ref": speaker.speaker_ref,
                    "display_label": speaker.display_label,
                }
                for speaker in item.located.speakers
            ],
            "matched_words": [_serialize_word(word) for word in evidence.matched_words],
            "context_segments": [
                _serialize_context_segment(segment)
                for segment in evidence.context_segments
            ],
            "note_count": 1,
            "tags": list(item.note.tags),
            "collections": list(item.note.collections),
        },
    }


def _serialize_saved_search_run(
    saved: SavedSearch,
    report: WorkspaceSearchResponse,
) -> dict[str, object]:
    return {
        "saved_search": _serialize_saved_search(saved),
        "query": report.navigation.retrieval.query.text,
        "evidence": [_serialize_workspace_passage(item) for item in report.results],
    }


def _filter_research_notes(
    params: _FilterResearchNotesParams,
    workspace: ResearchWorkspaceService,
) -> dict[str, object]:
    filters = ResearchQueryFilters(
        tags=params.tags,
        collections=params.collections,
    )
    notes = workspace.notes(filters=filters, limit=_DESKTOP_RESEARCH_LIST_LIMIT)
    return {
        "tags": list(filters.tags),
        "collections": list(filters.collections),
        "notes": [_serialize_note(item) for item in notes],
    }


def _create_research_note(
    params: _CreateResearchNoteParams,
    workspace: ResearchWorkspaceService,
) -> dict[str, object]:
    document = next(
        (
            item
            for item in workspace.transcript_library.documents()
            if item.document_id == params.document_id
        ),
        None,
    )
    if document is None:
        raise ResearchStateError("Transcript is not present in the local library")
    if document.canonical_sha256 != params.canonical_sha256:
        raise ResearchStateError(
            "Transcript evidence changed before the note could be saved; reopen verified evidence"
        )
    note = workspace.add_note(
        params.document_id,
        params.segment_ids,
        params.body,
        start_seconds=params.start_seconds,
        end_seconds=params.end_seconds,
    )
    return _serialize_note(note)


def _update_research_note(
    params: _UpdateResearchNoteParams,
    workspace: ResearchWorkspaceService,
) -> dict[str, object]:
    note = workspace.replace_note(
        params.note_id,
        params.body,
        tags=params.tags,
        collections=params.collections,
        expected_updated_at=params.expected_updated_at,
    )
    return _serialize_note(note)


def _delete_research_note(
    params: _DeleteResearchNoteParams,
    workspace: ResearchWorkspaceService,
) -> dict[str, object]:
    workspace.delete_note(
        params.note_id,
        expected_updated_at=params.expected_updated_at,
    )
    return {"note_id": params.note_id, "deleted": True}


def _open_research_note_evidence(
    params: _OpenResearchNoteEvidenceParams,
    workspace: ResearchWorkspaceService,
) -> dict[str, object]:
    opened = workspace.open_note_evidence(
        params.note_id,
        context_segments=params.context_segments,
    )
    return _serialize_note_evidence(opened)


def _create_saved_search(
    params: _CreateSavedSearchParams,
    workspace: ResearchWorkspaceService,
) -> dict[str, object]:
    saved = workspace.save_search(
        params.name,
        SearchQuery(params.query_text, limit=_DESKTOP_DEFAULT_SEARCH_LIMIT),
        context_segments=_DESKTOP_DEFAULT_CONTEXT_SEGMENTS,
        description=params.description,
    )
    return _serialize_saved_search(saved)


def _update_saved_search(
    params: _UpdateSavedSearchParams,
    workspace: ResearchWorkspaceService,
) -> dict[str, object]:
    saved = workspace.rename_saved_search(
        params.saved_search_id,
        name=params.name,
        description=params.description,
        expected_updated_at=params.expected_updated_at,
    )
    return _serialize_saved_search(saved)


def _delete_saved_search(
    params: _DeleteSavedSearchParams,
    workspace: ResearchWorkspaceService,
) -> dict[str, object]:
    workspace.delete_saved_search(
        params.saved_search_id,
        expected_updated_at=params.expected_updated_at,
    )
    return {"saved_search_id": params.saved_search_id, "deleted": True}


def _run_saved_search(
    params: _RunSavedSearchParams,
    workspace: ResearchWorkspaceService,
) -> dict[str, object]:
    saved = workspace.saved_search(params.saved_search_id)
    if saved is None:
        raise ResearchStateError("Saved search does not exist")
    report = workspace.run_saved_search(saved.saved_search_id)
    return _serialize_saved_search_run(saved, report)


def _dispatch_research_note(
    request: _DesktopRequest,
    workspace: ResearchWorkspaceService,
) -> object:
    if request.method == "workspace.research.note.create":
        create_params = _CreateResearchNoteParams.model_validate(request.params)
        return _create_research_note(create_params, workspace)
    if request.method == "workspace.research.note.update":
        update_params = _UpdateResearchNoteParams.model_validate(request.params)
        return _update_research_note(update_params, workspace)
    if request.method == "workspace.research.note.delete":
        delete_params = _DeleteResearchNoteParams.model_validate(request.params)
        return _delete_research_note(delete_params, workspace)
    if request.method == "workspace.research.note.evidence":
        evidence_params = _OpenResearchNoteEvidenceParams.model_validate(request.params)
        return _open_research_note_evidence(evidence_params, workspace)
    raise ValueError("Unsupported research note desktop method")


def _dispatch_saved_search(
    request: _DesktopRequest,
    workspace: ResearchWorkspaceService,
) -> object:
    if request.method == "workspace.research.saved_search.create":
        create_params = _CreateSavedSearchParams.model_validate(request.params)
        return _create_saved_search(create_params, workspace)
    if request.method == "workspace.research.saved_search.update":
        update_params = _UpdateSavedSearchParams.model_validate(request.params)
        return _update_saved_search(update_params, workspace)
    if request.method == "workspace.research.saved_search.delete":
        delete_params = _DeleteSavedSearchParams.model_validate(request.params)
        return _delete_saved_search(delete_params, workspace)
    if request.method == "workspace.research.saved_search.run":
        run_params = _RunSavedSearchParams.model_validate(request.params)
        return _run_saved_search(run_params, workspace)
    raise ValueError("Unsupported saved-search desktop method")


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

    if request.method == "workspace.research.notes.filter":
        filter_params = _FilterResearchNotesParams.model_validate(request.params)
        return _filter_research_notes(filter_params, services.workspace)

    if request.method.startswith("workspace.research.note."):
        return _dispatch_research_note(request, services.workspace)

    if request.method.startswith("workspace.research.saved_search."):
        return _dispatch_saved_search(request, services.workspace)

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
