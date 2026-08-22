import json
from unittest.mock import patch

from scholion.cli import app
from scholion.core.health_check import OverallStatus
from scholion.tests.test_cli import FakeContainer, report, runner


def test_fresh_execution_surfaces_resume_job_id_before_completion():
    container = FakeContainer(report(OverallStatus.HEALTHY))

    with patch("scholion.cli.AppContainer", return_value=container):
        result = runner.invoke(app, ["transcribe", "recording.wav"])

    assert result.exit_code == 0
    assert result.stderr.strip() == "Scholion job ID: job-1"
    assert "recording.wav" not in result.stderr


def test_job_id_notice_does_not_contaminate_json_stdout():
    container = FakeContainer(report(OverallStatus.HEALTHY))

    with patch("scholion.cli.AppContainer", return_value=container):
        result = runner.invoke(app, ["transcribe", "recording.wav", "--json"])

    payload = json.loads(result.stdout)
    assert result.exit_code == 0
    assert payload["job"]["job_id"] == "job-1"
    assert result.stderr.strip() == "Scholion job ID: job-1"
