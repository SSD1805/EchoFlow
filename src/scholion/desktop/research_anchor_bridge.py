"""Narrow desktop DTOs for explicit research-anchor review and re-anchoring."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from scholion.library.research import LocatedCanonicalEvidence
from scholion.library.research_anchor_review import (
    ResearchAnchorReview,
    ResearchAnchorReviewService,
)
from scholion.library.research_workspace import ResearchWorkspaceService


class _ReviewAnchorParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note_id: str = Field(min_length=1, max_length=200)
    context_segments: int = Field(default=1, ge=0, le=10)

    @field_validator("note_id")
    @classmethod
    def strip_note_id(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("note_id cannot be blank")
        return stripped


class _ReanchorNoteParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note_id: str = Field(min_length=1, max_length=200)
    expected_updated_at: str = Field(min_length=1, max_length=200)
    expected_candidate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("note_id", "expected_updated_at")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value cannot be blank")
        return stripped


def _serialize_evidence(item: LocatedCanonicalEvidence | None) -> object:
    if item is None:
        return None
    evidence = item.evidence
    result_ids = set(evidence.result_segment_ids)
    text = " ".join(
        segment.text
        for segment in evidence.context_segments
        if segment.segment_id in result_ids
    )
    return {
        "document_id": evidence.document_id,
        "canonical_sha256": evidence.canonical_sha256,
        "segment_ids": list(evidence.result_segment_ids),
        "start_seconds": evidence.start_seconds,
        "end_seconds": evidence.end_seconds,
        "seek_seconds": evidence.seek_seconds,
        "text": text,
    }


def _serialize_review(review: ResearchAnchorReview) -> dict[str, object]:
    return {
        "note_id": review.note.note.note_id,
        "updated_at": review.note.note.updated_at,
        "status": review.status.value,
        "anchored": _serialize_evidence(review.anchored),
        "candidate": _serialize_evidence(review.candidate),
        "history": [
            {
                "revision": entry.revision,
                "canonical_sha256": entry.anchor.canonical_sha256,
                "segment_ids": list(entry.anchor.segment_ids),
                "start_seconds": entry.anchor.start_seconds,
                "end_seconds": entry.anchor.end_seconds,
                "replaced_at": entry.replaced_at,
            }
            for entry in review.history
        ],
    }


def dispatch_research_anchor(
    method: str,
    params: dict[str, object],
    workspace: ResearchWorkspaceService,
) -> dict[str, object]:
    if method == "workspace.research.note.anchor.review":
        review_params = _ReviewAnchorParams.model_validate(params)
        service = ResearchAnchorReviewService.for_workspace(workspace)
        return _serialize_review(
            service.review(
                review_params.note_id,
                context_segments=review_params.context_segments,
            )
        )
    if method == "workspace.research.note.anchor.reanchor":
        reanchor_params = _ReanchorNoteParams.model_validate(params)
        service = ResearchAnchorReviewService.for_workspace(workspace)
        updated = service.reanchor_to_reviewed_current(
            reanchor_params.note_id,
            expected_updated_at=reanchor_params.expected_updated_at,
            expected_candidate_sha256=reanchor_params.expected_candidate_sha256,
        )
        return {
            "note_id": updated.note.note_id,
            "updated_at": updated.note.updated_at,
            "canonical_sha256": updated.note.anchor.canonical_sha256,
            "current": updated.current,
        }
    raise ValueError("Unsupported research anchor desktop method")
