import json
from pathlib import Path
from typing import Protocol

from echoflow.model_management.catalog import ModelCatalog
from echoflow.model_management.errors import ModelManagementError
from echoflow.model_management.models import (
    InstalledSnapshot,
    ManagedModelManifest,
    ModelInventoryItem,
)
from echoflow.model_management.provider import ModelProvider


class ModelFileStore(Protocol):
    def ensure_directory_exists(
        self, directory_path: str | Path, *, private: bool = False
    ) -> None: ...

    def save_file(
        self, content: bytes, file_path: str | Path, *, private: bool = False
    ) -> None: ...

    def read_file(self, file_path: str | Path) -> bytes: ...
    def file_exists(self, file_path: str | Path) -> bool: ...
    def delete_file(self, file_path: str | Path) -> None: ...


class ModelManager:
    """Own EchoFlow's local model inventory and provenance manifests."""

    def __init__(
        self,
        *,
        catalog: ModelCatalog,
        provider: ModelProvider,
        file_store: ModelFileStore,
        model_root: Path,
    ) -> None:
        self.catalog = catalog
        self.provider = provider
        self.file_store = file_store
        self.model_root = model_root.expanduser().resolve(strict=False)
        self.cache_root = self.model_root / "faster-whisper"
        self.registry_root = self.model_root / "registry" / "faster-whisper"

    def inventory(self) -> tuple[ModelInventoryItem, ...]:
        self._prepare_roots()
        return tuple(
            ModelInventoryItem(spec=spec, manifest=self._manifest(spec.model_id))
            for spec in self.catalog.specs
        )

    def install(
        self, model_id: str, *, revision: str | None = None
    ) -> ManagedModelManifest:
        spec = self.catalog.require(model_id)
        if revision is not None and not revision.strip():
            raise ValueError("revision cannot be empty")
        self._prepare_roots()
        try:
            snapshot = self.provider.install(
                spec,
                cache_root=self.cache_root,
                revision=revision,
            )
            self._validate_snapshot(snapshot)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as exc:
            raise ModelManagementError(
                "The selected model could not be downloaded and verified", cause=exc
            ) from exc
        manifest = ManagedModelManifest(
            schema_version=1,
            model_id=spec.model_id,
            engine=spec.engine,
            repository_id=spec.repository_id,
            requested_revision=revision,
            resolved_revision=snapshot.resolved_revision,
            snapshot_path=snapshot.snapshot_path,
            size_bytes=snapshot.size_bytes,
            verification=snapshot.verification,
        )
        self.file_store.save_file(
            json.dumps(manifest.to_dict(), sort_keys=True).encode("utf-8"),
            self._manifest_path(model_id),
            private=True,
        )
        return manifest

    def remove(self, model_id: str) -> ManagedModelManifest:
        spec = self.catalog.require(model_id)
        self._prepare_roots()
        manifest = self._manifest(spec.model_id)
        if manifest is None:
            raise ValueError(f"model is not managed by EchoFlow: {model_id}")
        snapshot = InstalledSnapshot(
            resolved_revision=manifest.resolved_revision,
            snapshot_path=manifest.snapshot_path,
            size_bytes=manifest.size_bytes,
            verification=manifest.verification,
        )
        try:
            self.provider.remove(snapshot, cache_root=self.cache_root)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as exc:
            raise ModelManagementError(
                "The managed model could not be removed safely", cause=exc
            ) from exc
        self.file_store.delete_file(self._manifest_path(model_id))
        return manifest

    def is_installed(self, model_id: str) -> bool:
        self.catalog.require(model_id)
        self._prepare_roots()
        return self._manifest(model_id) is not None

    def _prepare_roots(self) -> None:
        self.file_store.ensure_directory_exists(self.model_root, private=True)
        self.file_store.ensure_directory_exists(self.cache_root, private=True)
        self.file_store.ensure_directory_exists(self.registry_root, private=True)

    def _manifest(self, model_id: str) -> ManagedModelManifest | None:
        path = self._manifest_path(model_id)
        if not self.file_store.file_exists(path):
            return None
        try:
            document = json.loads(self.file_store.read_file(path).decode("utf-8"))
            if not isinstance(document, dict):
                raise ValueError("model manifest must be an object")
            manifest = ManagedModelManifest.from_dict(document)
            self._validate_manifest(model_id, manifest)
            return manifest
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise ModelManagementError(
                "The local model registry is invalid", cause=exc
            ) from exc

    def _validate_manifest(
        self, model_id: str, manifest: ManagedModelManifest
    ) -> None:
        spec = self.catalog.require(model_id)
        if (
            manifest.model_id != spec.model_id
            or manifest.engine != spec.engine
            or manifest.repository_id != spec.repository_id
        ):
            raise ValueError("model manifest identity does not match the catalog")
        self._validate_snapshot(
            InstalledSnapshot(
                resolved_revision=manifest.resolved_revision,
                snapshot_path=manifest.snapshot_path,
                size_bytes=manifest.size_bytes,
                verification=manifest.verification,
            )
        )

    def _validate_snapshot(self, snapshot: InstalledSnapshot) -> None:
        if not snapshot.snapshot_path.is_relative_to(self.cache_root):
            raise ValueError("managed model snapshot escapes the model cache")

    def _manifest_path(self, model_id: str) -> Path:
        allowed = "abcdefghijklmnopqrstuvwxyz0123456789-_"
        if any(character not in allowed for character in model_id):
            raise ValueError("model ID cannot be used as a registry filename")
        return self.registry_root / f"{model_id}.json"
