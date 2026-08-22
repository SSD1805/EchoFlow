import json
from unittest.mock import Mock

import typer
from typer.testing import CliRunner

from scholion.cli_library import register_library_commands
from scholion.library.speaker_label_service import SpeakerRosterEntry
from scholion.library.speaker_labels import SpeakerDisplayLabel


def _app_with_speakers(service: Mock) -> typer.Typer:
    app = typer.Typer()
    container = Mock()
    container.speaker_labels.return_value = service
    register_library_commands(app, lambda context: container)
    return app


def test_speaker_list_preserves_evidence_ref_and_human_label() -> None:
    service = Mock()
    service.roster.return_value = (
        SpeakerRosterEntry("speaker-01", "Interviewer"),
        SpeakerRosterEntry("speaker-02", None),
    )
    app = _app_with_speakers(service)
    runner = CliRunner()

    human = runner.invoke(app, ["library", "speakers", "list", "job-1"])
    machine = runner.invoke(app, ["library", "speakers", "list", "job-1", "--json"])

    assert human.exit_code == 0
    assert "Interviewer (speaker-01)" in human.stdout
    assert "speaker-02" in human.stdout
    assert machine.exit_code == 0
    payload = json.loads(machine.stdout)
    assert payload == [
        {
            "display_label": "Interviewer",
            "display_name": "Interviewer (speaker-01)",
            "speaker_ref": "speaker-01",
        },
        {
            "display_label": None,
            "display_name": "speaker-02",
            "speaker_ref": "speaker-02",
        },
    ]


def test_speaker_name_writes_user_label_without_replacing_ref() -> None:
    service = Mock()
    service.set_label.return_value = SpeakerDisplayLabel(
        document_id="job-1",
        canonical_sha256="a" * 64,
        speaker_ref="speaker-02",
        label="Dr. Chen",
    )
    app = _app_with_speakers(service)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "library",
            "speakers",
            "name",
            "job-1",
            "speaker-02",
            "Dr. Chen",
        ],
    )

    assert result.exit_code == 0
    assert "Dr. Chen (speaker-02)" in result.stdout
    service.set_label.assert_called_once_with(
        "job-1", speaker_ref="speaker-02", label="Dr. Chen"
    )


def test_speaker_name_json_keeps_binding_provenance() -> None:
    service = Mock()
    service.set_label.return_value = SpeakerDisplayLabel(
        document_id="job-1",
        canonical_sha256="b" * 64,
        speaker_ref="speaker-01",
        label="Host",
    )
    app = _app_with_speakers(service)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "library",
            "speakers",
            "name",
            "job-1",
            "speaker-01",
            "Host",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "canonical_sha256": "b" * 64,
        "document_id": "job-1",
        "label": "Host",
        "speaker_ref": "speaker-01",
    }


def test_forget_speaker_name_reports_whether_current_binding_existed() -> None:
    service = Mock()
    service.remove_label.return_value = True
    app = _app_with_speakers(service)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "library",
            "speakers",
            "forget-name",
            "job-1",
            "speaker-01",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "removed": True,
        "speaker_ref": "speaker-01",
        "transcript_id": "job-1",
    }
    service.remove_label.assert_called_once_with("job-1", speaker_ref="speaker-01")
