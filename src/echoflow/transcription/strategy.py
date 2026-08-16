from dataclasses import dataclass
from enum import StrEnum

from echoflow.runner.models import ProcessingProfile
from echoflow.transcription.errors import ResourceAdmissionError

_MIB = 1024**2


class RejectionReason(StrEnum):
    """Machine-checkable reason a local execution strategy is not feasible."""

    INSUFFICIENT_MEMORY = "insufficient_memory"


@dataclass(frozen=True, slots=True)
class StrategyDefinition:
    """One deterministic local transcription strategy advertised to the planner."""

    strategy_id: str
    model: str
    quality_rank: int
    model_cache_bytes: int
    estimated_peak_memory_bytes: int

    def __post_init__(self) -> None:
        if not self.strategy_id.strip():
            raise ValueError("strategy_id cannot be empty")
        if not self.model.strip():
            raise ValueError("model cannot be empty")
        if self.quality_rank < 0:
            raise ValueError("quality_rank cannot be negative")
        if self.model_cache_bytes < 0:
            raise ValueError("model_cache_bytes cannot be negative")
        if self.estimated_peak_memory_bytes < 1:
            raise ValueError("estimated_peak_memory_bytes must be positive")

    def to_dict(self) -> dict[str, object]:
        return {
            "strategy_id": self.strategy_id,
            "model": self.model,
            "quality_rank": self.quality_rank,
            "model_cache_bytes": self.model_cache_bytes,
            "estimated_peak_memory_bytes": self.estimated_peak_memory_bytes,
        }


@dataclass(frozen=True, slots=True)
class StrategyAssessment:
    """Feasibility result for one strategy against the current job memory budget."""

    strategy: StrategyDefinition
    memory_budget_bytes: int
    rejection_reasons: tuple[RejectionReason, ...] = ()

    def __post_init__(self) -> None:
        if self.memory_budget_bytes < 0:
            raise ValueError("memory_budget_bytes cannot be negative")

    @property
    def feasible(self) -> bool:
        return not self.rejection_reasons

    def to_dict(self) -> dict[str, object]:
        return {
            "strategy": self.strategy.to_dict(),
            "memory_budget_bytes": self.memory_budget_bytes,
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


class StrategyEvaluator:
    """Evaluate and rank local CPU strategies without hardware-name heuristics."""

    def assess(
        self, catalog: StrategyCatalog, *, memory_budget_bytes: int
    ) -> tuple[StrategyAssessment, ...]:
        if memory_budget_bytes < 0:
            raise ValueError("memory_budget_bytes cannot be negative")
        return tuple(
            StrategyAssessment(
                strategy=strategy,
                memory_budget_bytes=memory_budget_bytes,
                rejection_reasons=(
                    (RejectionReason.INSUFFICIENT_MEMORY,)
                    if strategy.estimated_peak_memory_bytes > memory_budget_bytes
                    else ()
                ),
            )
            for strategy in catalog.strategies
        )

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
                raise ResourceAdmissionError(
                    "Selected transcription strategy exceeds the current safe memory budget"
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
            return min(feasible, key=lambda item: item.strategy.quality_rank)
        if profile is ProcessingProfile.ACCURACY:
            return max(feasible, key=lambda item: item.strategy.quality_rank)

        standard = next(
            (
                assessment
                for assessment in feasible
                if assessment.strategy.strategy_id == "small-cpu-int8"
            ),
            None,
        )
        if standard is not None:
            return standard
        return max(feasible, key=lambda item: item.strategy.quality_rank)


def faster_whisper_cpu_catalog() -> StrategyCatalog:
    """Return conservative CPU/int8 strategies pending real-machine calibration."""

    return StrategyCatalog(
        strategies=(
            StrategyDefinition(
                strategy_id="tiny-cpu-int8",
                model="tiny",
                quality_rank=1,
                model_cache_bytes=150 * _MIB,
                estimated_peak_memory_bytes=1_280 * _MIB,
            ),
            StrategyDefinition(
                strategy_id="small-cpu-int8",
                model="small",
                quality_rank=2,
                model_cache_bytes=750 * _MIB,
                estimated_peak_memory_bytes=2_304 * _MIB,
            ),
            StrategyDefinition(
                strategy_id="medium-cpu-int8",
                model="medium",
                quality_rank=3,
                model_cache_bytes=2_500 * _MIB,
                estimated_peak_memory_bytes=4_352 * _MIB,
            ),
        )
    )
