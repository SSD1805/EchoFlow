from __future__ import annotations

from pathlib import Path
from typing import cast

from echoflow.core.errors import ErrorCode
from echoflow.core.health_check import HealthCheck
from echoflow.model_management.models import ModelInventoryItem
from echoflow.model_management.service import ModelManager
from echoflow.runner.inspector import RunnerInspector
from echoflow.runner.models import ProcessingProfile
from echoflow.runner.policy import RunnerPolicyPlanner
from echoflow.transcription.models import TranscriptionJobPlan
from echoflow.transcription.planner import TranscriptionJobPlanner
from echoflow.workspace.lifecycle import (
    JobLifecycleRecord,
    JobLifecycleStore,
    JobStatus,
)
from echoflow.workspace.models import JobId

_FAILURE_MESSAGES: dict[str, str] = {
    ErrorCode.CONFIGURATION.value: "EchoFlow configuration needs attention before this job can continue.",
    ErrorCode.STORAGE.value: "EchoFlow could not safely use the required local storage.",
    ErrorCode.NOT_FOUND.value: "A required local file or folder is no longer available.",
    ErrorCode.PERMISSION.value: "EchoFlow no longer has permission to use a required local path.",
    ErrorCode.INVALID_INPUT.value: "The recording or processing request was not valid.",
    ErrorCode.UNSAFE_PATH.value: "EchoFlow rejected a local path that crossed a custody boundary.",
    ErrorCode.MEDIA_TOOL_UNAVAILABLE.value: "FFmpeg or FFprobe is unavailable.",
    ErrorCode.MEDIA_PROBE.value: "EchoFlow could not inspect the recording safely.",
    ErrorCode.UNSUPPORTED_MEDIA.value: "The recording does not contain supported audio for this job.",
    ErrorCode.INPUT_CHANGED.value: "The recording changed after this job was planned.",
    ErrorCode.AUDIO_DECODE.value: "EchoFlow could not decode the selected audio stream.",
    ErrorCode.RESOURCE_ADMISSION.value: "Current CPU, memory, accelerator, or disk capacity is below this job's safe requirement.",
    ErrorCode.TRANSCRIPTION_DEPENDENCY.value: "The local transcription runtime is unavailable.",
    ErrorCode.MODEL_UNAVAILABLE.value: "The verified local transcription model required by this job is unavailable.",
    ErrorCode.TRANSCRIPTION.value: "Local transcription did not complete successfully.",
    ErrorCode.DIARIZATION_DEPENDENCY.value: "The optional local speaker-labeling runtime is unavailable.",
    ErrorCode.DIARIZATION_MODEL_UNAVAILABLE.value: "The optional speaker-labeling model is unavailable.",
    ErrorCode.DIARIZATION.value: "Optional local speaker labeling did not complete successfully.",
}


def _safe_failure_message(error_code: str | None) -> str | None:
    if error_code is None:
        return None
    return _FAILURE_MESSAGES.get(
        error_code,
        "The job stopped before completion. EchoFlow kept any valid private checkpoint state it could preserve.",
    )


def _serialize_model(item: ModelInventoryItem) -> dict[str, object]:
    manifest = item.manifest
    return {
        "model_id": item.spec.model_id,
        "engine": item.spec.engine,
        "estimated_cache_bytes": item.spec.estimated_cache_bytes,
        "quality_rank": item.spec.quality_rank,
        "installed": item.installed,
        "resolved_revision": None if manifest is None else manifest.resolved_revision,
        "installed_size_bytes": None if manifest is None else manifest.size_bytes,
        "verification": None if manifest is None else manifest.verification,
    }


def _serialize_job(record: JobLifecycleRecord, *, resumable: bool) -> dict[str, object]:
    return {
        "job_id": record.job_id.value,
        "recording_name": record.input_path.name,
        "status": record.status.value,
        "started_at": record.started_at,
        "updated_at": record.updated_at,
        "total_segments": record.total_segments,
        "completed_segments": record.completed_segments,
        "progress_fraction": record.progress_fraction,
        "resumable": resumable,
        "artifact_published": record.artifact_path is not None,
        "error_code": record.error_code,
        "failure_message": _safe_failure_message(record.error_code),
    }


def _serialize_preflight(
    plan: TranscriptionJobPlan,
    *,
    audio_stream_selection_required: bool = False,
) -> dict[str, object]:
    audio_streams = tuple(
        {
            "index": stream.index,
            "codec": stream.codec,
            "duration_seconds": stream.duration_seconds,
            "sample_rate_hz": stream.sample_rate_hz,
            "channels": stream.channels,
            "title": stream.title,
            "language": stream.language,
            "is_default": stream.is_default,
        }
        for stream in plan.media.streams
        if stream.kind.value == "audio"
    )
    return {
        "job_id": plan.job.job_id.value,
        "recording_name": plan.job.input_path.name,
        "source_sha256": plan.media.input.sha256,
        "container_format": plan.media.container_format,
        "duration_seconds": plan.media.duration_seconds,
        "audio_streams": list(audio_streams),
        "selected_audio_stream_index": plan.media.primary_audio_stream.index,
        "audio_stream_selection_required": audio_stream_selection_required,
        "profile": plan.policy.profile.value,
        "provisional": plan.policy.provisional,
        "strategy_id": _strategy_id(plan),
        "engine": plan.engine.engine,
        "model": plan.engine.model,
        "model_revision": plan.engine.model_revision,
        "device": plan.engine.device,
        "compute_type": plan.engine.compute_type,
        "cpu_threads": plan.engine.cpu_threads,
        "decode_strategy": plan.decoder.strategy.value,
        "enhancement_enabled": plan.enhancement.enabled,
        "estimated_disk_bytes": plan.resources.total_disk_bytes,
        "estimated_peak_memory_bytes": plan.resources.estimated_peak_memory_bytes,
        "memory_budget_bytes": plan.policy.memory_budget_bytes,
        "fits_memory_budget": plan.resources.fits_memory_budget,
        "warnings": list(plan.warnings),
    }


def _strategy_id(plan: TranscriptionJobPlan) -> str:
    return "-".join(
        (
            plan.engine.model,
            plan.engine.device,
            plan.engine.compute_type.replace("_", "-"),
        )
    )


def _requires_audio_stream_confirmation(
    plan: TranscriptionJobPlan,
    requested_index: int | None,
) -> bool:
    if requested_index is not None:
        return False
    return sum(stream.kind.value == "audio" for stream in plan.media.streams) > 1


class ProcessingCenterService:
    """Compose existing processing authorities for a thin desktop presentation layer."""

    def __init__(
        self,
        *,
        health_check: HealthCheck,
        runner_inspector: RunnerInspector,
        policy_planner: RunnerPolicyPlanner,
        planner: TranscriptionJobPlanner,
        model_manager: ModelManager,
        lifecycle_store: JobLifecycleStore,
    ) -> None:
        self.health_check = health_check
        self.runner_inspector = runner_inspector
        self.policy_planner = policy_planner
        self.planner = planner
        self.model_manager = model_manager
        self.lifecycle_store = lifecycle_store

    def readiness(self, profile: ProcessingProfile) -> dict[str, object]:
        """Return fresh machine/model readiness without leaking private filesystem paths."""
        health = self.health_check.run()
        resources = self.runner_inspector.inspect()
        policy = self.policy_planner.plan(resources, profile)
        assessments = self.planner.assess_strategies(profile=profile)
        recommended = next(
            (item for item in assessments if bool(item["recommended"])),
            None,
        )
        inventory = self.model_manager.inventory()
        recommended_model: str | None = None
        recommended_installed = False
        if recommended is not None:
            strategy = cast("dict[str, object]", recommended["strategy"])
            recommended_model = str(strategy["model"])
            recommended_installed = any(
                item.spec.model_id == recommended_model and item.installed
                for item in inventory
            )
        return {
            "health": {
                "status": health.status.value,
                "checks": [
                    {
                        "check_id": check.check_id,
                        "status": check.status.value,
                        "summary": check.summary,
                        "required": check.required,
                        "error_code": check.error_code,
                    }
                    for check in health.checks
                ],
            },
            "resources": {
                "platform": resources.platform,
                "machine": resources.machine,
                "effective_cpus": resources.effective_cpus,
                "effective_memory_available_bytes": resources.effective_memory_available_bytes,
                "constraints": list(resources.constraints),
            },
            "policy": {
                "profile": policy.profile.value,
                "provisional": policy.provisional,
                "cpu_threads": policy.cpu_threads,
                "memory_budget_bytes": policy.memory_budget_bytes,
                "constraints": list(policy.constraints),
            },
            "strategies": [self._serialize_strategy(item) for item in assessments],
            "models": [_serialize_model(item) for item in inventory],
            "recommended_model": recommended_model,
            "recommended_model_installed": recommended_installed,
        }

    @staticmethod
    def _serialize_strategy(assessment: dict[str, object]) -> dict[str, object]:
        strategy = cast("dict[str, object]", assessment["strategy"])
        return {
            "strategy_id": strategy["strategy_id"],
            "model": strategy["model"],
            "device": strategy["device"],
            "compute_type": strategy["compute_type"],
            "estimated_peak_memory_bytes": assessment["effective_peak_memory_bytes"],
            "estimated_peak_device_memory_bytes": strategy[
                "estimated_peak_device_memory_bytes"
            ],
            "model_cache_bytes": strategy["model_cache_bytes"],
            "feasible": assessment["feasible"],
            "rejection_reasons": assessment["rejection_reasons"],
            "recommended": assessment["recommended"],
        }

    def jobs(self) -> tuple[dict[str, object], ...]:
        return tuple(
            _serialize_job(
                record,
                resumable=self.lifecycle_store.is_resumable(record.job_id),
            )
            for record in self.lifecycle_store.list_records()
        )

    def preflight(
        self,
        input_path: str | Path,
        *,
        profile: ProcessingProfile,
        strategy_id: str | None = None,
        audio_stream_index: int | None = None,
        enhance: bool = False,
    ) -> dict[str, object]:
        plan = self.planner.plan(
            input_path,
            profile=profile,
            strategy_id=strategy_id,
            audio_stream_index=audio_stream_index,
            enhance=enhance,
        )
        return _serialize_preflight(
            plan,
            audio_stream_selection_required=_requires_audio_stream_confirmation(
                plan,
                audio_stream_index,
            ),
        )

    def retry_preflight(
        self,
        source_job_id: JobId,
        *,
        profile: ProcessingProfile,
        strategy_id: str | None = None,
        audio_stream_index: int | None = None,
        enhance: bool = False,
    ) -> dict[str, object]:
        record = self.lifecycle_store.get(source_job_id)
        if record.status is JobStatus.RUNNING:
            raise ValueError("a running job cannot be retried")
        return self.preflight(
            record.input_path,
            profile=profile,
            strategy_id=strategy_id,
            audio_stream_index=audio_stream_index,
            enhance=enhance,
        )

    def discard_job(self, job_id: JobId, *, expected_updated_at: str) -> None:
        record = self.lifecycle_store.get(job_id)
        if record.status is JobStatus.RUNNING:
            raise ValueError("a running job cannot be discarded")
        if record.updated_at != expected_updated_at:
            raise ValueError(
                "job state changed; refresh before discarding private state"
            )
        self.lifecycle_store.discard(job_id)

    def verify_model(self, model_id: str) -> dict[str, object]:
        revision = self.model_manager.resolved_revision(model_id)
        return {
            "model_id": model_id,
            "installed": revision is not None,
            "resolved_revision": revision,
        }
