import json
from unittest.mock import Mock, patch

from typer.testing import CliRunner

from echoflow.cli import app
from echoflow.core.health_check import OverallStatus
from echoflow.tests.test_cli import FakeContainer, Provider, report
from echoflow.transcription.export import TranscriptExportResult
from echoflow.workspace.models import Artifact, ArtifactKind

runner = CliRunner()


def _container_with_exporter() -> tuple[FakeContainer, Mock]:
    container = FakeContainer(report(OverallStatus.HEALTHY))
    exporter = Mock()
    result = container.transcription_executor().execute.return_value
    exporter.publish.return_value = TranscriptExportResult(
        (
            Artifact(
                result.job.job_id,
                ArtifactKind.TEXT,
                result.job.output_dir / "input.txt",
            ),
            Artifact(
                result.job.job_id,
                ArtifactKind.WEBVTT,
                result.job.output_dir / "input.vtt",
            ),
        )
    )
    container.transcript_exporter = Provider(exporter)
    return container, exporter


def test_transcribe_can_publish_repeatable_derived_exports():
    container, exporter = _container_with_exporter()
    with patch("echoflow.cli.AppContainer", return_value=container):
        result = runner.invoke(
            app,
            [
                "transcribe",
                "recording.wav",
                "--export",
                "txt",
                "--export",
                "vtt",
            ],
        )

    assert result.exit_code == 0
    assert "TXT export" in result.output
    assert "VTT export" in result.output
    execution = container.transcription_executor().execute.return_value
    exporter.publish.assert_called_once()
    assert exporter.publish.call_args.args[:2] == (execution.job, execution.transcript)
    assert tuple(value.value for value in exporter.publish.call_args.args[2]) == (
        "txt",
        "vtt",
    )


def test_transcribe_json_includes_derived_artifact_metadata():
    container, _ = _container_with_exporter()
    with patch("echoflow.cli.AppContainer", return_value=container):
        result = runner.invoke(
            app,
            ["transcribe", "recording.wav", "--export", "txt", "--json"],
        )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["transcript"]["text"] == "Test transcript."
    assert [artifact["kind"] for artifact in payload["exports"]] == ["txt", "vtt"]


def test_export_is_refused_for_dry_run_before_application_construction():
    with patch("echoflow.cli.AppContainer") as container:
        result = runner.invoke(
            app,
            ["transcribe", "recording.wav", "--dry-run", "--export", "srt"],
        )

    assert result.exit_code == 2
    assert "--export cannot be combined with --dry-run" in result.output
    container.assert_not_called()
