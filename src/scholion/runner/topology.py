from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from scholion.runner.inspector import RunnerInspector
from scholion.runner.models import RunnerResources

_MIB = 1024**2
_NVIDIA_SMI_TIMEOUT_SECONDS = 2.0


class AcceleratorBackend(StrEnum):
    """Execution backend exposed by a local accelerator runtime."""

    CUDA = "cuda"
    MPS = "mps"
    ROCM = "rocm"
    DIRECTML = "directml"
    OPENVINO = "openvino"
    UNKNOWN = "unknown"


class MemoryTopology(StrEnum):
    """Relationship between accelerator memory and process-visible system RAM."""

    DEDICATED = "dedicated"
    SHARED = "shared"
    UNIFIED = "unified"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class AcceleratorDevice:
    """One locally visible accelerator with conservative memory evidence."""

    accelerator_id: str
    backend: AcceleratorBackend
    device_index: int
    name: str
    memory_topology: MemoryTopology
    memory_total_bytes: int | None
    memory_available_bytes: int | None

    def __post_init__(self) -> None:
        if not self.accelerator_id.strip():
            raise ValueError("accelerator_id cannot be empty")
        if self.device_index < 0:
            raise ValueError("device_index cannot be negative")
        if not self.name.strip():
            raise ValueError("accelerator name cannot be empty")
        if self.memory_total_bytes is not None and self.memory_total_bytes < 1:
            raise ValueError("accelerator total memory must be positive")
        if self.memory_available_bytes is not None and self.memory_available_bytes < 0:
            raise ValueError("accelerator available memory cannot be negative")
        if (
            self.memory_total_bytes is not None
            and self.memory_available_bytes is not None
            and self.memory_available_bytes > self.memory_total_bytes
        ):
            raise ValueError("accelerator available memory cannot exceed total memory")

    def to_dict(self) -> dict[str, object]:
        return {
            "accelerator_id": self.accelerator_id,
            "backend": self.backend.value,
            "device_index": self.device_index,
            "name": self.name,
            "memory_topology": self.memory_topology.value,
            "memory_total_bytes": self.memory_total_bytes,
            "memory_available_bytes": self.memory_available_bytes,
        }


@dataclass(frozen=True, slots=True)
class HardwareTopology:
    """Process-visible CPU/RAM resources plus execution-capable accelerators."""

    resources: RunnerResources
    accelerators: tuple[AcceleratorDevice, ...] = ()

    def __post_init__(self) -> None:
        identities = tuple(
            (device.backend, device.device_index) for device in self.accelerators
        )
        if len(set(identities)) != len(identities):
            raise ValueError("accelerator backend/index pairs must be unique")

    def find(
        self, backend: AcceleratorBackend, device_index: int
    ) -> AcceleratorDevice | None:
        return next(
            (
                device
                for device in self.accelerators
                if device.backend is backend and device.device_index == device_index
            ),
            None,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "resources": self.resources.to_dict(),
            "accelerators": [device.to_dict() for device in self.accelerators],
        }


class AcceleratorProbe:
    """Small protocol-shaped base for local accelerator discovery."""

    def inspect(self) -> tuple[AcceleratorDevice, ...]:
        raise NotImplementedError


def _run_nvidia_smi(arguments: list[str], timeout_seconds: float) -> str:
    completed = subprocess.run(  # noqa: S603 - executable is resolved locally, no shell
        arguments,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    return completed.stdout


def _parse_nvidia_smi(output: str) -> tuple[AcceleratorDevice, ...]:
    devices: list[AcceleratorDevice] = []
    seen_indices: set[int] = set()
    for raw_line in output.splitlines():
        parts = tuple(part.strip() for part in raw_line.split(","))
        if len(parts) != 4:
            continue
        try:
            index = int(parts[0])
            total_mib = int(parts[2])
            free_mib = int(parts[3])
        except ValueError:
            continue
        if (
            index < 0
            or index in seen_indices
            or not parts[1]
            or total_mib < 1
            or free_mib < 0
            or free_mib > total_mib
        ):
            continue
        seen_indices.add(index)
        devices.append(
            AcceleratorDevice(
                accelerator_id=f"cuda:{index}",
                backend=AcceleratorBackend.CUDA,
                device_index=index,
                name=parts[1],
                memory_topology=MemoryTopology.DEDICATED,
                memory_total_bytes=total_mib * _MIB,
                memory_available_bytes=free_mib * _MIB,
            )
        )
    return tuple(devices)


@dataclass(frozen=True, slots=True)
class NvidiaSmiAcceleratorProbe(AcceleratorProbe):
    """Discover CUDA devices without importing a heavyweight ML framework."""

    timeout_seconds: float = _NVIDIA_SMI_TIMEOUT_SECONDS
    executable_resolver: Callable[[str], str | None] = shutil.which
    command_runner: Callable[[list[str], float], str] = _run_nvidia_smi

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("accelerator probe timeout must be positive")

    def inspect(self) -> tuple[AcceleratorDevice, ...]:
        executable = self.executable_resolver("nvidia-smi")
        if executable is None:
            return ()
        arguments = [
            executable,
            "--query-gpu=index,name,memory.total,memory.free",
            "--format=csv,noheader,nounits",
        ]
        try:
            output = self.command_runner(arguments, self.timeout_seconds)
        except (OSError, subprocess.SubprocessError):
            return ()
        return _parse_nvidia_smi(output)


@dataclass(frozen=True, slots=True)
class HardwareTopologyInspector:
    """Compose existing CPU/RAM inspection with independently safe accelerator probes."""

    runner_inspector: RunnerInspector
    accelerator_probe: AcceleratorProbe

    def inspect(self) -> HardwareTopology:
        return HardwareTopology(
            resources=self.runner_inspector.inspect(),
            accelerators=self.accelerator_probe.inspect(),
        )
