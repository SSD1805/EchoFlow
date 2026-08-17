import json
from contextlib import suppress
from dataclasses import replace
from pathlib import Path
from typing import Protocol

from echoflow.core.file_manager_facade import FileManagerFacade
from echoflow.core.ilogger import ILogger
from echoflow.core.measurements import ExecutionObserver, NoOpExecutionObserver
from echoflow.media.errors import InputChangedError
from echoflow.media.models import MediaInfo
from echoflow.runner.inspector import RunnerInspector
from echoflow.runner.policy import RunnerPolicyPlanner
from echoflow.transcription.audio import DecodedAudio
from echoflow.transcription.checkpoint import RestoredCheckpoint
from echoflow.transcription.errors import CheckpointError, ResourceAdmissionError
from echoflow.transcription.models import (
    AudioSegmentWindow,
    AutoLanguageMode,
    CanonicalTranscript,
    CpuEngineConfiguration,
    DecodeConfiguration,
    EngineProvenance,
    EngineTranscript,
    LanguageAttributionProvenance,
    LanguageSpan,
    RecognizedSegment,
    SegmentationConfiguration,
    TranscriptionExecutionResult,
    TranscriptionJobPlan,
    TranscriptSource,
)
from echoflow.transcription.segmentation import MaterializedAudioSegment
from echoflow.transcription.storage import StorageAdmissionPolicy, StorageAllocation
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


class TranscriptLanguageAttributor(Protocol):
    @property
    def provenance(self) -> LanguageAttributionProvenance: ...

    def attribute(self, text: str) -> tuple[LanguageSpan, ...]: ...


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
        storage_admission: StorageAdmissionPolicy | None = None,
        language_attributor: TranscriptLanguageAttributor | None = None,
        observer: ExecutionObserver | None = None,
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
        self.storage_admission = storage_admission
        self.language_attributor = language_attributor
        self.observer = observer or NoOpExecutionObserver()

    def execute(
        self,
        plan: TranscriptionJobPlan,
        *,
        allow_model_download: bool = False,
        resume: bool = False,
    ) -> TranscriptionExecutionResult:
        with self.observer.span("admission.initial"):
            self._admit(plan)
        with self.observer.span("media.verify"):
            verified_media = self.media_probe.probe(plan.job.input_path)
        if verified_media.input != plan.media.input:
            raise InputChangedError(
                "Input changed between transcription planning and execution"
            )
        with self.observer.span("admission.storage"):
            self._admit_storage(plan)

        with self.observer.span("workspace.claim"):
            job = self._claim_job(plan, resume=resume)
            artifact = self.workspace_service.reserve_artifact(
                job, ArtifactKind.CANONICAL_JSON
            )

        decoded: DecodedAudio | None = None
        try:
            with self.observer.span("decode"):
                decoded = self.audio_decoder.decode(
                    plan.media, plan.decoder, job.workspace_dir
                )
            with self.observer.span("segmentation.plan"):
                windows = self.audio_segmenter.plan(
                    decoded.path, plan.decoder, plan.segmentation
                )
            self.observer.record_value("segments.total", len(windows))
            with self.observer.span("checkpoint.prepare"):
                restored = self._checkpoint_state(job, plan, windows, resume=resume)
            self.observer.record_value("segments.restored", len(restored.completed))
            self.observer.record_value("segments.completed", len(restored.completed))
            with self.observer.span("admission.pre_model"):
                self._admit(plan)
            engine_result = self._transcribe_segments(
                plan,
                decoded,
                windows,
                job,
                restored,
                allow_model_download=allow_model_download,
            )
            with self.observer.span("transcript.canonicalize"):
                transcript = self._transcript(plan, engine_result)
                document = json.dumps(
                    transcript.to_dict(),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            with self.observer.span("artifact.write"):
                self.file_manager.save_file(f"{document}\n".encode(), artifact.path)
            with self.observer.span("checkpoint.cleanup"):
                self._clear_completed_checkpoints(job)
        except BaseException:
            self._release_failed_artifact(artifact)
            raise
        finally:
            if decoded is not None:
                with self.observer.span("decode.cleanup"):
                    self.audio_decoder.cleanup(decoded)
        return TranscriptionExecutionResult(job, artifact, transcript)

    def _claim_job(self, plan: TranscriptionJobPlan, *, resume: bool) -> Job:
        if resume:
            return self.workspace_service.resume_job(
                plan.job.input_path,
                output_dir=plan.job.output_dir,
                job_id=plan.job.job_id,
            )
        return self.workspace_service.create_job(
            plan.job.input_path,
            output_dir=plan.job.output_dir,
            job_id=plan.job.job_id,
        )

    def _checkpoint_state(
        self,
        job: Job,
        plan: TranscriptionJobPlan,
        windows: tuple[AudioSegmentWindow, ...],
        *,
        resume: bool,
    ) -> RestoredCheckpoint:
        if not resume:
            self.checkpoint_store.initialize(job, plan, windows)
            return RestoredCheckpoint((), None, None)
        restored = self.checkpoint_store.restore(job, plan, windows)
        self.logger.bind(job_id=job.job_id.value).info(
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
        results = list(restored.completed)
        if completed_count == len(windows):
            self.logger.bind(job_id=job.job_id.value).info(
                "transcription_resume_recognition_complete",
                segment_count=len(windows),
            )
            with self.observer.span("transcript.assemble"):
                return self.transcript_assembler.assemble(results)

        allowed_download = allow_model_download and completed_count == 0
        with self.observer.span("engine.open"):
            session = self._open_session(
                plan,
                restored,
                allow_model_download=allowed_download,
            )
        if (
            restored.engine_version is not None
            and session.engine_version != restored.engine_version
        ):
            raise CheckpointError(
                "Installed transcription engine version does not match checkpoints"
            )

        job_logger = self.logger.bind(job_id=job.job_id.value)
        for window in windows[completed_count:]:
            job_logger.info(
                "transcription_segment_started",
                segment_id=window.segment_id,
                segment_index=window.index,
                segment_count=len(windows),
            )
            with self.observer.span("segment.materialize"):
                materialized = self.audio_segmenter.materialize(
                    decoded.path,
                    window,
                    plan.decoder,
                    job.workspace_dir,
                )
            try:
                with self.observer.span("segment.transcribe"):
                    result = session.transcribe(materialized.path)
            finally:
                with self.observer.span("segment.cleanup"):
                    self.audio_segmenter.cleanup(materialized)
            with self.observer.span("checkpoint.write"):
                self.checkpoint_store.save_segment(job, plan, windows, window, result)
            results.append((window, result))
            self.observer.record_value("segments.completed", len(results))
            job_logger.info(
                "transcription_segment_completed",
                segment_id=window.segment_id,
                segment_index=window.index,
                segment_count=len(windows),
                checkpointed=True,
            )
        with self.observer.span("transcript.assemble"):
            return self.transcript_assembler.assemble(results)

    def _open_session(
        self,
        plan: TranscriptionJobPlan,
        restored: RestoredCheckpoint,
        *,
        allow_model_download: bool,
    ) -> TranscriptionSession:
        if (
            plan.engine.auto_language_mode is AutoLanguageMode.JOB_LATCHED
            and restored.detected_language is not None
        ):
            return self.transcriber.open_session(
                plan.engine,
                allow_model_download=allow_model_download,
                detected_language=restored.detected_language,
            )
        return self.transcriber.open_session(
            plan.engine,
            allow_model_download=allow_model_download,
        )

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

    def _admit_storage(self, plan: TranscriptionJobPlan) -> None:
        if self.storage_admission is None:
            return
        self.storage_admission.admit(
            (
                StorageAllocation(
                    plan.job.workspace_dir,
                    plan.resources.private_workspace_bytes,
                ),
                StorageAllocation(
                    plan.job.output_dir,
                    plan.resources.public_output_bytes,
                ),
            )
        )

    def _release_failed_artifact(self, artifact: Artifact) -> None:
        with suppress(Exception):
            self.file_manager.delete_file(artifact.path)

    def _transcript(
        self, plan: TranscriptionJobPlan, result: EngineTranscript
    ) -> CanonicalTranscript:
        segments, attribution = self._attribute_languages(result.segments)
        detected_languages: list[str] = []
        for segment in segments:
            for span in segment.language_spans:
                if span.language not in detected_languages:
                    detected_languages.append(span.language)
        if not detected_languages:
            for segment in segments:
                if (
                    segment.detected_language is not None
                    and segment.detected_language not in detected_languages
                ):
                    detected_languages.append(segment.detected_language)
        detected_language = (
            detected_languages[0] if len(detected_languages) == 1 else None
        )
        language_probability = (
            result.language_probability
            if plan.engine.auto_language_mode is AutoLanguageMode.JOB_LATCHED
            and detected_language is not None
            and detected_language == result.language
            else None
        )
        return CanonicalTranscript(
            job_id=plan.job.job_id.value,
            source=TranscriptSource.from_media(plan.media),
            profile=plan.policy.profile,
            provisional=plan.policy.provisional,
            decode_strategy=plan.decoder.strategy,
            engine=EngineProvenance.from_engine(plan.engine, result.engine_version),
            detected_language=detected_language,
            language_probability=language_probability,
            detected_languages=tuple(detected_languages),
            language_attribution=attribution,
            segments=segments,
        )

    def _attribute_languages(
        self, segments: tuple[RecognizedSegment, ...]
    ) -> tuple[tuple[RecognizedSegment, ...], LanguageAttributionProvenance | None]:
        if self.language_attributor is None or not segments:
            return segments, None

        document_text, bounds = self._language_attribution_document(segments)
        document_spans = self.language_attributor.attribute(document_text)
        attributed = tuple(
            self._project_language_spans(segment, start, end, document_spans)
            for segment, (start, end) in zip(segments, bounds, strict=True)
        )
        return attributed, self.language_attributor.provenance

    @staticmethod
    def _language_attribution_document(
        segments: tuple[RecognizedSegment, ...],
    ) -> tuple[str, tuple[tuple[int, int], ...]]:
        parts: list[str] = []
        bounds: list[tuple[int, int]] = []
        cursor = 0
        for index, segment in enumerate(segments):
            if index:
                parts.append("\n")
                cursor += 1
            start = cursor
            parts.append(segment.text)
            cursor += len(segment.text)
            bounds.append((start, cursor))
        return "".join(parts), tuple(bounds)

    @staticmethod
    def _project_language_spans(
        segment: RecognizedSegment,
        document_start: int,
        document_end: int,
        document_spans: tuple[LanguageSpan, ...],
    ) -> RecognizedSegment:
        projected: list[LanguageSpan] = []
        for span in document_spans:
            local = TranscriptionExecutor._project_language_span(
                segment,
                document_start,
                document_end,
                span,
            )
            if local is not None:
                projected.append(local)
        languages = {span.language for span in projected}
        language = next(iter(languages)) if len(languages) == 1 else None
        return replace(
            segment,
            language=language,
            language_spans=tuple(projected),
        )

    @staticmethod
    def _project_language_span(
        segment: RecognizedSegment,
        document_start: int,
        document_end: int,
        span: LanguageSpan,
    ) -> LanguageSpan | None:
        overlap_start = max(span.start_char, document_start)
        overlap_end = min(span.end_char, document_end)
        if overlap_start >= overlap_end:
            return None

        start = overlap_start - document_start
        end = overlap_end - document_start
        while start < end and segment.text[start].isspace():
            start += 1
        while end > start and segment.text[end - 1].isspace():
            end -= 1
        if start >= end:
            return None
        return LanguageSpan(
            start_char=start,
            end_char=end,
            language=span.language,
            confidence=span.confidence,
        )
