import math
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from echoflow.media.models import MediaInfo
from echoflow.runner.models import ExecutionPolicy, ProcessingProfile, RunnerResources
from echoflow.transcription.speaker_models import (
    DiarizationProvenance,
    SpeakerTurn,
)
from echoflow.workspace.models import Artifact, Job


class DecodeStrategy(StrEnum):
    DIRECT = "direct"
    FFMPEG_NORMALIZE = "ffmpeg_normalize"


class AutoLanguageMode(StrEnum):
    """How an automatically detected ASR language is applied across work units."""

    JOB_LATCHED = "job_latched_v1"
    NATIVE_MULTILINGUAL = "native_multilingual_v1"


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
class SegmentationConfiguration:
    """Versioned application-owned segmentation policy.

    Version 1 is intentionally sequential and non-overlapping. Overlap requires
    deterministic reconciliation semantics before it can become a supported
    execution choice.
    """

    segment_duration_seconds: int = 600
    overlap_seconds: int = 0
    concurrency: int = 1
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported segmentation schema version")
        if self.segment_duration_seconds < 1:
            raise ValueError("segment_duration_seconds must be positive")
        if self.overlap_seconds != 0:
            raise ValueError(
                "segmentation overlap is not supported by schema version 1"
            )
        if self.concurrency != 1:
            raise ValueError(
                "segmentation concurrency must be one for schema version 1"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "segment_duration_seconds": self.segment_duration_seconds,
            "overlap_seconds": self.overlap_seconds,
            "concurrency": self.concurrency,
        }


@dataclass(frozen=True, slots=True)
class AudioSegmentWindow:
    """One exact source-relative frame interval in canonical decoded audio."""

    index: int
    start_frame: int
    end_frame: int
    sample_rate_hz: int

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError("audio segment index cannot be negative")
        if self.start_frame < 0:
            raise ValueError("audio segment start_frame cannot be negative")
        if self.end_frame <= self.start_frame:
            raise ValueError("audio segment end_frame must be greater than start_frame")
        if self.sample_rate_hz < 1:
            raise ValueError("audio segment sample_rate_hz must be positive")

    @property
    def segment_id(self) -> str:
        return f"audio-{self.index:06d}"

    @property
    def start_seconds(self) -> float:
        return self.start_frame / self.sample_rate_hz

    @property
    def end_seconds(self) -> float:
        return self.end_frame / self.sample_rate_hz

    @property
    def duration_seconds(self) -> float:
        return (self.end_frame - self.start_frame) / self.sample_rate_hz

    def to_dict(self) -> dict[str, object]:
        return {
            "segment_id": self.segment_id,
            "index": self.index,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "sample_rate_hz": self.sample_rate_hz,
            "start_seconds": self.start_seconds,
            "end_seconds": self.end_seconds,
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
    auto_language_mode: AutoLanguageMode = AutoLanguageMode.JOB_LATCHED

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
        if self.language is not None and not self.language.strip():
            raise ValueError("language cannot be empty")
        if self.model_revision is not None and not self.model_revision.strip():
            raise ValueError("model_revision cannot be empty")

    def to_dict(self) -> dict[str, object]:
        document: dict[str, object] = {
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
        if self.auto_language_mode is AutoLanguageMode.NATIVE_MULTILINGUAL:
            document["auto_language_mode"] = self.auto_language_mode.value
        return document


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
    segmentation: SegmentationConfiguration = field(
        default_factory=SegmentationConfiguration
    )
    schema_version: int = 1
    paths_reserved: bool = False

    def __post_init__(self) -> None:
        if self.schema_version not in (1, 2):
            raise ValueError("unsupported job-plan schema version")
        if self.paths_reserved:
            raise ValueError("a dry-run plan cannot claim reserved paths")
        if self.job.job_id != self.artifact.job_id:
            raise ValueError("job and artifact IDs must match")
        if self.job.input_path != self.media.input.path:
            raise ValueError("job and media input paths must match")
        if self.segmentation.concurrency != 1:
            raise ValueError("job plan requires sequential segmentation")
        if (
            self.schema_version == 1
            and self.engine.auto_language_mode is not AutoLanguageMode.JOB_LATCHED
        ):
            raise ValueError(
                "job-plan schema version 1 requires legacy language latching"
            )
        if (
            self.schema_version == 2
            and self.engine.auto_language_mode
            is not AutoLanguageMode.NATIVE_MULTILINGUAL
        ):
            raise ValueError(
                "job-plan schema version 2 requires per-segment language detection"
            )

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
            "segmentation": self.segmentation.to_dict(),
            "resources": self.resources.to_dict(),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class LanguageSpan:
    """One text-relative language attribution inside a recognized segment."""

    start_char: int
    end_char: int
    language: str
    confidence: float | None = None

    def __post_init__(self) -> None:
        if self.start_char < 0 or self.end_char <= self.start_char:
            raise ValueError("language span character offsets must be ordered")
        if not self.language.strip():
            raise ValueError("language span language cannot be empty")
        if self.confidence is not None and not (
            math.isfinite(self.confidence) and 0 <= self.confidence <= 1
        ):
            raise ValueError("language span confidence must be between 0 and 1")

    def to_dict(self) -> dict[str, object]:
        return {
            "start_char": self.start_char,
            "end_char": self.end_char,
            "language": self.language,
            "confidence": self.confidence,
        }


@dataclass(frozen=True, slots=True)
class LanguageAttributionProvenance:
    provider: str
    package_version: str
    mode: str

    def __post_init__(self) -> None:
        for name in ("provider", "package_version", "mode"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} cannot be empty")

    def to_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "package_version": self.package_version,
            "mode": self.mode,
        }


@dataclass(frozen=True, slots=True)
class RecognizedSegment:
    index: int
    start_seconds: float
    end_seconds: float
    text: str
    average_log_probability: float | None = None
    no_speech_probability: float | None = None
    detected_language: str | None = None
    language_probability: float | None = None
    language: str | None = None
    language_spans: tuple[LanguageSpan, ...] = ()
    speaker_ref: str | None = None

    def __post_init__(self) -> None:
        self._validate_identity_and_text()
        self._validate_probabilities()
        self._validate_language_metadata()
        self._validate_language_spans()

    def _validate_identity_and_text(self) -> None:
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

    def _validate_probabilities(self) -> None:
        if self.average_log_probability is not None and not math.isfinite(
            self.average_log_probability
        ):
            raise ValueError("average_log_probability must be finite")
        if self.no_speech_probability is not None and not (
            math.isfinite(self.no_speech_probability)
            and 0 <= self.no_speech_probability <= 1
        ):
            raise ValueError("no_speech_probability must be between 0 and 1")
        if self.language_probability is not None and not (
            math.isfinite(self.language_probability)
            and 0 <= self.language_probability <= 1
        ):
            raise ValueError("language_probability must be between 0 and 1")

    def _validate_language_metadata(self) -> None:
        if self.detected_language is not None and not self.detected_language.strip():
            raise ValueError("detected_language cannot be empty")
        if self.language is not None and not self.language.strip():
            raise ValueError("language cannot be empty")
        if self.speaker_ref is not None and not self.speaker_ref.strip():
            raise ValueError("speaker_ref cannot be empty")

    def _validate_language_spans(self) -> None:
        previous_end = 0
        for span in self.language_spans:
            if span.end_char > len(self.text):
                raise ValueError("language span exceeds segment text")
            if span.start_char < previous_end:
                raise ValueError("language spans cannot overlap")
            previous_end = span.end_char
        languages = {span.language for span in self.language_spans}
        if self.language is not None and languages and languages != {self.language}:
            raise ValueError("segment language must match uniform language spans")
        if len(languages) > 1 and self.language is not None:
            raise ValueError("mixed-language segments cannot have one language label")

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
            "detected_language": self.detected_language,
            "language_probability": self.language_probability,
            "language": self.language,
            "language_spans": [span.to_dict() for span in self.language_spans],
            "speaker_ref": self.speaker_ref,
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
    auto_language_mode: AutoLanguageMode = AutoLanguageMode.JOB_LATCHED

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
            auto_language_mode=configuration.auto_language_mode,
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
            "auto_language_mode": self.auto_language_mode.value,
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
    schema_version: int = 2
    detected_languages: tuple[str, ...] = ()
    language_attribution: LanguageAttributionProvenance | None = None
    speaker_turns: tuple[SpeakerTurn, ...] = ()
    diarization: DiarizationProvenance | None = None

    def __post_init__(self) -> None:
        self._validate_core_contract()
        self._validate_diarization_contract()
        derived_languages = self._derived_languages()
        if not self.detected_languages:
            object.__setattr__(self, "detected_languages", derived_languages)
        elif derived_languages != self.detected_languages:
            raise ValueError(
                "detected_languages must match transcript language evidence"
            )
        self._validate_language_summary()

    def _validate_core_contract(self) -> None:
        if self.schema_version not in {2, 3}:
            raise ValueError("unsupported transcript schema version")
        if not self.job_id:
            raise ValueError("job_id cannot be empty")
        if self.provisional != (self.profile is ProcessingProfile.SCREENING):
            raise ValueError("provisional flag must match the processing profile")
        if tuple(segment.index for segment in self.segments) != tuple(
            range(len(self.segments))
        ):
            raise ValueError("segment indices must be contiguous and zero-based")

    def _validate_diarization_contract(self) -> None:
        if self.schema_version == 2:
            if self.diarization is not None or self.speaker_turns:
                raise ValueError(
                    "speaker diarization requires transcript schema version 3"
                )
            return
        if self.diarization is None:
            raise ValueError("schema version 3 requires diarization provenance")
        if any(
            turn.end_seconds > self.source.duration_seconds + 1e-6
            for turn in self.speaker_turns
        ):
            raise ValueError("speaker turn exceeds source duration")
        known_speakers = {turn.speaker_ref for turn in self.speaker_turns}
        for segment in self.segments:
            if (
                segment.speaker_ref is not None
                and segment.speaker_ref not in known_speakers
            ):
                raise ValueError("segment speaker_ref must come from diarization turns")

    def _derived_languages(self) -> tuple[str, ...]:
        languages: list[str] = []
        for segment in self.segments:
            for span in segment.language_spans:
                if span.language not in languages:
                    languages.append(span.language)
        if languages:
            return tuple(languages)
        for segment in self.segments:
            if (
                segment.detected_language is not None
                and segment.detected_language not in languages
            ):
                languages.append(segment.detected_language)
        return tuple(languages)

    def _validate_language_summary(self) -> None:
        if self.detected_language is not None and not self.detected_language.strip():
            raise ValueError("detected_language cannot be empty")
        if self.language_probability is not None and not (
            math.isfinite(self.language_probability)
            and 0 <= self.language_probability <= 1
        ):
            raise ValueError("language_probability must be between 0 and 1")
        if len(self.detected_languages) > 1 and self.detected_language is not None:
            raise ValueError(
                "mixed-language transcripts cannot have one detected_language"
            )
        if (
            self.detected_language is not None
            and self.detected_languages
            and self.detected_language != self.detected_languages[0]
        ):
            raise ValueError(
                "detected_language must match transcript language evidence"
            )
        if self.detected_language is None and self.language_probability is not None:
            raise ValueError("language_probability requires detected_language")

    @property
    def text(self) -> str:
        return " ".join(segment.text.strip() for segment in self.segments)

    def to_dict(self) -> dict[str, object]:
        document: dict[str, object] = {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "source": self.source.to_dict(),
            "profile": self.profile.value,
            "provisional": self.provisional,
            "decode_strategy": self.decode_strategy.value,
            "engine": self.engine.to_dict(),
            "detected_language": self.detected_language,
            "detected_languages": list(self.detected_languages),
            "language_probability": self.language_probability,
            "language_attribution": (
                None
                if self.language_attribution is None
                else self.language_attribution.to_dict()
            ),
            "text": self.text,
            "segments": [segment.to_dict() for segment in self.segments],
        }
        if self.schema_version == 3:
            document["diarization"] = (
                self.diarization.to_dict() if self.diarization else None
            )
            document["speaker_turns"] = [turn.to_dict() for turn in self.speaker_turns]
        return document


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
