from __future__ import annotations

import io
import json
import sys

import pytest

from scholion.desktop.host_protocol import (
    MAX_REQUEST_BYTES,
    BridgeHandler,
    failure_response,
    run_stdio_bridge,
    success_response,
)


class _BinaryInput:
    def __init__(self, payload: bytes) -> None:
        self.buffer = io.BytesIO(payload)


def _run(
    monkeypatch: pytest.MonkeyPatch,
    payload: bytes,
    handler: BridgeHandler,
) -> tuple[dict[str, object], str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    monkeypatch.setattr(sys, "stdin", _BinaryInput(payload))
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)
    result = run_stdio_bridge(
        handler,
        oversized_message="too large",
        invalid_json_message="bad json",
    )
    assert result == 0
    return json.loads(stdout.getvalue()), stderr.getvalue()


def test_response_builders_share_one_versioned_envelope() -> None:
    assert success_response("r-1", {"value": 7}) == {
        "protocol_version": 1,
        "request_id": "r-1",
        "ok": True,
        "result": {"value": 7},
        "error": None,
    }
    assert failure_response("r-2", code="invalid_request", message="nope") == {
        "protocol_version": 1,
        "request_id": "r-2",
        "ok": False,
        "result": None,
        "error": {"code": "invalid_request", "message": "nope"},
    }


def test_stdio_bridge_runs_only_valid_bounded_json_and_keeps_diagnostics_off_stdout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []

    def handler(payload: object) -> dict[str, object]:
        calls.append(payload)
        print("diagnostic from application service")
        return success_response("r-3", {"accepted": True})

    response, stderr = _run(monkeypatch, b'{"request_id":"r-3"}', handler)

    assert response["ok"] is True
    assert response["result"] == {"accepted": True}
    assert calls == [{"request_id": "r-3"}]
    assert "diagnostic from application service" in stderr


def test_stdio_bridge_rejects_invalid_json_before_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def handler(_payload: object) -> dict[str, object]:
        nonlocal called
        called = True
        return success_response("never", None)

    response, _ = _run(monkeypatch, b"not-json", handler)

    assert called is False
    assert response["error"] == {"code": "invalid_request", "message": "bad json"}


def test_stdio_bridge_rejects_oversized_input_before_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def handler(_payload: object) -> dict[str, object]:
        nonlocal called
        called = True
        return success_response("never", None)

    response, _ = _run(monkeypatch, b"x" * (MAX_REQUEST_BYTES + 1), handler)

    assert called is False
    assert response["error"] == {"code": "invalid_request", "message": "too large"}
