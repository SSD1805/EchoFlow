from contextlib import nullcontext
from unittest.mock import Mock

import pytest

from scholion.app.job_runner import TranscriptionJobRunner
from scholion.core.errors import ScholionError
from scholion.transcription.models import TranscriptionExecutionResult
from scholion.workspace.models import Artifact, ArtifactKind, Job, JobId


class _Observer:
    def span(self, name):
        del name
        return nullcontext()

    def record_value(self, name, value):
        del name, value


class _Executor:
    def __init__(self, outcome, observer):
        self.outcome = outcome
        self.observer = observer

    def execute(self, plan, **kwargs):
        del plan, kwargs
        self.observer.record_value("segments.total", 3)
        self.observer.record_value("segments.completed", 1)
        self.observer.record_value("segments.completed", 3)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


def _job(tmp_path):
    source = tmp_path / "audio.wav"
    source.write_bytes(b"audio")
    workspace = tmp_path / "state" / "jobs" / "job-1"
    workspace.mkdir(parents=True)
    output = tmp_path / "output"
    output.mkdir()
    return Job(JobId("job-1"), source, workspace, output)


def test_runner_records_progress_and_completion(tmp_path):
    job = _job(tmp_path)
    artifact = Artifact(
        job.job_id, ArtifactKind.CANONICAL_JSON, job.output_dir / "a.json"
    )
    result = Mock(spec=TranscriptionExecutionResult)
    result.job = job
    result.artifact = artifact
    lifecycle = Mock()
    executor_holder = {}

    def factory(observer):
        executor_holder["observer"] = observer
        return _Executor(result, observer)

    runner = TranscriptionJobRunner(lifecycle, factory)
    returned = runner.execute(Mock(job=job), observer=_Observer())

    assert returned is result
    lifecycle.start.assert_called_once_with(job)
    lifecycle.record_progress.assert_any_call(
        job, completed_segments=1, total_segments=3
    )
    lifecycle.record_progress.assert_any_call(
        job, completed_segments=3, total_segments=3
    )
    lifecycle.complete.assert_called_once_with(job, artifact)
    lifecycle.fail.assert_not_called()
    lifecycle.interrupt.assert_not_called()


def test_runner_marks_keyboard_interrupt(tmp_path):
    job = _job(tmp_path)
    lifecycle = Mock()
    runner = TranscriptionJobRunner(
        lifecycle, lambda observer: _Executor(KeyboardInterrupt(), observer)
    )

    with pytest.raises(KeyboardInterrupt):
        runner.execute(Mock(job=job))

    lifecycle.interrupt.assert_called_once_with(job)
    lifecycle.fail.assert_not_called()


def test_runner_records_typed_and_untyped_failures(tmp_path):
    job = _job(tmp_path)

    class ExampleError(ScholionError):
        pass

    typed_lifecycle = Mock()
    typed_runner = TranscriptionJobRunner(
        typed_lifecycle,
        lambda observer: _Executor(ExampleError("boom"), observer),
    )
    with pytest.raises(ExampleError):
        typed_runner.execute(Mock(job=job))
    typed_lifecycle.fail.assert_called_once()
    assert typed_lifecycle.fail.call_args.kwargs["error_code"] is not None

    untyped_lifecycle = Mock()
    untyped_runner = TranscriptionJobRunner(
        untyped_lifecycle,
        lambda observer: _Executor(RuntimeError("boom"), observer),
    )
    with pytest.raises(RuntimeError):
        untyped_runner.execute(Mock(job=job))
    untyped_lifecycle.fail.assert_called_once_with(job, error_code=None)
