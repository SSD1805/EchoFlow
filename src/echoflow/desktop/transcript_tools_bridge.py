"""Typed desktop bridge adapter for transcript and speaker tooling."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from echoflow.app.app_container import AppContainer
from echoflow.core.errors import EchoFlowError
from echoflow.desktop.host_protocol import (
    failure_response,
    run_stdio_bridge,
    success_response,
)
from echoflow.library.speaker_label_service import SpeakerRosterEntry
from echoflow.library.speaker_presentation import (
    SpeakerPresentationService,
    SpeakerPresentationSpan,
)
from echoflow.library.transcript_tools import TranscriptDetails, TranscriptToolsService
from echoflow.transcription.export import TranscriptExportFormat

TranscriptToolMethod = Literal[
    "transcripts.tools.inspect",
    "transcripts.tools.speakers",
    "transcripts.tools.speaker.set",
    "transcripts.tools.speaker.remove",
    "transcripts.tools.publish",
]


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: Literal[1]
    request_id: str = Field(min_length=1, max_length=128)
    method: TranscriptToolMethod
    params: dict[str, object] = Field(default_factory=dict)


class _GenerationParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1, max_length=1_024)
    canonical_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("document_id")
    @classmethod
    def strip_document_id(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("document_id cannot be blank")
        return stripped


class _SetSpeakerLabelParams(_GenerationParams):
    speaker_ref: str = Field(min_length=1, max_length=200)
    label: str = Field(min_length=1, max_length=200)

    @field_validator("speaker_ref", "label")
    @classmethod
    def strip_speaker_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("speaker values cannot be blank")
        return stripped


class _RemoveSpeakerLabelParams(_GenerationParams):
    speaker_ref: str = Field(min_length=1, max_length=200)

    @field_validator("speaker_ref")
    @classmethod
    def strip_speaker_ref(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("speaker_ref cannot be blank")
        return stripped


class _PublishParams(_GenerationParams):
    destination: str = Field(min_length=1, max_length=32_768)
    formats: tuple[TranscriptExportFormat, ...] = Field(min_length=1, max_length=3)

    @field_validator("destination")
    @classmethod
    def strip_destination(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("destination cannot be blank")
        return stripped


def _serialize_speaker(speaker: SpeakerRosterEntry) -> dict[str, object]:
    return {
        "speaker_ref": speaker.speaker_ref,
        "display_label": speaker.display_label,
        "display_name": speaker.display_name,
    }


def _serialize_details(details: TranscriptDetails) -> dict[str, object]:
    return {
        "document_id": details.document_id,
        "source_sha256": details.source_sha256,
        "canonical_sha256": details.canonical_sha256,
        "source_available": details.source_available,
        "source_size_bytes": details.source_size_bytes,
        "source_modified_ns": details.source_modified_ns,
        "container_format": details.container_format,
        "duration_seconds": details.duration_seconds,
        "audio_stream_index": details.audio_stream_index,
        "profile": details.profile,
        "provisional": details.provisional,
        "decode_strategy": details.decode_strategy,
        "detected_language": details.detected_language,
        "detected_languages": list(details.detected_languages),
        "segment_count": details.segment_count,
        "speaker_count": details.speaker_count,
        "engine": {
            "name": details.engine.name,
            "package_version": details.engine.package_version,
            "model": details.engine.model,
            "model_revision": details.engine.model_revision,
            "device": details.engine.device,
            "compute_type": details.engine.compute_type,
        },
        "diarization": (
            None
            if details.diarization is None
            else {
                "provider": details.diarization.provider,
                "package_version": details.diarization.package_version,
                "model": details.diarization.model,
                "model_revision": details.diarization.model_revision,
                "mode": details.diarization.mode,
            }
        ),
        "enhancement": (
            None
            if details.enhancement is None
            else {
                "provider": details.enhancement.provider,
                "provider_version": details.enhancement.provider_version,
                "operation": details.enhancement.operation,
                "model_id": details.enhancement.model_id,
                "model_revision": details.enhancement.model_revision,
            }
        ),
    }


def _serialize_span(span: SpeakerPresentationSpan) -> dict[str, object]:
    return span.to_dict()


def dispatch_transcript_tools(
    method: str,
    params: dict[str, object],
    service: TranscriptToolsService,
) -> object:
    if method == "transcripts.tools.inspect":
        parsed = _GenerationParams.model_validate(params)
        snapshot = service.inspect(
            parsed.document_id,
            expected_canonical_sha256=parsed.canonical_sha256,
        )
        return {
            "details": _serialize_details(snapshot.details),
            "speakers": [_serialize_speaker(item) for item in snapshot.speakers],
        }

    if method == "transcripts.tools.speakers":
        parsed = _GenerationParams.model_validate(params)
        spans = service.speaker_spans(
            parsed.document_id,
            expected_canonical_sha256=parsed.canonical_sha256,
        )
        return {"spans": [_serialize_span(span) for span in spans]}

    if method == "transcripts.tools.speaker.set":
        parsed = _SetSpeakerLabelParams.model_validate(params)
        speaker = service.set_speaker_label(
            parsed.document_id,
            expected_canonical_sha256=parsed.canonical_sha256,
            speaker_ref=parsed.speaker_ref,
            label=parsed.label,
        )
        return _serialize_speaker(speaker)

    if method == "transcripts.tools.speaker.remove":
        parsed = _RemoveSpeakerLabelParams.model_validate(params)
        removed = service.remove_speaker_label(
            parsed.document_id,
            expected_canonical_sha256=parsed.canonical_sha256,
            speaker_ref=parsed.speaker_ref,
        )
        return {"removed": removed}

    if method == "transcripts.tools.publish":
        parsed = _PublishParams.model_validate(params)
        published = service.publish(
            parsed.document_id,
            expected_canonical_sha256=parsed.canonical_sha256,
            destination=parsed.destination,
            formats=parsed.formats,
        )
        return {
            "canonical_sha256": published.canonical_sha256,
            "publications": [
                {"format": item.format.value, "filename": item.filename}
                for item in published.publications
            ],
        }

    raise ValueError("Unsupported transcript-tools method")


def _service(container: AppContainer) -> TranscriptToolsService:
    labels = container.speaker_label_store()
    return TranscriptToolsService(
        index=container.transcript_index(),
        speaker_labels=container.speaker_labels(),
        speaker_presentation=SpeakerPresentationService(
            index=container.transcript_index(),
            label_store=labels,
            file_manager=container.file_manager(),
        ),
        file_manager=container.file_manager(),
    )


def handle_request(
    payload: object, service: TranscriptToolsService
) -> dict[str, object]:
    request_id = "unknown"
    try:
        request = _Request.model_validate(payload)
        request_id = request.request_id
        return success_response(
            request_id,
            dispatch_transcript_tools(request.method, request.params, service),
        )
    except ValidationError:
        return failure_response(
            request_id,
            code="invalid_request",
            message="Transcript-tools request is invalid",
        )
    except EchoFlowError as exc:
        return failure_response(
            request_id,
            code=exc.code.value,
            message=exc.public_message,
        )
    except ValueError as exc:
        return failure_response(request_id, code="invalid_request", message=str(exc))
    except Exception:
        return failure_response(
            request_id,
            code="internal_error",
            message="EchoFlow could not complete that transcript-tools request",
        )


def main() -> int:
    return run_stdio_bridge(
        lambda payload: handle_request(payload, _service(AppContainer())),
        oversized_message="Transcript-tools request exceeded the safe size limit",
        invalid_json_message="Transcript-tools request was not valid JSON",
    )


if __name__ == "__main__":
    raise SystemExit(main())
