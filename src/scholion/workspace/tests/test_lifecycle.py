from unittest.mock import Mock

import pytest

from scholion.core.file_manager_facade import FileManagerFacade
from scholion.core.performance_tracker import PerformanceTracker
from scholion.interfaces.local_file_manager import LocalFileManager
from scholion.workspace.errors import JobNotFoundError
from scholion.workspace.lifecycle import JobLifecycleStore, JobStatus
from scholion.workspace.models import ArtifactKind, JobId, WorkspacePaths
from scholion.workspace.service import WorkspaceService


@pytest.fixture
def lifecycle_setup(tmp_path):
    paths = WorkspacePaths(
        state_dir=tmp_path / "state",
        cache_dir=tmp_path / "cache",
        model_dir=tmp_path / "cache" / "models",
        output_dir=tmp_path / "output",
    )
    facade = FileManagerFacade(LocalFileManager(), Mock(), PerformanceTracker())
    workspace = WorkspaceService(paths, facade, id_factory=lambda: "job-1")
    source = tmp_path / "interview.wav"
    source.write_bytes(b"audio")
    job = workspace.create_job(source)
    store = JobLifecycleStore(facade, paths)
    return store, workspace, job, paths


def test_lifecycle_tracks_progress_completion_and_listing(lifecycle_setup):
    store, workspace, job, paths = lifecycle_setup

    started = store.start(job)
    progressed = store.record_progress(job, completed_segments=2, total_segments=5)
    artifact = workspace.reserve_artifact(job, ArtifactKind.CANONICAL_JSON)
    artifact.path.write_text("{}")
    completed = store.complete(job, artifact)

    assert started.status is JobStatus.RUNNING
    assert progressed.progress_fraction == pytest.approx(0.4)
    assert completed.status is JobStatus.COMPLETED
    assert completed.completed_segments == 5
    assert completed.artifact_path == artifact.path
    assert store.get(job.job_id) == completed
    assert store.list_records() == (completed,)
    assert store.registry_dir.is_relative_to(paths.state_dir)
    assert not store.is_resumable(job.job_id)


def test_lifecycle_marks_interrupt_failure_and_stale_process(
    lifecycle_setup, monkeypatch
):
    store, _, job, _ = lifecycle_setup

    store.start(job)
    interrupted = store.interrupt(job)
    assert interrupted.status is JobStatus.INTERRUPTED

    store.start(job)
    failed = store.fail(job, error_code="resource_admission")
    assert failed.status is JobStatus.FAILED
    assert failed.error_code == "resource_admission"

    store.start(job)
    monkeypatch.setattr(
        JobLifecycleStore,
        "_process_is_active",
        staticmethod(lambda record: False),
    )
    reconciled = store.get(job.job_id)
    assert reconciled.status is JobStatus.INTERRUPTED
    assert reconciled.process_id is None


def test_resumable_state_and_discard_only_remove_private_job_state(lifecycle_setup):
    store, _, job, _ = lifecycle_setup
    store.start(job)
    checkpoint_dir = job.workspace_dir / "checkpoints"
    checkpoint_dir.mkdir()
    (checkpoint_dir / "manifest.json").write_text("{}")
    public = job.output_dir / "keep.json"
    public.write_text("published")

    assert store.is_resumable(job.job_id)
    store.discard(job.job_id)

    assert not job.workspace_dir.exists()
    assert not store.is_resumable(job.job_id)
    assert public.read_text() == "published"
    with pytest.raises(JobNotFoundError):
        store.get(job.job_id)


def test_lifecycle_rejects_invalid_limits_and_missing_jobs(lifecycle_setup):
    store, _, _, paths = lifecycle_setup
    with pytest.raises(ValueError, match="max_manifest_bytes must be positive"):
        JobLifecycleStore(store.file_manager, paths, max_manifest_bytes=0)
    with pytest.raises(JobNotFoundError):
        store.get(JobId("missing"))
    with pytest.raises(JobNotFoundError):
        store.discard(JobId("missing"))
