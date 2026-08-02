from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from time import perf_counter

import psutil


@dataclass(frozen=True, slots=True)
class SystemMetricsSnapshot:
    logical_cpus: int | None
    memory_available_bytes: int
    memory_total_bytes: int


class PerformanceTracker:
    """Measure operation duration with a monotonic clock."""

    def __init__(self, clock: Callable[[], float] = perf_counter):
        self.clock = clock
        self.metrics: dict[str, float] = {}

    @contextmanager
    def track_execution(self, operation_name: str) -> Iterator[None]:
        started = self.clock()
        try:
            yield
        finally:
            self.metrics[operation_name] = self.clock() - started

    def get_metric(self, operation_name: str) -> float | None:
        return self.metrics.get(operation_name)

    def track(self, operation_name: str) -> None:
        with self.track_execution(operation_name):
            pass


def collect_system_metrics() -> SystemMetricsSnapshot:
    """Collect a nonblocking resource snapshot; callers decide how to present it."""
    memory = psutil.virtual_memory()
    return SystemMetricsSnapshot(
        logical_cpus=psutil.cpu_count(logical=True),
        memory_available_bytes=memory.available,
        memory_total_bytes=memory.total,
    )
