from dataclasses import FrozenInstanceError, fields
from pathlib import Path

import pytest

from echoflow.workspace.errors import UnsafePathError
from echoflow.workspace.models import (
    Artifact,
    ArtifactKind,
    CollisionPolicy,
    Job,
    JobId,
    WorkspacePaths,
)


def test_job_id_is_path_safe_and_typed():
    job_id = JobId("job_2026-08")
    assert str(job_id) == "job_2026-08"


def test_job_id_validation_message_is_stable():
    with pytest.raises(UnsafePathError) as error:
        JobId("NOT-SAFE")
    assert str(error.value) == (
        "Job ID must contain 1-64 lowercase letters, digits, underscores, or hyphens"
    )


@pytest.mark.parametrize(
    "value",
    ["", "../job", "Job", "job.with.dot", "job/child", "job\\child", "a" * 65],
)
def test_job_id_rejects_traversal_and_ambiguous_values(value):
    with pytest.raises(UnsafePathError):
        JobId(value)


def test_workspace_paths_normalize_and_expose_only_string_serialization(tmp_path):
    paths = WorkspacePaths(
        state_dir=tmp_path / "state" / ".." / "state",
        cache_dir=tmp_path / "cache",
        model_dir=tmp_path / "cache" / "models",
        output_dir=tmp_path / "Downloads" / "EchoFlow",
    )
    assert paths.state_dir == (tmp_path / "state").resolve()
    assert paths.jobs_dir == paths.state_dir / "jobs"
    assert paths.to_dict() == {
        "state_dir": str(paths.state_dir),
        "cache_dir": str(paths.cache_dir),
        "model_dir": str(paths.model_dir),
        "output_dir": str(paths.output_dir),
    }


def test_model_directory_must_remain_in_private_cache(tmp_path):
    with pytest.raises(UnsafePathError) as error:
        WorkspacePaths(
            state_dir=tmp_path / "state",
            cache_dir=tmp_path / "cache",
            model_dir=tmp_path / "models",
            output_dir=tmp_path / "output",
        )
    assert str(error.value) == "The model directory must be inside the private cache"


@pytest.mark.parametrize("private_name", ["state", "cache"])
def test_public_output_cannot_overlap_private_roots(tmp_path, private_name):
    private_root = tmp_path / private_name
    with pytest.raises(UnsafePathError) as error:
        WorkspacePaths(
            state_dir=tmp_path / "state",
            cache_dir=tmp_path / "cache",
            model_dir=tmp_path / "cache" / "models",
            output_dir=private_root / "output",
        )
    assert str(error.value) == (
        "The public output directory must be separate from private state and cache"
    )


def test_public_output_cannot_contain_private_roots(tmp_path):
    with pytest.raises(UnsafePathError):
        WorkspacePaths(
            state_dir=tmp_path / "state",
            cache_dir=tmp_path / "cache",
            model_dir=tmp_path / "cache" / "models",
            output_dir=tmp_path,
        )


@pytest.mark.parametrize(
    ("kind", "suffix"),
    [
        (ArtifactKind.CANONICAL_JSON, ".json"),
        (ArtifactKind.TEXT, ".txt"),
        (ArtifactKind.SUBRIP, ".srt"),
        (ArtifactKind.WEBVTT, ".vtt"),
    ],
)
def test_artifact_kinds_own_their_file_suffix(kind, suffix):
    assert kind.suffix == suffix


def test_policy_and_artifact_enum_wire_values_are_stable():
    assert CollisionPolicy.RENAME.value == "rename"
    assert CollisionPolicy.ERROR.value == "error"
    assert [kind.value for kind in ArtifactKind] == ["json", "txt", "srt", "vtt"]


def test_with_output_revalidates_the_public_private_boundary(tmp_path):
    paths = WorkspacePaths(
        state_dir=tmp_path / "state",
        cache_dir=tmp_path / "cache",
        model_dir=tmp_path / "cache" / "models",
        output_dir=tmp_path / "output",
    )
    with pytest.raises(UnsafePathError):
        paths.with_output(Path(paths.state_dir / "public"))


def test_job_and_artifact_value_objects_normalize_paths(tmp_path):
    job = Job(
        job_id=JobId("job-1"),
        input_path=tmp_path / "incoming" / ".." / "input.wav",
        workspace_dir=tmp_path / "state" / "jobs" / "job-1",
        output_dir=tmp_path / "output" / ".",
    )
    artifact = Artifact(
        job_id=job.job_id,
        kind=ArtifactKind.TEXT,
        path=job.output_dir / "nested" / ".." / "input.txt",
    )
    assert job.input_path == (tmp_path / "input.wav").resolve()
    assert artifact.path == (tmp_path / "output" / "input.txt").resolve()
    assert job.to_dict() == {
        "job_id": "job-1",
        "input_path": str((tmp_path / "input.wav").resolve()),
        "workspace_dir": str((tmp_path / "state/jobs/job-1").resolve()),
        "output_dir": str((tmp_path / "output").resolve()),
    }
    assert artifact.to_dict() == {
        "job_id": "job-1",
        "kind": "txt",
        "path": str((tmp_path / "output/input.txt").resolve()),
    }

    paths = WorkspacePaths(
        state_dir=tmp_path / "state",
        cache_dir=tmp_path / "cache",
        model_dir=tmp_path / "cache" / "models",
        output_dir=tmp_path / "output",
    )
    for value in (job.job_id, paths, job, artifact):
        assert not hasattr(value, "__dict__")
        field_name = fields(value)[0].name
        with pytest.raises(FrozenInstanceError):
            setattr(value, field_name, None)
