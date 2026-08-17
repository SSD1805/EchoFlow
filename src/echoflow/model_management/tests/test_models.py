from pathlib import Path

import pytest

from echoflow.model_management.models import (
    InstalledSnapshot,
    ManagedModelManifest,
    ModelInventoryItem,
    ModelSpec,
)


def _manifest() -> ManagedModelManifest:
    return ManagedModelManifest(
        schema_version=1,
        model_id="small",
        engine="faster-whisper",
        repository_id="Systran/faster-whisper-small",
        requested_revision="release-v1",
        resolved_revision="abc123",
        snapshot_path=Path("cache/models/faster-whisper/snapshots/abc123"),
        size_bytes=123,
        verification="required_files_v1",
    )


def test_manifest_round_trip_preserves_model_provenance() -> None:
    manifest = _manifest()

    restored = ManagedModelManifest.from_dict(manifest.to_dict())

    assert restored == manifest
    assert restored.requested_revision == "release-v1"
    assert restored.resolved_revision == "abc123"
    assert restored.verification == "required_files_v1"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("schema_version", 2),
        ("schema_version", True),
        ("model_id", 7),
        ("size_bytes", "123"),
        ("requested_revision", 7),
        ("verification", ""),
    ],
)
def test_manifest_parser_rejects_schema_and_type_mutations(
    key: str, value: object
) -> None:
    document = _manifest().to_dict()
    document[key] = value

    with pytest.raises(ValueError, match="invalid model manifest"):
        ManagedModelManifest.from_dict(document)


def test_model_spec_rejects_storage_and_identity_boundaries() -> None:
    with pytest.raises(ValueError, match="estimated_cache_bytes must be positive"):
        ModelSpec("small", "faster-whisper", "repo/small", 0, 1)
    with pytest.raises(ValueError, match="quality_rank cannot be negative"):
        ModelSpec("small", "faster-whisper", "repo/small", 1, -1)
    with pytest.raises(ValueError, match="model_id cannot be empty"):
        ModelSpec(" ", "faster-whisper", "repo/small", 1, 1)
    with pytest.raises(ValueError, match="filenames cannot be empty"):
        ModelSpec("small", "faster-whisper", "repo/small", 1, 1, ("",))


def test_installed_snapshot_rejects_empty_verification_and_nonpositive_size() -> None:
    with pytest.raises(ValueError, match="size_bytes must be positive"):
        InstalledSnapshot("abc", Path("snapshot"), 0, "verified")
    with pytest.raises(ValueError, match="verification cannot be empty"):
        InstalledSnapshot("abc", Path("snapshot"), 1, " ")


def test_inventory_item_installed_state_tracks_manifest_presence() -> None:
    spec = ModelSpec("small", "faster-whisper", "repo/small", 1, 1)

    uninstalled = ModelInventoryItem(spec)
    installed = ModelInventoryItem(spec, _manifest())

    assert uninstalled.installed is False
    assert installed.installed is True
    assert uninstalled.to_dict()["manifest"] is None
    assert installed.to_dict()["manifest"] is not None
