import json
from pathlib import Path
from unittest.mock import Mock

import typer
from typer.testing import CliRunner

from echoflow.cli_jobs import register_job_commands
from echoflow.workspace.lifecycle import JobLifecycleRecord, JobStatus
from echoflow.workspace.models import JobId


def _record(status=JobStatus.COMPLETED):
    fixture_root = Path.cwd() / "test-fixtures"
    output = fixture_root / "output"
    return JobLifecycleRecord(
        job_id=JobId("job-1"),
        input_path=fixture_root / "interview.wav",
        output_dir=output,
        status=status,
        started_at="2026-08-17T00:00:00+00:00",
        updated_at="2026-08-17T00:01:00+00:00",
        process_id=None,
        process_started_at=None,
        total_segments=4,
        completed_segments=4 if status is JobStatus.COMPLETED else 2,
        artifact_path=output / "interview.json"
        if status is JobStatus.COMPLETED
        else None,
    )


def _app_with_store(store):
    app = typer.Typer()
    container = Mock()
    container.job_lifecycle_store.return_value = store
    register_job_commands(app, lambda context: container)
    return app


def test_jobs_list_and_show_have_machine_readable_contracts():
    store = Mock()
    record = _record()
    store.list_records.return_value = (record,)
    store.get.return_value = record
    store.is_resumable.return_value = False
    runner = CliRunner()
    app = _app_with_store(store)

    listed = runner.invoke(app, ["jobs", "--json"])
    shown = runner.invoke(app, ["jobs", "show", "job-1", "--json"])

    assert listed.exit_code == 0
    assert json.loads(listed.stdout)[0]["job_id"] == "job-1"
    assert shown.exit_code == 0
    assert json.loads(shown.stdout)["status"] == "completed"


def test_jobs_human_views_include_progress_and_resume_state():
    store = Mock()
    record = _record(JobStatus.INTERRUPTED)
    store.list_records.return_value = (record,)
    store.get.return_value = record
    store.is_resumable.return_value = True
    runner = CliRunner()
    app = _app_with_store(store)

    listed = runner.invoke(app, ["jobs"])
    shown = runner.invoke(app, ["jobs", "show", "job-1"])

    assert listed.exit_code == 0
    assert "2/4" in listed.stdout
    assert "interview.wav" in listed.stdout
    assert shown.exit_code == 0
    assert "Resume" in shown.stdout
    assert "job-1" in shown.stdout


def test_jobs_discard_requires_nonrunning_job_and_can_skip_confirmation():
    store = Mock()
    store.get.return_value = _record()
    runner = CliRunner()
    app = _app_with_store(store)

    discarded = runner.invoke(app, ["jobs", "discard", "job-1", "--yes"])

    assert discarded.exit_code == 0
    store.discard.assert_called_once_with(JobId("job-1"))
    assert "Discarded private EchoFlow job job-1" in discarded.stdout

    store.reset_mock()
    store.get.return_value = _record(JobStatus.RUNNING)
    blocked = runner.invoke(app, ["jobs", "discard", "job-1", "--yes"])
    assert blocked.exit_code != 0
    store.discard.assert_not_called()
