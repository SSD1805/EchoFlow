from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from echoflow.media.models import MediaInfo
from echoflow.runner.models import ExecutionPolicy, RunnerResources
from echoflow.workspace.models import Artifact, Job


class DecodeStrategy(StrEnum):
    DIRECT = "direct"
    FFMPEG_NORMALIZE = "ffmpeg_normalize"


@dataclass(frozen=True, slots=True)
class DecodeConfiguration:
    strategy: DecodeStrategy
    output_codec: str
    sample_rate_hz: int
    channels: int

    def __post_init__(self) -> None:
        if not self.output_codec:
            raise ValueError("output_codec cannot be empty")
        if self.sample_rate_hz < 1:
            raise ValueError("sample_rate_hz must be positive")
        if self.channels < 1:
            raise ValueError("channels must be positive")

    def to_dict(self) -> dict[str, object]:
        return {
            "strategy": self.strategy.value,
            "output_codec": self.output_codec,
            "sample_rate_hz": self.sample_rate_hz,
            "channels": self.channels,
        }


@dataclass(frozen=True, slots=True)
class CpuEngineConfiguration:
    engine: str
    model: str
    device: str
    compute_type: str
    cpu_threads: int
    beam_size: int
    language: str | None
    model_cache_path: Path

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "model_cache_path",
            self.model_cache_path.expanduser().resolve(strict=False),
        )
        for name in ("engine", "model", "device", "compute_type"):
            if not getattr(self, name):
                raise ValueError(f"{name} cannot be empty")
        if self.cpu_threads < 1:
            raise ValueError("cpu_threads must be positive")
        if self.beam_size < 1:
            raise ValueError("beam_size must be positive")

    def to_dict(self) -> dict[str, object]:
        return {
            "engine": self.engine,
            "model": self.model,
            "device": self.device,
            "compute_type": self.compute_type,
            "cpu_threads": self.cpu_threads,
            "beam_size": self.beam_size,
            "language": self.language,
            "model_cache_path": str(self.model_cache_path),
        }


@dataclass(frozen=True, slots=True)
class ResourceEstimate:
    private_workspace_bytes: int
    public_output_bytes: int
    model_cache_bytes: int
    estimated_peak_memory_bytes: int
    memory_budget_bytes: int
    fits_memory_budget: bool
    heuristic: bool = True

    def __post_init__(self) -> None:
        for name in (
            "private_workspace_bytes",
            "public_output_bytes",
            "model_cache_bytes",
            "estimated_peak_memory_bytes",
            "memory_budget_bytes",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} cannot be negative")

    @property
    def total_disk_bytes(self) -> int:
        return (
            self.private_workspace_bytes
            + self.public_output_bytes
            + self.model_cache_bytes
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "private_workspace_bytes": self.private_workspace_bytes,
            "public_output_bytes": self.public_output_bytes,
            "model_cache_bytes": self.model_cache_bytes,
            "total_disk_bytes": self.total_disk_bytes,
            "estimated_peak_memory_bytes": self.estimated_peak_memory_bytes,
            "memory_budget_bytes": self.memory_budget_bytes,
            "fits_memory_budget": self.fits_memory_budget,
            "heuristic": self.heuristic,
        }


@dataclass(frozen=True, slots=True)
class TranscriptionJobPlan:
    job: Job
    artifact: Artifact
    media: MediaInfo
    runner: RunnerResources
    policy: ExecutionPolicy
    engine: CpuEngineConfiguration
    decoder: DecodeConfiguration
    resources: ResourceEstimate
    warnings: tuple[str, ...]
    schema_version: int = 1
    paths_reserved: bool = False

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported job-plan schema version")
        if self.paths_reserved:
            raise ValueError("a dry-run plan cannot claim reserved paths")
        if self.job.job_id != self.artifact.job_id:
            raise ValueError("job and artifact IDs must match")
        if self.job.input_path != self.media.input.path:
            raise ValueError("job and media input paths must match")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "dry_run": True,
            "paths_reserved": self.paths_reserved,
            "job": self.job.to_dict(),
            "artifact": self.artifact.to_dict(),
            "media": self.media.to_dict(),
            "runner": self.runner.to_dict(),
            "policy": self.policy.to_dict(),
            "engine": self.engine.to_dict(),
            "decoder": self.decoder.to_dict(),
            "resources": self.resources.to_dict(),
            "warnings": list(self.warnings),
        }
