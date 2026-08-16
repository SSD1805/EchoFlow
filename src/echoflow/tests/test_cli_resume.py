from pathlib import Path
from unittest.mock import patch

import pytest

from echoflow.cli import app
from echoflow.core.health_check import OverallStatus
from echoflow.tests.test_cli import FakeContainer, report, runner
from echoflow.workspace.models import JobId


def test_resume_restores_plan_by_job_id_and_explicitly_resumes_execution():
    container = FakeContainer(report(OverallStatus.HEALTHY))
    planner = container.transcription_planner()
    planner.plan_resume.return_value = planner.plan.return_value

    with patch("echoflow.cli.AppContainer", return_value=container):
        result = runner.invoke(
            app,
            ["transcribe", "recording.wav", "--resume", "job-1"],
        )

    assert result.exit_code == 0
    planner.plan_resume.assert_called_once_with(
        Path("recording.wav"),
        output_dir=None,
        job_id=JobId("job-1"),
    )
    planner.plan.assert_not_called()
    container.transcription_executor().execute.assert_called_once_with(
        planner.plan_resume.return_value,
        allow_model_download=False,
        resume=True,
    )


@pytest.mark.parametrize(
    "override",
    [
        ["--strategy", "small-cpu-int8"],
        ["--profile", "accuracy"],
    ],
)
def test_resume_refuses_profile_or_strategy_override(override):
    container = FakeContainer(report(OverallStatus.HEALTHY))

    with patch("echoflow.cli.AppContainer", return_value=container):
        result = runner.invoke(
            app,
            ["transcribe", "recording.wav", "--resume", "job-1", *override],
        )

    assert result.exit_code == 2
    assert "restores the original profile and strategy" in result.output
    container.transcription_planner().plan.assert_not_called()
    container.transcription_planner().plan_resume.assert_not_called()
    container.transcription_executor().execute.assert_not_called()


def test_resume_cannot_be_combined_with_dry_run():
    container = FakeContainer(report(OverallStatus.HEALTHY))

    with patch("echoflow.cli.AppContainer", return_value=container):
        result = runner.invoke(
            app,
            ["transcribe", "recording.wav", "--resume", "job-1", "--dry-run"],
        )

    assert result.exit_code == 2
    assert "--resume cannot be combined with --dry-run" in result.output
    container.transcription_planner().plan.assert_not_called()
    container.transcription_planner().plan_resume.assert_not_called()
    container.transcription_executor().execute.assert_not_called()


def test_invalid_resume_job_id_fails_before_planning_without_echoing_input_path():
    container = FakeContainer(report(OverallStatus.HEALTHY))

    with patch("echoflow.cli.AppContainer", return_value=container):
        result = runner.invoke(
            app,
            ["transcribe", "participant-secret.wav", "--resume", "../unsafe"],
        )

    assert result.exit_code == 2
    assert "participant-secret.wav" not in result.output
    container.transcription_planner().plan.assert_not_called()
    container.transcription_planner().plan_resume.assert_not_called()
    container.transcription_executor().execute.assert_not_called()
