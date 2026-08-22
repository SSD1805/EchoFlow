from __future__ import annotations

import json
import platform
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from time import perf_counter
from typing import Protocol
from uuid import uuid4

from scholion.core.file_manager_facade import FileManagerFacade
from scholion.core.measurements import ExecutionObserver, MeasurementRecorder
from scholion.transcription.models import (
    TranscriptionExecutionResult,
    TranscriptionJobPlan,
    TranscriptSource,
)
from scholion.workspace.service import WorkspaceService

from .models import (
    BenchmarkReport,
    BenchmarkRunError,
    BenchmarkRunResult,
    BenchmarkStatus,
)
from .resources import ProcessTreeObservation, ProcessTreeSampler


class ResourceSampler(Protocol):
    def start(self) -> None: ...
    def stop(self) -> ProcessTreeObservation: ...


def _scholion_version() -> str:
    try:
        return version("scholion")
    except PackageNotFoundError:
        return "0+unknown"


def _benchmark_id() -> str:
    return uuid4().hex


class BenchmarkRunner:
    """Run one real transcription attempt while collecting local benchmark evidence."""

    def __init__(
        self,
        *,
        file_manager: FileManagerFacade,
        workspace_service: WorkspaceService,
        sampler_factory: Callable[[], ResourceSampler] = ProcessTreeSampler,
        clock: Callable[[], float] = perf_counter,
        id_factory: Callable[[], str] = _benchmark_id,
        version_factory: Callable[[], str] = _scholion_version,
        python_version_factory: Callable[[], str] = platform.python_version,
    ):
        self.file_manager = file_manager
        self.workspace_service = workspace_service
        self.sampler_factory = sampler_factory
        self.clock = clock
        self.id_factory = id_factory
        self.version_factory = version_factory
        self.python_version_factory = python_version_factory

    def run(
        self,
        plan: TranscriptionJobPlan,
        *,
        execute: Callable[[ExecutionObserver], TranscriptionExecutionResult],
        resume: bool = False,
        planning_wall_seconds: float = 0.0,
    ) -> BenchmarkRunResult:
        if planning_wall_seconds < 0:
            raise ValueError("planning_wall_seconds cannot be negative")
        benchmark_id = self.id_factory()
        report_path = self._reserve_report(plan, benchmark_id)
        recorder = MeasurementRecorder(clock=self.clock)
        sampler = self.sampler_factory()
        started = self.clock()
        sampler.start()

        result: TranscriptionExecutionResult | None = None
        error: BaseException | None = None
        status = BenchmarkStatus.COMPLETED
        try:
            result = execute(recorder)
        except KeyboardInterrupt as exc:
            status = BenchmarkStatus.INTERRUPTED
            error = exc
        except BaseException as exc:
            status = BenchmarkStatus.FAILED
            error = exc

        process_tree = sampler.stop()
        execution_wall_seconds = max(0.0, self.clock() - started)
        report = BenchmarkReport(
            benchmark_id=benchmark_id,
            job_id=plan.job.job_id.value,
            status=status,
            resume=resume,
            scholion_version=self.version_factory(),
            python_version=self.python_version_factory(),
            source=self._source(plan),
            plan=plan,
            planning_wall_seconds=planning_wall_seconds,
            execution_wall_seconds=execution_wall_seconds,
            process_tree=process_tree,
            stages=recorder.stages(),
            values=recorder.values(),
            canonical_artifact_bytes=self._artifact_size(result),
            error_type=None if error is None else type(error).__name__,
        )
        self._write_report(report_path, report)

        if error is not None:
            raise BenchmarkRunError(report_path, status, error) from error
        if result is None:
            raise RuntimeError(
                "completed benchmark did not produce a transcription result"
            )
        return BenchmarkRunResult(report_path, report, result)

    def _reserve_report(self, plan: TranscriptionJobPlan, benchmark_id: str) -> Path:
        self.workspace_service.initialize(plan.job.output_dir)
        report_path = (
            plan.job.output_dir / f"scholion-benchmark-{benchmark_id}.json"
        ).resolve(strict=False)
        self.file_manager.reserve_file(report_path)
        return report_path

    def _artifact_size(self, result: TranscriptionExecutionResult | None) -> int | None:
        if result is None or not self.file_manager.file_exists(result.artifact.path):
            return None
        return int(self.file_manager.get_file_metadata(result.artifact.path)["size"])

    def _write_report(self, path: Path, report: BenchmarkReport) -> None:
        document = json.dumps(
            report.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        self.file_manager.save_file(f"{document}\n".encode(), path)

    @staticmethod
    def _source(plan: TranscriptionJobPlan) -> TranscriptSource:
        return TranscriptSource.from_media(plan.media)
