from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from echoflow.core.measurements import StageMeasurement
from echoflow.transcription.models import (
    TranscriptionExecutionResult,
    TranscriptionJobPlan,
    TranscriptSource,
)

from .resources import ProcessTreeObservation


class BenchmarkStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    """Path-minimized benchmark evidence for one execution attempt."""

    benchmark_id: str
    job_id: str
    status: BenchmarkStatus
    resume: bool
    echoflow_version: str
    python_version: str
    source: TranscriptSource
    plan: TranscriptionJobPlan
    planning_wall_seconds: float
    execution_wall_seconds: float
    process_tree: ProcessTreeObservation
    stages: tuple[StageMeasurement, ...]
    values: dict[str, int | float]
    canonical_artifact_bytes: int | None = None
    error_type: str | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported benchmark schema version")
        if not self.benchmark_id or not self.job_id:
            raise ValueError("benchmark and job IDs cannot be empty")
        if self.planning_wall_seconds < 0 or self.execution_wall_seconds < 0:
            raise ValueError("benchmark wall-clock durations cannot be negative")
        if self.canonical_artifact_bytes is not None and self.canonical_artifact_bytes < 0:
            raise ValueError("canonical_artifact_bytes cannot be negative")
        if self.status is BenchmarkStatus.COMPLETED and self.error_type is not None:
            raise ValueError("completed benchmark cannot carry an error type")
        if self.status is not BenchmarkStatus.COMPLETED and not self.error_type:
            raise ValueError("incomplete benchmark must carry an error type")

    @property
    def total_wall_seconds(self) -> float:
        return self.planning_wall_seconds + self.execution_wall_seconds

    @property
    def real_time_factor(self) -> float:
        return self.total_wall_seconds / self.source.duration_seconds

    @property
    def execution_real_time_factor(self) -> float:
        return self.execution_wall_seconds / self.source.duration_seconds

    @property
    def peak_rss_to_estimate_ratio(self) -> float | None:
        estimate = self.plan.resources.estimated_peak_memory_bytes
        if estimate <= 0:
            return None
        return self.process_tree.peak_rss_bytes / estimate

    def to_dict(self) -> dict[str, object]:
        engine = self.plan.engine
        return {
            "schema_version": self.schema_version,
            "benchmark_id": self.benchmark_id,
            "job_id": self.job_id,
            "status": self.status.value,
            "resume": self.resume,
            "environment": {
                "echoflow_version": self.echoflow_version,
                "python_version": self.python_version,
            },
            "source": self.source.to_dict(),
            "runner": self.plan.runner.to_dict(),
            "policy": self.plan.policy.to_dict(),
            "execution_contract": {
                "engine": {
                    "engine": engine.engine,
                    "model": engine.model,
                    "device": engine.device,
                    "compute_type": engine.compute_type,
                    "cpu_threads": engine.cpu_threads,
                    "beam_size": engine.beam_size,
                    "language": engine.language,
                    "model_revision": engine.model_revision,
                },
                "decoder": self.plan.decoder.to_dict(),
                "segmentation": self.plan.segmentation.to_dict(),
                "resource_estimate": self.plan.resources.to_dict(),
            },
            "observed": {
                "planning_wall_seconds": self.planning_wall_seconds,
                "execution_wall_seconds": self.execution_wall_seconds,
                "total_wall_seconds": self.total_wall_seconds,
                "real_time_factor": self.real_time_factor,
                "execution_real_time_factor": self.execution_real_time_factor,
                "process_tree": self.process_tree.to_dict(),
                "stages": [stage.to_dict() for stage in self.stages],
                "values": dict(sorted(self.values.items())),
                "canonical_artifact_bytes": self.canonical_artifact_bytes,
                "peak_rss_to_estimate_ratio": self.peak_rss_to_estimate_ratio,
            },
            "error_type": self.error_type,
        }


@dataclass(frozen=True, slots=True)
class BenchmarkRunResult:
    report_path: Path
    report: BenchmarkReport
    transcription: TranscriptionExecutionResult

    def to_dict(self) -> dict[str, object]:
        return {
            "benchmark_report_path": str(self.report_path),
            "transcript_artifact_path": str(self.transcription.artifact.path),
            "report": self.report.to_dict(),
        }


class BenchmarkRunError(Exception):
    """Execution failed or was interrupted after a partial report was persisted."""

    def __init__(
        self,
        report_path: Path,
        status: BenchmarkStatus,
        cause: BaseException,
    ):
        self.report_path = report_path
        self.status = status
        self.cause = cause
        super().__init__(f"benchmark {status.value}")
