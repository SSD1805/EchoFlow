from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module
from typing import Any, Protocol

from echoflow.runner.topology import AcceleratorBackend, HardwareTopology


@dataclass(frozen=True, slots=True)
class EngineExecutionTarget:
    """One execution target an installed engine runtime can actually consume."""

    device: str
    device_index: int
    compute_types: tuple[str, ...]
    accelerator_backend: AcceleratorBackend | None = None
    verified: bool = True

    def __post_init__(self) -> None:
        if not self.device.strip():
            raise ValueError("execution target device cannot be empty")
        if self.device_index < 0:
            raise ValueError("execution target device_index cannot be negative")
        if not self.compute_types or any(
            not compute_type.strip() for compute_type in self.compute_types
        ):
            raise ValueError("execution target compute_types cannot be empty")
        if len(set(self.compute_types)) != len(self.compute_types):
            raise ValueError("execution target compute_types must be unique")
        if self.device == "cpu" and self.accelerator_backend is not None:
            raise ValueError(
                "CPU execution target cannot require an accelerator backend"
            )

    def supports(self, *, device: str, device_index: int, compute_type: str) -> bool:
        return (
            self.device == device
            and self.device_index == device_index
            and compute_type in self.compute_types
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "device": self.device,
            "device_index": self.device_index,
            "compute_types": list(self.compute_types),
            "accelerator_backend": (
                None
                if self.accelerator_backend is None
                else self.accelerator_backend.value
            ),
            "verified": self.verified,
        }


@dataclass(frozen=True, slots=True)
class EngineCapabilities:
    """Execution targets currently available to one engine adapter."""

    engine: str
    targets: tuple[EngineExecutionTarget, ...]

    def __post_init__(self) -> None:
        if not self.engine.strip():
            raise ValueError("engine capability name cannot be empty")
        identities = tuple(
            (target.device, target.device_index) for target in self.targets
        )
        if len(set(identities)) != len(identities):
            raise ValueError("engine execution target identities must be unique")

    def supports(self, *, device: str, device_index: int, compute_type: str) -> bool:
        return any(
            target.supports(
                device=device,
                device_index=device_index,
                compute_type=compute_type,
            )
            for target in self.targets
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "engine": self.engine,
            "targets": [target.to_dict() for target in self.targets],
        }


class EngineCapabilityProvider(Protocol):
    engine: str

    def inspect(self, topology: HardwareTopology) -> EngineCapabilities: ...


class EngineCapabilityRegistry:
    """Resolve engine-specific runtime capabilities without teaching the planner vendors."""

    def __init__(self, providers: tuple[EngineCapabilityProvider, ...] = ()):
        names = tuple(provider.engine for provider in providers)
        if len(set(names)) != len(names):
            raise ValueError("engine capability providers must be unique by engine")
        self._providers = {provider.engine: provider for provider in providers}

    def inspect(self, engine: str, topology: HardwareTopology) -> EngineCapabilities:
        provider = self._providers.get(engine)
        if provider is None:
            return EngineCapabilities(engine=engine, targets=())
        return provider.inspect(topology)


class FasterWhisperCapabilityProbe:
    """Advertise the stable CPU contract plus runtime-verified CTranslate2 CUDA targets."""

    engine = "faster-whisper"

    def __init__(
        self,
        *,
        module_loader: Callable[[str], Any] = import_module,
    ):
        self.module_loader = module_loader

    def inspect(self, topology: HardwareTopology) -> EngineCapabilities:
        targets = [
            EngineExecutionTarget(
                device="cpu",
                device_index=0,
                compute_types=("int8",),
                verified=False,
            )
        ]
        module = self._ctranslate2()
        if module is None:
            return EngineCapabilities(self.engine, tuple(targets))

        cuda_count = self._cuda_device_count(module)
        for device_index in range(cuda_count):
            accelerator = topology.find(AcceleratorBackend.CUDA, device_index)
            if accelerator is None:
                continue
            compute_types = self._compute_types(module, device_index)
            if not compute_types:
                continue
            targets.append(
                EngineExecutionTarget(
                    device="cuda",
                    device_index=device_index,
                    compute_types=compute_types,
                    accelerator_backend=AcceleratorBackend.CUDA,
                )
            )
        return EngineCapabilities(self.engine, tuple(targets))

    def _ctranslate2(self) -> Any | None:
        try:
            return self.module_loader("ctranslate2")
        except (ImportError, OSError):
            return None

    @staticmethod
    def _cuda_device_count(module: Any) -> int:
        reader = getattr(module, "get_cuda_device_count", None)
        if not callable(reader):
            return 0
        try:
            count = int(reader())
        except (RuntimeError, TypeError, ValueError):
            return 0
        return min(max(0, count), 16)

    @staticmethod
    def _compute_types(module: Any, device_index: int) -> tuple[str, ...]:
        reader = getattr(module, "get_supported_compute_types", None)
        if not callable(reader):
            return ()
        try:
            raw = reader("cuda", device_index)
            values = {str(value).strip() for value in raw if str(value).strip()}
        except (RuntimeError, TypeError, ValueError):
            return ()
        return tuple(sorted(values))
