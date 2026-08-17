from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import cast

import psutil

from echoflow.core.file_manager_facade import FileManagerFacade
from echoflow.workspace.errors import JobNotFoundError
from echoflow.workspace.models import Artifact, Job, JobId, WorkspacePaths

_JOB_MANIFEST_NAME = "job.json"
_MAX_JOB_MANIFEST_BYTES = 64 * 1024


class JobStatus(StrEnum):
    RUNNING = "running"
    INTERRUPTED = "interrupted"
    FAILED = "failed"
    COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class JobLifecycleRecord:
    """Private, local execution state for one EchoFlow job."""

    job_id: JobId
    input_path: Path
    output_dir: Path
    status: JobStatus
    started_at: str
    updated_at: str
    process_id: int | None
    process_started_at: float | None
    total_segments: int | None = None
    completed_segments: int = 0
    artifact_path: Path | None = None
    error_code: str | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_path", self.input_path.expanduser().resolve())
        object.__setattr__(self, "output_dir", self.output_dir.expanduser().resolve())
        if self.artifact_path is not None:
            object.__setattr__(
                self, "artifact_path", self.artifact_path.expanduser().resolve()
            )
        if self.schema_version != 1:
            raise ValueError("job lifecycle schema version is unsupported")
        if self.completed_segments < 0:
            raise ValueError("completed segment count cannot be negative")
        if self.total_segments is not None:
            if self.total_segments < 0:
                raise ValueError("total segment count cannot be negative")
            if self.completed_segments > self.total_segments:
                raise ValueError("completed segment count exceeds total segments")
        if (self.process_id is None) != (self.process_started_at is None):
            raise ValueError("process identity must be fully present or absent")

    @property
    def progress_fraction(self) -> float | None:
        if self.total_segments is None or self.total_segments == 0:
            return None
        return self.completed_segments / self.total_segments

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "job_id": self.job_id.value,
            "input_path": str(self.input_path),
            "output_dir": str(self.output_dir),
            "status": self.status.value,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "process_id": self.process_id,
            "process_started_at": self.process_started_at,
            "total_segments": self.total_segments,
            "completed_segments": self.completed_segments,
            "artifact_path": (
                None if self.artifact_path is None else str(self.artifact_path)
            ),
            "error_code": self.error_code,
        }

    @classmethod
    def from_dict(cls, document: dict[str, object]) -> JobLifecycleRecord:
        try:
            artifact = document.get("artifact_path")
            process_id = document.get("process_id")
            process_started_at = document.get("process_started_at")
            total_segments = document.get("total_segments")
            return cls(
                schema_version=int(cast("int", document["schema_version"])),
                job_id=JobId(str(document["job_id"])),
                input_path=Path(str(document["input_path"])),
                output_dir=Path(str(document["output_dir"])),
                status=JobStatus(str(document["status"])),
                started_at=str(document["started_at"]),
                updated_at=str(document["updated_at"]),
                process_id=(
                    None if process_id is None else int(cast("int", process_id))
                ),
                process_started_at=(
                    None
                    if process_started_at is None
                    else float(cast("float", process_started_at))
                ),
                total_segments=(
                    None
                    if total_segments is None
                    else int(cast("int", total_segments))
                ),
                completed_segments=int(
                    cast("int", document.get("completed_segments", 0))
                ),
                artifact_path=None if artifact is None else Path(str(artifact)),
                error_code=(
                    None
                    if document.get("error_code") is None
                    else str(document["error_code"])
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("private job lifecycle manifest is malformed") from exc


class JobLifecycleStore:
    """Persist and inspect private lifecycle state without owning transcript custody."""

    def __init__(
        self,
        file_manager: FileManagerFacade,
        paths: WorkspacePaths,
        *,
        max_manifest_bytes: int = _MAX_JOB_MANIFEST_BYTES,
    ) -> None:
        if max_manifest_bytes < 1:
            raise ValueError("max_manifest_bytes must be positive")
        self.file_manager = file_manager
        self.paths = paths
        self.max_manifest_bytes = max_manifest_bytes

    def start(self, job: Job) -> JobLifecycleRecord:
        now = self._now()
        existing = self._load_if_present(job.job_id)
        pid = os.getpid()
        process_started_at = psutil.Process(pid).create_time()
        record = JobLifecycleRecord(
            job_id=job.job_id,
            input_path=job.input_path,
            output_dir=job.output_dir,
            status=JobStatus.RUNNING,
            started_at=existing.started_at if existing is not None else now,
            updated_at=now,
            process_id=pid,
            process_started_at=process_started_at,
            total_segments=(None if existing is None else existing.total_segments),
            completed_segments=(
                0 if existing is None else existing.completed_segments
            ),
        )
        self._write(record)
        return record

    def record_progress(
        self,
        job: Job,
        *,
        completed_segments: int,
        total_segments: int,
    ) -> JobLifecycleRecord:
        record = self._required(job.job_id)
        updated = replace(
            record,
            status=JobStatus.RUNNING,
            completed_segments=completed_segments,
            total_segments=total_segments,
            updated_at=self._now(),
        )
        self._write(updated)
        return updated

    def complete(self, job: Job, artifact: Artifact) -> JobLifecycleRecord:
        record = self._required(job.job_id)
        completed = record.completed_segments
        if record.total_segments is not None:
            completed = record.total_segments
        updated = replace(
            record,
            status=JobStatus.COMPLETED,
            completed_segments=completed,
            artifact_path=artifact.path,
            error_code=None,
            process_id=None,
            process_started_at=None,
            updated_at=self._now(),
        )
        self._write(updated)
        return updated

    def interrupt(self, job: Job) -> JobLifecycleRecord:
        return self._finish(job, status=JobStatus.INTERRUPTED, error_code=None)

    def fail(self, job: Job, *, error_code: str | None) -> JobLifecycleRecord:
        return self._finish(job, status=JobStatus.FAILED, error_code=error_code)

    def get(self, job_id: JobId) -> JobLifecycleRecord:
        record = self._required(job_id)
        if record.status is JobStatus.RUNNING and not self._process_is_active(record):
            record = replace(
                record,
                status=JobStatus.INTERRUPTED,
                process_id=None,
                process_started_at=None,
                updated_at=self._now(),
            )
            self._write(record)
        return record

    def list_records(self) -> tuple[JobLifecycleRecord, ...]:
        self.file_manager.ensure_directory_exists(self.paths.jobs_dir, private=True)
        records: list[JobLifecycleRecord] = []
        for directory in self.file_manager.list_directories(self.paths.jobs_dir):
            try:
                job_id = JobId(directory.name)
                records.append(self.get(job_id))
            except (JobNotFoundError, ValueError):
                continue
        return tuple(sorted(records, key=lambda item: item.updated_at, reverse=True))

    def is_resumable(self, job_id: JobId) -> bool:
        return self.file_manager.file_exists(
            self.paths.jobs_dir / job_id.value / "checkpoints" / "manifest.json"
        )

    def discard(self, job_id: JobId) -> None:
        workspace = (self.paths.jobs_dir / job_id.value).resolve()
        expected_parent = self.paths.jobs_dir.resolve()
        if workspace.parent != expected_parent or not workspace.is_dir():
            raise JobNotFoundError(job_id.value)
        self.file_manager.delete_directory(workspace)

    def _finish(
        self,
        job: Job,
        *,
        status: JobStatus,
        error_code: str | None,
    ) -> JobLifecycleRecord:
        record = self._required(job.job_id)
        updated = replace(
            record,
            status=status,
            error_code=error_code,
            process_id=None,
            process_started_at=None,
            updated_at=self._now(),
        )
        self._write(updated)
        return updated

    def _required(self, job_id: JobId) -> JobLifecycleRecord:
        record = self._load_if_present(job_id)
        if record is None:
            raise JobNotFoundError(job_id.value)
        return record

    def _load_if_present(self, job_id: JobId) -> JobLifecycleRecord | None:
        path = self._manifest_path(job_id)
        if not self.file_manager.file_exists(path):
            return None
        metadata = self.file_manager.get_file_metadata(path)
        if metadata["size"] < 2 or metadata["size"] > self.max_manifest_bytes:
            raise ValueError("private job lifecycle manifest size is outside safe bounds")
        try:
            parsed = json.loads(self.file_manager.read_file(path))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("private job lifecycle manifest is invalid JSON") from exc
        if not isinstance(parsed, dict):
            raise ValueError("private job lifecycle manifest must be an object")
        record = JobLifecycleRecord.from_dict(cast("dict[str, object]", parsed))
        if record.job_id != job_id:
            raise ValueError("private job lifecycle manifest belongs to another job")
        return record

    def _write(self, record: JobLifecycleRecord) -> None:
        path = self._manifest_path(record.job_id)
        payload = json.dumps(
            record.to_dict(), sort_keys=True, separators=(",", ":")
        ).encode()
        if len(payload) > self.max_manifest_bytes:
            raise ValueError("private job lifecycle manifest exceeds safe bounds")
        self.file_manager.save_file(payload + b"\n", path, private=True)

    def _manifest_path(self, job_id: JobId) -> Path:
        return self.paths.jobs_dir / job_id.value / _JOB_MANIFEST_NAME

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _process_is_active(record: JobLifecycleRecord) -> bool:
        if record.process_id is None or record.process_started_at is None:
            return False
        try:
            process = psutil.Process(record.process_id)
            return abs(process.create_time() - record.process_started_at) < 0.01
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            return False
        except psutil.AccessDenied:
            return True
