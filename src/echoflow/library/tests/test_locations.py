import json
from pathlib import Path

import pytest

from echoflow.interfaces.local_file_manager import LocalFileManager
from echoflow.library.errors import LibraryLocationError
from echoflow.library.locations import (
    JsonLibraryLocationStore,
    LibraryLocationKind,
    LibraryLocationService,
    RecordingProcessingPolicy,
)
from echoflow.library.service import LibraryRefreshReport
from echoflow.workspace.models import WorkspacePaths


class _TranscriptLibrary:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[Path, ...], bool]] = []

    def refresh(
        self,
        additional_paths: tuple[Path, ...] = (),
        *,
        verify: bool = False,
    ) -> LibraryRefreshReport:
        self.calls.append((additional_paths, verify))
        return LibraryRefreshReport(
            backend_id="test-index",
            indexed_documents=3,
            added_document_ids=(),
            updated_document_ids=(),
            removed_document_ids=(),
            unchanged_document_ids=("doc-a", "doc-b", "doc-c"),
            skipped_files=0,
            semantic_invalidated=False,
            verified_all_tracked=verify,
        )


def _paths(tmp_path: Path) -> WorkspacePaths:
    return WorkspacePaths(
        state_dir=tmp_path / "private-state",
        cache_dir=tmp_path / "private-cache",
        model_dir=tmp_path / "private-cache" / "models",
        output_dir=tmp_path / "public-output",
    )


def _service(tmp_path: Path) -> tuple[LibraryLocationService, _TranscriptLibrary]:
    paths = _paths(tmp_path)
    manager = LocalFileManager()
    library = _TranscriptLibrary()
    store = JsonLibraryLocationStore(
        paths.state_dir / "library" / "user-state" / "library-locations.json",
        manager,  # type: ignore[arg-type]
    )
    return (
        LibraryLocationService(
            store=store,
            transcript_library=library,  # type: ignore[arg-type]
            file_manager=manager,  # type: ignore[arg-type]
            paths=paths,
        ),
        library,
    )


def test_add_location_persists_normalized_private_state(tmp_path):
    root = tmp_path / "research transcripts"
    root.mkdir()
    service, _ = _service(tmp_path)

    location = service.add(
        root,
        kind=LibraryLocationKind.TRANSCRIPT_LIBRARY,
        location_id="location-transcripts",
    )

    assert location.path == str(root.resolve())
    assert location.processing_policy is RecordingProcessingPolicy.MANUAL
    assert service.locations() == (location,)
    state_path = (
        _paths(tmp_path).state_dir
        / "library"
        / "user-state"
        / "library-locations.json"
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["schema_version"] == 1
    assert state["locations"][0]["location_id"] == "location-transcripts"


def test_same_directory_can_have_distinct_transcript_and_recording_permissions(tmp_path):
    root = tmp_path / "research"
    root.mkdir()
    service, _ = _service(tmp_path)

    transcript = service.add(
        root,
        kind=LibraryLocationKind.TRANSCRIPT_LIBRARY,
        location_id="transcripts",
    )
    recording = service.add(
        root,
        kind=LibraryLocationKind.RECORDING_SOURCE,
        location_id="recordings",
    )

    assert {item.location_id for item in service.locations()} == {
        transcript.location_id,
        recording.location_id,
    }


def test_duplicate_permission_is_refused(tmp_path):
    root = tmp_path / "research"
    root.mkdir()
    service, _ = _service(tmp_path)
    service.add(root, kind=LibraryLocationKind.RECORDING_SOURCE)

    with pytest.raises(LibraryLocationError, match="already remembered"):
        service.add(root, kind=LibraryLocationKind.RECORDING_SOURCE)


def test_private_state_cache_and_models_cannot_be_registered(tmp_path):
    service, _ = _service(tmp_path)
    paths = _paths(tmp_path)
    paths.state_dir.mkdir(parents=True)
    paths.model_dir.mkdir(parents=True)

    for forbidden in (
        paths.state_dir,
        paths.state_dir / "jobs",
        paths.cache_dir,
        paths.model_dir,
    ):
        forbidden.mkdir(parents=True, exist_ok=True)
        with pytest.raises(LibraryLocationError, match="Private EchoFlow"):
            service.add(forbidden, kind=LibraryLocationKind.RECORDING_SOURCE)


def test_configured_output_directory_is_already_implicit(tmp_path):
    service, _ = _service(tmp_path)
    output = _paths(tmp_path).output_dir
    output.mkdir(parents=True)

    with pytest.raises(LibraryLocationError, match="already discovered automatically"):
        service.add(output, kind=LibraryLocationKind.TRANSCRIPT_LIBRARY)


def test_automatic_processing_is_explicit_and_recording_only(tmp_path):
    transcript_root = tmp_path / "transcripts"
    recording_root = tmp_path / "recordings"
    transcript_root.mkdir()
    recording_root.mkdir()
    service, _ = _service(tmp_path)

    with pytest.raises(LibraryLocationError, match="only to recording-source"):
        service.add(
            transcript_root,
            kind=LibraryLocationKind.TRANSCRIPT_LIBRARY,
            processing_policy=RecordingProcessingPolicy.AUTOMATIC,
        )

    recording = service.add(
        recording_root,
        kind=LibraryLocationKind.RECORDING_SOURCE,
        processing_policy=RecordingProcessingPolicy.AUTOMATIC,
        location_id="auto-recordings",
    )
    assert recording.processing_policy is RecordingProcessingPolicy.AUTOMATIC


def test_policy_can_be_changed_without_processing_anything(tmp_path):
    root = tmp_path / "recordings"
    root.mkdir()
    (root / "interview.wav").write_bytes(b"not-real-media")
    service, _ = _service(tmp_path)
    location = service.add(
        root,
        kind=LibraryLocationKind.RECORDING_SOURCE,
        location_id="source",
    )

    updated = service.set_processing_policy(
        location.location_id,
        processing_policy=RecordingProcessingPolicy.AUTOMATIC,
    )

    assert updated.processing_policy is RecordingProcessingPolicy.AUTOMATIC
    assert (root / "interview.wav").read_bytes() == b"not-real-media"


def test_recording_discovery_is_cheap_candidate_enumeration(tmp_path):
    root = tmp_path / "recordings"
    root.mkdir()
    (root / "Interview.MP4").write_bytes(b"video")
    (root / "audio.wav").write_bytes(b"audio")
    (root / "notes.txt").write_text("not media", encoding="utf-8")
    (root / ".hidden.mp3").write_bytes(b"hidden")
    service, _ = _service(tmp_path)
    service.add(
        root,
        kind=LibraryLocationKind.RECORDING_SOURCE,
        processing_policy=RecordingProcessingPolicy.AUTOMATIC,
        location_id="source",
    )

    report = service.discover_recordings()

    assert tuple(Path(item.path).name for item in report.recordings) == (
        "Interview.MP4",
        "audio.wav",
    )
    assert all(item.location_ids == ("source",) for item in report.recordings)
    assert len(report.automatic_candidates) == 2
    assert report.unavailable_location_ids == ()


def test_disabled_recording_location_is_not_discovered(tmp_path):
    root = tmp_path / "recordings"
    root.mkdir()
    (root / "interview.mp3").write_bytes(b"audio")
    service, _ = _service(tmp_path)
    location = service.add(
        root,
        kind=LibraryLocationKind.RECORDING_SOURCE,
        location_id="source",
    )
    service.set_enabled(location.location_id, enabled=False)

    assert service.discover_recordings().recordings == ()


def test_missing_removable_recording_root_is_reported_not_deleted(tmp_path):
    root = tmp_path / "removable"
    root.mkdir()
    service, _ = _service(tmp_path)
    service.add(
        root,
        kind=LibraryLocationKind.RECORDING_SOURCE,
        location_id="usb",
    )
    root.rmdir()

    report = service.discover_recordings()

    assert report.recordings == ()
    assert report.unavailable_location_ids == ("usb",)
    assert service.locations()[0].location_id == "usb"


def test_transcript_refresh_uses_available_enabled_roots_and_reports_missing(tmp_path):
    available = tmp_path / "available"
    missing = tmp_path / "missing"
    disabled = tmp_path / "disabled"
    available.mkdir()
    missing.mkdir()
    disabled.mkdir()
    service, library = _service(tmp_path)
    service.add(
        available,
        kind=LibraryLocationKind.TRANSCRIPT_LIBRARY,
        location_id="available",
    )
    service.add(
        missing,
        kind=LibraryLocationKind.TRANSCRIPT_LIBRARY,
        location_id="missing",
    )
    disabled_location = service.add(
        disabled,
        kind=LibraryLocationKind.TRANSCRIPT_LIBRARY,
        location_id="disabled",
    )
    service.set_enabled(disabled_location.location_id, enabled=False)
    missing.rmdir()

    result = service.refresh_transcript_locations(verify=True)

    assert library.calls == (((available.resolve(),), True),)
    assert result.unavailable_location_ids == ("missing",)
    assert result.refresh.verified_all_tracked is True


def test_remove_forgets_permission_without_deleting_directory(tmp_path):
    root = tmp_path / "research"
    root.mkdir()
    marker = root / "keep-me.txt"
    marker.write_text("user data", encoding="utf-8")
    service, _ = _service(tmp_path)
    location = service.add(
        root,
        kind=LibraryLocationKind.RECORDING_SOURCE,
        location_id="source",
    )

    service.remove(location.location_id)

    assert service.locations() == ()
    assert marker.read_text(encoding="utf-8") == "user data"


def test_corrupt_location_state_fails_closed(tmp_path):
    paths = _paths(tmp_path)
    state_path = (
        paths.state_dir / "library" / "user-state" / "library-locations.json"
    )
    state_path.parent.mkdir(parents=True)
    state_path.write_text('{"schema_version": 1, "locations": [', encoding="utf-8")
    service, _ = _service(tmp_path)

    with pytest.raises(LibraryLocationError, match="validated safely"):
        service.locations()


def test_unsupported_location_schema_fails_closed(tmp_path):
    paths = _paths(tmp_path)
    state_path = (
        paths.state_dir / "library" / "user-state" / "library-locations.json"
    )
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps({"schema_version": 999, "locations": []}),
        encoding="utf-8",
    )
    service, _ = _service(tmp_path)

    with pytest.raises(LibraryLocationError, match="unsupported EchoFlow schema"):
        service.locations()
