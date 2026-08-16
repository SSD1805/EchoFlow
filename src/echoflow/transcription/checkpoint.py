from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import cast

from echoflow.core.file_manager_facade import FileManagerFacade
from echoflow.runner.models import ProcessingProfile
from echoflow.transcription.errors import CheckpointError
from echoflow.transcription.models import (
    AudioSegmentWindow,
    CpuEngineConfiguration,
    DecodeConfiguration,
    DecodeStrategy,
    EngineTranscript,
    RecognizedSegment,
    SegmentationConfiguration,
    TranscriptionJobPlan,
    TranscriptSource,
)
from echoflow.workspace.models import Job

_CHECKPOINT_SCHEMA_VERSION = 1
_MANIFEST_NAME = "manifest.json"
_MAX_CHECKPOINT_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class RestoredCheckpoint:
    """Validated completed work that can be skipped during resume."""

    completed: tuple[tuple[AudioSegmentWindow, EngineTranscript], ...]
    detected_language: str | None
    engine_version: str | None


@dataclass(frozen=True, slots=True)
class ResumeEngineSettings:
    """Engine semantics persisted without a machine-local model-cache path."""

    engine: str
    model: str
    device: str
    compute_type: str
    cpu_threads: int
    beam_size: int
    language: str | None
    model_revision: str | None

    def configuration(self, model_cache_path: Path) -> CpuEngineConfiguration:
        return CpuEngineConfiguration(
            engine=self.engine,
            model=self.model,
            device=self.device,
            compute_type=self.compute_type,
            cpu_threads=self.cpu_threads,
            beam_size=self.beam_size,
            language=self.language,
            model_cache_path=model_cache_path,
            model_revision=self.model_revision,
        )


@dataclass(frozen=True, slots=True)
class ResumeSettings:
    """Typed immutable execution semantics recovered from a valid manifest."""

    source: TranscriptSource
    profile: ProcessingProfile
    provisional: bool
    engine: ResumeEngineSettings
    decoder: DecodeConfiguration
    segmentation: SegmentationConfiguration
    model_cache_bytes: int
    estimated_peak_memory_bytes: int
    job_plan_schema_version: int

    def __post_init__(self) -> None:
        if self.provisional != (self.profile is ProcessingProfile.SCREENING):
            raise ValueError("checkpoint provisional flag does not match profile")
        if self.model_cache_bytes < 0:
            raise ValueError("checkpoint model_cache_bytes cannot be negative")
        if self.estimated_peak_memory_bytes < 1:
            raise ValueError("checkpoint estimated_peak_memory_bytes must be positive")
        if self.job_plan_schema_version != 1:
            raise ValueError("checkpoint job-plan schema version is unsupported")


class LocalCheckpointStore:
    """Persist resumable transcript fragments inside one private local job."""

    def __init__(
        self,
        file_manager: FileManagerFacade,
        *,
        max_checkpoint_bytes: int = _MAX_CHECKPOINT_BYTES,
    ):
        if max_checkpoint_bytes < 1:
            raise ValueError("max_checkpoint_bytes must be positive")
        self.file_manager = file_manager
        self.max_checkpoint_bytes = max_checkpoint_bytes

    def initialize(
        self,
        job: Job,
        plan: TranscriptionJobPlan,
        windows: tuple[AudioSegmentWindow, ...],
    ) -> None:
        checkpoint_dir = self._checkpoint_dir(job)
        self.file_manager.ensure_directory_exists(checkpoint_dir, private=True)
        manifest_path = checkpoint_dir / _MANIFEST_NAME
        if self.file_manager.file_exists(manifest_path):
            raise CheckpointError(
                "Private checkpoint state already exists for this job"
            )

        contract = self._contract(plan, windows)
        manifest = {
            "schema_version": _CHECKPOINT_SCHEMA_VERSION,
            "job_id": job.job_id.value,
            "contract_sha256": self._digest(contract),
            "contract": contract,
        }
        self.file_manager.save_file(
            self._canonical_bytes(manifest), manifest_path, private=True
        )

    def resume_settings(self, job: Job) -> ResumeSettings:
        """Read the original immutable execution semantics for a restart."""
        _, contract = self._validated_stored_manifest(job)
        return self._settings_from_contract(contract)

    def restore(
        self,
        job: Job,
        plan: TranscriptionJobPlan,
        windows: tuple[AudioSegmentWindow, ...],
    ) -> RestoredCheckpoint:
        expected_contract = self._contract(plan, windows)
        expected_digest = self._digest(expected_contract)
        stored_digest, stored_contract = self._validated_stored_manifest(job)
        if stored_digest != expected_digest or stored_contract != expected_contract:
            raise CheckpointError(
                "Private checkpoint does not match the current transcription contract"
            )

        checkpoint_dir = self._checkpoint_dir(job)
        expected_by_name = {
            f"{window.segment_id}.json": window for window in windows
        }
        segment_files = []
        for candidate in self.file_manager.list_files(checkpoint_dir, (".json",)):
            if candidate.name == _MANIFEST_NAME:
                continue
            if candidate.name not in expected_by_name:
                raise CheckpointError("Private checkpoint state contains an unknown segment")
            segment_files.append(candidate)

        restored: list[tuple[AudioSegmentWindow, EngineTranscript]] = []
        for candidate in sorted(segment_files):
            window = expected_by_name[candidate.name]
            restored.append(
                (
                    window,
                    self._restore_segment(
                        candidate,
                        job_id=job.job_id.value,
                        contract_digest=expected_digest,
                        window=window,
                    ),
                )
            )

        indices = tuple(window.index for window, _ in restored)
        if indices and indices != tuple(range(indices[-1] + 1)):
            raise CheckpointError(
                "Completed private checkpoints are not a contiguous prefix"
            )

        versions = {result.engine_version for _, result in restored}
        if len(versions) > 1:
            raise CheckpointError(
                "Completed private checkpoints use inconsistent engine versions"
            )
        engine_version = next(iter(versions), None)
        detected_language = next(
            (
                result.language
                for _, result in restored
                if result.language is not None
            ),
            None,
        )
        return RestoredCheckpoint(
            completed=tuple(restored),
            detected_language=detected_language,
            engine_version=engine_version,
        )

    def save_segment(
        self,
        job: Job,
        plan: TranscriptionJobPlan,
        windows: tuple[AudioSegmentWindow, ...],
        window: AudioSegmentWindow,
        result: EngineTranscript,
    ) -> None:
        checkpoint_dir = self._checkpoint_dir(job)
        manifest_path = checkpoint_dir / _MANIFEST_NAME
        if not self.file_manager.file_exists(manifest_path):
            raise CheckpointError("Private checkpoint manifest is missing")
        if window not in windows:
            raise CheckpointError("Segment is outside the current checkpoint contract")

        contract_digest = self._digest(self._contract(plan, windows))
        result_document = self._result_to_dict(result)
        envelope = {
            "schema_version": _CHECKPOINT_SCHEMA_VERSION,
            "job_id": job.job_id.value,
            "contract_sha256": contract_digest,
            "segment_id": window.segment_id,
            "window": self._window_contract(window),
            "result_sha256": self._digest(result_document),
            "result": result_document,
        }
        destination = checkpoint_dir / f"{window.segment_id}.json"
        if self.file_manager.file_exists(destination):
            raise CheckpointError("Completed segment checkpoint already exists")
        self.file_manager.save_file(
            self._canonical_bytes(envelope), destination, private=True
        )

    def clear(self, job: Job) -> None:
        checkpoint_dir = self._checkpoint_dir(job)
        if not checkpoint_dir.is_dir():
            return
        for candidate in self.file_manager.list_files(checkpoint_dir):
            self.file_manager.delete_file(candidate)

    @staticmethod
    def _checkpoint_dir(job: Job) -> Path:
        return job.workspace_dir / "checkpoints"

    @classmethod
    def _contract(
        cls,
        plan: TranscriptionJobPlan,
        windows: tuple[AudioSegmentWindow, ...],
    ) -> dict[str, object]:
        engine = plan.engine.to_dict()
        engine.pop("model_cache_path")
        return {
            "checkpoint_schema_version": _CHECKPOINT_SCHEMA_VERSION,
            "job_plan_schema_version": plan.schema_version,
            "source": TranscriptSource.from_media(plan.media).to_dict(),
            "profile": plan.policy.profile.value,
            "provisional": plan.policy.provisional,
            "engine": engine,
            "decoder": plan.decoder.to_dict(),
            "segmentation": plan.segmentation.to_dict(),
            "resources": {
                "model_cache_bytes": plan.resources.model_cache_bytes,
                "estimated_peak_memory_bytes": (
                    plan.resources.estimated_peak_memory_bytes
                ),
            },
            "windows": [cls._window_contract(window) for window in windows],
        }

    @staticmethod
    def _window_contract(window: AudioSegmentWindow) -> dict[str, int | str]:
        return {
            "segment_id": window.segment_id,
            "index": window.index,
            "start_frame": window.start_frame,
            "end_frame": window.end_frame,
            "sample_rate_hz": window.sample_rate_hz,
        }

    def _validated_stored_manifest(
        self, job: Job
    ) -> tuple[str, dict[str, object]]:
        manifest_path = self._checkpoint_dir(job) / _MANIFEST_NAME
        if not self.file_manager.file_exists(manifest_path):
            raise CheckpointError("No private checkpoint state exists for this job")
        manifest = self._read_object(manifest_path)
        try:
            schema_version = int(cast("int", manifest["schema_version"]))
            stored_job_id = str(manifest["job_id"])
            stored_digest = str(manifest["contract_sha256"])
            stored_contract = cast("dict[str, object]", manifest["contract"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CheckpointError("Private checkpoint manifest is malformed") from exc

        if schema_version != _CHECKPOINT_SCHEMA_VERSION:
            raise CheckpointError("Private checkpoint schema version is unsupported")
        if stored_job_id != job.job_id.value:
            raise CheckpointError("Private checkpoint belongs to a different job")
        if self._digest(stored_contract) != stored_digest:
            raise CheckpointError("Private checkpoint manifest integrity check failed")
        return stored_digest, stored_contract

    @staticmethod
    def _settings_from_contract(contract: dict[str, object]) -> ResumeSettings:
        try:
            source = cast("dict[str, object]", contract["source"])
            engine = cast("dict[str, object]", contract["engine"])
            decoder = cast("dict[str, object]", contract["decoder"])
            segmentation = cast("dict[str, object]", contract["segmentation"])
            resources = cast("dict[str, object]", contract["resources"])
            return ResumeSettings(
                source=TranscriptSource(
                    sha256=str(source["sha256"]),
                    size_bytes=int(cast("int", source["size_bytes"])),
                    modified_ns=int(cast("int", source["modified_ns"])),
                    container_format=str(source["container_format"]),
                    duration_seconds=float(cast("float", source["duration_seconds"])),
                    audio_stream_index=int(
                        cast("int", source["audio_stream_index"])
                    ),
                ),
                profile=ProcessingProfile(str(contract["profile"])),
                provisional=bool(contract["provisional"]),
                engine=ResumeEngineSettings(
                    engine=str(engine["engine"]),
                    model=str(engine["model"]),
                    device=str(engine["device"]),
                    compute_type=str(engine["compute_type"]),
                    cpu_threads=int(cast("int", engine["cpu_threads"])),
                    beam_size=int(cast("int", engine["beam_size"])),
                    language=(
                        None
                        if engine.get("language") is None
                        else str(engine["language"])
                    ),
                    model_revision=(
                        None
                        if engine.get("model_revision") is None
                        else str(engine["model_revision"])
                    ),
                ),
                decoder=DecodeConfiguration(
                    strategy=DecodeStrategy(str(decoder["strategy"])),
                    output_codec=str(decoder["output_codec"]),
                    sample_rate_hz=int(cast("int", decoder["sample_rate_hz"])),
                    channels=int(cast("int", decoder["channels"])),
                ),
                segmentation=SegmentationConfiguration(
                    segment_duration_seconds=int(
                        cast("int", segmentation["segment_duration_seconds"])
                    ),
                    overlap_seconds=int(
                        cast("int", segmentation["overlap_seconds"])
                    ),
                    concurrency=int(cast("int", segmentation["concurrency"])),
                    schema_version=int(cast("int", segmentation["schema_version"])),
                ),
                model_cache_bytes=int(cast("int", resources["model_cache_bytes"])),
                estimated_peak_memory_bytes=int(
                    cast("int", resources["estimated_peak_memory_bytes"])
                ),
                job_plan_schema_version=int(
                    cast("int", contract["job_plan_schema_version"])
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CheckpointError("Private checkpoint contract is malformed") from exc

    def _restore_segment(
        self,
        path: Path,
        *,
        job_id: str,
        contract_digest: str,
        window: AudioSegmentWindow,
    ) -> EngineTranscript:
        envelope = self._read_object(path)
        try:
            schema_version = int(cast("int", envelope["schema_version"]))
            stored_job_id = str(envelope["job_id"])
            stored_contract_digest = str(envelope["contract_sha256"])
            segment_id = str(envelope["segment_id"])
            stored_window = cast("dict[str, object]", envelope["window"])
            result_digest = str(envelope["result_sha256"])
            result_document = cast("dict[str, object]", envelope["result"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CheckpointError("Private segment checkpoint is malformed") from exc

        if schema_version != _CHECKPOINT_SCHEMA_VERSION:
            raise CheckpointError("Private segment checkpoint schema is unsupported")
        if stored_job_id != job_id or stored_contract_digest != contract_digest:
            raise CheckpointError("Private segment checkpoint contract does not match")
        if segment_id != window.segment_id or stored_window != self._window_contract(window):
            raise CheckpointError("Private segment checkpoint window does not match")
        if self._digest(result_document) != result_digest:
            raise CheckpointError("Private segment checkpoint integrity check failed")
        return self._result_from_dict(result_document)

    def _read_object(self, path: Path) -> dict[str, object]:
        metadata = self.file_manager.get_file_metadata(path)
        if metadata["size"] < 2 or metadata["size"] > self.max_checkpoint_bytes:
            raise CheckpointError("Private checkpoint file size is outside safe bounds")
        try:
            parsed = json.loads(self.file_manager.read_file(path))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise CheckpointError("Private checkpoint JSON is invalid") from exc
        if not isinstance(parsed, dict):
            raise CheckpointError("Private checkpoint JSON must be an object")
        return cast("dict[str, object]", parsed)

    @staticmethod
    def _result_to_dict(result: EngineTranscript) -> dict[str, object]:
        return {
            "engine_version": result.engine_version,
            "language": result.language,
            "language_probability": result.language_probability,
            "segments": [segment.to_dict() for segment in result.segments],
        }

    @staticmethod
    def _result_from_dict(document: dict[str, object]) -> EngineTranscript:
        try:
            raw_segments = cast("list[dict[str, object]]", document["segments"])
            segments = tuple(
                RecognizedSegment(
                    index=int(cast("int", raw["index"])),
                    start_seconds=float(cast("float", raw["start_seconds"])),
                    end_seconds=float(cast("float", raw["end_seconds"])),
                    text=str(raw["text"]),
                    average_log_probability=(
                        None
                        if raw.get("average_log_probability") is None
                        else float(cast("float", raw["average_log_probability"]))
                    ),
                    no_speech_probability=(
                        None
                        if raw.get("no_speech_probability") is None
                        else float(cast("float", raw["no_speech_probability"]))
                    ),
                )
                for raw in raw_segments
            )
            language_value = document.get("language")
            probability_value = document.get("language_probability")
            return EngineTranscript(
                segments=segments,
                language=None if language_value is None else str(language_value),
                language_probability=(
                    None
                    if probability_value is None
                    else float(cast("float", probability_value))
                ),
                engine_version=str(document["engine_version"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CheckpointError("Private segment result is malformed") from exc

    @staticmethod
    def _canonical_bytes(value: object) -> bytes:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")

    @classmethod
    def _digest(cls, value: object) -> str:
        return sha256(cls._canonical_bytes(value)).hexdigest()
