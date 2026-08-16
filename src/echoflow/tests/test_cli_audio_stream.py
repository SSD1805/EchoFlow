from pathlib import Path
from unittest.mock import patch

from echoflow.cli import app
from echoflow.core.health_check import OverallStatus
from echoflow.tests.test_cli import FakeContainer, report, runner


def test_dry_run_passes_explicit_audio_stream_to_fresh_planner() -> None:
    container = FakeContainer(report(OverallStatus.HEALTHY))

    with patch("echoflow.cli.AppContainer", return_value=container):
        result = runner.invoke(
            app,
            ["transcribe", "recording.mkv", "--dry-run", "--audio-stream", "5", "--json"],
        )

    assert result.exit_code == 0
    container.transcription_planner().plan.assert_called_once_with(
        Path("recording.mkv"),
        output_dir=None,
        profile=container.config().PROCESSING_PROFILE,
        audio_stream_index=5,
    )
    container.transcription_executor().execute.assert_not_called()
