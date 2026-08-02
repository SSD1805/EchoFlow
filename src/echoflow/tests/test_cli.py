import json
from pathlib import Path
from unittest.mock import Mock, patch

from typer.testing import CliRunner

from echoflow.cli import app
from echoflow.core.config import AppConfig
from echoflow.core.health_check import (
    CheckResult,
    CheckStatus,
    HealthReport,
    OverallStatus,
)

runner = CliRunner()


def report(status: OverallStatus) -> HealthReport:
    check_status = {
        OverallStatus.HEALTHY: CheckStatus.PASS,
        OverallStatus.DEGRADED: CheckStatus.WARN,
        OverallStatus.UNHEALTHY: CheckStatus.FAIL,
    }[status]
    return HealthReport(
        status,
        (
            CheckResult(
                "workspace",
                check_status,
                "workspace result",
                status is not OverallStatus.DEGRADED,
            ),
        ),
    )


class Provider:
    def __init__(self, value):
        self.value = value

    def __call__(self):
        return self.value

    def override(self, value):
        self.value = value


class FakeContainer:
    def __init__(self, health_report):
        self.config = Provider(
            AppConfig(
                WORKSPACE_DIR=Path("original"),
                MIN_FREE_DISK_BYTES=0,
                WARN_FREE_DISK_BYTES=0,
                _env_file=None,
            )
        )
        service = Mock()
        service.run.return_value = health_report
        self.health_check = Provider(service)


def invoke_doctor(status: OverallStatus, *arguments: str):
    container = FakeContainer(report(status))
    with patch("echoflow.cli.AppContainer", return_value=container):
        result = runner.invoke(app, ["doctor", *arguments])
    return result, container


def test_bare_command_shows_help_without_constructing_application():
    with patch("echoflow.cli.AppContainer") as container:
        result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "doctor" in result.output
    container.assert_not_called()


def test_healthy_doctor_exits_zero_and_renders_each_check_once():
    result, _ = invoke_doctor(OverallStatus.HEALTHY)
    assert result.exit_code == 0
    assert result.output.count("workspace result") == 1


def test_degraded_exit_code_depends_on_strict_mode():
    ordinary, _ = invoke_doctor(OverallStatus.DEGRADED)
    strict, _ = invoke_doctor(OverallStatus.DEGRADED, "--strict")
    assert ordinary.exit_code == 0
    assert strict.exit_code == 1


def test_unhealthy_doctor_exits_one():
    result, _ = invoke_doctor(OverallStatus.UNHEALTHY)
    assert result.exit_code == 1


def test_json_output_is_parseable_and_unstyled():
    result, _ = invoke_doctor(OverallStatus.HEALTHY, "--json")
    payload = json.loads(result.stdout)
    assert payload["status"] == "healthy"
    assert "\x1b[" not in result.stdout


def test_workspace_option_reaches_config_as_a_path(tmp_path):
    result, container = invoke_doctor(
        OverallStatus.HEALTHY, "--workspace", str(tmp_path)
    )
    assert result.exit_code == 0
    assert tmp_path == container.config().WORKSPACE_DIR


def test_unknown_option_uses_click_usage_exit_code():
    result = runner.invoke(app, ["doctor", "--does-not-exist"])
    assert result.exit_code == 2


def test_unexpected_internal_failure_uses_reserved_internal_exit_code():
    with patch("echoflow.cli.AppContainer", side_effect=RuntimeError("private detail")):
        result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 3
    assert "RuntimeError" in result.stderr
    assert "private detail" not in result.output
