from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from scholion.core.errors import StorageAlreadyExistsError
from scholion.core.file_manager_facade import FileManagerFacade
from scholion.workspace.errors import (
    ArtifactCollisionError,
    InvalidInputError,
    JobCollisionError,
    JobNotFoundError,
    UnsafePathError,
)
from scholion.workspace.models import (
    Artifact,
    ArtifactKind,
    CollisionPolicy,
    Job,
    JobId,
    WorkspacePaths,
)


def _new_job_id() -> str:
    return uuid4().hex


class WorkspaceService:
    """Own private job paths and reserve public artifact paths safely."""

    def __init__(
        self,
        paths: WorkspacePaths,
        file_manager: FileManagerFacade,
        id_factory: Callable[[], str] = _new_job_id,
        max_collision_attempts: int = 1_000,
    ):
        if max_collision_attempts < 1:
            raise ValueError("max_collision_attempts must be positive")
        self.paths = paths
        self.file_manager = file_manager
        self.id_factory = id_factory
        self.max_collision_attempts = max_collision_attempts

    def initialize(self, output_dir: str | Path | None = None) -> WorkspacePaths:
        layout = self._layout(output_dir)
        for directory in (
            layout.state_dir,
            layout.jobs_dir,
            layout.cache_dir,
            layout.model_dir,
        ):
            self.file_manager.ensure_directory_exists(directory, private=True)
        self.file_manager.ensure_directory_exists(layout.output_dir)
        return layout

    def create_job(
        self,
        input_path: str | Path,
        *,
        output_dir: str | Path | None = None,
        job_id: JobId | None = None,
    ) -> Job:
        job = self.plan_job(input_path, output_dir=output_dir, job_id=job_id)
        self.initialize(job.output_dir)
        try:
            self.file_manager.reserve_directory(job.workspace_dir, private=True)
        except StorageAlreadyExistsError as exc:
            raise JobCollisionError(job.job_id.value, cause=exc) from exc
        return job

    def resume_job(
        self,
        input_path: str | Path,
        *,
        job_id: JobId,
        output_dir: str | Path | None = None,
    ) -> Job:
        """Resolve an existing private job without creating a replacement workspace."""
        job = self.plan_job(input_path, output_dir=output_dir, job_id=job_id)
        self.initialize(job.output_dir)
        if not job.workspace_dir.is_dir():
            raise JobNotFoundError(job.job_id.value)
        self.file_manager.ensure_directory_exists(job.workspace_dir, private=True)
        self._validate_job(job, require_workspace=True)
        return job

    def plan_job(
        self,
        input_path: str | Path,
        *,
        output_dir: str | Path | None = None,
        job_id: JobId | None = None,
    ) -> Job:
        """Resolve a valid job without creating or reserving any paths."""
        source = Path(input_path).expanduser().resolve(strict=False)
        if not source.is_file():
            raise InvalidInputError(source)

        layout = self._layout(output_dir)
        selected_id = job_id or JobId(self.id_factory())
        job = Job(
            job_id=selected_id,
            input_path=source,
            workspace_dir=layout.jobs_dir / selected_id.value,
            output_dir=layout.output_dir,
        )
        self._validate_job(job, require_workspace=False)
        return job

    def plan_artifact(
        self,
        job: Job,
        kind: ArtifactKind,
        *,
        filename: str | None = None,
        collision: CollisionPolicy = CollisionPolicy.RENAME,
    ) -> Artifact:
        """Choose an unreserved artifact candidate without mutating the filesystem."""
        self._validate_job(job, require_workspace=False)
        base_name = self._artifact_name(job, kind, filename)
        for index in range(1, self.max_collision_attempts + 1):
            candidate = job.output_dir / self._numbered_name(base_name, index)
            if not candidate.exists():
                return Artifact(job_id=job.job_id, kind=kind, path=candidate)
            if collision is CollisionPolicy.ERROR:
                raise ArtifactCollisionError(candidate)
        raise ArtifactCollisionError(
            job.output_dir / self._numbered_name(base_name, self.max_collision_attempts)
        )

    def reserve_artifact(
        self,
        job: Job,
        kind: ArtifactKind,
        *,
        filename: str | None = None,
        collision: CollisionPolicy = CollisionPolicy.RENAME,
    ) -> Artifact:
        self._validate_job(job, require_workspace=True)
        base_name = self._artifact_name(job, kind, filename)
        for index in range(1, self.max_collision_attempts + 1):
            candidate = job.output_dir / self._numbered_name(base_name, index)
            try:
                self.file_manager.reserve_file(candidate)
            except StorageAlreadyExistsError as exc:
                if collision is CollisionPolicy.ERROR:
                    raise ArtifactCollisionError(candidate, cause=exc) from exc
                continue
            return Artifact(job_id=job.job_id, kind=kind, path=candidate)
        raise ArtifactCollisionError(
            job.output_dir / self._numbered_name(base_name, self.max_collision_attempts)
        )

    def _layout(self, output_dir: str | Path | None) -> WorkspacePaths:
        if output_dir is None:
            return self.paths
        return self.paths.with_output(Path(output_dir))

    def _validate_job(self, job: Job, *, require_workspace: bool) -> None:
        expected_workspace = self.paths.jobs_dir / job.job_id.value
        if job.workspace_dir != expected_workspace or (
            require_workspace and not job.workspace_dir.is_dir()
        ):
            raise UnsafePathError("Job workspace is outside the private jobs directory")
        self.paths.with_output(job.output_dir)

    def _artifact_name(self, job: Job, kind: ArtifactKind, filename: str | None) -> str:
        if filename is None:
            stem = self.file_manager.sanitize_filename(job.input_path.stem).strip()
            return f"{stem}{kind.suffix}"
        if (
            not filename.strip()
            or self.file_manager.sanitize_filename(filename) != filename
        ):
            raise UnsafePathError("Artifact filename must be one safe filename")
        if Path(filename).suffix.lower() != kind.suffix:
            raise UnsafePathError(
                f"Artifact filename must use the {kind.suffix} extension"
            )
        return filename

    @staticmethod
    def _numbered_name(filename: str, index: int) -> str:
        if index == 1:
            return filename
        path = Path(filename)
        return f"{path.stem}-{index}{path.suffix}"
