"""Narrow desktop adapter for Processing Center control-plane requests.

Long-running model acquisition and transcription execution do not cross this adapter. Those
are supervised by Tauri and executed by the dedicated Python processing worker. This module
only serves bounded readiness, preflight, lifecycle inspection, verification, and guarded
private-state mutation requests.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from echoflow.app.processing_center import ProcessingCenterService
from echoflow.runner.models import ProcessingProfile
from echoflow.workspace.models import JobId


class _NoParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _ReadinessParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: ProcessingProfile = ProcessingProfile.BALANCED


class _PreflightParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_path: str = Field(min_length=1, max_length=32_768)
    profile: ProcessingProfile = ProcessingProfile.BALANCED
    strategy_id: str | None = Field(default=None, min_length=1, max_length=200)
    audio_stream_index: int | None = Field(default=None, ge=0, le=10_000)
    enhance: bool = False

    @field_validator("input_path", "strategy_id")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("processing text values cannot be blank")
        return stripped


class _RetryPreflightParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_job_id: str = Field(min_length=1, max_length=200)
    profile: ProcessingProfile = ProcessingProfile.BALANCED
    strategy_id: str | None = Field(default=None, min_length=1, max_length=200)
    audio_stream_index: int | None = Field(default=None, ge=0, le=10_000)
    enhance: bool = False

    @field_validator("source_job_id", "strategy_id")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("processing text values cannot be blank")
        return stripped


class _DiscardJobParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(min_length=1, max_length=200)
    expected_updated_at: str = Field(min_length=1, max_length=200)

    @field_validator("job_id", "expected_updated_at")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("job identity and version cannot be blank")
        return stripped


class _VerifyModelParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(min_length=1, max_length=200)

    @field_validator("model_id")
    @classmethod
    def strip_model_id(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("model_id cannot be blank")
        return stripped


def dispatch_processing(
    method: str,
    params: dict[str, object],
    service: ProcessingCenterService,
) -> object:
    """Dispatch bounded Processing Center operations after the outer allowlist accepts them."""
    if method == "processing.readiness":
        parsed = _ReadinessParams.model_validate(params)
        return service.readiness(parsed.profile)
    if method == "processing.jobs.list":
        _NoParams.model_validate(params)
        return list(service.jobs())
    if method == "processing.preflight":
        parsed = _PreflightParams.model_validate(params)
        return service.preflight(
            parsed.input_path,
            profile=parsed.profile,
            strategy_id=parsed.strategy_id,
            audio_stream_index=parsed.audio_stream_index,
            enhance=parsed.enhance,
        )
    if method == "processing.retry.preflight":
        parsed = _RetryPreflightParams.model_validate(params)
        return service.retry_preflight(
            JobId(parsed.source_job_id),
            profile=parsed.profile,
            strategy_id=parsed.strategy_id,
            audio_stream_index=parsed.audio_stream_index,
            enhance=parsed.enhance,
        )
    if method == "processing.job.discard":
        parsed = _DiscardJobParams.model_validate(params)
        service.discard_job(
            JobId(parsed.job_id),
            expected_updated_at=parsed.expected_updated_at,
        )
        return {"job_id": parsed.job_id, "discarded": True}
    if method == "processing.model.verify":
        parsed = _VerifyModelParams.model_validate(params)
        return service.verify_model(parsed.model_id)
    raise ValueError("Unsupported Processing Center desktop method")
