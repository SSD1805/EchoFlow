from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from time import perf_counter
from typing import Protocol


class CheckStatus(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class OverallStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


DetailValue = str | int | float | bool | None


@dataclass(frozen=True, slots=True)
class CheckResult:
    check_id: str
    status: CheckStatus
    summary: str
    required: bool
    duration_ms: float = 0.0
    error_code: str | None = None
    details: Mapping[str, DetailValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["status"] = self.status.value
        return result


@dataclass(frozen=True, slots=True)
class HealthReport:
    status: OverallStatus
    checks: tuple[CheckResult, ...]

    def exit_code(self, *, strict: bool = False) -> int:
        if self.status is OverallStatus.UNHEALTHY:
            return 1
        if strict and self.status is OverallStatus.DEGRADED:
            return 1
        return 0

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "checks": [check.to_dict() for check in self.checks],
        }


class HealthProbe(Protocol):
    check_id: str
    required: bool

    def check(self) -> CheckResult: ...


class HealthCheck:
    """Run independent local diagnostics and aggregate their typed results."""

    def __init__(self, probes: Sequence[HealthProbe]):
        if not probes:
            raise ValueError("At least one health probe is required")
        check_ids = [probe.check_id for probe in probes]
        if len(set(check_ids)) != len(check_ids):
            raise ValueError("Health probe IDs must be unique")
        self.probes = tuple(probes)

    def run(self) -> HealthReport:
        results = tuple(self._run_probe(probe) for probe in self.probes)
        return HealthReport(status=self._aggregate(results), checks=results)

    @staticmethod
    def _run_probe(probe: HealthProbe) -> CheckResult:
        started = perf_counter()
        try:
            result = probe.check()
        except Exception as exc:
            return CheckResult(
                check_id=probe.check_id,
                status=CheckStatus.FAIL,
                summary="Diagnostic could not complete",
                required=probe.required,
                duration_ms=(perf_counter() - started) * 1000,
                error_code="probe_error",
                details={"exception_type": type(exc).__name__},
            )
        return CheckResult(
            check_id=result.check_id,
            status=result.status,
            summary=result.summary,
            required=result.required,
            duration_ms=(perf_counter() - started) * 1000,
            error_code=result.error_code,
            details=result.details,
        )

    @staticmethod
    def _aggregate(results: Sequence[CheckResult]) -> OverallStatus:
        if any(
            result.required and result.status is CheckStatus.FAIL for result in results
        ):
            return OverallStatus.UNHEALTHY
        if any(result.status is not CheckStatus.PASS for result in results):
            return OverallStatus.DEGRADED
        return OverallStatus.HEALTHY
