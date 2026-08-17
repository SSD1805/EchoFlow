import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from echoflow.cli import app
from echoflow.core.health_check import OverallStatus
from echoflow.runner.models import ProcessingProfile
from echoflow.tests.test_cli import FakeContainer, report, transcription_plan

runner = CliRunner()


def strategy_assessments():
    return (
        {
            "strategy": {
                "strategy_id": "tiny-cpu-int8",
                "model": "tiny",
                "quality_rank": 1,
                "model_cache_bytes": 150 * 1024**2,
                "estimated_peak_memory_bytes": 1_280 * 1024**2,
            },
            "memory_budget_bytes": 3 * 1024**3,
            "feasible": True,
            "rejection_reasons": [],
            "recommended": False,
            "cpu_threads": 4,
            "profile": "balanced",
        },
        {
            "strategy": {
                "strategy_id": "small-cpu-int8",
                "model": "small",
                "quality_rank": 2,
                "model_cache_bytes": 750 * 1024**2,
                "estimated_peak_memory_bytes": 2_304 * 1024**2,
            },
            "memory_budget_bytes": 3 * 1024**3,
            "feasible": True,
            "rejection_reasons": [],
            "recommended": True,
            "cpu_threads": 4,
            "profile": "balanced",
        },
        {
            "strategy": {
                "strategy_id": "medium-cpu-int8",
                "model": "medium",
                "quality_rank": 3,
                "model_cache_bytes": 2_500 * 1024**2,
                "estimated_peak_memory_bytes": 4_352 * 1024**2,
            },
            "memory_budget_bytes": 3 * 1024**3,
            "feasible": False,
            "rejection_reasons": ["insufficient_memory"],
            "recommended": False,
            "cpu_threads": 4,
            "profile": "balanced",
        },
    )


def configured_container():
    container = FakeContainer(report(OverallStatus.HEALTHY))
    container.transcription_planner().assess_strategies.return_value = (
        strategy_assessments()
    )
    return container


def test_strategies_json_exposes_feasible_recommended_and_rejected_choices():
    container = configured_container()
    with patch("echoflow.cli.AppContainer", return_value=container):
        result = runner.invoke(app, ["strategies", "--json"])

    payload = json.loads(result.stdout)
    assert result.exit_code == 0
    assert [item["strategy"]["strategy_id"] for item in payload] == [
        "tiny-cpu-int8",
        "small-cpu-int8",
        "medium-cpu-int8",
    ]
    assert [item["feasible"] for item in payload] == [True, True, False]
    assert payload[1]["recommended"] is True
    assert payload[2]["rejection_reasons"] == ["insufficient_memory"]
    container.transcription_planner().assess_strategies.assert_called_once_with(
        profile=ProcessingProfile.BALANCED
    )


def test_strategies_rich_output_marks_recommendation_and_capacity_state():
    container = configured_container()
    with patch("echoflow.cli.AppContainer", return_value=container):
        result = runner.invoke(app, ["strategies"])

    assert result.exit_code == 0
    assert "EchoFlow local transcription strategies" in result.output
    assert "small" in result.output
    assert "recommended" in result.output
    assert "false" in result.output


def test_strategies_profile_override_reaches_ranker():
    container = configured_container()
    with patch("echoflow.cli.AppContainer", return_value=container):
        result = runner.invoke(app, ["strategies", "--profile", "accuracy", "--json"])

    assert result.exit_code == 0
    container.transcription_planner().assess_strategies.assert_called_once_with(
        profile=ProcessingProfile.ACCURACY
    )


def test_transcribe_explicit_strategy_reaches_planner_without_silent_substitution():
    container = configured_container()
    with patch("echoflow.cli.AppContainer", return_value=container):
        result = runner.invoke(
            app,
            [
                "transcribe",
                "recording.wav",
                "--dry-run",
                "--strategy",
                "tiny-cpu-int8",
            ],
        )

    assert result.exit_code == 0
    container.transcription_planner().plan.assert_called_once_with(
        Path("recording.wav"),
        output_dir=None,
        profile=ProcessingProfile.BALANCED,
        strategy_id="tiny-cpu-int8",
        audio_stream_index=None,
        enhance=False,
    )


def test_accelerated_dry_run_renders_actual_device_and_compute_type():
    container = configured_container()
    plan = transcription_plan()
    container.transcription_planner().plan.return_value = replace(
        plan,
        engine=replace(plan.engine, device="cuda", compute_type="float16"),
    )

    with patch("echoflow.cli.AppContainer", return_value=container):
        result = runner.invoke(app, ["transcribe", "recording.wav", "--dry-run"])

    assert result.exit_code == 0
    assert "Execution target" in result.output
    assert "cuda / float16" in result.output
    assert "CPU configuration" not in result.output
