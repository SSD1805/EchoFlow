"""Durable user-selected library roots and recording discovery policy.

Location state is application-managed private state. Remembering a directory grants
EchoFlow permission to discover files there at explicit lifecycle points; it never grants
implicit permission to run ASR. Automatic processing is a durable opt-in policy consumed
by a higher-level application adapter, not an action performed by this service.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol, runtime_checkable
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, ValidationError

from echoflow.core.file_manager_facade import FileManagerFacade
from echoflow.library.errors import LibraryLocationError
from echoflow.library.service import LibraryRefreshReport, TranscriptLibraryService
from echoflow.workspace.models import WorkspacePaths

_STATE_SCHEMA_VERSION = 1
_MAX_LOCATIONS = 1_000
_MAX_DISCOVERED_RECORDINGS = 10_000
_RECORDING_EXTENSIONS = frozenset(
    {
        ".aac",
        ".aiff",
        ".avi",
        ".flac",
        ".m4a",
        ".m4v",
        ".mkv",
        ".mov",
        ".mp3",
        ".mp4",
        ".mpeg",
        ".mpg",
        ".ogg",
        ".opus",
        ".wav",
        ".webm",
        ".wma",
    }
)


class LibraryLocationKind(StrEnum):
    """Purpose granted to one remembered local directory."""

    TRANSCRIPT_LIBRARY = "transcript-library"
    RECORDING_SOURCE = "recording-source"


class RecordingProcessingPolicy(StrEnum):
    """What a higher-level adapter may do after discovering a recording."""

    MANUAL = "manual"
    AUTOMATIC = "automatic"


@dataclass(frozen=True, slots=True)
class LibraryLocation:
    """One durable directory permission chosen by the user."""

    location_id: str
    path: str
    kind: LibraryLocationKind
    enabled: bool
    processing_policy: RecordingProcessingPolicy
    created_at: str
    updated_at: str

    def __post_init__(self) -> None:
        if not self.location_id.strip():
            raise ValueError("location_id cannot be empty")
        if not self.path.strip() or "\x00" in self.path:
            raise ValueError("location path cannot be empty or contain NUL")
        if not Path(self.path).is_absolute():
            raise ValueError("location path must be absolute")
        if (
            self.kind is LibraryLocationKind.TRANSCRIPT_LIBRARY
            and self.processing_policy is not RecordingProcessingPolicy.MANUAL
        ):
            raise ValueError("transcript library locations cannot request processing")
        if not self.created_at.strip() or not self.updated_at.strip():
            raise ValueError("location timestamps cannot be empty")

    def to_dict(self) -> dict[str, object]:
        return {
            "location_id": self.location_id,
            "path": self.path,
            "kind": self.kind.value,
            "enabled": self.enabled,
            "processing_policy": self.processing_policy.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True, slots=True)
class DiscoveredRecording:
    """Cheap recording candidate discovery without opening or hashing media bytes."""

    path: str
    size_bytes: int
    location_ids: tuple[str, ...]
    automatic_processing_requested: bool

    def __post_init__(self) -> None:
        if not self.path.strip() or not Path(self.path).is_absolute():
            raise ValueError("discovered recording path must be absolute")
        if self.size_bytes < 1:
            raise ValueError("discovered recording size must be positive")
        if not self.location_ids or any(not item.strip() for item in self.location_ids):
            raise ValueError("discovered recording requires location provenance")


@dataclass(frozen=True, slots=True)
class RecordingDiscoveryReport:
    recordings: tuple[DiscoveredRecording, ...]
    unavailable_location_ids: tuple[str, ...]

    @property
    def automatic_candidates(self) -> tuple[DiscoveredRecording, ...]:
        return tuple(
            item for item in self.recordings if item.automatic_processing_requested
        )


@dataclass(frozen=True, slots=True)
class ManagedTranscriptRefreshReport:
    refresh: LibraryRefreshReport
    unavailable_location_ids: tuple[str, ...]


@runtime_checkable
class LibraryLocationStore(Protocol):
    def locations(self) -> tuple[LibraryLocation, ...]: ...

    def replace_all(self, locations: tuple[LibraryLocation, ...]) -> None: ...


class _StoredLocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location_id: str
    path: str
    kind: LibraryLocationKind
    enabled: bool
    processing_policy: RecordingProcessingPolicy
    created_at: str
    updated_at: str


class _StoredState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int
    locations: list[_StoredLocation]


class JsonLibraryLocationStore:
    """Private atomic JSON authority for application-managed location preferences."""

    def __init__(self, path: Path, file_manager: FileManagerFacade) -> None:
        self.path = path.expanduser().resolve(strict=False)
        self.file_manager = file_manager

    def locations(self) -> tuple[LibraryLocation, ...]:
        if not self.file_manager.file_exists(self.path):
            return ()
        try:
            state = _StoredState.model_validate(
                json.loads(self.file_manager.read_file(self.path))
            )
            if state.schema_version != _STATE_SCHEMA_VERSION:
                raise LibraryLocationError(
                    "Library location state was written by an unsupported EchoFlow schema"
                )
            locations = tuple(
                LibraryLocation(
                    location_id=item.location_id,
                    path=item.path,
                    kind=item.kind,
                    enabled=item.enabled,
                    processing_policy=item.processing_policy,
                    created_at=item.created_at,
                    updated_at=item.updated_at,
                )
                for item in state.locations
            )
            self._validate_unique(locations)
            return tuple(sorted(locations, key=self._sort_key))
        except LibraryLocationError:
            raise
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
            ValidationError,
            ValueError,
        ) as exc:
            raise LibraryLocationError(
                "Library location state could not be validated safely",
                cause=exc,
            ) from exc

    def replace_all(self, locations: tuple[LibraryLocation, ...]) -> None:
        if len(locations) > _MAX_LOCATIONS:
            raise LibraryLocationError(
                f"EchoFlow cannot remember more than {_MAX_LOCATIONS} library locations"
            )
        self._validate_unique(locations)
        self.file_manager.ensure_directory_exists(self.path.parent, private=True)
        payload = (
            json.dumps(
                {
                    "schema_version": _STATE_SCHEMA_VERSION,
                    "locations": [
                        item.to_dict()
                        for item in sorted(locations, key=self._sort_key)
                    ],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
        self.file_manager.save_file(payload, self.path, private=True)

    @staticmethod
    def _validate_unique(locations: tuple[LibraryLocation, ...]) -> None:
        ids = tuple(item.location_id for item in locations)
        if len(ids) != len(set(ids)):
            raise LibraryLocationError("Library location state contains duplicate IDs")
        keys = tuple((item.kind, item.path.casefold()) for item in locations)
        if len(keys) != len(set(keys)):
            raise LibraryLocationError(
                "Library location state contains duplicate directory permissions"
            )

    @staticmethod
    def _sort_key(item: LibraryLocation) -> tuple[str, str, str]:
        return (item.kind.value, item.path.casefold(), item.location_id)


class LibraryLocationService:
    """Manage remembered roots while keeping discovery separate from processing."""

    def __init__(
        self,
        *,
        store: LibraryLocationStore,
        transcript_library: TranscriptLibraryService,
        file_manager: FileManagerFacade,
        paths: WorkspacePaths,
    ) -> None:
        self.store = store
        self.transcript_library = transcript_library
        self.file_manager = file_manager
        self.paths = paths

    def locations(self) -> tuple[LibraryLocation, ...]:
        return self.store.locations()

    def add(
        self,
        path: str | Path,
        *,
        kind: LibraryLocationKind,
        processing_policy: RecordingProcessingPolicy = RecordingProcessingPolicy.MANUAL,
        enabled: bool = True,
        location_id: str | None = None,
    ) -> LibraryLocation:
        resolved = self._validate_new_root(path)
        if (
            kind is LibraryLocationKind.TRANSCRIPT_LIBRARY
            and processing_policy is not RecordingProcessingPolicy.MANUAL
        ):
            raise LibraryLocationError(
                "Automatic processing applies only to recording-source locations"
            )
        existing = self.store.locations()
        if any(
            item.kind is kind and self._resolved(item.path) == resolved
            for item in existing
        ):
            raise LibraryLocationError(
                "That directory is already remembered for this library purpose"
            )
        now = self._now()
        location = LibraryLocation(
            location_id=(location_id or f"location-{uuid4().hex}").strip(),
            path=str(resolved),
            kind=kind,
            enabled=enabled,
            processing_policy=processing_policy,
            created_at=now,
            updated_at=now,
        )
        self.store.replace_all(existing + (location,))
        return location

    def remove(self, location_id: str) -> None:
        current = self.store.locations()
        retained = tuple(item for item in current if item.location_id != location_id)
        if len(retained) == len(current):
            raise LibraryLocationError("Library location does not exist")
        self.store.replace_all(retained)

    def set_enabled(self, location_id: str, *, enabled: bool) -> LibraryLocation:
        return self._replace_location(location_id, enabled=enabled)

    def set_processing_policy(
        self,
        location_id: str,
        *,
        processing_policy: RecordingProcessingPolicy,
    ) -> LibraryLocation:
        current = self._require_location(location_id)
        if (
            current.kind is LibraryLocationKind.TRANSCRIPT_LIBRARY
            and processing_policy is not RecordingProcessingPolicy.MANUAL
        ):
            raise LibraryLocationError(
                "Transcript library locations cannot request automatic processing"
            )
        return self._replace_location(
            location_id,
            processing_policy=processing_policy,
        )

    def refresh_transcript_locations(
        self, *, verify: bool = False
    ) -> ManagedTranscriptRefreshReport:
        roots: list[Path] = []
        unavailable: list[str] = []
        for location in self.store.locations():
            if not location.enabled or location.kind is not LibraryLocationKind.TRANSCRIPT_LIBRARY:
                continue
            root = self._resolved(location.path)
            if not root.is_dir():
                unavailable.append(location.location_id)
                continue
            roots.append(root)
        report = self.transcript_library.refresh(tuple(roots), verify=verify)
        return ManagedTranscriptRefreshReport(
            refresh=report,
            unavailable_location_ids=tuple(sorted(unavailable)),
        )

    def discover_recordings(self) -> RecordingDiscoveryReport:
        discovered: dict[Path, tuple[int, set[str], bool]] = {}
        unavailable: list[str] = []
        for location in self.store.locations():
            if not location.enabled or location.kind is not LibraryLocationKind.RECORDING_SOURCE:
                continue
            root = self._resolved(location.path)
            if not root.is_dir():
                unavailable.append(location.location_id)
                continue
            for candidate in self.file_manager.list_files(root):
                resolved = candidate.resolve(strict=False)
                if resolved.name.startswith(".") or resolved.suffix.lower() not in _RECORDING_EXTENSIONS:
                    continue
                metadata = self.file_manager.get_file_metadata(resolved)
                size = int(metadata["size"])
                if size < 1:
                    continue
                previous = discovered.get(resolved)
                ids = set() if previous is None else set(previous[1])
                ids.add(location.location_id)
                automatic = (
                    location.processing_policy is RecordingProcessingPolicy.AUTOMATIC
                    or (False if previous is None else previous[2])
                )
                discovered[resolved] = (size, ids, automatic)
                if len(discovered) > _MAX_DISCOVERED_RECORDINGS:
                    raise LibraryLocationError(
                        "Recording discovery exceeded the safe candidate limit"
                    )
        recordings = tuple(
            DiscoveredRecording(
                path=str(path),
                size_bytes=value[0],
                location_ids=tuple(sorted(value[1])),
                automatic_processing_requested=value[2],
            )
            for path, value in sorted(discovered.items(), key=lambda item: str(item[0]))
        )
        return RecordingDiscoveryReport(
            recordings=recordings,
            unavailable_location_ids=tuple(sorted(unavailable)),
        )

    def _replace_location(
        self,
        location_id: str,
        *,
        enabled: bool | None = None,
        processing_policy: RecordingProcessingPolicy | None = None,
    ) -> LibraryLocation:
        current = self.store.locations()
        target = self._require_location(location_id, current=current)
        updated = replace(
            target,
            enabled=target.enabled if enabled is None else enabled,
            processing_policy=(
                target.processing_policy
                if processing_policy is None
                else processing_policy
            ),
            updated_at=self._now(),
        )
        self.store.replace_all(
            tuple(updated if item.location_id == location_id else item for item in current)
        )
        return updated

    def _require_location(
        self,
        location_id: str,
        *,
        current: tuple[LibraryLocation, ...] | None = None,
    ) -> LibraryLocation:
        if not location_id.strip():
            raise ValueError("location_id cannot be empty")
        for item in current if current is not None else self.store.locations():
            if item.location_id == location_id:
                return item
        raise LibraryLocationError("Library location does not exist")

    def _validate_new_root(self, path: str | Path) -> Path:
        resolved = self._resolved(path)
        if not resolved.is_dir():
            raise LibraryLocationError(
                "A remembered library location must be an existing local directory"
            )
        private_roots = (
            self.paths.state_dir.resolve(strict=False),
            self.paths.cache_dir.resolve(strict=False),
            self.paths.model_dir.resolve(strict=False),
        )
        if any(resolved == root or root in resolved.parents for root in private_roots):
            raise LibraryLocationError(
                "Private EchoFlow application state cannot be registered as a library location"
            )
        if resolved == self.paths.output_dir.resolve(strict=False):
            raise LibraryLocationError(
                "EchoFlow's configured output directory is already discovered automatically"
            )
        return resolved

    @staticmethod
    def _resolved(path: str | Path) -> Path:
        return Path(path).expanduser().resolve(strict=False)

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()
