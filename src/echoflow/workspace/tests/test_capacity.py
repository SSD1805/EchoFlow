from pathlib import Path
from unittest.mock import Mock

import pytest

from echoflow.transcription.errors import ResourceAdmissionError
from echoflow.workspace.capacity import (
    StorageAdmissionPolicy,
    StorageAllocation,
    StorageCapacityInspector,
    StorageVolume,
)


def test_same_filesystem_allocations_are_summed_before_admission(tmp_path: Path) -> None:
    inspector = Mock(spec=StorageCapacityInspector)
    inspector.inspect.return_value = StorageVolume(1, "/", 1_500)
    policy = StorageAdmissionPolicy(500, inspector=inspector)

    with pytest.raises(
        ResourceAdmissionError,
        match="^Available disk space is below the planned job allocation$",
    ):
        policy.admit(
            (
                StorageAllocation(tmp_path / "private", 700),
                StorageAllocation(tmp_path / "public", 400),
            )
        )


def test_distinct_filesystems_are_admitted_independently(tmp_path: Path) -> None:
    inspector = Mock(spec=StorageCapacityInspector)
    inspector.inspect.side_effect = (
        StorageVolume(1, "/state", 1_200),
        StorageVolume(2, "/output", 900),
    )
    policy = StorageAdmissionPolicy(500, inspector=inspector)

    policy.admit(
        (
            StorageAllocation(tmp_path / "private", 700),
            StorageAllocation(tmp_path / "public", 400),
        )
    )


def test_inspector_uses_existing_ancestor_for_future_destination(tmp_path: Path) -> None:
    future = tmp_path / "not-created" / "nested" / "artifact.json"

    volume = StorageCapacityInspector().inspect(future)

    assert volume.device_id == tmp_path.stat().st_dev
    assert volume.free_bytes > 0


@pytest.mark.parametrize("value", [-1, -100])
def test_negative_capacity_inputs_are_rejected(value: int, tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        StorageAdmissionPolicy(value)
    with pytest.raises(ValueError):
        StorageAllocation(tmp_path, value)
