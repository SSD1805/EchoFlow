from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ModelSpec:
    model_id: str
    engine: str
    repository_id: str
    estimated_cache_bytes: int
    quality_rank: int
    required_files: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("model_id", "engine", "repository_id"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} cannot be empty")
        if self.estimated_cache_bytes < 1:
            raise ValueError("estimated_cache_bytes must be positive")
        if self.quality_rank < 0:
            raise ValueError("quality_rank cannot be negative")
        if any(not name.strip() for name in self.required_files):
            raise ValueError("required model filenames cannot be empty")

    def to_dict(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "engine": self.engine,
            "repository_id": self.repository_id,
            "estimated_cache_bytes": self.estimated_cache_bytes,
            "quality_rank": self.quality_rank,
            "required_files": list(self.required_files),
        }


@dataclass(frozen=True, slots=True)
class InstalledSnapshot:
    resolved_revision: str
    snapshot_path: Path
    size_bytes: int
    verification: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "snapshot_path",
            self.snapshot_path.expanduser().resolve(strict=False),
        )
        if not self.resolved_revision.strip():
            raise ValueError("resolved_revision cannot be empty")
        if self.size_bytes < 1:
            raise ValueError("size_bytes must be positive")
        if not self.verification.strip():
            raise ValueError("verification cannot be empty")


@dataclass(frozen=True, slots=True)
class ManagedModelManifest:
    schema_version: int
    model_id: str
    engine: str
    repository_id: str
    requested_revision: str | None
    resolved_revision: str
    snapshot_path: Path
    size_bytes: int
    verification: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported model manifest schema version")
        for name in (
            "model_id",
            "engine",
            "repository_id",
            "resolved_revision",
            "verification",
        ):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} cannot be empty")
        if self.requested_revision is not None and not self.requested_revision.strip():
            raise ValueError("requested_revision cannot be empty")
        object.__setattr__(
            self,
            "snapshot_path",
            self.snapshot_path.expanduser().resolve(strict=False),
        )
        if self.size_bytes < 1:
            raise ValueError("size_bytes must be positive")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "model_id": self.model_id,
            "engine": self.engine,
            "repository_id": self.repository_id,
            "requested_revision": self.requested_revision,
            "resolved_revision": self.resolved_revision,
            "snapshot_path": str(self.snapshot_path),
            "size_bytes": self.size_bytes,
            "verification": self.verification,
        }

    @classmethod
    def from_dict(cls, document: dict[str, object]) -> "ManagedModelManifest":
        try:
            requested = document.get("requested_revision")
            return cls(
                schema_version=int(document["schema_version"]),
                model_id=str(document["model_id"]),
                engine=str(document["engine"]),
                repository_id=str(document["repository_id"]),
                requested_revision=(None if requested is None else str(requested)),
                resolved_revision=str(document["resolved_revision"]),
                snapshot_path=Path(str(document["snapshot_path"])),
                size_bytes=int(document["size_bytes"]),
                verification=str(document["verification"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("invalid model manifest") from exc


@dataclass(frozen=True, slots=True)
class ModelInventoryItem:
    spec: ModelSpec
    manifest: ManagedModelManifest | None = None

    @property
    def installed(self) -> bool:
        return self.manifest is not None

    def to_dict(self) -> dict[str, object]:
        return {
            "spec": self.spec.to_dict(),
            "installed": self.installed,
            "manifest": None if self.manifest is None else self.manifest.to_dict(),
        }
