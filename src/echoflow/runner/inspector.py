import math
import os
import platform
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, cast

import psutil

from echoflow.runner.models import RunnerResources

_CPU_MAX = Path("/sys/fs/cgroup/cpu.max")
_MEMORY_MAX = Path("/sys/fs/cgroup/memory.max")
_MEMORY_CURRENT = Path("/sys/fs/cgroup/memory.current")


class VirtualMemory(Protocol):
    total: int
    available: int


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None


def _affinity_count() -> int | None:
    try:
        affinity = os.sched_getaffinity(0)
    except (AttributeError, OSError):
        return None
    return len(affinity) or None


def _cpu_quota_cores(value: str | None) -> float | None:
    if value is None:
        return None
    parts = value.split()
    if len(parts) != 2:
        return None
    try:
        quota, period = (int(part) for part in parts)
    except ValueError:
        return None
    if quota <= 0 or period <= 0:
        return None
    return quota / period


def _finite_bytes(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed > 0 else None


class RunnerInspector:
    """Inspect resources visible to this process, including common cgroup limits."""

    def __init__(
        self,
        *,
        cpu_count: Callable[[bool], int | None] = psutil.cpu_count,
        virtual_memory: Callable[[], VirtualMemory] | None = None,
        affinity_count: Callable[[], int | None] = _affinity_count,
        text_reader: Callable[[Path], str | None] = _read_text,
        platform_name: Callable[[], str] = platform.system,
        machine_name: Callable[[], str] = platform.machine,
    ):
        self.cpu_count = cpu_count
        self.virtual_memory = virtual_memory or cast(
            "Callable[[], VirtualMemory]", psutil.virtual_memory
        )
        self.affinity_count = affinity_count
        self.text_reader = text_reader
        self.platform_name = platform_name
        self.machine_name = machine_name

    def inspect(self) -> RunnerResources:
        logical = max(1, self.cpu_count(True) or 1)
        physical = self.cpu_count(False)
        affinity = self.affinity_count()
        quota = _cpu_quota_cores(self.text_reader(_CPU_MAX))
        cpu_candidates = [logical]
        constraints: list[str] = []
        if affinity is not None:
            cpu_candidates.append(affinity)
            if affinity < logical:
                constraints.append("cpu_affinity")
        if quota is not None:
            quota_threads = max(1, math.floor(quota))
            cpu_candidates.append(quota_threads)
            if quota_threads < logical:
                constraints.append("cpu_quota")

        memory = self.virtual_memory()
        memory_limit = _finite_bytes(self.text_reader(_MEMORY_MAX))
        memory_current = _finite_bytes(self.text_reader(_MEMORY_CURRENT))
        effective_memory = memory.available
        if memory_limit is not None:
            cgroup_available = memory_limit
            if memory_current is not None:
                cgroup_available = max(0, memory_limit - memory_current)
            if cgroup_available < effective_memory:
                effective_memory = cgroup_available
                constraints.append("memory_limit")

        return RunnerResources(
            platform=self.platform_name(),
            machine=self.machine_name(),
            logical_cpus=logical,
            physical_cpus=physical,
            affinity_cpus=affinity,
            cpu_quota_cores=quota,
            effective_cpus=min(cpu_candidates),
            memory_total_bytes=memory.total,
            memory_available_bytes=memory.available,
            memory_limit_bytes=memory_limit,
            effective_memory_available_bytes=effective_memory,
            constraints=tuple(constraints),
        )
