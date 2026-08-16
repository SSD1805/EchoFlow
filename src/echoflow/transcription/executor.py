import json
from contextlib import suppress
from pathlib import Path
from typing import Protocol

from echoflow.core.file_manager_facade import FileManagerFacade
from echoflow.core.ilogger import ILogger
from echoflow.media.errors import InputChangedError
from echoflow.media.models import MediaInfo
from echoflow.runner.inspector import RunnerInspector
from echoflow.runner.policy import RunnerPolicyPlanner
from echoflow.transcription.audio import DecodedAudio
from echoflow.transcription.checkpoint import RestoredCheckpoint
from echoflow.transcription.errors import CheckpointError, ResourceAdmissionError
from echoflow.transcription.models import (
    AudioSegmentWindow,
    CanonicalTranscript,
    CpuEngineConfiguration,
    DecodeConfiguration,
    EngineProvenance,
    EngineTranscript,
    SegmentationConfiguration,
    TranscriptionExecutionResult,
    TranscriptionJobPlan,
    TranscriptSource,
)
from echoflow.transcription.segmentation import MaterializedAudioSegment
from echoflow.workspace.models import Artifact, ArtifactKind, Job
from echoflow.workspace.service import WorkspaceService


class MediaProbe(Protocol):
    def probe(self, input_path: str | Path) -> MediaInfo: ...


class AudioDecoder(Protocol):
    def decode(
        self,
        media: MediaInfo,
        configuration: DecodeConfiguration,
        workspace_dir: Path,
    ) -> DecodedAudio: ...

    def cleanup(self, audio: DecodedAudio) -> None: ...


class AudioSegmenter(Protocol):
    def plan(
        self,
        audio_path: Path,
        decoder: DecodeConfiguration,
        configuration: SegmentationConfiguration,
    ) -> tuple[AudioSegmentWindow, ...]: ...

    def materialize(
        self,
        audio_path: Path,
        window: AudioSegmentWindow,
        decoder: DecodeConfiguration,
        workspace_dir: Path,
    ) -> MaterializedAudioSegment: ...

    def cleanup(self, segment: MaterializedAudioSegment) -> None: ...


class TranscriptionSession(Protocol):
    engine_version: str

    def transcribe(self, audio_path: Path) -> EngineTranscript: ...


class SessionTranscriber(Protocol):
    def open_session(
        self,
        configuration: CpuEngineConfiguration,
        *,
        allow_model_download: bool,
        detected_language: str | None = None,
    ) -> TranscriptionSession: ...


class SegmentTranscriptAssembler(Protocol):
    def assemble(
        self,
        results: list[tuple[AudioSegmentWindow, EngineTranscript]],
    ) -> EngineTranscript: ...


class SegmentCheckpointStore(Protocol):
    def initialize(
        self,
        job: Job,
        plan: TranscriptionJobPlan,
        windows: tuple[AudioSegmentWindow, ...],
    ) -> None: ...

    def restore(
        self,
        job: Job,
        plan: TranscriptionJobPlan,
        windows: tuple[AudioSegmentWindow, ...],
    ) -> RestoredCheckpoint: ...

    def save_segment(
        self,
        job: Job,
        plan: TranscriptionJobPlan,
        windows: tuple[AudioSegmentWindow, ...],
        window: AudioSegmentWindow,
        result: EngineTranscript,
    ) -> None: ...

    def clear(self, job: Job) -> None: ...


class _NoCheckpointStore:
    def initialize(
        self,
        job: Job,
        plan: TranscriptionJobPlan,
        windows: tuple[AudioSegmentWindow, ...],
    ) -> None:
        del job, plan, windows

    def restore(
        self,
        job: Job,
        plan: TranscriptionJobPlan,
        windows: tuple[AudioSegmentWindow, ...],
    ) -> RestoredCheckpoint:
        del job, plan, windows
        raise CheckpointError("Checkpoint resume is not configured")

    def save_segment(
        self,
        job: Job,
        plan: TranscriptionJobPlan,
        windows: tuple[AudioSegmentWindow, ...],
        window: AudioSegmentWindow,
        result: EngineTranscript,
    ) -> None:
        del job, plan, windows, window, result

    def clear(self, job: Job) -> None:
        del job


class TranscriptionExecutor:
    """Claim a plan, checkpoint deterministic segments, and publish JSON."""

    def __init__(
        self,
        *,
        media_probe: MediaProbe,
        workspace_service: WorkspaceService,
        file_manager: FileManagerFacade,
        runner_inspector: RunnerInspector,
        policy_planner: RunnerPolicyPlanner,
        audio_decoder: AudioDecoder,
        audio_segmenter: AudioSegmenter,
        transcriber: SessionTranscriber,
        transcript_assembler: SegmentTranscriptAssembler,
        logger: ILogger,
        checkpoint_store: SegmentCheckpointStore | None = None,
    ):
        self.media_probe = media_probe
        self.workspace_service = workspace_service
        self.file_manager = file_manager
        self.runner_inspector = runner_inspector
        self.policy_planner = policy_planner
        self.audio_decoder = audio_decoder
        self.audio_segmenter = audio_segmenter
        self.transcriber = transcriber
        self.transcript_assembler = transcript_assembler
        self.logger = logger
        self.checkpoint_store = checkpoint_store or _NoCheckpointStore()

    def execute(
        self,
        plan: TranscriptionJobPlan,
        *,
        allow_model_download: bool = False,
        resume: bool = False,
    ) -> TranscriptionExecutionResult:
        self._admit(plan)
        verified_media = self.media_probe.probe(plan.job.input_path)
        if verified_media.input != plan.media.input:
            raise InputChangedError(
                "Input changed between transcription planning and execution"
            )

        if resume:
            job = self.workspace_service.resume_job(
                plan.job.input_path,
                output_dir=plan.job.output_dir,
                job_id=plan.job.job_id,
            )
        else:
            job = self.workspace_service.create_job(
                plan.job.input_path,
                output_dir=plan.job.output_dir,
                job_id=plan.job.job_id,
            )
        artifact = self.workspace_service.reserve_artifact(
            job, ArtifactKind.CANONICAL_JSON
        )
        decoded: DecodedAudio | None = None
        try:
            decoded = self.audio_decoder.decode(
                plan.media, plan.decoder, job.workspace_dir
            )
            windows = self.audio_segmenter.plan(
                decoded.path, plan.decoder, plan.segmentation
            )
            restored = self._checkpoint_state(job, plan, windows, resume=resume)
            self._admit(plan)
            engine_result = self._transcribe_segments(
                plan,
                decoded,
                windows,
                job,
                restored,
                allow_model_download=allow_model_download,
            )
            transcript = self._transcript(plan, engine_result)
            document = json.dumps(
                transcript.to_dict(),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            self.file_manager.save_file(f"{document}\n".encode(), artifact.path)
            self._clear_completed_checkpoints(job)
        except BaseException:
            self._release_failed_artifact(artifact)
            raise
        finally:
            if decoded is not None:
                self.audio_decoder.cleanup(decoded)
        return TranscriptionExecutionResult(job, artifact, transcript)

    def _checkpoint_state(
        self,
        job: Job,
        plan: TranscriptionJobPlan,
        windows: tuple[AudioSegmentWindow, ...],
        *,
        resume: bool,
    ) -> RestoredCheckpoint:
        job_logger = self.logger.bind(job_id=job.job_id.value)
        if not resume:
            self.checkpoint_store.initialize(job, plan, windows)
            return RestoredCheckpoint((), None, None)
        restored = self.checkpoint_store.restore(job, plan, windows)
        job_logger.info(
            "transcription_resume_validated",
            completed_segment_count=len(restored.completed),
            segment_count=len(windows),
        )
        return restored

    def _transcribe_segments(
        self,
        plan: TranscriptionJobPlan,
        decoded: DecodedAudio,
        windows: tuple[AudioSegmentWindow, ...],
        job: Job,
        restored: RestoredCheckpoint,
        *,
        allow_model_download: bool,
    ) -> EngineTranscript:
        completed_count = len(restored.completed)
        allowed_download = allow_model_download and completed_count == 0
        if restored.detected_language is None:
            session = self.transcriber.open_session(
                plan.engine,
                allow_model_download=allowed_download,
            )
        else:
            session = self.transcriber.open_session(
                plan.engine,
                allow_model_download=allowed_download,
                detected_language=restored.detected_language,
            )
        if (
            restored.engine_version is not None
            and session.engine_version != restored.engine_version
        ):
            raise CheckpointError(
                "Installed transcription engine version does not match checkpoints"
            )

        results = list(restored.completed)
        job_logger = self.logger.bind(job_id=job.job_id.value)
        for window in windows[completed_count:]:
            job_logger.info(
                "transcription_segment_started",
                segment_id=window.segment_id,
                segment_index=window.index,
                segment_count=len(windows),
            )
            materialized = self.audio_segmenter.materialize(
                decoded.path,
                window,
                plan.decoder,
                job.workspace_dir,
            )
            try:
                result = session.transcribe(materialized.path)
            finally:
                self.audio_segmenter.cleanup(materialized)
            self.checkpoint_store.save_segment(job, plan, windows, window, result)
            results.append((window, result))
            job_logger.info(
                "transcription_segment_completed",
                segment_id=window.segment_id,
                segment_index=window.index,
                segment_count=len(windows),
                checkpointed=True,
            )
        return self.transcript_assembler.assemble(results)

    def _clear_completed_checkpoints(self, job: Job) -> None:
        try:
            self.checkpoint_store.clear(job)
        except Exception as exc:
            self.logger.warning(
                "transcription_checkpoint_cleanup_failed",
                job_id=job.job_id.value,
                exception_type=type(exc).__name__,
            )

    def _admit(self, plan: TranscriptionJobPlan) -> None:
        current_resources = self.runner_inspector.inspect()
        current_policy = self.policy_planner.plan(
            current_resources, plan.policy.profile
        )
        if (
            not plan.resources.fits_memory_budget
            or plan.resources.estimated_peak_memory_bytes
            > current_policy.memory_budget_bytes
        ):
            raise ResourceAdmissionError(
                "Available memory is below the selected model's safe execution budget"
            )
        if plan.engine.cpu_threads > current_policy.cpu_threads:
            raise ResourceAdmissionError(
                "Available CPU capacity changed; create a new transcription plan"
            )

    def _release_failed_artifact(self, artifact: Artifact) -> None:
        with suppress(Exception):
            self.file_manager.delete_file(artifact.path)

    @staticmethod
    def _transcript(
        plan: TranscriptionJobPlan, result: EngineTranscript
    ) -> CanonicalTranscript:
        return CanonicalTranscript(
            job_id=plan.job.job_id.value,
            source=TranscriptSource.from_media(plan.media),
            profile=plan.policy.profile,
            provisional=plan.policy.provisional,
            decode_strategy=plan.decoder.strategy,
            engine=EngineProvenance.from_engine(plan.engine, result.engine_version),
            detected_language=result.language,
            language_probability=result.language_probability,
            segments=result.segments,
        )
