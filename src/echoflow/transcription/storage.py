import shutil
from dataclasses import dataclass
from pathlib import Path

from echoflow.transcription.errors import ResourceAdmissionError


@dataclass(frozen=True, slots=True)
class StorageVolume:
    """Free-space view for the filesystem containing one planned path."""

    device_id: int
    anchor: str
    free_bytes: int

    def __post_init__(self) -> None:
        if self.free_bytes < 0:
            raise ValueError("free_bytes cannot be negative")

    @property
    def key(self) -> tuple[int, str]:
        return self.device_id, self.anchor.casefold()


@dataclass(frozen=True, slots=True)
class StorageAllocation:
    """Bytes one transcription attempt expects to create under one path."""

    path: Path
    required_bytes: int

    def __post_init__(self) -> None:
        if self.required_bytes < 0:
            raise ValueError("required_bytes cannot be negative")


class StorageCapacityInspector:
    """Inspect free bytes without requiring the planned destination to exist yet."""

    def inspect(self, path: Path) -> StorageVolume:
        target = path.expanduser().absolute()
        while not target.exists() and target != target.parent:
            target = target.parent
        try:
            details = target.stat()
            free_bytes = shutil.disk_usage(target).free
        except OSError as exc:
            raise ResourceAdmissionError(
                "Available disk space could not be determined"
            ) from exc
        return StorageVolume(
            device_id=details.st_dev,
            anchor=target.anchor,
            free_bytes=free_bytes,
        )


class StorageAdmissionPolicy:
    """Fail before work when known transcription allocations cannot fit safely."""

    def __init__(
        self,
        minimum_free_bytes: int,
        inspector: StorageCapacityInspector | None = None,
    ) -> None:
        if minimum_free_bytes < 0:
            raise ValueError("minimum_free_bytes cannot be negative")
        self.minimum_free_bytes = minimum_free_bytes
        self.inspector = inspector or StorageCapacityInspector()

    def admit(self, allocations: tuple[StorageAllocation, ...]) -> None:
        required_by_volume: dict[tuple[int, str], int] = {}
        free_by_volume: dict[tuple[int, str], int] = {}
        for allocation in allocations:
            volume = self.inspector.inspect(allocation.path)
            required_by_volume[volume.key] = (
                required_by_volume.get(volume.key, 0) + allocation.required_bytes
            )
            previous_free = free_by_volume.get(volume.key)
            free_by_volume[volume.key] = (
                volume.free_bytes
                if previous_free is None
                else min(previous_free, volume.free_bytes)
            )

        for key, required_bytes in required_by_volume.items():
            safe_required = required_bytes + self.minimum_free_bytes
            if free_by_volume[key] < safe_required:
                raise ResourceAdmissionError(
                    "Available disk space is below the planned job allocation"
                )
