from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from threading import Lock
from time import perf_counter
from typing import Protocol


@dataclass(frozen=True, slots=True)
class StageMeasurement:
    """Aggregate repeated observations of one execution stage."""

    name: str
    count: int
    failed_count: int
    total_seconds: float
    max_seconds: float

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "count": self.count,
            "failed_count": self.failed_count,
            "total_seconds": self.total_seconds,
            "max_seconds": self.max_seconds,
        }


class ExecutionObserver(Protocol):
    """Small measurement seam shared by current and future execution pipelines."""

    def span(self, name: str) -> AbstractContextManager[None]: ...
    def record_value(self, name: str, value: int | float) -> None: ...


class NoOpExecutionObserver:
    """Default observer for ordinary execution."""

    @contextmanager
    def span(self, name: str) -> Iterator[None]:
        del name
        yield

    def record_value(self, name: str, value: int | float) -> None:
        del name, value


@dataclass(slots=True)
class _MutableStage:
    count: int = 0
    failed_count: int = 0
    total_seconds: float = 0.0
    max_seconds: float = 0.0


class MeasurementRecorder:
    """Thread-safe aggregate recorder suitable for sequential or future parallel work."""

    def __init__(self, clock: Callable[[], float] = perf_counter):
        self.clock = clock
        self._stages: dict[str, _MutableStage] = {}
        self._values: dict[str, int | float] = {}
        self._lock = Lock()

    @contextmanager
    def span(self, name: str) -> Iterator[None]:
        started = self.clock()
        failed = False
        try:
            yield
        except BaseException:
            failed = True
            raise
        finally:
            duration = max(0.0, self.clock() - started)
            with self._lock:
                stage = self._stages.setdefault(name, _MutableStage())
                stage.count += 1
                stage.failed_count += int(failed)
                stage.total_seconds += duration
                stage.max_seconds = max(stage.max_seconds, duration)

    def record_value(self, name: str, value: int | float) -> None:
        with self._lock:
            self._values[name] = value

    def stages(self) -> tuple[StageMeasurement, ...]:
        with self._lock:
            return tuple(
                StageMeasurement(
                    name=name,
                    count=stage.count,
                    failed_count=stage.failed_count,
                    total_seconds=stage.total_seconds,
                    max_seconds=stage.max_seconds,
                )
                for name, stage in sorted(self._stages.items())
            )

    def values(self) -> dict[str, int | float]:
        with self._lock:
            return dict(sorted(self._values.items()))
