from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.core.performance_tracker import PerformanceTracker, collect_system_metrics


def test_tracker_uses_injected_monotonic_clock():
    readings = iter((10.0, 10.25))
    tracker = PerformanceTracker(clock=lambda: next(readings))
    with tracker.track_execution("decode"):
        pass
    assert tracker.get_metric("decode") == pytest.approx(0.25)


def test_tracker_records_duration_when_operation_raises():
    readings = iter((3.0, 3.5))
    tracker = PerformanceTracker(clock=lambda: next(readings))
    with (
        pytest.raises(RuntimeError, match="decoder"),
        tracker.track_execution("decode"),
    ):
        raise RuntimeError("decoder")
    assert tracker.get_metric("decode") == pytest.approx(0.5)


def test_unknown_metric_returns_none():
    assert PerformanceTracker().get_metric("missing") is None


@patch("src.core.performance_tracker.psutil.cpu_count", return_value=8)
@patch(
    "src.core.performance_tracker.psutil.virtual_memory",
    return_value=SimpleNamespace(available=1024, total=4096),
)
def test_resource_snapshot_is_data_not_a_logging_side_effect(_memory, _cpu):
    snapshot = collect_system_metrics()
    assert snapshot.logical_cpus == 8
    assert snapshot.memory_available_bytes == 1024
    assert snapshot.memory_total_bytes == 4096
