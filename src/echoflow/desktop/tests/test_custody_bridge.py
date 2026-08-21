from __future__ import annotations

from typing import cast

import pytest
from pydantic import ValidationError

from echoflow.desktop.custody_bridge import dispatch_custody, handle_request
from echoflow.library.custody import (
    DeletionAction,
    DeletionPlan,
    DeletionReceipt,
    DeletionScope,
    DeletionTarget,
    LibraryCustodyService,
    RetentionCandidate,
    RetentionPlan,
    RetentionPolicy,
    RetentionReceipt,
)
from echoflow.library.index import IndexedDocument
from echoflow.workspace.lifecycle import JobStatus


class _TranscriptLibrary:
    def documents(self) -> tuple[IndexedDocument, ...]:
        return (
            IndexedDocument(
                document_id="doc-1",
                source_sha256="b" * 64,
                detected_language="en",
                canonical_path="/private/library/doc-1.json",
                source_path="/secret/interviews/oral-history.m4a",
                segment_count=12,
                canonical_sha256="a" * 64,
            ),
        )


class _CustodyFake:
    def __init__(self) -> None:
        self.transcript_library = _TranscriptLibrary()
        self.deletion_allow_source: bool | None = None
        self.retention_policy: RetentionPolicy | None = None
        self.fail_unexpected = False

    def plan_deletion(
        self,
        document_id: str,
        scopes: tuple[DeletionScope, ...],
        *,
        allow_source: bool = False,
    ) -> DeletionPlan:
        if self.fail_unexpected:
            raise RuntimeError("secret /private/library/doc-1.json")
        self.deletion_allow_source = allow_source
        return DeletionPlan(
            document_id=document_id,
            canonical_sha256="a" * 64,
            requested_scopes=scopes,
            effective_scopes=scopes,
            actions=(
                DeletionAction(
                    target=DeletionTarget.CANONICAL_TRANSCRIPT,
                    object_id="a" * 64,
                    description="delete canonical transcript evidence",
                    path="/private/library/doc-1.json",
                ),
            ),
            preserved_note_ids=("note-1", "note-2"),
            affected_saved_search_ids=("search-1",),
            confirmation_token="delete:bound-plan",
        )

    def execute_deletion(
        self,
        document_id: str,
        scopes: tuple[DeletionScope, ...],
        *,
        confirmation_token: str,
        allow_source: bool = False,
    ) -> DeletionReceipt:
        assert confirmation_token == "delete:bound-plan"
        self.deletion_allow_source = allow_source
        return DeletionReceipt(
            document_id=document_id,
            confirmation_token=confirmation_token,
            executed_targets=(DeletionTarget.CANONICAL_TRANSCRIPT,),
            preserved_note_ids=("note-1",),
            affected_saved_search_ids=("search-1",),
        )

    def plan_retention(self, policy: RetentionPolicy) -> RetentionPlan:
        self.retention_policy = policy
        return RetentionPlan(
            policy=policy,
            candidates=(
                RetentionCandidate(
                    job_id="job-1",
                    status=JobStatus.INTERRUPTED,
                    updated_at="2026-07-01T00:00:00+00:00",
                    workspace_path="/private/state/jobs/job-1",
                    resume_capability_lost=True,
                ),
            ),
            confirmation_token="retention:bound-plan",
        )

    def execute_retention(
        self,
        policy: RetentionPolicy,
        *,
        confirmation_token: str,
    ) -> RetentionReceipt:
        assert confirmation_token == "retention:bound-plan"
        self.retention_policy = policy
        return RetentionReceipt(
            confirmation_token=confirmation_token,
            discarded_job_ids=("job-1",),
        )


def _service(fake: _CustodyFake | None = None) -> LibraryCustodyService:
    return cast(LibraryCustodyService, fake or _CustodyFake())


def test_document_list_exposes_only_source_basename() -> None:
    result = dispatch_custody("lifecycle.documents.list", {}, _service())

    assert result == [
        {
            "document_id": "doc-1",
            "canonical_sha256": "a" * 64,
            "source_name": "oral-history.m4a",
            "segment_count": 12,
            "detected_language": "en",
            "deletion_ready": True,
        }
    ]
    assert "/secret/" not in repr(result)
    assert "canonical_path" not in repr(result)


def test_deletion_plan_omits_action_paths_and_preserves_backend_decisions() -> None:
    fake = _CustodyFake()
    result = dispatch_custody(
        "lifecycle.deletion.plan",
        {
            "document_id": "doc-1",
            "scopes": ["canonical-transcript", "source-recording"],
            "allow_source": True,
        },
        _service(fake),
    )

    assert isinstance(result, dict)
    assert result["actions"] == [
        {
            "target": "canonical-transcript",
            "description": "delete canonical transcript evidence",
        }
    ]
    assert result["preserved_note_count"] == 2
    assert result["affected_saved_search_count"] == 1
    assert fake.deletion_allow_source is True
    assert "/private/" not in repr(result)
    assert "path" not in repr(result)


def test_deletion_execute_forwards_exact_plan_confirmation() -> None:
    fake = _CustodyFake()
    result = dispatch_custody(
        "lifecycle.deletion.execute",
        {
            "document_id": "doc-1",
            "scopes": ["canonical-transcript"],
            "allow_source": False,
            "confirmation_token": "delete:bound-plan",
        },
        _service(fake),
    )

    assert result == {
        "document_id": "doc-1",
        "executed_targets": ["canonical-transcript"],
        "preserved_note_count": 1,
        "affected_saved_search_count": 1,
    }


def test_retention_plan_omits_private_workspace_path_and_reports_resume_loss() -> None:
    fake = _CustodyFake()
    result = dispatch_custody(
        "lifecycle.retention.plan",
        {"execution_days": 45, "include_incomplete": True},
        _service(fake),
    )

    assert isinstance(result, dict)
    assert result["candidates"] == [
        {
            "job_id": "job-1",
            "status": "interrupted",
            "updated_at": "2026-07-01T00:00:00+00:00",
            "resume_capability_lost": True,
        }
    ]
    assert fake.retention_policy == RetentionPolicy(
        execution_days=45,
        include_incomplete=True,
    )
    assert "/private/state" not in repr(result)
    assert "workspace_path" not in repr(result)


def test_retention_execute_forwards_reviewed_policy_and_token() -> None:
    fake = _CustodyFake()
    result = dispatch_custody(
        "lifecycle.retention.execute",
        {
            "execution_days": 30,
            "include_incomplete": False,
            "confirmation_token": "retention:bound-plan",
        },
        _service(fake),
    )

    assert result == {"discarded_job_ids": ["job-1"]}
    assert fake.retention_policy == RetentionPolicy(execution_days=30)


@pytest.mark.parametrize(
    "method,params",
    [
        ("lifecycle.documents.list", {"extra": True}),
        (
            "lifecycle.deletion.plan",
            {
                "document_id": "doc-1",
                "scopes": ["library-view", "library-view"],
            },
        ),
        (
            "lifecycle.retention.plan",
            {"execution_days": 36_501, "include_incomplete": False},
        ),
    ],
)
def test_dispatch_rejects_extra_duplicate_or_out_of_range_inputs(
    method: str,
    params: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        dispatch_custody(method, params, _service())


def test_closed_protocol_rejects_unknown_method() -> None:
    response = handle_request(
        {
            "protocol_version": 1,
            "request_id": "request-1",
            "method": "lifecycle.files.delete-anything",
            "params": {},
        },
        _service(),
    )

    assert response["ok"] is False
    assert response["error"] == {
        "code": "invalid_request",
        "message": "Lifecycle request is invalid or incompatible",
    }


def test_unexpected_errors_are_masked_without_paths() -> None:
    fake = _CustodyFake()
    fake.fail_unexpected = True
    response = handle_request(
        {
            "protocol_version": 1,
            "request_id": "request-2",
            "method": "lifecycle.deletion.plan",
            "params": {"document_id": "doc-1", "scopes": ["library-view"]},
        },
        _service(fake),
    )

    assert response["ok"] is False
    assert response["error"] == {
        "code": "internal_error",
        "message": "EchoFlow could not complete the local lifecycle request",
    }
    assert "/private/" not in repr(response)
