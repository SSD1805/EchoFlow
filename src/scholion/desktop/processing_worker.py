"""Dedicated worker entrypoint for long-running desktop processing tasks.

Tauri starts this module directly and owns the child-process lifetime. The worker accepts only
a small typed operation union, then delegates planning, model custody, checkpointing,
transcription, and publication to existing Python application services.
"""

from __future__ import annotations

import json
import sys
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from scholion.app.app_container import AppContainer
from scholion.app.job_runner import TranscriptionJobRunner
from scholion.runner.models import ProcessingProfile
from scholion.transcription.export import TranscriptExportFormat
from scholion.transcription.speaker_models import SpeakerDiarizationRequest
from scholion.workspace.models import JobId

_MAX_TASK_BYTES = 64 * 1024


class _TaskKind(BaseModel):
    model_config = ConfigDict(extra="allow")

    task_id: str = Field(min_length=1, max_length=128)
    kind: Literal[
        "transcription_start",
        "transcription_resume",
        "transcription_retry",
        "model_install",
        "model_remove",
    ]


class _TranscriptionOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1, max_length=128)
    job_id: str = Field(min_length=1, max_length=200)
    profile: ProcessingProfile = ProcessingProfile.BALANCED
    strategy_id: str | None = Field(default=None, min_length=1, max_length=200)
    audio_stream_index: int | None = Field(default=None, ge=0, le=10_000)
    enhance: bool = False
    diarize: bool = False
    allow_diarization_model_download: bool = False
    speakers: int | None = Field(default=None, ge=1, le=100)
    min_speakers: int | None = Field(default=None, ge=1, le=100)
    max_speakers: int | None = Field(default=None, ge=1, le=100)
    export_formats: tuple[TranscriptExportFormat, ...] = Field(default=(), max_length=3)

    @field_validator("task_id", "job_id", "strategy_id")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("processing task text values cannot be blank")
        return stripped

    def diarization_request(self) -> SpeakerDiarizationRequest | None:
        if not self.diarize:
            if self.allow_diarization_model_download or any(
                value is not None
                for value in (self.speakers, self.min_speakers, self.max_speakers)
            ):
                raise ValueError(
                    "diarization options require diarization to be enabled"
                )
            return None
        return SpeakerDiarizationRequest(
            num_speakers=self.speakers,
            min_speakers=self.min_speakers,
            max_speakers=self.max_speakers,
        )


class _TranscriptionStart(_TranscriptionOptions):
    kind: Literal["transcription_start"]
    input_path: str = Field(min_length=1, max_length=32_768)

    @field_validator("input_path")
    @classmethod
    def strip_input_path(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("input_path cannot be blank")
        return stripped


class _TranscriptionResume(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1, max_length=128)
    kind: Literal["transcription_resume"]
    job_id: str = Field(min_length=1, max_length=200)
    diarize: bool = False
    allow_diarization_model_download: bool = False
    speakers: int | None = Field(default=None, ge=1, le=100)
    min_speakers: int | None = Field(default=None, ge=1, le=100)
    max_speakers: int | None = Field(default=None, ge=1, le=100)
    export_formats: tuple[TranscriptExportFormat, ...] = Field(default=(), max_length=3)

    def diarization_request(self) -> SpeakerDiarizationRequest | None:
        if not self.diarize:
            if self.allow_diarization_model_download or any(
                value is not None
                for value in (self.speakers, self.min_speakers, self.max_speakers)
            ):
                raise ValueError(
                    "diarization options require diarization to be enabled"
                )
            return None
        return SpeakerDiarizationRequest(
            num_speakers=self.speakers,
            min_speakers=self.min_speakers,
            max_speakers=self.max_speakers,
        )


class _TranscriptionRetry(_TranscriptionOptions):
    kind: Literal["transcription_retry"]
    source_job_id: str = Field(min_length=1, max_length=200)


class _ModelInstall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1, max_length=128)
    kind: Literal["model_install"]
    model_id: str = Field(min_length=1, max_length=200)
    revision: str | None = Field(default=None, min_length=1, max_length=500)


class _ModelRemove(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1, max_length=128)
    kind: Literal["model_remove"]
    model_id: str = Field(min_length=1, max_length=200)
    expected_revision: str = Field(min_length=1, max_length=500)


def _runner(container: AppContainer) -> TranscriptionJobRunner:
    return TranscriptionJobRunner(
        lifecycle_store=container.job_lifecycle_store(),
        executor_factory=lambda observer: container.transcription_executor(
            observer=observer
        ),
    )


def _publish(
    container: AppContainer,
    result: object,
    formats: tuple[TranscriptExportFormat, ...],
) -> None:
    if not formats:
        return
    from scholion.transcription.models import TranscriptionExecutionResult

    if not isinstance(result, TranscriptionExecutionResult):
        raise TypeError("unexpected transcription result")
    container.transcript_exporter().publish(result.job, result.transcript, formats)


def _run_start(task: _TranscriptionStart, container: AppContainer) -> None:
    plan = container.transcription_planner().plan(
        task.input_path,
        profile=task.profile,
        strategy_id=task.strategy_id,
        audio_stream_index=task.audio_stream_index,
        job_id=JobId(task.job_id),
        enhance=task.enhance,
    )
    result = _runner(container).execute(
        plan,
        diarization_request=task.diarization_request(),
        allow_diarization_model_download=task.allow_diarization_model_download,
    )
    _publish(container, result, task.export_formats)


def _run_resume(task: _TranscriptionResume, container: AppContainer) -> None:
    job_id = JobId(task.job_id)
    record = container.job_lifecycle_store().get(job_id)
    plan = container.transcription_planner().plan_resume(
        record.input_path,
        job_id=job_id,
    )
    result = _runner(container).execute(
        plan,
        resume=True,
        diarization_request=task.diarization_request(),
        allow_diarization_model_download=task.allow_diarization_model_download,
    )
    _publish(container, result, task.export_formats)


def _run_retry(task: _TranscriptionRetry, container: AppContainer) -> None:
    source = container.job_lifecycle_store().get(JobId(task.source_job_id))
    plan = container.transcription_planner().plan(
        source.input_path,
        profile=task.profile,
        strategy_id=task.strategy_id,
        audio_stream_index=task.audio_stream_index,
        job_id=JobId(task.job_id),
        enhance=task.enhance,
    )
    result = _runner(container).execute(
        plan,
        diarization_request=task.diarization_request(),
        allow_diarization_model_download=task.allow_diarization_model_download,
    )
    _publish(container, result, task.export_formats)


def _run_model_install(task: _ModelInstall, container: AppContainer) -> None:
    container.model_manager().install(task.model_id, revision=task.revision)


def _run_model_remove(task: _ModelRemove, container: AppContainer) -> None:
    manager = container.model_manager()
    current = manager.resolved_revision(task.model_id)
    if current != task.expected_revision:
        raise ValueError("model state changed; refresh before removing it")
    manager.remove(task.model_id)


def run_task(payload: object, container: AppContainer) -> None:
    kind = _TaskKind.model_validate(payload)
    if kind.kind == "transcription_start":
        _run_start(_TranscriptionStart.model_validate(payload), container)
        return
    if kind.kind == "transcription_resume":
        _run_resume(_TranscriptionResume.model_validate(payload), container)
        return
    if kind.kind == "transcription_retry":
        _run_retry(_TranscriptionRetry.model_validate(payload), container)
        return
    if kind.kind == "model_install":
        _run_model_install(_ModelInstall.model_validate(payload), container)
        return
    _run_model_remove(_ModelRemove.model_validate(payload), container)


def main() -> int:
    raw = sys.stdin.buffer.read(_MAX_TASK_BYTES + 1)
    if len(raw) > _MAX_TASK_BYTES:
        return 2
    try:
        payload = json.loads(raw)
        run_task(payload, AppContainer())
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, ValueError):
        return 2
    except KeyboardInterrupt:
        return 130
    except BaseException:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
