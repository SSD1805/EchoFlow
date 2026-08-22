from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from scholion.app.processing_center import ProcessingCenterService
from scholion.core.health_check import (
    CheckResult,
    CheckStatus,
    HealthReport,
    OverallStatus,
)
from scholion.model_management.models import (
    ManagedModelManifest,
    ModelInventoryItem,
    ModelSpec,
)
from scholion.runner.models import ExecutionPolicy, ProcessingProfile, RunnerResources
from scholion.workspace.lifecycle import JobLifecycleRecord, JobStatus
from scholion.workspace.models import JobId


class _Health:
    def run(self) -> HealthReport:
        return HealthReport(
            status=OverallStatus.DEGRADED,
            checks=(
                CheckResult(
                    check_id="ffmpeg",
                    status=CheckStatus.WARN,
                    summary="FFmpeg needs attention",
                    required=True,
                    error_code="ffmpeg_warning",
                ),
            ),
        )


class _Inspector:
    def inspect(self) -> RunnerResources:
        return RunnerResources(
            platform="TestOS",
            machine="test-machine",
            logical_cpus=8,
            physical_cpus=4,
            affinity_cpus=6,
            cpu_quota_cores=None,
            effective_cpus=6,
            memory_total_bytes=16_000,
            memory_available_bytes=12_000,
            memory_limit_bytes=None,
            effective_memory_available_bytes=12_000,
            constraints=("cpu_affinity",),
        )


class _PolicyPlanner:
    def plan(
        self, resources: RunnerResources, profile: ProcessingProfile
    ) -> ExecutionPolicy:
        assert resources.effective_cpus == 6
        return ExecutionPolicy(
            profile=profile,
            provisional=profile is ProcessingProfile.SCREENING,
            cpu_threads=5,
            memory_budget_bytes=9_000,
            constraints=("configured_memory_limit",),
        )


class _Planner:
    def __init__(self, plan: object) -> None:
        self.plan_result = plan
        self.plan_calls: list[tuple[object, ...]] = []
        self.assessment_calls: list[ProcessingProfile] = []

    def assess_strategies(
        self, *, profile: ProcessingProfile
    ) -> tuple[dict[str, object], ...]:
        self.assessment_calls.append(profile)
        return (
            {
                "strategy": {
                    "strategy_id": "small-cpu-int8",
                    "model": "small",
                    "device": "cpu",
                    "compute_type": "int8",
                    "estimated_peak_device_memory_bytes": 0,
                    "model_cache_bytes": 750,
                },
                "effective_peak_memory_bytes": 2_304,
                "feasible": True,
                "rejection_reasons": [],
                "recommended": True,
            },
            {
                "strategy": {
                    "strategy_id": "medium-cpu-int8",
                    "model": "medium",
                    "device": "cpu",
                    "compute_type": "int8",
                    "estimated_peak_device_memory_bytes": 0,
                    "model_cache_bytes": 2_500,
                },
                "effective_peak_memory_bytes": 4_352,
                "feasible": False,
                "rejection_reasons": ["insufficient_memory"],
                "recommended": False,
            },
        )

    def plan(
        self,
        input_path: str | Path,
        *,
        profile: ProcessingProfile,
        strategy_id: str | None = None,
        audio_stream_index: int | None = None,
        enhance: bool = False,
    ) -> object:
        self.plan_calls.append(
            (input_path, profile, strategy_id, audio_stream_index, enhance)
        )
        return self.plan_result


class _Models:
    def __init__(self, *, revision: str | None = "revision-small") -> None:
        self.revision = revision
        spec = ModelSpec(
            model_id="small",
            engine="faster-whisper",
            repository_id="Systran/faster-whisper-small",
            estimated_cache_bytes=750,
            quality_rank=2,
        )
        manifest = (
            None
            if revision is None
            else ManagedModelManifest(
                schema_version=1,
                model_id="small",
                engine="faster-whisper",
                repository_id="Systran/faster-whisper-small",
                requested_revision=None,
                resolved_revision=revision,
                snapshot_path=Path("/models/small"),
                size_bytes=700,
                verification="required-files",
            )
        )
        self.items = (ModelInventoryItem(spec=spec, manifest=manifest),)

    def inventory(self) -> tuple[ModelInventoryItem, ...]:
        return self.items

    def resolved_revision(self, model_id: str) -> str | None:
        assert model_id == "small"
        return self.revision


class _Lifecycle:
    def __init__(self, records: tuple[JobLifecycleRecord, ...] = ()) -> None:
        self.records = {record.job_id: record for record in records}
        self.discarded: list[JobId] = []
        self.resumable: set[JobId] = set()

    def list_records(self) -> tuple[JobLifecycleRecord, ...]:
        return tuple(self.records.values())

    def is_resumable(self, job_id: JobId) -> bool:
        return job_id in self.resumable

    def get(self, job_id: JobId) -> JobLifecycleRecord:
        return self.records[job_id]

    def discard(self, job_id: JobId) -> None:
        self.discarded.append(job_id)


def _record(
    *,
    job_id: str = "job-1",
    status: JobStatus = JobStatus.FAILED,
    updated_at: str = "2026-08-20T12:05:00+00:00",
    error_code: str | None = "transcription_failed",
    artifact: bool = False,
) -> JobLifecycleRecord:
    return JobLifecycleRecord(
        job_id=JobId(job_id),
        input_path=Path("/private/interview.m4a"),
        output_dir=Path("/private/output"),
        status=status,
        started_at="2026-08-20T12:00:00+00:00",
        updated_at=updated_at,
        process_id=None,
        process_started_at=None,
        total_segments=10,
        completed_segments=4,
        artifact_path=Path("/private/output/transcript.json") if artifact else None,
        error_code=error_code,
    )


def _plan() -> object:
    audio = SimpleNamespace(
        index=2,
        codec="aac",
        duration_seconds=42.0,
        sample_rate_hz=48_000,
        channels=2,
        kind=SimpleNamespace(value="audio"),
    )
    video = SimpleNamespace(
        index=0,
        codec="h264",
        duration_seconds=42.0,
        sample_rate_hz=None,
        channels=None,
        kind=SimpleNamespace(value="video"),
    )
    return SimpleNamespace(
        job=SimpleNamespace(
            job_id=JobId("planned-job"),
            input_path=Path("/private/recording.mp4"),
        ),
        media=SimpleNamespace(
            input=SimpleNamespace(sha256="a" * 64),
            container_format="mov,mp4",
            duration_seconds=42.0,
            streams=(video, audio),
            primary_audio_stream=audio,
        ),
        policy=SimpleNamespace(
            profile=ProcessingProfile.BALANCED,
            provisional=False,
            memory_budget_bytes=8_000,
        ),
        engine=SimpleNamespace(
            engine="faster-whisper",
            model="small",
            model_revision="revision-small",
            device="cpu",
            compute_type="int8_float16",
            cpu_threads=4,
        ),
        decoder=SimpleNamespace(strategy=SimpleNamespace(value="ffmpeg-normalize")),
        enhancement=SimpleNamespace(enabled=True),
        resources=SimpleNamespace(
            total_disk_bytes=12_000,
            estimated_peak_memory_bytes=2_000,
            fits_memory_budget=True,
        ),
        warnings=("noise_suppression_enabled",),
    )


def _service(
    *,
    lifecycle: _Lifecycle | None = None,
    models: _Models | None = None,
) -> tuple[ProcessingCenterService, _Planner, _Lifecycle]:
    plan = _plan()
    planner = _Planner(plan)
    state = lifecycle or _Lifecycle()
    service = ProcessingCenterService(
        health_check=cast(Any, _Health()),
        runner_inspector=cast(Any, _Inspector()),
        policy_planner=cast(Any, _PolicyPlanner()),
        planner=cast(Any, planner),
        model_manager=cast(Any, models or _Models()),
        lifecycle_store=cast(Any, state),
    )
    return service, planner, state


def test_readiness_composes_health_resources_strategy_and_verified_model_state() -> (
    None
):
    service, planner, _ = _service()

    result = service.readiness(ProcessingProfile.BALANCED)

    assert result["health"] == {
        "status": "degraded",
        "checks": [
            {
                "check_id": "ffmpeg",
                "status": "warn",
                "summary": "FFmpeg needs attention",
                "required": True,
                "error_code": "ffmpeg_warning",
            }
        ],
    }
    assert result["resources"] == {
        "platform": "TestOS",
        "machine": "test-machine",
        "effective_cpus": 6,
        "effective_memory_available_bytes": 12_000,
        "constraints": ["cpu_affinity"],
    }
    assert result["policy"] == {
        "profile": "balanced",
        "provisional": False,
        "cpu_threads": 5,
        "memory_budget_bytes": 9_000,
        "constraints": ["configured_memory_limit"],
    }
    assert result["recommended_model"] == "small"
    assert result["recommended_model_installed"] is True
    assert result["models"] == [
        {
            "model_id": "small",
            "engine": "faster-whisper",
            "estimated_cache_bytes": 750,
            "quality_rank": 2,
            "installed": True,
            "resolved_revision": "revision-small",
            "installed_size_bytes": 700,
            "verification": "required-files",
        }
    ]
    strategies = cast(list[dict[str, object]], result["strategies"])
    assert strategies[0]["strategy_id"] == "small-cpu-int8"
    assert strategies[0]["recommended"] is True
    assert strategies[1]["rejection_reasons"] == ["insufficient_memory"]
    assert planner.assessment_calls == [ProcessingProfile.BALANCED]


def test_readiness_reports_recommended_model_as_not_installed() -> None:
    service, _, _ = _service(models=_Models(revision=None))

    result = service.readiness(ProcessingProfile.ACCURACY)

    assert result["recommended_model"] == "small"
    assert result["recommended_model_installed"] is False
    models = cast(list[dict[str, object]], result["models"])
    assert models[0]["installed"] is False
    assert models[0]["resolved_revision"] is None


def test_jobs_minimize_paths_and_render_safe_failure_state() -> None:
    failed = _record()
    unknown = _record(
        job_id="job-2",
        status=JobStatus.INTERRUPTED,
        error_code="unknown_backend_code",
        artifact=True,
    )
    lifecycle = _Lifecycle((failed, unknown))
    lifecycle.resumable.add(failed.job_id)
    service, _, _ = _service(lifecycle=lifecycle)

    jobs = service.jobs()

    assert jobs[0]["recording_name"] == "interview.m4a"
    assert jobs[0]["progress_fraction"] == 0.4
    assert jobs[0]["resumable"] is True
    assert (
        jobs[0]["failure_message"]
        == "Local transcription did not complete successfully."
    )
    assert jobs[1]["artifact_published"] is True
    assert jobs[1]["failure_message"] == (
        "The job stopped before completion. Scholion kept any valid private checkpoint state it could preserve."
    )
    assert "/private" not in str(jobs)


def test_preflight_returns_backend_plan_without_private_paths() -> None:
    service, planner, _ = _service()

    result = service.preflight(
        "/private/recording.mp4",
        profile=ProcessingProfile.BALANCED,
        strategy_id="small-cpu-int8-float16",
        audio_stream_index=2,
        enhance=True,
    )

    assert result["job_id"] == "planned-job"
    assert result["recording_name"] == "recording.mp4"
    assert result["selected_audio_stream_index"] == 2
    assert result["strategy_id"] == "small-cpu-int8-float16"
    assert result["audio_streams"] == [
        {
            "index": 2,
            "codec": "aac",
            "duration_seconds": 42.0,
            "sample_rate_hz": 48_000,
            "channels": 2,
        }
    ]
    assert result["enhancement_enabled"] is True
    assert result["fits_memory_budget"] is True
    assert "/private" not in str(result)
    assert planner.plan_calls == [
        (
            "/private/recording.mp4",
            ProcessingProfile.BALANCED,
            "small-cpu-int8-float16",
            2,
            True,
        )
    ]


def test_retry_preflight_replans_nonrunning_job_and_rejects_running_job() -> None:
    failed = _record()
    running = _record(job_id="job-running", status=JobStatus.RUNNING, error_code=None)
    lifecycle = _Lifecycle((failed, running))
    service, planner, _ = _service(lifecycle=lifecycle)

    result = service.retry_preflight(
        failed.job_id,
        profile=ProcessingProfile.SCREENING,
        enhance=False,
    )

    assert result["job_id"] == "planned-job"
    assert planner.plan_calls[-1][0] == failed.input_path
    assert planner.plan_calls[-1][1] is ProcessingProfile.SCREENING
    with pytest.raises(ValueError, match="running job cannot be retried"):
        service.retry_preflight(
            running.job_id,
            profile=ProcessingProfile.BALANCED,
        )


def test_discard_is_version_bound_and_never_accepts_running_state() -> None:
    failed = _record()
    running = _record(job_id="job-running", status=JobStatus.RUNNING, error_code=None)
    lifecycle = _Lifecycle((failed, running))
    service, _, state = _service(lifecycle=lifecycle)

    with pytest.raises(ValueError, match="running job cannot be discarded"):
        service.discard_job(running.job_id, expected_updated_at=running.updated_at)
    with pytest.raises(ValueError, match="job state changed"):
        service.discard_job(failed.job_id, expected_updated_at="stale")

    service.discard_job(failed.job_id, expected_updated_at=failed.updated_at)

    assert state.discarded == [failed.job_id]


def test_model_verification_is_read_only_and_explicit() -> None:
    installed, _, _ = _service(models=_Models(revision="revision-small"))
    missing, _, _ = _service(models=_Models(revision=None))

    assert installed.verify_model("small") == {
        "model_id": "small",
        "installed": True,
        "resolved_revision": "revision-small",
    }
    assert missing.verify_model("small") == {
        "model_id": "small",
        "installed": False,
        "resolved_revision": None,
    }
