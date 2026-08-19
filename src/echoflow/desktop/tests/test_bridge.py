from pathlib import Path

from echoflow.desktop.bridge import handle_request
from echoflow.library.errors import LibraryLocationError
from echoflow.library.locations import (
    DiscoveredRecording,
    LibraryLocation,
    LibraryLocationKind,
    ManagedTranscriptRefreshReport,
    RecordingDiscoveryReport,
    RecordingProcessingPolicy,
)
from echoflow.library.service import LibraryRefreshReport


class _LocationService:
    def __init__(self) -> None:
        self.location = LibraryLocation(
            location_id="location-one",
            path=str(Path("/research").resolve()),
            kind=LibraryLocationKind.RECORDING_SOURCE,
            enabled=True,
            processing_policy=RecordingProcessingPolicy.MANUAL,
            created_at="2026-08-19T19:20:00+00:00",
            updated_at="2026-08-19T19:20:00+00:00",
        )
        self.add_calls = []

    def locations(self):
        return (self.location,)

    def add(self, path, *, kind, processing_policy):
        self.add_calls.append((path, kind, processing_policy))
        return self.location

    def discover_recordings(self):
        return RecordingDiscoveryReport(
            recordings=(
                DiscoveredRecording(
                    path=str(Path("/research/interview.mp4").resolve()),
                    size_bytes=42,
                    location_ids=("location-one",),
                    automatic_processing_requested=False,
                ),
            ),
            unavailable_location_ids=(),
        )

    def refresh_transcript_locations(self, *, verify=False):
        return ManagedTranscriptRefreshReport(
            refresh=LibraryRefreshReport(
                backend_id="test",
                indexed_documents=1,
                added_document_ids=(),
                updated_document_ids=(),
                removed_document_ids=(),
                unchanged_document_ids=("doc-1",),
                skipped_files=0,
                semantic_invalidated=False,
                verified_all_tracked=verify,
            ),
            unavailable_location_ids=(),
        )


def _request(method, params=None):
    return {
        "protocol_version": 1,
        "request_id": "request-1",
        "method": method,
        "params": {} if params is None else params,
    }


def test_list_locations_serializes_only_typed_location_state():
    response = handle_request(_request("locations.list"), _LocationService())

    assert response["ok"] is True
    assert response["result"][0]["location_id"] == "location-one"
    assert response["result"][0]["kind"] == "recording-source"


def test_add_location_preserves_explicit_automatic_opt_in():
    service = _LocationService()
    response = handle_request(
        _request(
            "locations.add",
            {
                "path": "/research",
                "kind": "recording-source",
                "processing_policy": "automatic",
            },
        ),
        service,
    )

    assert response["ok"] is True
    assert service.add_calls == [
        (
            "/research",
            LibraryLocationKind.RECORDING_SOURCE,
            RecordingProcessingPolicy.AUTOMATIC,
        )
    ]


def test_unknown_method_fails_closed_without_dispatch():
    response = handle_request(_request("shell.exec"), _LocationService())

    assert response["ok"] is False
    assert response["error"] == {
        "code": "invalid_request",
        "message": "The desktop request was invalid or incompatible",
    }


def test_extra_params_fail_closed():
    response = handle_request(
        _request("locations.list", {"sql": "DROP TABLE transcripts"}),
        _LocationService(),
    )

    assert response["ok"] is False
    assert response["error"]["code"] == "invalid_request"


def test_safe_application_error_crosses_bridge_without_cause_details():
    class _FailingService(_LocationService):
        def add(self, path, *, kind, processing_policy):
            raise LibraryLocationError(
                "That location is not available",
                cause=RuntimeError("secret internal path detail"),
            )

    response = handle_request(
        _request(
            "locations.add",
            {
                "path": "/research",
                "kind": "recording-source",
                "processing_policy": "manual",
            },
        ),
        _FailingService(),
    )

    assert response["ok"] is False
    assert response["error"]["message"] == "That location is not available"
    assert "secret internal path detail" not in str(response)


def test_recording_discovery_does_not_claim_processing_occurred():
    response = handle_request(_request("recordings.discover"), _LocationService())

    assert response["ok"] is True
    assert response["result"]["recordings"] == [
        {
            "path": str(Path("/research/interview.mp4").resolve()),
            "size_bytes": 42,
            "location_ids": ["location-one"],
            "automatic_processing_requested": False,
        }
    ]


def test_transcript_refresh_respects_verify_flag():
    response = handle_request(
        _request("transcripts.refresh", {"verify": True}),
        _LocationService(),
    )

    assert response["ok"] is True
    assert response["result"]["verified_all_tracked"] is True
