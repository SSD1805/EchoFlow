import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from echoflow.workspace.errors import UnsafePathError

_JOB_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def _normalized(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _overlaps(first: Path, second: Path) -> bool:
    return (
        first == second or first.is_relative_to(second) or second.is_relative_to(first)
    )


class CollisionPolicy(StrEnum):
    RENAME = "rename"
    ERROR = "error"


class ArtifactKind(StrEnum):
    CANONICAL_JSON = "json"
    TEXT = "txt"
    SUBRIP = "srt"
    WEBVTT = "vtt"

    @property
    def suffix(self) -> str:
        return f".{self.value}"


@dataclass(frozen=True, slots=True)
class JobId:
    value: str

    def __post_init__(self) -> None:
        if not _JOB_ID_PATTERN.fullmatch(self.value):
            raise UnsafePathError(
                "Job ID must contain 1-64 lowercase letters, digits, underscores, or hyphens"
            )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class WorkspacePaths:
    state_dir: Path
    cache_dir: Path
    model_dir: Path
    output_dir: Path

    def __post_init__(self) -> None:
        for field_name in ("state_dir", "cache_dir", "model_dir", "output_dir"):
            object.__setattr__(self, field_name, _normalized(getattr(self, field_name)))
        if not self.model_dir.is_relative_to(self.cache_dir):
            raise UnsafePathError(
                "The model directory must be inside the private cache"
            )
        if _overlaps(self.output_dir, self.state_dir) or _overlaps(
            self.output_dir, self.cache_dir
        ):
            raise UnsafePathError(
                "The public output directory must be separate from private state and cache"
            )

    @property
    def jobs_dir(self) -> Path:
        return self.state_dir / "jobs"

    def with_output(self, output_dir: Path) -> "WorkspacePaths":
        return WorkspacePaths(
            state_dir=self.state_dir,
            cache_dir=self.cache_dir,
            model_dir=self.model_dir,
            output_dir=output_dir,
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "state_dir": str(self.state_dir),
            "cache_dir": str(self.cache_dir),
            "model_dir": str(self.model_dir),
            "output_dir": str(self.output_dir),
        }


@dataclass(frozen=True, slots=True)
class Job:
    job_id: JobId
    input_path: Path
    workspace_dir: Path
    output_dir: Path

    def __post_init__(self) -> None:
        for field_name in ("input_path", "workspace_dir", "output_dir"):
            object.__setattr__(self, field_name, _normalized(getattr(self, field_name)))

    def to_dict(self) -> dict[str, str]:
        return {
            "job_id": self.job_id.value,
            "input_path": str(self.input_path),
            "workspace_dir": str(self.workspace_dir),
            "output_dir": str(self.output_dir),
        }


@dataclass(frozen=True, slots=True)
class Artifact:
    job_id: JobId
    kind: ArtifactKind
    path: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _normalized(self.path))

    def to_dict(self) -> dict[str, str]:
        return {
            "job_id": self.job_id.value,
            "kind": self.kind.value,
            "path": str(self.path),
        }
