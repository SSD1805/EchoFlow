from collections.abc import Callable
from importlib import import_module
from pathlib import Path
from typing import Any, Protocol

from echoflow.model_management.models import InstalledSnapshot, ModelSpec


class ModelProvider(Protocol):
    def install(
        self,
        spec: ModelSpec,
        *,
        cache_root: Path,
        revision: str | None,
    ) -> InstalledSnapshot: ...

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
        snapshot_path = Path(
            hub.snapshot_download(
                repo_id=spec.repository_id,
                revision=revision,
                cache_dir=str(cache_root),
                local_files_only=False,
            )
        ).resolve(strict=False)
        if not snapshot_path.is_relative_to(cache_root.resolve(strict=False)):
            raise ValueError("model provider returned a snapshot outside the model cache")
        resolved_revision = snapshot_path.name
        if not resolved_revision:
            raise ValueError("model provider returned an unidentified snapshot")
        size_bytes = sum(
            path.stat().st_size for path in snapshot_path.rglob("*") if path.is_file()
        )
        return InstalledSnapshot(
            resolved_revision=resolved_revision,
            snapshot_path=snapshot_path,
            size_bytes=size_bytes,
        )

    def remove(
        self,
        snapshot: InstalledSnapshot,
        *,
        cache_root: Path,
    ) -> None:
        hub = self.module_loader("huggingface_hub")
        cache_info = hub.scan_cache_dir(cache_dir=cache_root)
        deletion = cache_info.delete_revisions(snapshot.resolved_revision)
        deletion.execute()
