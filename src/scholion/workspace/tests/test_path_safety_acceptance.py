import os
from pathlib import Path
from unittest.mock import Mock

import pytest

from scholion.core.file_manager_facade import FileManagerFacade
from scholion.core.performance_tracker import PerformanceTracker
from scholion.interfaces.local_file_manager import LocalFileManager
from scholion.workspace.errors import UnsafePathError
from scholion.workspace.models import JobId, WorkspacePaths
from scholion.workspace.service import WorkspaceService


@pytest.mark.skipif(
    os.name == "nt", reason="portable symlink creation is not guaranteed"
)
def test_job_planning_rejects_preexisting_symlink_escape_before_mutation(
    tmp_path: Path,
) -> None:
    source = tmp_path / "interview.wav"
    source.write_bytes(b"audio")
    paths = WorkspacePaths(
        state_dir=tmp_path / "state",
        cache_dir=tmp_path / "cache",
        model_dir=tmp_path / "cache" / "models",
        output_dir=tmp_path / "output",
    )
    paths.jobs_dir.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    escape = paths.jobs_dir / "known-job"
    escape.symlink_to(outside / "created-by-escape", target_is_directory=True)
    service = WorkspaceService(
        paths,
        FileManagerFacade(LocalFileManager(), Mock(), PerformanceTracker()),
    )

    with pytest.raises(
        UnsafePathError,
        match="^Job workspace is outside the private jobs directory$",
    ):
        service.plan_job(source, job_id=JobId("known-job"))

    assert not (outside / "created-by-escape").exists()
