import math
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from echoflow.media.models import MediaInfo
from echoflow.runner.models import ExecutionPolicy, ProcessingProfile, RunnerResources
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
    model_revision: str | None = None

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
        if self.model_revision is not None and not self.model_revision.strip():
            raise ValueError("model_revision cannot be empty")

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
            "model_revision": self.model_revision,
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


@dataclass(frozen=True, slots=True)
class RecognizedSegment:
    index: int
    start_seconds: float
    end_seconds: float
    text: str
    average_log_probability: float | None = None
    no_speech_probability: float | None = None

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError("segment index cannot be negative")
        if (
            not math.isfinite(self.start_seconds)
            or not math.isfinite(self.end_seconds)
            or self.start_seconds < 0
            or self.end_seconds < self.start_seconds
        ):
            raise ValueError("segment timestamps must be finite and ordered")
        if not self.text.strip():
            raise ValueError("segment text cannot be empty")
        if self.average_log_probability is not None and not math.isfinite(
            self.average_log_probability
        ):
            raise ValueError("average_log_probability must be finite")
        if self.no_speech_probability is not None and not (
            math.isfinite(self.no_speech_probability)
            and 0 <= self.no_speech_probability <= 1
        ):
            raise ValueError("no_speech_probability must be between 0 and 1")

    @property
    def segment_id(self) -> str:
        return f"segment-{self.index:06d}"

    def to_dict(self) -> dict[str, object]:
        return {
            "segment_id": self.segment_id,
            "index": self.index,
            "start_seconds": self.start_seconds,
            "end_seconds": self.end_seconds,
            "text": self.text,
            "average_log_probability": self.average_log_probability,
            "no_speech_probability": self.no_speech_probability,
        }


@dataclass(frozen=True, slots=True)
class EngineTranscript:
    segments: tuple[RecognizedSegment, ...]
    language: str | None
    language_probability: float | None
    engine_version: str

    def __post_init__(self) -> None:
        if self.language is not None and not self.language.strip():
            raise ValueError("language cannot be empty")
        if self.language_probability is not None and not (
            math.isfinite(self.language_probability)
            and 0 <= self.language_probability <= 1
        ):
            raise ValueError("language_probability must be between 0 and 1")
        if not self.engine_version:
            raise ValueError("engine_version cannot be empty")


@dataclass(frozen=True, slots=True)
class TranscriptSource:
    sha256: str
    size_bytes: int
    modified_ns: int
    container_format: str
    duration_seconds: float
    audio_stream_index: int

    def __post_init__(self) -> None:
        if len(self.sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.sha256
        ):
            raise ValueError("source sha256 must be a lowercase 64-character digest")
        if self.size_bytes < 1:
            raise ValueError("source size_bytes must be positive")
        if self.modified_ns < 0:
            raise ValueError("source modified_ns cannot be negative")
        if not self.container_format:
            raise ValueError("source container_format cannot be empty")
        if not math.isfinite(self.duration_seconds) or self.duration_seconds <= 0:
            raise ValueError("source duration_seconds must be finite and positive")
        if self.audio_stream_index < 0:
            raise ValueError("source audio_stream_index cannot be negative")

    @classmethod
    def from_media(cls, media: MediaInfo) -> "TranscriptSource":
        return cls(
            sha256=media.input.sha256,
            size_bytes=media.input.size_bytes,
            modified_ns=media.input.modified_ns,
            container_format=media.container_format,
            duration_seconds=media.duration_seconds,
            audio_stream_index=media.primary_audio_stream_index,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "modified_ns": self.modified_ns,
            "container_format": self.container_format,
            "duration_seconds": self.duration_seconds,
            "audio_stream_index": self.audio_stream_index,
        }


@dataclass(frozen=True, slots=True)
class EngineProvenance:
    name: str
    package_version: str
    model: str
    model_revision: str | None
    device: str
    compute_type: str
    cpu_threads: int
    beam_size: int
    requested_language: str | None

    def __post_init__(self) -> None:
        for name in ("name", "package_version", "model", "device", "compute_type"):
            if not getattr(self, name):
                raise ValueError(f"{name} cannot be empty")
        if self.model_revision is not None and not self.model_revision.strip():
            raise ValueError("model_revision cannot be empty")
        if self.cpu_threads < 1:
            raise ValueError("cpu_threads must be positive")
        if self.beam_size < 1:
            raise ValueError("beam_size must be positive")

    @classmethod
    def from_engine(
        cls, configuration: CpuEngineConfiguration, package_version: str
    ) -> "EngineProvenance":
        return cls(
            name=configuration.engine,
            package_version=package_version,
            model=configuration.model,
            model_revision=configuration.model_revision,
            device=configuration.device,
            compute_type=configuration.compute_type,
            cpu_threads=configuration.cpu_threads,
            beam_size=configuration.beam_size,
            requested_language=configuration.language,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "package_version": self.package_version,
            "model": self.model,
            "model_revision": self.model_revision,
            "device": self.device,
            "compute_type": self.compute_type,
            "cpu_threads": self.cpu_threads,
            "beam_size": self.beam_size,
            "requested_language": self.requested_language,
        }


@dataclass(frozen=True, slots=True)
class CanonicalTranscript:
    job_id: str
    source: TranscriptSource
    profile: ProcessingProfile
    provisional: bool
    decode_strategy: DecodeStrategy
    engine: EngineProvenance
    detected_language: str | None
    language_probability: float | None
    segments: tuple[RecognizedSegment, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported transcript schema version")
        if not self.job_id:
            raise ValueError("job_id cannot be empty")
        if self.provisional != (self.profile is ProcessingProfile.SCREENING):
            raise ValueError("provisional flag must match the processing profile")
        if self.detected_language is not None and not self.detected_language.strip():
            raise ValueError("detected_language cannot be empty")
        if self.language_probability is not None and not (
            math.isfinite(self.language_probability)
            and 0 <= self.language_probability <= 1
        ):
            raise ValueError("language_probability must be between 0 and 1")
        if tuple(segment.index for segment in self.segments) != tuple(
            range(len(self.segments))
        ):
            raise ValueError("segment indices must be contiguous and zero-based")

    @property
    def text(self) -> str:
        return " ".join(segment.text.strip() for segment in self.segments)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "source": self.source.to_dict(),
            "profile": self.profile.value,
            "provisional": self.provisional,
            "decode_strategy": self.decode_strategy.value,
            "engine": self.engine.to_dict(),
            "detected_language": self.detected_language,
            "language_probability": self.language_probability,
            "text": self.text,
            "segments": [segment.to_dict() for segment in self.segments],
        }


@dataclass(frozen=True, slots=True)
class TranscriptionExecutionResult:
    job: Job
    artifact: Artifact
    transcript: CanonicalTranscript

    def __post_init__(self) -> None:
        if self.job.job_id != self.artifact.job_id:
            raise ValueError("job and artifact IDs must match")
        if self.job.job_id.value != self.transcript.job_id:
            raise ValueError("job and transcript IDs must match")

    def to_dict(self) -> dict[str, object]:
        return {
            "dry_run": False,
            "paths_reserved": True,
            "job": self.job.to_dict(),
            "artifact": self.artifact.to_dict(),
            "transcript": self.transcript.to_dict(),
        }
