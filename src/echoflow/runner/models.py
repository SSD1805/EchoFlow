from dataclasses import asdict, dataclass
from enum import StrEnum


class ProcessingProfile(StrEnum):
    """User intent used to rank feasible processing strategies."""

    SCREENING = "screening"
    BALANCED = "balanced"
    ACCURACY = "accuracy"


class ModelTier(StrEnum):
    """Deprecated compatibility value; transcription strategy owns model selection."""

    COMPACT = "compact"
    STANDARD = "standard"
    LARGE = "large"


@dataclass(frozen=True, slots=True)
class RunnerResources:
    platform: str
    machine: str
    logical_cpus: int
    physical_cpus: int | None
    affinity_cpus: int | None
    cpu_quota_cores: float | None
    effective_cpus: int
    memory_total_bytes: int
    memory_available_bytes: int
    memory_limit_bytes: int | None
    effective_memory_available_bytes: int
    constraints: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ExecutionPolicy:
    """Engine-neutral resource budget derived from process-visible capacity."""

    profile: ProcessingProfile
    provisional: bool
    cpu_threads: int
    memory_budget_bytes: int
    recommended_model_tier: ModelTier | None = None
    constraints: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["profile"] = self.profile.value
        result["recommended_model_tier"] = (
            self.recommended_model_tier.value
            if self.recommended_model_tier is not None
            else None
        )
        return result
