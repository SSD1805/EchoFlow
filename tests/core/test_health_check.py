from dataclasses import FrozenInstanceError, replace
from unittest.mock import patch

import pytest

from src.core.health_check import (
    CheckResult,
    CheckStatus,
    HealthCheck,
    HealthReport,
    OverallStatus,
)


class Probe:
    def __init__(
        self,
        check_id: str,
        status: CheckStatus = CheckStatus.PASS,
        *,
        required: bool = True,
        error: Exception | None = None,
    ):
        self.check_id = check_id
        self.status = status
        self.required = required
        self.error = error

    def check(self) -> CheckResult:
        if self.error:
            raise self.error
        return CheckResult(
            self.check_id, self.status, f"{self.check_id} result", self.required
        )


def test_all_passing_probes_are_healthy_and_keep_order():
    report = HealthCheck((Probe("workspace"), Probe("disk"))).run()
    assert report.status is OverallStatus.HEALTHY
    assert [check.check_id for check in report.checks] == ["workspace", "disk"]
    assert all(check.duration_ms >= 0 for check in report.checks)
    assert report.exit_code() == 0


def test_status_values_are_stable_wire_contracts():
    assert [status.value for status in CheckStatus] == ["pass", "warn", "fail"]
    assert [status.value for status in OverallStatus] == [
        "healthy",
        "degraded",
        "unhealthy",
    ]


@pytest.mark.parametrize(
    ("status", "required", "overall"),
    [
        (CheckStatus.WARN, True, OverallStatus.DEGRADED),
        (CheckStatus.FAIL, False, OverallStatus.DEGRADED),
        (CheckStatus.FAIL, True, OverallStatus.UNHEALTHY),
    ],
)
def test_aggregation_distinguishes_warning_optional_and_required_failures(
    status, required, overall
):
    report = HealthCheck((Probe("diagnostic", status, required=required),)).run()
    assert report.status is overall


def test_required_failure_takes_precedence_over_warning_in_any_order():
    warn = Probe("optional", CheckStatus.WARN, required=False)
    fail = Probe("required", CheckStatus.FAIL)
    assert HealthCheck((warn, fail)).run().status is OverallStatus.UNHEALTHY
    assert HealthCheck((fail, warn)).run().status is OverallStatus.UNHEALTHY


def test_strict_mode_changes_only_degraded_exit_code():
    degraded = HealthCheck((Probe("ffmpeg", CheckStatus.WARN, required=False),)).run()
    assert degraded.exit_code() == 0
    assert degraded.exit_code(strict=True) == 1
    healthy = replace(degraded, status=OverallStatus.HEALTHY)
    assert healthy.exit_code(strict=True) == 0
    unhealthy = replace(degraded, status=OverallStatus.UNHEALTHY)
    assert unhealthy.exit_code() == 1


def test_result_models_are_immutable_slotted_values_with_safe_defaults():
    result = CheckResult("probe", CheckStatus.PASS, "done", True)
    assert result.duration_ms == 0.0
    assert result.error_code is None
    assert result.details == {}
    assert not hasattr(result, "__dict__")
    with pytest.raises(FrozenInstanceError):
        result.summary = "changed"

    report = HealthReport(OverallStatus.HEALTHY, (result,))
    assert not hasattr(report, "__dict__")
    with pytest.raises(FrozenInstanceError):
        report.status = OverallStatus.UNHEALTHY


def test_probe_exception_is_sanitized_and_later_probes_still_run():
    report = HealthCheck(
        (Probe("broken", error=RuntimeError("secret detail")), Probe("next"))
    ).run()
    broken, next_result = report.checks
    assert broken.status is CheckStatus.FAIL
    assert broken.error_code == "probe_error"
    assert broken.details == {"exception_type": "RuntimeError"}
    assert "secret detail" not in broken.summary
    assert next_result.status is CheckStatus.PASS


def test_empty_and_duplicate_probe_sets_are_rejected():
    with pytest.raises(ValueError, match="At least one"):
        HealthCheck(())
    with pytest.raises(ValueError, match="unique"):
        HealthCheck((Probe("same"), Probe("same")))


def test_report_serialization_uses_plain_enum_values():
    payload = HealthCheck((Probe("workspace"),)).run().to_dict()
    assert set(payload) == {"status", "checks"}
    assert payload["status"] == "healthy"
    assert set(payload["checks"][0]) == {
        "check_id",
        "status",
        "summary",
        "required",
        "duration_ms",
        "error_code",
        "details",
    }
    assert payload["checks"][0]["status"] == "pass"


def test_probe_durations_are_reported_in_milliseconds():
    with patch("src.core.health_check.perf_counter", side_effect=(10.0, 10.25)):
        result = HealthCheck((Probe("timed"),)).run().checks[0]
    assert result.duration_ms == pytest.approx(250.0)


def test_failed_probe_duration_is_reported_in_milliseconds():
    with patch("src.core.health_check.perf_counter", side_effect=(2.0, 2.5)):
        result = HealthCheck((Probe("timed", error=RuntimeError()),)).run().checks[0]
    assert result.duration_ms == pytest.approx(500.0)
