import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from typer.testing import CliRunner

from scholion.benchmarking.cli import app
from scholion.benchmarking.models import BenchmarkRunError, BenchmarkStatus
from scholion.core.measurements import NoOpExecutionObserver
from scholion.runner.models import ProcessingProfile
from scholion.tests.test_cli import transcription_plan

runner = CliRunner()


class Provider:
    def __init__(self, value):
        self.value = value
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self.value

    def override(self, value):
        self.value = value


class FakeContainer:
    def __init__(self):
        self.config = Provider(
            SimpleNamespace(PROCESSING_PROFILE=ProcessingProfile.BALANCED)
        )
        planner = Mock()
        planner.plan.return_value = transcription_plan()
        planner.plan_resume.return_value = planner.plan.return_value
        self.transcription_planner = Provider(planner)

        executor = Mock()
        executor.execute.return_value = Mock()
        self.transcription_executor = Provider(executor)

        benchmark_runner = Mock()

        def run(plan, *, execute, resume=False, planning_wall_seconds=0.0):
            execute(NoOpExecutionObserver())
            report = SimpleNamespace(
                status=BenchmarkStatus.COMPLETED,
                job_id=plan.job.job_id.value,
                real_time_factor=0.5,
                total_wall_seconds=1.0,
                planning_wall_seconds=planning_wall_seconds,
                execution_wall_seconds=0.9,
                process_tree=SimpleNamespace(
                    peak_rss_bytes=1024,
                    peak_cpu_percent=50.0,
                ),
            )
            return SimpleNamespace(
                report=report,
                report_path=Path("benchmark.json"),
                transcription=SimpleNamespace(
                    artifact=SimpleNamespace(path=Path("transcript.json"))
                ),
                to_dict=lambda: {
                    "benchmark_report_path": "benchmark.json",
                    "report": {"status": "completed", "resume": resume},
                },
            )

        benchmark_runner.run.side_effect = run
        self.benchmark_runner = Provider(benchmark_runner)


def test_fresh_benchmark_plans_executes_with_observer_and_emits_json():
    container = FakeContainer()

    with patch("scholion.benchmarking.cli.AppContainer", return_value=container):
        result = runner.invoke(app, ["recording.wav", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["report"]["status"] == "completed"
    assert "Scholion job ID: job-1" in result.stderr
    container.transcription_planner().plan.assert_called_once_with(
        Path("recording.wav"),
        output_dir=None,
        profile=ProcessingProfile.BALANCED,
    )
    observer = container.transcription_executor.calls[-1]["observer"]
    assert isinstance(observer, NoOpExecutionObserver)
    container.transcription_executor.value.execute.assert_called_once_with(
        container.transcription_planner().plan.return_value
    )


def test_resume_uses_authoritative_resume_plan_and_explicit_resume_execution():
    container = FakeContainer()

    with patch("scholion.benchmarking.cli.AppContainer", return_value=container):
        result = runner.invoke(
            app,
            ["recording.wav", "--resume", "job-1", "--json"],
        )

    assert result.exit_code == 0
    assert "Scholion job ID" not in result.stderr
    container.transcription_planner().plan_resume.assert_called_once()
    container.transcription_executor.value.execute.assert_called_once_with(
        container.transcription_planner().plan_resume.return_value,
        resume=True,
    )


def test_legacy_model_download_flag_is_not_exposed():
    container = FakeContainer()

    with patch("scholion.benchmarking.cli.AppContainer", return_value=container):
        result = runner.invoke(app, ["recording.wav", "--allow-model-download"])

    assert result.exit_code == 2
    container.benchmark_runner().run.assert_not_called()


@pytest.mark.parametrize(
    "override",
    [
        ["--strategy", "small-cpu-int8"],
        ["--profile", "accuracy"],
    ],
)
def test_resume_refuses_profile_or_strategy_override(override):
    container = FakeContainer()

    with patch("scholion.benchmarking.cli.AppContainer", return_value=container):
        result = runner.invoke(
            app,
            ["recording.wav", "--resume", "job-1", *override],
        )

    assert result.exit_code == 2
    assert "restores the original profile and strategy" in result.output
    container.benchmark_runner().run.assert_not_called()


def test_interrupted_benchmark_reports_path_and_exit_130():
    container = FakeContainer()
    container.benchmark_runner().run.side_effect = BenchmarkRunError(
        Path("partial.json"), BenchmarkStatus.INTERRUPTED, KeyboardInterrupt()
    )

    with patch("scholion.benchmarking.cli.AppContainer", return_value=container):
        result = runner.invoke(app, ["recording.wav"])

    assert result.exit_code == 130
    assert "partial.json" in result.stderr
    assert "completed checkpoints were retained" in result.stderr


def test_internal_failure_reports_type_without_secret_exception_message():
    container = FakeContainer()
    container.benchmark_runner().run.side_effect = BenchmarkRunError(
        Path("partial.json"),
        BenchmarkStatus.FAILED,
        RuntimeError("participant-secret-name"),
    )

    with patch("scholion.benchmarking.cli.AppContainer", return_value=container):
        result = runner.invoke(app, ["recording.wav"])

    assert result.exit_code == 3
    assert "RuntimeError" in result.stderr
    assert "participant-secret-name" not in result.output
