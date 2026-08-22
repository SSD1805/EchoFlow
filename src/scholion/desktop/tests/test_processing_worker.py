from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from scholion.desktop import processing_worker as worker
from scholion.runner.models import ProcessingProfile
from scholion.transcription.export import TranscriptExportFormat
from scholion.workspace.models import JobId


class _Planner:
    def __init__(self) -> None:
        self.plan_calls: list[dict[str, object]] = []
        self.resume_calls: list[tuple[Path, JobId]] = []
        self.plan_result = object()
        self.resume_result = object()

    def plan(self, input_path: str | Path, **kwargs: object) -> object:
        self.plan_calls.append({"input_path": input_path, **kwargs})
        return self.plan_result

    def plan_resume(self, input_path: Path, *, job_id: JobId) -> object:
        self.resume_calls.append((input_path, job_id))
        return self.resume_result


class _Lifecycle:
    def __init__(self) -> None:
        self.records = {
            JobId("source-job"): SimpleNamespace(
                input_path=Path("/private/source.m4a")
            ),
            JobId("resume-job"): SimpleNamespace(
                input_path=Path("/private/resume.m4a")
            ),
        }

    def get(self, job_id: JobId) -> object:
        return self.records[job_id]


class _ModelManager:
    def __init__(self) -> None:
        self.revisions = {"small": "revision-1"}
        self.installs: list[tuple[str, str | None]] = []
        self.removals: list[str] = []

    def install(self, model_id: str, *, revision: str | None) -> None:
        self.installs.append((model_id, revision))

    def resolved_revision(self, model_id: str) -> str | None:
        return self.revisions.get(model_id)

    def remove(self, model_id: str) -> None:
        self.removals.append(model_id)


class _Container:
    def __init__(self) -> None:
        self.planner = _Planner()
        self.lifecycle = _Lifecycle()
        self.models = _ModelManager()
        self.executor_observers: list[object] = []

    def transcription_planner(self) -> _Planner:
        return self.planner

    def job_lifecycle_store(self) -> _Lifecycle:
        return self.lifecycle

    def model_manager(self) -> _ModelManager:
        return self.models

    def transcription_executor(self, *, observer: object) -> str:
        self.executor_observers.append(observer)
        return "executor"


class _Runner:
    def __init__(self) -> None:
        self.calls: list[tuple[object, dict[str, object]]] = []
        self.result = object()

    def execute(self, plan: object, **kwargs: object) -> object:
        self.calls.append((plan, kwargs))
        return self.result


def _install_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[_Runner, list[tuple[object, object, tuple[TranscriptExportFormat, ...]]]]:
    runner = _Runner()
    publications: list[tuple[object, object, tuple[TranscriptExportFormat, ...]]] = []
    monkeypatch.setattr(worker, "_runner", lambda container: runner)
    monkeypatch.setattr(
        worker,
        "_publish",
        lambda container, result, formats: publications.append(
            (container, result, formats)
        ),
    )
    return runner, publications


def test_start_uses_exact_job_identity_and_explicit_processing_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    container = _Container()
    runner, publications = _install_runner(monkeypatch)

    worker.run_task(
        {
            "task_id": "task-start",
            "kind": "transcription_start",
            "job_id": "new-job",
            "input_path": "  /private/interview.m4a  ",
            "profile": "accuracy",
            "strategy_id": "small-cpu-int8",
            "audio_stream_index": 2,
            "enhance": True,
            "diarize": True,
            "allow_diarization_model_download": True,
            "min_speakers": 2,
            "max_speakers": 4,
            "export_formats": ["txt", "srt"],
        },
        cast(Any, container),
    )

    assert container.planner.plan_calls == [
        {
            "input_path": "/private/interview.m4a",
            "profile": ProcessingProfile.ACCURACY,
            "strategy_id": "small-cpu-int8",
            "audio_stream_index": 2,
            "job_id": JobId("new-job"),
            "enhance": True,
        }
    ]
    assert len(runner.calls) == 1
    _, kwargs = runner.calls[0]
    request = kwargs["diarization_request"]
    assert request is not None
    assert request.min_speakers == 2
    assert request.max_speakers == 4
    assert kwargs["allow_diarization_model_download"] is True
    assert publications == [
        (
            container,
            runner.result,
            (TranscriptExportFormat.TEXT, TranscriptExportFormat.SUBRIP),
        )
    ]


def test_resume_restores_backend_checkpoint_contract_without_replanning_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    container = _Container()
    runner, publications = _install_runner(monkeypatch)

    worker.run_task(
        {
            "task_id": "task-resume",
            "kind": "transcription_resume",
            "job_id": "resume-job",
            "export_formats": ["vtt"],
        },
        cast(Any, container),
    )

    assert container.planner.resume_calls == [
        (Path("/private/resume.m4a"), JobId("resume-job"))
    ]
    assert container.planner.plan_calls == []
    assert runner.calls == [
        (
            container.planner.resume_result,
            {
                "resume": True,
                "diarization_request": None,
                "allow_diarization_model_download": False,
            },
        )
    ]
    assert publications == [
        (
            container,
            runner.result,
            (TranscriptExportFormat.WEBVTT,),
        )
    ]


def test_retry_creates_fresh_plan_from_source_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    container = _Container()
    runner, _ = _install_runner(monkeypatch)

    worker.run_task(
        {
            "task_id": "task-retry",
            "kind": "transcription_retry",
            "job_id": "fresh-job",
            "source_job_id": "source-job",
            "profile": "screening",
            "enhance": False,
        },
        cast(Any, container),
    )

    assert container.planner.plan_calls == [
        {
            "input_path": Path("/private/source.m4a"),
            "profile": ProcessingProfile.SCREENING,
            "strategy_id": None,
            "audio_stream_index": None,
            "job_id": JobId("fresh-job"),
            "enhance": False,
        }
    ]
    assert runner.calls[0][0] is container.planner.plan_result
    assert runner.calls[0][1]["diarization_request"] is None


def test_model_install_and_version_bound_remove_are_explicit() -> None:
    container = _Container()

    worker.run_task(
        {
            "task_id": "task-install",
            "kind": "model_install",
            "model_id": "small",
            "revision": "requested-revision",
        },
        cast(Any, container),
    )
    worker.run_task(
        {
            "task_id": "task-remove",
            "kind": "model_remove",
            "model_id": "small",
            "expected_revision": "revision-1",
        },
        cast(Any, container),
    )

    assert container.models.installs == [("small", "requested-revision")]
    assert container.models.removals == ["small"]


def test_model_remove_refuses_changed_local_revision() -> None:
    container = _Container()

    with pytest.raises(ValueError, match="model state changed"):
        worker.run_task(
            {
                "task_id": "task-remove",
                "kind": "model_remove",
                "model_id": "small",
                "expected_revision": "stale-revision",
            },
            cast(Any, container),
        )

    assert container.models.removals == []


def test_diarization_parameters_require_explicit_enablement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    container = _Container()
    _install_runner(monkeypatch)

    with pytest.raises(ValueError, match="require diarization"):
        worker.run_task(
            {
                "task_id": "task-invalid-diarization",
                "kind": "transcription_start",
                "job_id": "new-job",
                "input_path": "/private/interview.m4a",
                "diarize": False,
                "speakers": 2,
            },
            cast(Any, container),
        )


def test_worker_runner_uses_existing_lifecycle_and_executor_authorities() -> None:
    container = _Container()

    result = worker._runner(cast(Any, container))
    executor = result.executor_factory(cast(Any, object()))

    assert result.lifecycle_store is container.lifecycle
    assert executor == "executor"
    assert len(container.executor_observers) == 1


def test_publish_is_noop_without_formats_and_rejects_unexpected_result() -> None:
    container = _Container()

    worker._publish(cast(Any, container), object(), ())
    with pytest.raises(TypeError, match="unexpected transcription result"):
        worker._publish(
            cast(Any, container),
            object(),
            (TranscriptExportFormat.TEXT,),
        )


def _stdin(monkeypatch: pytest.MonkeyPatch, payload: bytes) -> None:
    monkeypatch.setattr(
        worker.sys,
        "stdin",
        cast(Any, SimpleNamespace(buffer=BytesIO(payload))),
    )


def test_main_rejects_oversized_invalid_and_validation_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stdin(monkeypatch, b"x" * (worker._MAX_TASK_BYTES + 1))
    assert worker.main() == 2

    _stdin(monkeypatch, b"not-json")
    assert worker.main() == 2

    _stdin(monkeypatch, b"{}")
    assert worker.main() == 2


def test_main_maps_success_interrupt_and_unexpected_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = b'{"task_id":"task","kind":"model_install","model_id":"small"}'
    monkeypatch.setattr(worker, "AppContainer", lambda: cast(Any, object()))

    _stdin(monkeypatch, payload)
    monkeypatch.setattr(worker, "run_task", lambda value, container: None)
    assert worker.main() == 0

    _stdin(monkeypatch, payload)

    def interrupt(value: object, container: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(worker, "run_task", interrupt)
    assert worker.main() == 130

    _stdin(monkeypatch, payload)

    def explode(value: object, container: object) -> None:
        raise RuntimeError("private internal failure")

    monkeypatch.setattr(worker, "run_task", explode)
    assert worker.main() == 1
