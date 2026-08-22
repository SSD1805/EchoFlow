import io
import json
import sys

import pytest
from pydantic import ValidationError

from scholion.desktop.playback_bridge import dispatch_playback, handle_request, main
from scholion.library.errors import PlaybackAuthorizationError
from scholion.library.playback import PlaybackGrant


class PlaybackStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, float]] = []

    def authorize(
        self,
        document_id: str,
        *,
        expected_canonical_sha256: str,
        seek_seconds: float,
    ) -> PlaybackGrant:
        self.calls.append((document_id, expected_canonical_sha256, seek_seconds))
        return PlaybackGrant(
            document_id=document_id,
            canonical_sha256=expected_canonical_sha256,
            source_sha256="b" * 64,
            source_path="/private/evidence/interview.m4a",
            source_size_bytes=1234,
            source_modified_ns=42,
            duration_seconds=120.0,
            seek_seconds=seek_seconds,
            audio_stream_index=0,
            media_kind="audio",
            container_format="mov,mp4,m4a,3gp,3g2,mj2",
        )


class PlaybackFailureStub(PlaybackStub):
    def authorize(
        self,
        document_id: str,
        *,
        expected_canonical_sha256: str,
        seek_seconds: float,
    ) -> PlaybackGrant:
        raise PlaybackAuthorizationError("Original recording does not match")


class UnexpectedFailureStub(PlaybackStub):
    def authorize(
        self,
        document_id: str,
        *,
        expected_canonical_sha256: str,
        seek_seconds: float,
    ) -> PlaybackGrant:
        raise RuntimeError("private source path detail")


class BinaryInput:
    def __init__(self, payload: bytes) -> None:
        self.buffer = io.BytesIO(payload)


def _valid_request() -> dict[str, object]:
    return {
        "protocol_version": 1,
        "request_id": "playback-1",
        "method": "playback.authorize",
        "params": {
            "document_id": "interview-1",
            "canonical_sha256": "a" * 64,
            "seek_seconds": 12.5,
        },
    }


def test_dispatch_serializes_trusted_host_grant() -> None:
    stub = PlaybackStub()

    result = dispatch_playback(
        "playback.authorize",
        {
            "document_id": " interview-1 ",
            "canonical_sha256": "a" * 64,
            "seek_seconds": 12.5,
        },
        stub,  # type: ignore[arg-type]
    )

    assert isinstance(result, dict)
    assert result["source_path"] == "/private/evidence/interview.m4a"
    assert result["seek_seconds"] == 12.5
    assert result["media_kind"] == "audio"
    assert stub.calls == [("interview-1", "a" * 64, 12.5)]


@pytest.mark.parametrize(
    "params",
    [
        {"document_id": "x", "canonical_sha256": "A" * 64, "seek_seconds": 1.0},
        {"document_id": "x", "canonical_sha256": "a" * 63, "seek_seconds": 1.0},
        {"document_id": "   ", "canonical_sha256": "a" * 64, "seek_seconds": 1.0},
        {"document_id": "x", "canonical_sha256": "a" * 64, "seek_seconds": -1.0},
        {
            "document_id": "x",
            "canonical_sha256": "a" * 64,
            "seek_seconds": 1.0,
            "source_path": "/attacker/chosen/path",
        },
    ],
)
def test_dispatch_rejects_invalid_or_extra_values(params: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        dispatch_playback(
            "playback.authorize",
            params,
            PlaybackStub(),  # type: ignore[arg-type]
        )


def test_unknown_method_is_denied_before_service_dispatch() -> None:
    stub = PlaybackStub()
    response = handle_request(
        {
            "protocol_version": 1,
            "request_id": "playback-1",
            "method": "playback.open-path",
            "params": {"path": "attacker-chosen-secret"},
        },
        stub,  # type: ignore[arg-type]
    )

    assert response["ok"] is False
    assert response["error"] == {
        "code": "invalid_request",
        "message": "Playback authorization request is invalid",
    }
    assert stub.calls == []


def test_handle_request_translates_application_and_unexpected_failures() -> None:
    application = handle_request(
        _valid_request(),
        PlaybackFailureStub(),  # type: ignore[arg-type]
    )
    unexpected = handle_request(
        _valid_request(),
        UnexpectedFailureStub(),  # type: ignore[arg-type]
    )

    assert application["error"] == {
        "code": "internal_error",
        "message": "Original recording does not match",
    }
    assert unexpected["error"] == {
        "code": "internal_error",
        "message": "Scholion could not authorize local playback",
    }
    assert "private source path detail" not in str(unexpected)


def _run_main(monkeypatch: pytest.MonkeyPatch, payload: bytes) -> dict[str, object]:
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdin", BinaryInput(payload))
    monkeypatch.setattr(sys, "stdout", stdout)
    main()
    return json.loads(stdout.getvalue())


def test_main_rejects_invalid_json_without_constructing_services(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _run_main(monkeypatch, b"not-json")

    assert response["ok"] is False
    assert (
        response["error"]["message"]
        == "Playback authorization request was not valid JSON"
    )


def test_main_rejects_oversized_request_before_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _run_main(monkeypatch, b"x" * (128 * 1024 + 1))

    assert response["ok"] is False
    assert "safe size limit" in response["error"]["message"]
