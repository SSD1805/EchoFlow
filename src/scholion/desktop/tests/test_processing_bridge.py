from typing import Any, cast

import pytest
from pydantic import ValidationError

from scholion.desktop.processing_bridge import dispatch_processing
from scholion.runner.models import ProcessingProfile
from scholion.workspace.models import JobId


class _ProcessingService:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def readiness(self, profile: ProcessingProfile) -> dict[str, object]:
        self.calls.append(("readiness", profile))
        return {"profile": profile.value}

    def jobs(self) -> tuple[dict[str, object], ...]:
        self.calls.append(("jobs",))
        return ({"job_id": "job-1"},)

    def preflight(
        self,
        input_path: str,
        *,
        profile: ProcessingProfile,
        strategy_id: str | None,
        audio_stream_index: int | None,
        enhance: bool,
    ) -> dict[str, object]:
        self.calls.append(
            (
                "preflight",
                input_path,
                profile,
                strategy_id,
                audio_stream_index,
                enhance,
            )
        )
        return {"recording_name": "interview.m4a"}

    def retry_preflight(
        self,
        source_job_id: JobId,
        *,
        profile: ProcessingProfile,
        strategy_id: str | None,
        audio_stream_index: int | None,
        enhance: bool,
    ) -> dict[str, object]:
        self.calls.append(
            (
                "retry",
                source_job_id,
                profile,
                strategy_id,
                audio_stream_index,
                enhance,
            )
        )
        return {"job_id": "job-new"}

    def discard_job(self, job_id: JobId, *, expected_updated_at: str) -> None:
        self.calls.append(("discard", job_id, expected_updated_at))

    def verify_model(self, model_id: str) -> dict[str, object]:
        self.calls.append(("verify", model_id))
        return {
            "model_id": model_id,
            "installed": True,
            "resolved_revision": "revision-1",
        }


def _service() -> tuple[_ProcessingService, Any]:
    service = _ProcessingService()
    return service, cast(Any, service)


def test_readiness_uses_typed_profile() -> None:
    service, typed = _service()

    result = dispatch_processing(
        "processing.readiness",
        {"profile": "accuracy"},
        typed,
    )

    assert result == {"profile": "accuracy"}
    assert service.calls == [("readiness", ProcessingProfile.ACCURACY)]


def test_preflight_strips_text_and_delegates_only_typed_options() -> None:
    service, typed = _service()

    result = dispatch_processing(
        "processing.preflight",
        {
            "input_path": "  /private/interview.m4a  ",
            "profile": "balanced",
            "strategy_id": "  small-cpu-int8  ",
            "audio_stream_index": 2,
            "enhance": True,
        },
        typed,
    )

    assert result == {"recording_name": "interview.m4a"}
    assert service.calls == [
        (
            "preflight",
            "/private/interview.m4a",
            ProcessingProfile.BALANCED,
            "small-cpu-int8",
            2,
            True,
        )
    ]


def test_retry_and_discard_are_bound_to_backend_job_identity() -> None:
    service, typed = _service()

    retry = dispatch_processing(
        "processing.retry.preflight",
        {
            "source_job_id": "source-job",
            "profile": "screening",
            "strategy_id": None,
            "audio_stream_index": None,
            "enhance": False,
        },
        typed,
    )
    discarded = dispatch_processing(
        "processing.job.discard",
        {
            "job_id": "source-job",
            "expected_updated_at": "2026-08-20T12:00:00+00:00",
        },
        typed,
    )

    assert retry == {"job_id": "job-new"}
    assert discarded == {"job_id": "source-job", "discarded": True}
    assert service.calls == [
        (
            "retry",
            JobId("source-job"),
            ProcessingProfile.SCREENING,
            None,
            None,
            False,
        ),
        (
            "discard",
            JobId("source-job"),
            "2026-08-20T12:00:00+00:00",
        ),
    ]


def test_model_verification_is_explicit_and_bounded() -> None:
    service, typed = _service()

    result = dispatch_processing(
        "processing.model.verify",
        {"model_id": " small "},
        typed,
    )

    assert result == {
        "model_id": "small",
        "installed": True,
        "resolved_revision": "revision-1",
    }
    assert service.calls == [("verify", "small")]


def test_jobs_reject_client_authored_query_or_storage_parameters() -> None:
    _, typed = _service()

    with pytest.raises(ValidationError):
        dispatch_processing(
            "processing.jobs.list",
            {"sql": "SELECT * FROM lifecycle", "path": "/private"},
            typed,
        )


def test_unknown_processing_method_fails_closed() -> None:
    _, typed = _service()

    with pytest.raises(ValueError, match="Unsupported Processing Center"):
        dispatch_processing("processing.shell.exec", {}, typed)
