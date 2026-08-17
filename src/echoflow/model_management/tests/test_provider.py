from pathlib import Path
from types import SimpleNamespace

import pytest

from echoflow.model_management.models import InstalledSnapshot, ModelSpec
from echoflow.model_management.provider import HuggingFaceModelProvider


def _spec() -> ModelSpec:
    return ModelSpec(
        model_id="small",
        engine="faster-whisper",
        repository_id="Systran/faster-whisper-small",
        estimated_cache_bytes=750,
        quality_rank=2,
    )


def test_provider_installs_snapshot_into_requested_cache(tmp_path: Path) -> None:
    cache_root = tmp_path / "cache"
    snapshot = cache_root / "models--Systran--faster-whisper-small" / "snapshots" / "abc123"
    snapshot.mkdir(parents=True)
    (snapshot / "model.bin").write_bytes(b"1234")
    calls: list[dict[str, object]] = []

    def snapshot_download(**kwargs: object) -> str:
        calls.append(kwargs)
        return str(snapshot)

    module = SimpleNamespace(snapshot_download=snapshot_download)
    provider = HuggingFaceModelProvider(module_loader=lambda _: module)

    installed = provider.install(_spec(), cache_root=cache_root, revision="release-v1")

    assert installed.resolved_revision == "abc123"
    assert installed.snapshot_path == snapshot.resolve()
    assert installed.size_bytes == 4
    assert calls == [
        {
            "repo_id": "Systran/faster-whisper-small",
            "revision": "release-v1",
            "cache_dir": str(cache_root),
            "local_files_only": False,
        }
    ]


def test_provider_rejects_snapshot_outside_cache(tmp_path: Path) -> None:
    cache_root = tmp_path / "cache"
    escaped = tmp_path / "escaped" / "abc123"
    escaped.mkdir(parents=True)
    module = SimpleNamespace(snapshot_download=lambda **_: str(escaped))
    provider = HuggingFaceModelProvider(module_loader=lambda _: module)

    with pytest.raises(ValueError, match="outside"):
        provider.install(_spec(), cache_root=cache_root, revision=None)


def test_provider_removes_only_resolved_revision(tmp_path: Path) -> None:
    executed: list[bool] = []
    revisions: list[str] = []

    class Deletion:
        def execute(self) -> None:
            executed.append(True)

    class CacheInfo:
        def delete_revisions(self, revision: str) -> Deletion:
            revisions.append(revision)
            return Deletion()

    module = SimpleNamespace(scan_cache_dir=lambda **_: CacheInfo())
    provider = HuggingFaceModelProvider(module_loader=lambda _: module)
    snapshot = InstalledSnapshot(
        resolved_revision="abc123",
        snapshot_path=tmp_path / "cache" / "snapshots" / "abc123",
        size_bytes=4,
    )

    provider.remove(snapshot, cache_root=tmp_path / "cache")

    assert revisions == ["abc123"]
    assert executed == [True]
