from dataclasses import dataclass
from enum import StrEnum

from echoflow.runner.models import ProcessingProfile
from echoflow.runner.topology import (
    AcceleratorBackend,
    AcceleratorDevice,
    MemoryTopology,
)
from echoflow.transcription.capabilities import EngineCapabilities
from echoflow.transcription.errors import ResourceAdmissionError

_MIB = 1024**2


class RejectionReason(StrEnum):
    """Machine-checkable reason a local execution strategy is not feasible."""

    INSUFFICIENT_MEMORY = "insufficient_memory"
    UNSUPPORTED_EXECUTION_TARGET = "unsupported_execution_target"
    ACCELERATOR_UNAVAILABLE = "accelerator_unavailable"
    DEVICE_MEMORY_UNKNOWN = "device_memory_unknown"
    INSUFFICIENT_DEVICE_MEMORY = "insufficient_device_memory"


@dataclass(frozen=True, slots=True)
class StrategyDefinition:
    """One deterministic engine strategy advertised to the application planner."""

    strategy_id: str
    model: str
    quality_rank: int
    model_cache_bytes: int
    estimated_peak_memory_bytes: int
    engine: str = "faster-whisper"
    device: str = "cpu"
    compute_type: str = "int8"
    device_index: int = 0
    accelerator_backend: AcceleratorBackend | None = None
    estimated_peak_device_memory_bytes: int = 0
    performance_rank: int = 0

    def __post_init__(self) -> None:
        self._validate_identity()
        self._validate_numeric_boundaries()
        self._validate_placement()

    def _validate_identity(self) -> None:
        for name in ("strategy_id", "model", "engine", "device", "compute_type"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} cannot be empty")

    def _validate_numeric_boundaries(self) -> None:
        if self.quality_rank < 0:
            raise ValueError("quality_rank cannot be negative")
        if self.model_cache_bytes < 0:
            raise ValueError("model_cache_bytes cannot be negative")
        if self.estimated_peak_memory_bytes < 1:
            raise ValueError("estimated_peak_memory_bytes must be positive")
        if self.device_index < 0:
            raise ValueError("device_index cannot be negative")
        if self.estimated_peak_device_memory_bytes < 0:
            raise ValueError("estimated_peak_device_memory_bytes cannot be negative")
        if self.performance_rank < 0:
            raise ValueError("performance_rank cannot be negative")

    def _validate_placement(self) -> None:
        if self.device == "cpu":
            if self.accelerator_backend is not None:
                raise ValueError("CPU strategy cannot require an accelerator backend")
            if self.estimated_peak_device_memory_bytes != 0:
                raise ValueError("CPU strategy cannot require device memory")
            return
        if self.accelerator_backend is None:
            raise ValueError("accelerated strategy requires an accelerator backend")
        if self.estimated_peak_device_memory_bytes < 1:
            raise ValueError("accelerated strategy requires positive device memory")

    @property
    def accelerated(self) -> bool:
        return self.device != "cpu"

    def to_dict(self) -> dict[str, object]:
        document: dict[str, object] = {
            "strategy_id": self.strategy_id,
            "engine": self.engine,
            "model": self.model,
            "quality_rank": self.quality_rank,
            "performance_rank": self.performance_rank,
            "device": self.device,
            "device_index": self.device_index,
            "compute_type": self.compute_type,
            "model_cache_bytes": self.model_cache_bytes,
            "estimated_peak_memory_bytes": self.estimated_peak_memory_bytes,
            "estimated_peak_device_memory_bytes": (
                self.estimated_peak_device_memory_bytes
            ),
        }
        if self.accelerator_backend is not None:
            document["accelerator_backend"] = self.accelerator_backend.value
        return document


@dataclass(frozen=True, slots=True)
class StrategyAssessment:
    """Feasibility result for one strategy against current resource topology."""

    strategy: StrategyDefinition
    memory_budget_bytes: int
    rejection_reasons: tuple[RejectionReason, ...] = ()
    effective_peak_memory_bytes: int | None = None
    device_memory_budget_bytes: int | None = None
    accelerator_id: str | None = None

    def __post_init__(self) -> None:
        if self.memory_budget_bytes < 0:
            raise ValueError("memory_budget_bytes cannot be negative")
        if (
            self.effective_peak_memory_bytes is not None
            and self.effective_peak_memory_bytes < 1
        ):
            raise ValueError("effective_peak_memory_bytes must be positive")
        if (
            self.device_memory_budget_bytes is not None
            and self.device_memory_budget_bytes < 0
        ):
            raise ValueError("device_memory_budget_bytes cannot be negative")

    @property
    def feasible(self) -> bool:
        return not self.rejection_reasons

    @property
    def peak_system_memory_bytes(self) -> int:
        return self.effective_peak_memory_bytes or self.strategy.estimated_peak_memory_bytes

    def to_dict(self) -> dict[str, object]:
        return {
            "strategy": self.strategy.to_dict(),
            "memory_budget_bytes": self.memory_budget_bytes,
            "effective_peak_memory_bytes": self.peak_system_memory_bytes,
            "device_memory_budget_bytes": self.device_memory_budget_bytes,
            "accelerator_id": self.accelerator_id,
            "feasible": self.feasible,
            "rejection_reasons": [reason.value for reason in self.rejection_reasons],
        }


@dataclass(frozen=True, slots=True)
class StrategyCatalog:
    """Ordered, versioned set of engine strategies considered by one planner."""

    strategies: tuple[StrategyDefinition, ...]
    version: int = 1

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError("strategy catalog version must be positive")
        if not self.strategies:
            raise ValueError("strategy catalog cannot be empty")
        identifiers = tuple(strategy.strategy_id for strategy in self.strategies)
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("strategy IDs must be unique")

    @property
    def engines(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(strategy.engine for strategy in self.strategies))

    def find_configuration(
        self,
        *,
        engine: str,
        model: str,
        device: str,
        compute_type: str,
    ) -> StrategyDefinition | None:
        return next(
            (
                strategy
                for strategy in self.strategies
                if strategy.engine == engine
                and strategy.model == model
                and strategy.device == device
                and strategy.compute_type == compute_type
            ),
            None,
        )


@dataclass(frozen=True, slots=True)
class StrategyEvaluator:
    """Rank strategies without assuming that every visible GPU is executable."""

    device_memory_budget_fraction: float = 0.80

    def __post_init__(self) -> None:
        if not 0 < self.device_memory_budget_fraction <= 1:
            raise ValueError(
                "device_memory_budget_fraction must be greater than 0 and at most 1"
            )

    def assess(
        self,
        catalog: StrategyCatalog,
        *,
        memory_budget_bytes: int,
        accelerators: tuple[AcceleratorDevice, ...] = (),
        capabilities: tuple[EngineCapabilities, ...] = (),
    ) -> tuple[StrategyAssessment, ...]:
        if memory_budget_bytes < 0:
            raise ValueError("memory_budget_bytes cannot be negative")
        capability_map = {capability.engine: capability for capability in capabilities}
        return tuple(
            self._assess_strategy(
                strategy,
                memory_budget_bytes=memory_budget_bytes,
                accelerators=accelerators,
                capability=capability_map.get(strategy.engine),
            )
            for strategy in catalog.strategies
        )

    def _assess_strategy(
        self,
        strategy: StrategyDefinition,
        *,
        memory_budget_bytes: int,
        accelerators: tuple[AcceleratorDevice, ...],
        capability: EngineCapabilities | None,
    ) -> StrategyAssessment:
        reasons: list[RejectionReason] = []
        effective_memory = strategy.estimated_peak_memory_bytes
        device_budget: int | None = None
        accelerator: AcceleratorDevice | None = None

        if strategy.accelerated:
            if capability is None or not capability.supports(
                device=strategy.device,
                device_index=strategy.device_index,
                compute_type=strategy.compute_type,
            ):
                reasons.append(RejectionReason.UNSUPPORTED_EXECUTION_TARGET)
            accelerator = self._matching_accelerator(strategy, accelerators)
            if accelerator is None:
                reasons.append(RejectionReason.ACCELERATOR_UNAVAILABLE)
            else:
                effective_memory, device_budget = self._device_budget(
                    strategy, accelerator, effective_memory, reasons
                )

        if effective_memory > memory_budget_bytes:
            reasons.insert(0, RejectionReason.INSUFFICIENT_MEMORY)

        return StrategyAssessment(
            strategy=strategy,
            memory_budget_bytes=memory_budget_bytes,
            rejection_reasons=tuple(dict.fromkeys(reasons)),
            effective_peak_memory_bytes=effective_memory,
            device_memory_budget_bytes=device_budget,
            accelerator_id=(None if accelerator is None else accelerator.accelerator_id),
        )

    @staticmethod
    def _matching_accelerator(
        strategy: StrategyDefinition,
        accelerators: tuple[AcceleratorDevice, ...],
    ) -> AcceleratorDevice | None:
        return next(
            (
                accelerator
                for accelerator in accelerators
                if accelerator.backend is strategy.accelerator_backend
                and accelerator.device_index == strategy.device_index
            ),
            None,
        )

    def _device_budget(
        self,
        strategy: StrategyDefinition,
        accelerator: AcceleratorDevice,
        effective_memory: int,
        reasons: list[RejectionReason],
    ) -> tuple[int, int | None]:
        if accelerator.memory_topology in {
            MemoryTopology.SHARED,
            MemoryTopology.UNIFIED,
        }:
            effective_memory += strategy.estimated_peak_device_memory_bytes
        if (
            accelerator.memory_topology is MemoryTopology.UNKNOWN
            or accelerator.memory_available_bytes is None
        ):
            reasons.append(RejectionReason.DEVICE_MEMORY_UNKNOWN)
            return effective_memory, None
        device_budget = int(
            accelerator.memory_available_bytes * self.device_memory_budget_fraction
        )
        if strategy.estimated_peak_device_memory_bytes > device_budget:
            reasons.append(RejectionReason.INSUFFICIENT_DEVICE_MEMORY)
        return effective_memory, device_budget

    def select(
        self,
        assessments: tuple[StrategyAssessment, ...],
        *,
        profile: ProcessingProfile,
        requested_strategy_id: str | None = None,
    ) -> StrategyAssessment:
        if requested_strategy_id is not None:
            requested = next(
                (
                    assessment
                    for assessment in assessments
                    if assessment.strategy.strategy_id == requested_strategy_id
                ),
                None,
            )
            if requested is None:
                raise ResourceAdmissionError("Unknown transcription strategy")
            if not requested.feasible:
                if requested.rejection_reasons == (
                    RejectionReason.INSUFFICIENT_MEMORY,
                ):
                    raise ResourceAdmissionError(
                        "Selected transcription strategy exceeds the current safe memory budget"
                    )
                raise ResourceAdmissionError(
                    "Selected transcription strategy is not feasible on the current runner"
                )
            return requested

        feasible = tuple(
            assessment for assessment in assessments if assessment.feasible
        )
        if not feasible:
            raise ResourceAdmissionError(
                "No local transcription strategy fits the current safe memory budget"
            )
        if profile is ProcessingProfile.SCREENING:
            quality = min(item.strategy.quality_rank for item in feasible)
            return self._fastest(
                tuple(item for item in feasible if item.strategy.quality_rank == quality)
            )
        if profile is ProcessingProfile.ACCURACY:
            quality = max(item.strategy.quality_rank for item in feasible)
            return self._fastest(
                tuple(item for item in feasible if item.strategy.quality_rank == quality)
            )

        distance = min(abs(item.strategy.quality_rank - 2) for item in feasible)
        nearest = tuple(
            item for item in feasible if abs(item.strategy.quality_rank - 2) == distance
        )
        quality = max(item.strategy.quality_rank for item in nearest)
        return self._fastest(
            tuple(item for item in nearest if item.strategy.quality_rank == quality)
        )

    @staticmethod
    def _fastest(
        assessments: tuple[StrategyAssessment, ...],
    ) -> StrategyAssessment:
        return max(
            assessments,
            key=lambda item: (item.strategy.performance_rank, item.strategy.strategy_id),
        )


def _cpu_strategies() -> tuple[StrategyDefinition, ...]:
    return (
        StrategyDefinition(
            strategy_id="tiny-cpu-int8",
            model="tiny",
            quality_rank=1,
            model_cache_bytes=150 * _MIB,
            estimated_peak_memory_bytes=1_280 * _MIB,
            performance_rank=10,
        ),
        StrategyDefinition(
            strategy_id="small-cpu-int8",
            model="small",
            quality_rank=2,
            model_cache_bytes=750 * _MIB,
            estimated_peak_memory_bytes=2_304 * _MIB,
            performance_rank=10,
        ),
        StrategyDefinition(
            strategy_id="medium-cpu-int8",
            model="medium",
            quality_rank=3,
            model_cache_bytes=2_500 * _MIB,
            estimated_peak_memory_bytes=4_352 * _MIB,
            performance_rank=10,
        ),
    )


def _cuda_strategy(
    *,
    model: str,
    quality_rank: int,
    model_cache_mib: int,
    system_memory_mib: int,
    device_memory_mib: int,
    compute_type: str,
    performance_rank: int,
) -> StrategyDefinition:
    compute_id = compute_type.replace("_", "-")
    return StrategyDefinition(
        strategy_id=f"{model}-cuda-{compute_id}",
        engine="faster-whisper",
        model=model,
        quality_rank=quality_rank,
        model_cache_bytes=model_cache_mib * _MIB,
        estimated_peak_memory_bytes=system_memory_mib * _MIB,
        device="cuda",
        compute_type=compute_type,
        accelerator_backend=AcceleratorBackend.CUDA,
        estimated_peak_device_memory_bytes=device_memory_mib * _MIB,
        performance_rank=performance_rank,
    )


def faster_whisper_cpu_catalog() -> StrategyCatalog:
    """Return conservative CPU/int8 strategies retained for compatibility."""

    return StrategyCatalog(strategies=_cpu_strategies())


def faster_whisper_catalog() -> StrategyCatalog:
    """Return CPU plus conservative CUDA candidates pending device calibration."""

    accelerated = (
        _cuda_strategy(
            model="tiny",
            quality_rank=1,
            model_cache_mib=150,
            system_memory_mib=768,
            device_memory_mib=512,
            compute_type="float16",
            performance_rank=30,
        ),
        _cuda_strategy(
            model="tiny",
            quality_rank=1,
            model_cache_mib=150,
            system_memory_mib=768,
            device_memory_mib=384,
            compute_type="int8_float16",
            performance_rank=20,
        ),
        _cuda_strategy(
            model="small",
            quality_rank=2,
            model_cache_mib=750,
            system_memory_mib=1_280,
            device_memory_mib=1_280,
            compute_type="float16",
            performance_rank=30,
        ),
        _cuda_strategy(
            model="small",
            quality_rank=2,
            model_cache_mib=750,
            system_memory_mib=1_280,
            device_memory_mib=896,
            compute_type="int8_float16",
            performance_rank=20,
        ),
        _cuda_strategy(
            model="medium",
            quality_rank=3,
            model_cache_mib=2_500,
            system_memory_mib=2_048,
            device_memory_mib=3_072,
            compute_type="float16",
            performance_rank=30,
        ),
        _cuda_strategy(
            model="medium",
            quality_rank=3,
            model_cache_mib=2_500,
            system_memory_mib=2_048,
            device_memory_mib=2_048,
            compute_type="int8_float16",
            performance_rank=20,
        ),
    )
    return StrategyCatalog(strategies=(*_cpu_strategies(), *accelerated), version=2)
