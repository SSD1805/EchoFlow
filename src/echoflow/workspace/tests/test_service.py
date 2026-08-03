from unittest.mock import Mock, call

import pytest

from echoflow.core.file_manager_facade import FileManagerFacade
from echoflow.core.performance_tracker import PerformanceTracker
from echoflow.interfaces.local_file_manager import LocalFileManager
from echoflow.workspace.errors import (
    ArtifactCollisionError,
    InvalidInputError,
    JobCollisionError,
    UnsafePathError,
)
from echoflow.workspace.models import (
    ArtifactKind,
    CollisionPolicy,
    Job,
    JobId,
    WorkspacePaths,
)
from echoflow.workspace.service import WorkspaceService


@pytest.fixture
def paths(tmp_path):
    return WorkspacePaths(
        state_dir=tmp_path / "state",
        cache_dir=tmp_path / "cache",
        model_dir=tmp_path / "cache" / "models",
        output_dir=tmp_path / "Downloads" / "EchoFlow",
    )


@pytest.fixture
def service(paths):
    facade = FileManagerFacade(LocalFileManager(), Mock(), PerformanceTracker())
    return WorkspaceService(paths, facade, id_factory=lambda: "job-1")


def test_first_run_initializes_each_private_and_public_directory_idempotently(
    service, paths
):
    first = service.initialize()
    second = service.initialize()
    assert first == second == paths
    assert paths.state_dir.is_dir()
    assert paths.jobs_dir.is_dir()
    assert paths.cache_dir.is_dir()
    assert paths.model_dir.is_dir()
    assert paths.output_dir.is_dir()


def test_create_job_preserves_input_and_keeps_private_work_empty(
    service, paths, tmp_path
):
    source = tmp_path / "incoming" / "interview.wav"
    source.parent.mkdir()
    source.write_bytes(b"original-audio")

    job = service.create_job(source)

    assert job.job_id == JobId("job-1")
    assert job.input_path == source.resolve()
    assert job.output_dir == paths.output_dir
    assert job.workspace_dir == paths.jobs_dir / "job-1"
    assert list(job.workspace_dir.iterdir()) == []
    assert source.read_bytes() == b"original-audio"


def test_plan_job_resolves_paths_without_initializing_or_reserving(
    service, paths, tmp_path
):
    source = tmp_path / "incoming" / "interview.wav"
    source.parent.mkdir()
    source.write_bytes(b"original-audio")

    job = service.plan_job(source)

    assert job.job_id == JobId("job-1")
    assert job.workspace_dir == paths.jobs_dir / "job-1"
    assert job.output_dir == paths.output_dir
    assert not paths.state_dir.exists()
    assert not paths.cache_dir.exists()
    assert not paths.output_dir.exists()
    assert source.read_bytes() == b"original-audio"


def test_planned_artifact_uses_next_collision_candidate_without_reserving_it(
    service, paths, tmp_path
):
    source = tmp_path / "field recording.wav"
    source.write_bytes(b"audio")
    paths.output_dir.mkdir(parents=True)
    (paths.output_dir / "field recording.json").write_text("existing")
    job = service.plan_job(source)

    artifact = service.plan_artifact(job, ArtifactKind.CANONICAL_JSON)

    assert artifact.path.name == "field recording-2.json"
    assert not artifact.path.exists()
    assert not job.workspace_dir.exists()


def test_planned_artifact_error_policy_reports_existing_candidate(
    service, paths, tmp_path
):
    source = tmp_path / "recording.wav"
    source.write_bytes(b"audio")
    paths.output_dir.mkdir(parents=True)
    (paths.output_dir / "recording.txt").write_text("existing")
    job = service.plan_job(source)

    with pytest.raises(ArtifactCollisionError) as error:
        service.plan_artifact(job, ArtifactKind.TEXT, collision=CollisionPolicy.ERROR)

    assert error.value.path.name == "recording.txt"
    assert str(error.value) == "Artifact path is already occupied"


def test_planned_artifact_collision_search_is_bounded(service, paths, tmp_path):
    source = tmp_path / "bounded.wav"
    source.write_bytes(b"audio")
    paths.output_dir.mkdir(parents=True)
    (paths.output_dir / "bounded.txt").write_text("first")
    (paths.output_dir / "bounded-2.txt").write_text("second")
    bounded = WorkspaceService(
        paths,
        service.file_manager,
        id_factory=lambda: "bounded",
        max_collision_attempts=2,
    )
    job = bounded.plan_job(source)

    with pytest.raises(ArtifactCollisionError) as error:
        bounded.plan_artifact(job, ArtifactKind.TEXT)

    assert error.value.path.name == "bounded-2.txt"
    assert str(error.value) == "Artifact path is already occupied"


def test_planned_artifact_uses_configured_final_collision_candidate(
    service, paths, tmp_path
):
    source = tmp_path / "final-plan.wav"
    source.write_bytes(b"audio")
    paths.output_dir.mkdir(parents=True)
    (paths.output_dir / "final-plan.txt").write_text("first")
    bounded = WorkspaceService(
        paths,
        service.file_manager,
        id_factory=lambda: "final-plan",
        max_collision_attempts=2,
    )
    job = bounded.plan_job(source)

    artifact = bounded.plan_artifact(job, ArtifactKind.TEXT)

    assert artifact.path.name == "final-plan-2.txt"
    assert not artifact.path.exists()


def test_plan_artifact_rejects_forged_unreserved_job_paths(service, paths, tmp_path):
    forged = Job(
        JobId("forged-plan"),
        tmp_path / "input.wav",
        tmp_path / "outside/forged-plan",
        paths.output_dir,
    )
    with pytest.raises(
        UnsafePathError,
        match="^Job workspace is outside the private jobs directory$",
    ):
        service.plan_artifact(forged, ArtifactKind.CANONICAL_JSON)


def test_reservation_requires_previously_claimed_workspace(service, tmp_path):
    source = tmp_path / "unreserved.wav"
    source.write_bytes(b"audio")
    planned = service.plan_job(source)
    with pytest.raises(
        UnsafePathError,
        match="^Job workspace is outside the private jobs directory$",
    ):
        service.reserve_artifact(planned, ArtifactKind.CANONICAL_JSON)


def test_initialization_and_job_reservation_pass_private_intent_exactly(
    paths, tmp_path
):
    source = tmp_path / "private.wav"
    source.write_bytes(b"audio")
    file_manager = Mock()
    service = WorkspaceService(
        paths,
        file_manager,
        id_factory=lambda: "private-job",
    )

    job = service.create_job(source)

    assert file_manager.ensure_directory_exists.call_args_list == [
        call(paths.state_dir, private=True),
        call(paths.jobs_dir, private=True),
        call(paths.cache_dir, private=True),
        call(paths.model_dir, private=True),
        call(paths.output_dir),
    ]
    file_manager.reserve_directory.assert_called_once_with(
        job.workspace_dir, private=True
    )


def test_missing_or_directory_input_is_rejected_without_initializing(service, paths):
    missing = paths.state_dir / "sensitive-participant-001.wav"
    with pytest.raises(InvalidInputError) as error:
        service.create_job(missing)
    assert error.value.path == missing.resolve()
    assert str(error.value) == "Input is not a readable local file"
    assert "sensitive-participant-001" not in str(error.value)
    with pytest.raises(InvalidInputError):
        service.create_job(paths.state_dir.parent)
    assert not paths.state_dir.exists()


def test_explicit_job_id_collision_is_typed(service, tmp_path):
    source = tmp_path / "source.wav"
    source.write_bytes(b"audio")
    selected = JobId("stable-job")
    service.create_job(source, job_id=selected)
    with pytest.raises(JobCollisionError) as error:
        service.create_job(source, job_id=selected)
    assert error.value.job_id == "stable-job"


def test_artifact_allocation_is_exclusive_and_renames_collisions(service, tmp_path):
    source = tmp_path / "field recording.wav"
    source.write_bytes(b"audio")
    job = service.create_job(source)

    first = service.reserve_artifact(job, ArtifactKind.CANONICAL_JSON)
    second = service.reserve_artifact(job, ArtifactKind.CANONICAL_JSON)

    assert first.path.name == "field recording.json"
    assert second.path.name == "field recording-2.json"
    assert first.path.read_bytes() == b""
    assert second.path.read_bytes() == b""
    assert first.job_id == second.job_id == job.job_id


def test_error_collision_policy_never_overwrites_existing_artifact(service, tmp_path):
    source = tmp_path / "recording.wav"
    source.write_bytes(b"audio")
    job = service.create_job(source)
    existing = job.output_dir / "recording.txt"
    existing.write_text("keep me")

    with pytest.raises(ArtifactCollisionError):
        service.reserve_artifact(
            job, ArtifactKind.TEXT, collision=CollisionPolicy.ERROR
        )
    assert existing.read_text() == "keep me"


def test_rename_policy_is_bounded_when_every_candidate_exists(service, paths, tmp_path):
    source = tmp_path / "recording.wav"
    source.write_bytes(b"audio")
    bounded = WorkspaceService(
        paths,
        service.file_manager,
        id_factory=lambda: "bounded",
        max_collision_attempts=2,
    )
    job = bounded.create_job(source)
    (job.output_dir / "recording.txt").write_text("first")
    (job.output_dir / "recording-2.txt").write_text("second")
    with pytest.raises(ArtifactCollisionError):
        bounded.reserve_artifact(job, ArtifactKind.TEXT)


def test_rename_policy_tries_the_configured_final_candidate(service, paths, tmp_path):
    source = tmp_path / "final.wav"
    source.write_bytes(b"audio")
    bounded = WorkspaceService(
        paths,
        service.file_manager,
        id_factory=lambda: "final-candidate",
        max_collision_attempts=2,
    )
    job = bounded.create_job(source)
    (job.output_dir / "final.txt").write_text("occupied")
    artifact = bounded.reserve_artifact(job, ArtifactKind.TEXT)
    assert artifact.path.name == "final-2.txt"


def test_input_file_is_treated_as_a_collision_not_an_output_target(service, tmp_path):
    source = tmp_path / "incoming" / "recording.json"
    source.parent.mkdir()
    source.write_bytes(b"source")
    job = service.create_job(source, output_dir=source.parent)

    artifact = service.reserve_artifact(job, ArtifactKind.CANONICAL_JSON)

    assert artifact.path.name == "recording-2.json"
    assert source.read_bytes() == b"source"


@pytest.mark.parametrize(
    "filename",
    ["", ".", "..", "../escape.json", "nested/file.json", "nested\\file.json"],
)
def test_artifact_filename_rejects_empty_and_traversal_values(
    service, tmp_path, filename
):
    source = tmp_path / "recording.wav"
    source.write_bytes(b"audio")
    job = service.create_job(source)
    with pytest.raises(UnsafePathError) as error:
        service.reserve_artifact(job, ArtifactKind.CANONICAL_JSON, filename=filename)
    assert str(error.value) == "Artifact filename must be one safe filename"


def test_artifact_filename_must_match_its_typed_kind(service, tmp_path):
    source = tmp_path / "recording.wav"
    source.write_bytes(b"audio")
    job = service.create_job(source)
    with pytest.raises(UnsafePathError) as error:
        service.reserve_artifact(
            job, ArtifactKind.CANONICAL_JSON, filename="recording.txt"
        )
    assert str(error.value) == "Artifact filename must use the .json extension"


def test_safe_explicit_artifact_filename_is_preserved(service, tmp_path):
    source = tmp_path / "recording.wav"
    source.write_bytes(b"audio")
    job = service.create_job(source)
    artifact = service.reserve_artifact(
        job, ArtifactKind.CANONICAL_JSON, filename="edited-name.json"
    )
    assert artifact.path.name == "edited-name.json"


def test_collision_attempt_limit_must_be_positive(service, paths):
    with pytest.raises(ValueError, match="^max_collision_attempts must be positive$"):
        WorkspaceService(paths, service.file_manager, max_collision_attempts=0)


def test_one_collision_attempt_is_valid(service, paths):
    one_attempt = WorkspaceService(
        paths, service.file_manager, max_collision_attempts=1
    )
    assert one_attempt.max_collision_attempts == 1


def test_default_collision_attempt_budget_is_stable(service, paths):
    default = WorkspaceService(paths, service.file_manager)
    assert default.max_collision_attempts == 1_000


def test_default_job_id_factory_creates_a_valid_unique_directory(
    service, paths, tmp_path
):
    source = tmp_path / "generated.wav"
    source.write_bytes(b"audio")
    default = WorkspaceService(paths, service.file_manager)
    job = default.create_job(source)
    assert len(job.job_id.value) == 32
    assert int(job.job_id.value, 16) >= 0
    assert job.workspace_dir.is_dir()


def test_forged_job_workspace_cannot_allocate_public_artifacts(
    service, paths, tmp_path
):
    forged = Job(
        job_id=JobId("forged"),
        input_path=tmp_path / "input.wav",
        workspace_dir=tmp_path / "outside" / "forged",
        output_dir=paths.output_dir,
    )
    with pytest.raises(UnsafePathError) as error:
        service.reserve_artifact(forged, ArtifactKind.TEXT)
    assert str(error.value) == "Job workspace is outside the private jobs directory"


def test_job_id_and_workspace_directory_must_match(service, paths, tmp_path):
    paths.jobs_dir.mkdir(parents=True)
    mismatched_workspace = paths.jobs_dir / "different"
    mismatched_workspace.mkdir()
    forged = Job(
        job_id=JobId("forged"),
        input_path=tmp_path / "input.wav",
        workspace_dir=mismatched_workspace,
        output_dir=paths.output_dir,
    )
    with pytest.raises(UnsafePathError):
        service.reserve_artifact(forged, ArtifactKind.TEXT)


def test_forged_output_cannot_overlap_private_state(service, paths, tmp_path):
    source = tmp_path / "source.wav"
    source.write_bytes(b"audio")
    job = service.create_job(source)
    forged = Job(
        job_id=job.job_id,
        input_path=job.input_path,
        workspace_dir=job.workspace_dir,
        output_dir=paths.state_dir / "public",
    )
    with pytest.raises(UnsafePathError):
        service.reserve_artifact(forged, ArtifactKind.TEXT)
