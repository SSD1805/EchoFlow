from pathlib import Path

import pytest

from echoflow.model_management.catalog import ModelCatalog
from echoflow.model_management.errors import ModelManagementError
from echoflow.model_management.models import InstalledSnapshot, ModelSpec
from echoflow.model_management.service import ModelManager


class MinimalStore:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def ensure_directory_exists(
        self, directory_path: str | Path, *, private: bool = False
    ) -> None:
        assert private
        self.events.append("mkdir")

    def save_file(
        self, content: bytes, file_path: str | Path, *, private: bool = False
    ) -> None:
        assert private
        self.events.append("manifest")

    def read_file(self, file_path: str | Path) -> bytes:
        raise AssertionError("no registry read expected")

    def file_exists(self, file_path: str | Path) -> bool:
        return False

    def delete_file(self, file_path: str | Path) -> None:
        raise AssertionError("no registry deletion expected")


class RecordingAdmitter:
    def __init__(self, events: list[str], *, reject: bool = False) -> None:
        self.events = events
        self.reject = reject
        self.calls: list[tuple[Path, int]] = []

    def admit(self, path: Path, required_bytes: int) -> None:
        self.events.append("admit")
        self.calls.append((path, required_bytes))
        if self.reject:
            raise ModelManagementError("insufficient model storage")


class RecordingProvider:
    def __init__(self, events: list[str], snapshot_path: Path) -> None:
        self.events = events
        self.snapshot_path = snapshot_path

    def install(
        self,
        spec: ModelSpec,
        *,
        cache_root: Path,
        revision: str | None,
    ) -> InstalledSnapshot:
        self.events.append("download")
        return InstalledSnapshot(
            resolved_revision="abc123",
            snapshot_path=self.snapshot_path,
            size_bytes=1,
            verification="test_verifier",
        )

    def validate(
        self,
        spec: ModelSpec,
        snapshot: InstalledSnapshot,
        *,
        cache_root: Path,
    ) -> None:
        self.events.append("validate")

    def remove(
        self,
        snapshot: InstalledSnapshot,
        *,
        cache_root: Path,
    ) -> None:
        raise AssertionError("no removal expected")


def _manager(
    tmp_path: Path, *, reject: bool
) -> tuple[ModelManager, RecordingAdmitter, list[str]]:
    events: list[str] = []
    model_root = tmp_path / "models"
    spec = ModelSpec(
        model_id="small",
        engine="faster-whisper",
        repository_id="Systran/faster-whisper-small",
        estimated_cache_bytes=750,
        quality_rank=2,
    )
    admitter = RecordingAdmitter(events, reject=reject)
    manager = ModelManager(
        catalog=ModelCatalog((spec,)),
        provider=RecordingProvider(
            events, model_root / "faster-whisper" / "snapshots" / "abc123"
        ),
        file_store=MinimalStore(events),
        model_root=model_root,
        storage_admitter=admitter,
    )
    return manager, admitter, events


def test_storage_is_admitted_before_private_state_or_download(tmp_path: Path) -> None:
    manager, admitter, events = _manager(tmp_path, reject=False)

    manager.install("small")

    assert admitter.calls == [(manager.cache_root, 750)]
    assert events[0] == "admit"
    assert events.index("admit") < events.index("mkdir") < events.index("download")


def test_storage_rejection_prevents_directory_creation_and_download(
    tmp_path: Path,
) -> None:
    manager, admitter, events = _manager(tmp_path, reject=True)

    with pytest.raises(ModelManagementError, match="insufficient model storage"):
        manager.install("small")

    assert admitter.calls == [(manager.cache_root, 750)]
    assert events == ["admit"]
