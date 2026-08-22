import hashlib
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest

from scholion.library.custody import (
    DeletionScope,
    DeletionTarget,
    LibraryCustodyService,
    RetentionPolicy,
)
from scholion.library.errors import CustodyOperationError
from scholion.library.evidence import EvidenceAnchor
from scholion.library.index import IndexedDocument, SearchQuery
from scholion.library.research_state import ResearchNote
from scholion.library.service import LibraryEvidenceReceipt, SourceIntegrity
from scholion.library.workspace_metadata import SavedSearch, SavedSearchIntent
from scholion.workspace.lifecycle import JobLifecycleRecord, JobStatus
from scholion.workspace.models import JobId, WorkspacePaths


class LocalFiles:
    def file_exists(self, path: str | Path) -> bool:
        return Path(path).is_file()

    def read_file(self, path: str | Path) -> bytes:
        return Path(path).read_bytes()

    def delete_file(self, path: str | Path) -> None:
        Path(path).unlink()

    def delete_directory(self, path: str | Path) -> None:
        shutil.rmtree(path)


def _document(
    tmp_path: Path,
    *,
    source_integrity: SourceIntegrity = SourceIntegrity.MATCHES,
):
    output = tmp_path / "output"
    output.mkdir()
    canonical = output / "interview.json"
    canonical.write_bytes(b'{"canonical":"evidence"}\n')
    canonical_sha = hashlib.sha256(canonical.read_bytes()).hexdigest()
    source = tmp_path / "recording.wav"
    source.write_bytes(b"source-audio")
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    document = IndexedDocument(
        document_id="job-1",
        source_sha256=source_sha,
        detected_language="en",
        canonical_path=str(canonical),
        source_path=str(source),
        segment_count=2,
        canonical_sha256=canonical_sha,
    )
    receipt = LibraryEvidenceReceipt(
        document=document,
        source_integrity=source_integrity,
        current_source_sha256=source_sha,
    )
    return document, receipt, canonical, source


def _note(note_id: str, canonical_sha256: str) -> ResearchNote:
    return ResearchNote(
        note_id=note_id,
        body=f"body {note_id}",
        anchor=EvidenceAnchor(
            document_id="job-1",
            source_sha256="0" * 64,
            canonical_sha256=canonical_sha256,
            canonical_path="/evidence/interview.json",
            source_path="/evidence/recording.wav",
            segment_ids=("segment-000001",),
            start_seconds=1.0,
            end_seconds=2.0,
        ),
        tag_ids=(),
        collection_ids=(),
        created_at="2026-08-01T00:00:00+00:00",
        updated_at="2026-08-01T00:00:00+00:00",
    )


def _saved(saved_id: str, document_ids: tuple[str, ...]) -> SavedSearch:
    return SavedSearch(
        saved_search_id=saved_id,
        name=saved_id,
        description=None,
        intent=SavedSearchIntent(
            query=SearchQuery("housing", document_ids=document_ids),
        ),
        created_at="2026-08-01T00:00:00+00:00",
        updated_at="2026-08-01T00:00:00+00:00",
    )


def _record(
    job_id: str,
    *,
    status: JobStatus,
    updated_at: str,
    artifact_path: Path | None = None,
) -> JobLifecycleRecord:
    return JobLifecycleRecord(
        job_id=JobId(job_id),
        input_path=Path("/tmp/recording.wav"),
        output_dir=Path("/tmp/output"),
        status=status,
        started_at="2026-07-01T00:00:00+00:00",
        updated_at=updated_at,
        process_id=None,
        process_started_at=None,
        artifact_path=artifact_path,
    )


def _service(
    tmp_path: Path,
    *,
    source_integrity: SourceIntegrity = SourceIntegrity.MATCHES,
):
    document, receipt, canonical, source = _document(
        tmp_path,
        source_integrity=source_integrity,
    )
    paths = WorkspacePaths(
        state_dir=tmp_path / "state",
        cache_dir=tmp_path / "cache",
        model_dir=tmp_path / "cache" / "models",
        output_dir=tmp_path / "output",
    )
    workspace = paths.jobs_dir / "job-1"
    workspace.mkdir(parents=True)
    (workspace / "checkpoint.bin").write_bytes(b"checkpoint")

    library = Mock()
    library.inspect.return_value = receipt
    lexical = Mock()
    semantic = Mock()
    semantic.state.return_value = object()

    lifecycle = Mock()
    lifecycle.list_records.return_value = (
        _record(
            "job-1",
            status=JobStatus.COMPLETED,
            updated_at="2026-08-01T00:00:00+00:00",
            artifact_path=canonical,
        ),
    )
    current_note = _note("note-current", document.canonical_sha256 or "")
    old_note = _note("note-old-generation", "f" * 64)
    research = Mock()
    research.notes.return_value = (current_note, old_note)

    metadata = Mock()
    metadata.saved_searches.return_value = (
        _saved("search-scoped", ("job-1",)),
        _saved("search-global", ()),
    )
    service = LibraryCustodyService(
        transcript_library=library,
        lexical_index=lexical,
        semantic_index=semantic,
        lifecycle_store=lifecycle,
        research_state=research,
        workspace_metadata=metadata,
        paths=paths,
        file_manager=LocalFiles(),  # type: ignore[arg-type]
    )
    return service, lexical, semantic, research, document, canonical, source, workspace


def test_canonical_deletion_plan_expands_only_disposable_descendants(
    tmp_path: Path,
) -> None:
    (
        service,
        _,
        _,
        _,
        document,
        canonical,
        source,
        workspace,
    ) = _service(tmp_path)
    canonical.with_suffix(".txt").write_text("derived")
    canonical.with_suffix(".srt").write_text("derived")

    plan = service.plan_deletion(
        "job-1",
        (DeletionScope.CANONICAL_TRANSCRIPT,),
    )

    assert plan.requested_scopes == (DeletionScope.CANONICAL_TRANSCRIPT,)
    assert plan.effective_scopes == (
        DeletionScope.LIBRARY_VIEW,
        DeletionScope.DERIVED_ARTIFACTS,
        DeletionScope.EXECUTION_STATE,
        DeletionScope.CANONICAL_TRANSCRIPT,
    )
    assert [action.target for action in plan.actions] == [
        DeletionTarget.LEXICAL_INDEX,
        DeletionTarget.SEMANTIC_INDEX,
        DeletionTarget.DERIVED_ARTIFACT,
        DeletionTarget.DERIVED_ARTIFACT,
        DeletionTarget.EXECUTION_STATE,
        DeletionTarget.CANONICAL_TRANSCRIPT,
    ]
    assert plan.preserved_note_ids == ("note-current",)
    assert plan.affected_saved_search_ids == ("search-scoped",)
    assert source.is_file()
    assert workspace.is_dir()
    assert document.canonical_sha256[:12] in plan.confirmation_token


def test_deletion_requires_exact_current_plan_and_preserves_notes_by_default(
    tmp_path: Path,
) -> None:
    service, lexical, semantic, research, _, canonical, source, workspace = _service(
        tmp_path
    )
    derived = canonical.with_suffix(".vtt")
    derived.write_text("derived")
    plan = service.plan_deletion(
        "job-1",
        (DeletionScope.CANONICAL_TRANSCRIPT,),
    )

    with pytest.raises(CustodyOperationError, match="confirmation token"):
        service.execute_deletion(
            "job-1",
            (DeletionScope.CANONICAL_TRANSCRIPT,),
            confirmation_token="delete:stale",
        )

    lexical.remove.assert_not_called()
    receipt = service.execute_deletion(
        "job-1",
        (DeletionScope.CANONICAL_TRANSCRIPT,),
        confirmation_token=plan.confirmation_token,
    )

    lexical.remove.assert_called_once_with("job-1")
    semantic.clear.assert_called_once_with()
    research.delete_note.assert_not_called()
    assert receipt.preserved_note_ids == ("note-current",)
    assert not canonical.exists()
    assert not derived.exists()
    assert not workspace.exists()
    assert source.exists()


def test_canonical_integrity_is_rechecked_before_any_mutation(tmp_path: Path) -> None:
    service, lexical, _, research, _, canonical, _, _ = _service(tmp_path)
    plan = service.plan_deletion(
        "job-1",
        (DeletionScope.CANONICAL_TRANSCRIPT,),
    )
    canonical.write_text('{"changed":true}\n')

    with pytest.raises(CustodyOperationError, match="changed after indexing"):
        service.execute_deletion(
            "job-1",
            (DeletionScope.CANONICAL_TRANSCRIPT,),
            confirmation_token=plan.confirmation_token,
        )

    lexical.remove.assert_not_called()
    research.delete_note.assert_not_called()
    assert canonical.exists()


def test_research_and_source_are_separate_explicit_destructive_scopes(
    tmp_path: Path,
) -> None:
    service, lexical, semantic, research, _, canonical, source, _ = _service(tmp_path)
    scopes = (
        DeletionScope.RESEARCH_NOTES,
        DeletionScope.SOURCE_RECORDING,
    )

    with pytest.raises(CustodyOperationError, match="allow-source"):
        service.plan_deletion("job-1", scopes)

    plan = service.plan_deletion("job-1", scopes, allow_source=True)
    assert plan.preserved_note_ids == ()
    assert [action.target for action in plan.actions] == [
        DeletionTarget.SOURCE_RECORDING,
        DeletionTarget.RESEARCH_NOTE,
    ]

    service.execute_deletion(
        "job-1",
        scopes,
        allow_source=True,
        confirmation_token=plan.confirmation_token,
    )

    research.delete_note.assert_called_once_with("note-current")
    lexical.remove.assert_not_called()
    semantic.clear.assert_not_called()
    assert canonical.exists()
    assert not source.exists()


def test_source_deletion_refuses_changed_or_unverifiable_input(tmp_path: Path) -> None:
    service, *_ = _service(
        tmp_path,
        source_integrity=SourceIntegrity.CHANGED,
    )

    with pytest.raises(CustodyOperationError, match="no longer matches"):
        service.plan_deletion(
            "job-1",
            (DeletionScope.SOURCE_RECORDING,),
            allow_source=True,
        )


def test_library_view_only_removes_indexes_and_never_files(tmp_path: Path) -> None:
    service, lexical, semantic, research, _, canonical, source, workspace = _service(
        tmp_path
    )
    plan = service.plan_deletion("job-1", (DeletionScope.LIBRARY_VIEW,))

    assert [action.target for action in plan.actions] == [
        DeletionTarget.LEXICAL_INDEX,
        DeletionTarget.SEMANTIC_INDEX,
    ]
    service.execute_deletion(
        "job-1",
        (DeletionScope.LIBRARY_VIEW,),
        confirmation_token=plan.confirmation_token,
    )

    lexical.remove.assert_called_once_with("job-1")
    semantic.clear.assert_called_once_with()
    research.delete_note.assert_not_called()
    assert canonical.exists()
    assert source.exists()
    assert workspace.exists()


def test_retention_defaults_to_old_completed_private_workspaces_only(
    tmp_path: Path,
) -> None:
    service, _, _, _, _, canonical, _, _ = _service(tmp_path)
    now = datetime(2026, 8, 19, tzinfo=UTC)
    lifecycle = service.lifecycle_store

    old_completed = service.paths.jobs_dir / "completed-old"
    old_failed = service.paths.jobs_dir / "failed-old"
    recent_completed = service.paths.jobs_dir / "completed-recent"
    running = service.paths.jobs_dir / "running-old"
    for path in (old_completed, old_failed, recent_completed, running):
        path.mkdir(parents=True)
        (path / "private.bin").write_bytes(b"x")

    lifecycle.list_records.return_value = (
        _record(
            "completed-old",
            status=JobStatus.COMPLETED,
            updated_at=(now - timedelta(days=40)).isoformat(),
            artifact_path=canonical,
        ),
        _record(
            "failed-old",
            status=JobStatus.FAILED,
            updated_at=(now - timedelta(days=40)).isoformat(),
        ),
        _record(
            "completed-recent",
            status=JobStatus.COMPLETED,
            updated_at=(now - timedelta(days=2)).isoformat(),
            artifact_path=canonical,
        ),
        _record(
            "running-old",
            status=JobStatus.RUNNING,
            updated_at=(now - timedelta(days=90)).isoformat(),
        ),
    )

    plan = service.plan_retention(RetentionPolicy(execution_days=30), now=now)

    assert [item.job_id for item in plan.candidates] == ["completed-old"]
    assert not plan.candidates[0].resume_capability_lost
    receipt = service.execute_retention(
        RetentionPolicy(execution_days=30),
        confirmation_token=plan.confirmation_token,
        now=now,
    )

    assert receipt.discarded_job_ids == ("completed-old",)
    assert not old_completed.exists()
    assert old_failed.exists()
    assert recent_completed.exists()
    assert running.exists()
    assert canonical.exists()


def test_retention_incomplete_cleanup_is_explicit_and_plan_bound(
    tmp_path: Path,
) -> None:
    service, *_ = _service(tmp_path)
    now = datetime(2026, 8, 19, tzinfo=UTC)
    failed = service.paths.jobs_dir / "failed-old"
    failed.mkdir(parents=True)
    service.lifecycle_store.list_records.return_value = (
        _record(
            "failed-old",
            status=JobStatus.INTERRUPTED,
            updated_at=(now - timedelta(days=31)).isoformat(),
        ),
    )
    policy = RetentionPolicy(execution_days=30, include_incomplete=True)
    plan = service.plan_retention(policy, now=now)

    assert len(plan.candidates) == 1
    assert plan.candidates[0].resume_capability_lost

    failed.rmdir()
    refreshed = service.plan_retention(policy, now=now)
    assert refreshed.candidates == ()
    assert refreshed.confirmation_token != plan.confirmation_token
    with pytest.raises(CustodyOperationError, match="Retention plan changed"):
        service.execute_retention(
            policy,
            confirmation_token=plan.confirmation_token,
            now=now,
        )


def test_retention_rejects_naive_clock_and_malformed_lifecycle_time(
    tmp_path: Path,
) -> None:
    service, *_ = _service(tmp_path)
    with pytest.raises(ValueError, match="timezone-aware"):
        service.plan_retention(
            RetentionPolicy(),
            now=datetime(2026, 8, 19),
        )

    workspace = service.paths.jobs_dir / "bad-time"
    workspace.mkdir(parents=True)
    service.lifecycle_store.list_records.return_value = (
        _record(
            "bad-time",
            status=JobStatus.COMPLETED,
            updated_at="not-a-time",
        ),
    )
    with pytest.raises(CustodyOperationError, match="timestamp is invalid"):
        service.plan_retention(
            RetentionPolicy(execution_days=0),
            now=datetime(2026, 8, 19, tzinfo=UTC),
        )


def test_deletion_token_binds_preserved_notes_and_document_scoped_searches(
    tmp_path: Path,
) -> None:
    service, _, _, research, document, *_ = _service(tmp_path)
    first = service.plan_deletion("job-1", (DeletionScope.CANONICAL_TRANSCRIPT,))

    research.notes.return_value = (
        _note("note-current", document.canonical_sha256 or ""),
        _note("note-new", document.canonical_sha256 or ""),
    )
    second = service.plan_deletion("job-1", (DeletionScope.CANONICAL_TRANSCRIPT,))
    assert second.confirmation_token != first.confirmation_token

    service.workspace_metadata.saved_searches.return_value = (
        _saved("search-scoped", ("job-1",)),
        _saved("search-new", ("job-1",)),
    )
    third = service.plan_deletion("job-1", (DeletionScope.CANONICAL_TRANSCRIPT,))
    assert third.confirmation_token != second.confirmation_token


def test_saved_search_deletion_is_separate_explicit_authority_scope(
    tmp_path: Path,
) -> None:
    service, lexical, semantic, research, _, canonical, source, _ = _service(tmp_path)
    scopes = (DeletionScope.SAVED_SEARCHES,)
    plan = service.plan_deletion("job-1", scopes)

    assert [action.target for action in plan.actions] == [DeletionTarget.SAVED_SEARCH]
    assert plan.affected_saved_search_ids == ("search-scoped",)

    service.execute_deletion(
        "job-1",
        scopes,
        confirmation_token=plan.confirmation_token,
    )

    service.workspace_metadata.delete_saved_search.assert_called_once_with(
        "search-scoped"
    )
    research.delete_note.assert_not_called()
    lexical.remove.assert_not_called()
    semantic.clear.assert_not_called()
    assert canonical.exists()
    assert source.exists()


def test_deletion_scope_validation_and_optional_semantic_state(tmp_path: Path) -> None:
    service, _, semantic, _, _, _, _, _ = _service(tmp_path)
    with pytest.raises(ValueError, match="at least one deletion scope"):
        service.plan_deletion("job-1", ())

    semantic.state.return_value = None
    plan = service.plan_deletion(
        "job-1",
        (DeletionScope.LIBRARY_VIEW, DeletionScope.LIBRARY_VIEW),
    )
    assert plan.requested_scopes == (DeletionScope.LIBRARY_VIEW,)
    assert [action.target for action in plan.actions] == [DeletionTarget.LEXICAL_INDEX]


def test_deletion_refuses_unhashed_canonical_and_missing_source_path(
    tmp_path: Path,
) -> None:
    service, *_ = _service(tmp_path)
    receipt = service.transcript_library.inspect.return_value
    service.transcript_library.inspect.return_value = LibraryEvidenceReceipt(
        document=IndexedDocument(
            document_id=receipt.document.document_id,
            source_sha256=receipt.document.source_sha256,
            detected_language=receipt.document.detected_language,
            canonical_path=receipt.document.canonical_path,
            source_path=receipt.document.source_path,
            segment_count=receipt.document.segment_count,
            canonical_sha256=None,
        ),
        source_integrity=receipt.source_integrity,
        current_source_sha256=receipt.current_source_sha256,
    )
    with pytest.raises(CustodyOperationError, match="predates canonical hashing"):
        service.plan_deletion("job-1", (DeletionScope.LIBRARY_VIEW,))

    document = receipt.document
    service.transcript_library.inspect.return_value = LibraryEvidenceReceipt(
        document=IndexedDocument(
            document_id=document.document_id,
            source_sha256=document.source_sha256,
            detected_language=document.detected_language,
            canonical_path=document.canonical_path,
            source_path=None,
            segment_count=document.segment_count,
            canonical_sha256=document.canonical_sha256,
        ),
        source_integrity=SourceIntegrity.UNKNOWN,
        current_source_sha256=None,
    )
    with pytest.raises(CustodyOperationError, match="path is unavailable"):
        service.plan_deletion(
            "job-1",
            (DeletionScope.SOURCE_RECORDING,),
            allow_source=True,
        )


def test_retention_policy_and_value_objects_reject_invalid_state() -> None:
    from scholion.library.custody import (
        DeletionAction,
        DeletionPlan,
        RetentionCandidate,
        RetentionPlan,
    )

    with pytest.raises(ValueError, match="retention days"):
        RetentionPolicy(execution_days=-1)
    with pytest.raises(ValueError, match="retention days"):
        RetentionPolicy(execution_days=36_501)
    with pytest.raises(ValueError, match="identity and path"):
        RetentionCandidate("", JobStatus.COMPLETED, "time", "/private", False)
    with pytest.raises(ValueError, match="confirmation token"):
        RetentionPlan(RetentionPolicy(), (), "")
    with pytest.raises(ValueError, match="object_id"):
        DeletionAction(DeletionTarget.LEXICAL_INDEX, "", "remove")
    with pytest.raises(ValueError, match="description"):
        DeletionAction(DeletionTarget.LEXICAL_INDEX, "job-1", "")
    with pytest.raises(ValueError, match="path"):
        DeletionAction(DeletionTarget.DERIVED_ARTIFACT, "txt", "delete", "")
    with pytest.raises(ValueError, match="lowercase digest"):
        DeletionPlan(
            "job-1",
            "Z" * 64,
            (DeletionScope.LIBRARY_VIEW,),
            (DeletionScope.LIBRARY_VIEW,),
            (),
            (),
            (),
            "token",
        )
