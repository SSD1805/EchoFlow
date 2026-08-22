from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager, suppress
from typing import Protocol

from scholion.core.errors import ScholionError
from scholion.core.measurements import ExecutionObserver, NoOpExecutionObserver
from scholion.transcription.models import (
    TranscriptionExecutionResult,
    TranscriptionJobPlan,
)
from scholion.transcription.speaker_models import SpeakerDiarizationRequest
from scholion.workspace.lifecycle import JobLifecycleStore
from scholion.workspace.models import Job


class TranscriptionExecutorLike(Protocol):
    def execute(
        self,
        plan: TranscriptionJobPlan,
        *,
        resume: bool = False,
        diarization_request: SpeakerDiarizationRequest | None = None,
        allow_diarization_model_download: bool = False,
    ) -> TranscriptionExecutionResult: ...


ExecutorFactory = Callable[[ExecutionObserver], TranscriptionExecutorLike]


class _LifecycleProgressObserver:
    def __init__(self, store: JobLifecycleStore, job: Job) -> None:
        self.store = store
        self.job = job
        self.total_segments: int | None = None
        self.completed_segments = 0

    @contextmanager
    def span(self, name: str) -> Iterator[None]:
        del name
        yield

    def record_value(self, name: str, value: int | float) -> None:
        if name == "segments.total":
            self.total_segments = int(value)
        elif name == "segments.completed":
            self.completed_segments = int(value)
        else:
            return
        if self.total_segments is None:
            return
        self.store.record_progress(
            self.job,
            completed_segments=self.completed_segments,
            total_segments=self.total_segments,
        )


class _CombinedExecutionObserver:
    def __init__(self, *observers: ExecutionObserver) -> None:
        self.observers = observers

    @contextmanager
    def span(self, name: str) -> Iterator[None]:
        with ExitStack() as stack:
            for observer in self.observers:
                stack.enter_context(observer.span(name))
            yield

    def record_value(self, name: str, value: int | float) -> None:
        for observer in self.observers:
            observer.record_value(name, value)


class TranscriptionJobRunner:
    """Own lifecycle state around one synchronous transcription execution."""

    def __init__(
        self,
        lifecycle_store: JobLifecycleStore,
        executor_factory: ExecutorFactory,
    ) -> None:
        self.lifecycle_store = lifecycle_store
        self.executor_factory = executor_factory

    def execute(
        self,
        plan: TranscriptionJobPlan,
        *,
        resume: bool = False,
        diarization_request: SpeakerDiarizationRequest | None = None,
        allow_diarization_model_download: bool = False,
        observer: ExecutionObserver | None = None,
    ) -> TranscriptionExecutionResult:
        self.lifecycle_store.start(plan.job)
        lifecycle_observer = _LifecycleProgressObserver(self.lifecycle_store, plan.job)
        combined = _CombinedExecutionObserver(
            lifecycle_observer,
            observer or NoOpExecutionObserver(),
        )
        executor = self.executor_factory(combined)
        try:
            result = executor.execute(
                plan,
                resume=resume,
                diarization_request=diarization_request,
                allow_diarization_model_download=allow_diarization_model_download,
            )
        except KeyboardInterrupt:
            with suppress(Exception):
                self.lifecycle_store.interrupt(plan.job)
            raise
        except BaseException as exc:
            error_code = exc.code.value if isinstance(exc, ScholionError) else None
            with suppress(Exception):
                self.lifecycle_store.fail(plan.job, error_code=error_code)
            raise
        self.lifecycle_store.complete(result.job, result.artifact)
        return result
