"""Trusted-host bridge for generation-bound local playback authorization.

This adapter returns a source path only to EchoFlow's fixed Rust host command. The Rust
host must convert it to an opaque media session before returning anything to the webview.
"""

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
from echoflow.library.playback import PlaybackAuthorizationService, PlaybackGrant

PlaybackMethod = Literal["playback.authorize"]


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: Literal[1]
    request_id: str = Field(min_length=1, max_length=128)
    method: PlaybackMethod
    params: dict[str, object] = Field(default_factory=dict)


class _AuthorizeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1, max_length=1_024)
    canonical_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    seek_seconds: float = Field(ge=0)

    @field_validator("document_id")
    @classmethod
    def strip_document_id(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("document_id cannot be blank")
        return stripped


def _serialize_grant(grant: PlaybackGrant) -> dict[str, object]:
    """Serialize the trusted-host grant. Never forward this object to React."""
    return {
        "document_id": grant.document_id,
        "canonical_sha256": grant.canonical_sha256,
        "source_sha256": grant.source_sha256,
        "source_path": grant.source_path,
        "source_size_bytes": grant.source_size_bytes,
        "source_modified_ns": grant.source_modified_ns,
        "duration_seconds": grant.duration_seconds,
        "seek_seconds": grant.seek_seconds,
        "audio_stream_index": grant.audio_stream_index,
        "media_kind": grant.media_kind,
        "container_format": grant.container_format,
    }


def dispatch_playback(
    method: str,
    params: dict[str, object],
    service: PlaybackAuthorizationService,
) -> object:
    if method != "playback.authorize":
        raise ValueError("Unsupported playback method")
    parsed = _AuthorizeParams.model_validate(params)
    return _serialize_grant(
        service.authorize(
            parsed.document_id,
            expected_canonical_sha256=parsed.canonical_sha256,
            seek_seconds=parsed.seek_seconds,
        )
    )


def handle_request(
    payload: object,
    service: PlaybackAuthorizationService,
) -> dict[str, object]:
    request_id = "unknown"
    try:
        request = _Request.model_validate(payload)
        request_id = request.request_id
        return success_response(
            request_id,
            dispatch_playback(request.method, request.params, service),
        )
    except ValidationError:
        return failure_response(
            request_id,
            code="invalid_request",
            message="Playback authorization request is invalid",
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
            message="EchoFlow could not authorize local playback",
        )


def main() -> int:
    return run_stdio_bridge(
        lambda payload: handle_request(
            payload, AppContainer().playback_authorization()
        ),
        oversized_message="Playback authorization request exceeded the safe size limit",
        invalid_json_message="Playback authorization request was not valid JSON",
    )


if __name__ == "__main__":
    raise SystemExit(main())
