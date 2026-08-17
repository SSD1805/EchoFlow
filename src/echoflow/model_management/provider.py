from collections.abc import Callable
from importlib import import_module
from pathlib import Path
from typing import Any, Protocol

from echoflow.model_management.models import InstalledSnapshot, ModelSpec

_VERIFICATION_METHOD = "huggingface_snapshot_required_files_v1"


class ModelProvider(Protocol):
    def install(
        self,
        spec: ModelSpec,
        *,
        cache_root: Path,
        revision: str | None,
    ) -> InstalledSnapshot: ...

    def validate(
        self,
        spec: ModelSpec,
        snapshot: InstalledSnapshot,
        *,
        cache_root: Path,
    ) -> None: ...

    def remove(
        self,
        snapshot: InstalledSnapshot,
        *,
        cache_root: Path,
    ) -> None: ...


class HuggingFaceModelProvider:
    """Install immutable snapshots into the cache faster-whisper already consumes."""

    def __init__(
        self,
        *,
        module_loader: Callable[[str], Any] = import_module,
    ) -> None:
        self.module_loader = module_loader

    def install(
        self,
        spec: ModelSpec,
        *,
        cache_root: Path,
        revision: str | None,
    ) -> InstalledSnapshot:
        hub = self.module_loader("huggingface_hub")
        resolved_cache_root = cache_root.expanduser().resolve(strict=False)
        snapshot_path = Path(
            hub.snapshot_download(
                repo_id=spec.repository_id,
                revision=revision,
                cache_dir=str(resolved_cache_root),
                local_files_only=False,
            )
        ).resolve(strict=False)
        self._require_contained(snapshot_path, resolved_cache_root)
        resolved_revision = snapshot_path.name
        if not resolved_revision:
            raise ValueError("model provider returned an unidentified snapshot")
        size_bytes = sum(
            path.stat().st_size for path in snapshot_path.rglob("*") if path.is_file()
        )
        snapshot = InstalledSnapshot(
            resolved_revision=resolved_revision,
            snapshot_path=snapshot_path,
            size_bytes=size_bytes,
            verification=_VERIFICATION_METHOD,
        )
        self.validate(spec, snapshot, cache_root=resolved_cache_root)
        return snapshot

    def validate(
        self,
        spec: ModelSpec,
        snapshot: InstalledSnapshot,
        *,
        cache_root: Path,
    ) -> None:
        resolved_cache_root = cache_root.expanduser().resolve(strict=False)
        self._require_contained(snapshot.snapshot_path, resolved_cache_root)
        self._require_repository_identity(spec, snapshot, resolved_cache_root)
        if snapshot.verification != _VERIFICATION_METHOD:
            raise ValueError("model snapshot verification method is not supported")
        self._verify_required_files(snapshot.snapshot_path, spec.required_files)

    def remove(
        self,
        snapshot: InstalledSnapshot,
        *,
        cache_root: Path,
    ) -> None:
        resolved_cache_root = cache_root.expanduser().resolve(strict=False)
        self._require_contained(snapshot.snapshot_path, resolved_cache_root)
        hub = self.module_loader("huggingface_hub")
        cache_info = hub.scan_cache_dir(cache_dir=resolved_cache_root)
        deletion = cache_info.delete_revisions(snapshot.resolved_revision)
        deletion.execute()

    @staticmethod
    def _verify_required_files(
        snapshot_path: Path, required_files: tuple[str, ...]
    ) -> None:
        missing = tuple(
            filename
            for filename in required_files
            if not (snapshot_path / filename).is_file()
            or (snapshot_path / filename).stat().st_size < 1
        )
        if missing:
            raise ValueError(
                "model snapshot failed required-file verification: "
                + ", ".join(missing)
            )

    @staticmethod
    def _require_contained(path: Path, cache_root: Path) -> None:
        if not path.is_relative_to(cache_root):
            raise ValueError(
                "model provider returned a snapshot outside the model cache"
            )

    @staticmethod
    def _require_repository_identity(
        spec: ModelSpec,
        snapshot: InstalledSnapshot,
        cache_root: Path,
    ) -> None:
        repository_cache = (
            cache_root / f"models--{spec.repository_id.replace('/', '--')}"
        )
        expected_parent = repository_cache / "snapshots"
        if snapshot.snapshot_path.parent != expected_parent:
            raise ValueError("model snapshot does not match the declared repository")
        if snapshot.snapshot_path.name != snapshot.resolved_revision:
            raise ValueError("model snapshot path does not match the resolved revision")
