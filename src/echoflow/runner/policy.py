from dataclasses import dataclass

from echoflow.runner.models import ExecutionPolicy, ProcessingProfile, RunnerResources


@dataclass(frozen=True, slots=True)
class RunnerPolicyPlanner:
    """Turn process-visible resources and user ceilings into a safe job budget."""

    memory_budget_fraction: float = 0.75
    max_cpu_threads: int | None = None
    max_memory_bytes: int | None = None

    def __post_init__(self) -> None:
        if not 0 < self.memory_budget_fraction <= 1:
            raise ValueError(
                "memory_budget_fraction must be greater than 0 and at most 1"
            )
        if self.max_cpu_threads is not None and self.max_cpu_threads < 1:
            raise ValueError("max_cpu_threads must be positive")
        if self.max_memory_bytes is not None and self.max_memory_bytes < 1:
            raise ValueError("max_memory_bytes must be positive")

    def plan(
        self, resources: RunnerResources, profile: ProcessingProfile
    ) -> ExecutionPolicy:
        constraints = list(resources.constraints)
        cpu_threads = resources.effective_cpus
        if self.max_cpu_threads is not None and self.max_cpu_threads < cpu_threads:
            cpu_threads = self.max_cpu_threads
            constraints.append("configured_cpu_limit")

        memory_budget = int(
            resources.effective_memory_available_bytes * self.memory_budget_fraction
        )
        if self.max_memory_bytes is not None and self.max_memory_bytes < memory_budget:
            memory_budget = self.max_memory_bytes
            constraints.append("configured_memory_limit")

        return ExecutionPolicy(
            profile=profile,
            provisional=profile is ProcessingProfile.SCREENING,
            cpu_threads=max(1, cpu_threads),
            memory_budget_bytes=max(0, memory_budget),
            constraints=tuple(dict.fromkeys(constraints)),
        )
