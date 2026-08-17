from __future__ import annotations

from pathlib import Path

from echoflow.core.file_manager_facade import FileManagerFacade
from echoflow.core.ilogger import ILogger
from echoflow.core.measurements import ExecutionObserver
from echoflow.runner.inspector import RunnerInspector
from echoflow.runner.policy import RunnerPolicyPlanner
from echoflow.runner.topology import AcceleratorProbe, HardwareTopology
from echoflow.transcription.audio import DecodedAudio
from echoflow.transcription.capabilities import EngineCapabilityRegistry
from echoflow.transcription.checkpoint import RestoredCheckpoint
from echoflow.transcription.errors import CheckpointError, ResourceAdmissionError
from echoflow.transcription.executor import (
    AudioDecoder,
    AudioSegmenter,
    MediaProbe,
    SegmentCheckpointStore,
    SegmentTranscriptAssembler,
    SessionTranscriber,
    SpeakerDiarizer,
    TranscriptLanguageAttributor,
    TranscriptionExecutor,
)
from echoflow.transcription.models import (
    AudioSegmentWindow,
    EngineTranscript,
    TranscriptionJobPlan,
)
from echoflow.transcription.pipeline import OrderedSegmentPrefetcher
from echoflow.transcription.segmentation import MaterializedAudioSegment
from echoflow.transcription.storage import StorageAdmissionPolicy
from echoflow.transcription.strategy import StrategyCatalog, StrategyEvaluator
from echoflow.workspace.models import Job
from echoflow.workspace.service import WorkspaceService


class AdaptiveTranscriptionExecutor(TranscriptionExecutor):
    """Preserve sequential CPU execution and add bounded overlap for accelerators."""

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
        accelerator_probe: AcceleratorProbe,
        capability_registry: EngineCapabilityRegistry,
        strategy_catalog: StrategyCatalog,
        strategy_evaluator: StrategyEvaluator | None = None,
        checkpoint_store: SegmentCheckpointStore | None = None,
        storage_admission: StorageAdmissionPolicy | None = None,
        language_attributor: TranscriptLanguageAttributor | None = None,
        speaker_diarizer: SpeakerDiarizer | None = None,
        observer: ExecutionObserver | None = None,
    ):
        super().__init__(
            media_probe=media_probe,
            workspace_service=workspace_service,
            file_manager=file_manager,
            runner_inspector=runner_inspector,
            policy_planner=policy_planner,
            audio_decoder=audio_decoder,
            audio_segmenter=audio_segmenter,
            transcriber=transcriber,
            transcript_assembler=transcript_assembler,
            logger=logger,
            checkpoint_store=checkpoint_store,
            storage_admission=storage_admission,
            language_attributor=language_attributor,
            speaker_diarizer=speaker_diarizer,
            observer=observer,
        )
        self.accelerator_probe = accelerator_probe
        self.capability_registry = capability_registry
        self.strategy_catalog = strategy_catalog
        self.strategy_evaluator = strategy_evaluator or StrategyEvaluator()

    def _admit(self, plan: TranscriptionJobPlan) -> None:
        super()._admit(plan)
        if plan.engine.device == "cpu":
            return
        self._admit_accelerator(plan)

    def _admit_accelerator(self, plan: TranscriptionJobPlan) -> None:
        strategy = self.strategy_catalog.find_configuration(
            engine=plan.engine.engine,
            model=plan.engine.model,
            device=plan.engine.device,
            compute_type=plan.engine.compute_type,
        )
        if strategy is None:
            raise ResourceAdmissionError(
                "Selected accelerator strategy is no longer supported"
            )
        topology = HardwareTopology(
            resources=plan.runner,
            accelerators=self.accelerator_probe.inspect(),
        )
        capabilities = (
            self.capability_registry.inspect(plan.engine.engine, topology),
        )
        assessment = self.strategy_evaluator.assess(
            StrategyCatalog((strategy,), version=self.strategy_catalog.version),
            memory_budget_bytes=plan.resources.memory_budget_bytes,
            accelerators=topology.accelerators,
            capabilities=capabilities,
        )[0]
        if not assessment.feasible:
            raise ResourceAdmissionError(
                "Selected accelerator is unavailable or below its safe resource budget"
            )

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
        if plan.engine.device == "cpu":
            return super()._transcribe_segments(
                plan,
                decoded,
                windows,
                job,
                restored,
                allow_model_download=allow_model_download,
            )
        return self._transcribe_accelerated(
            plan,
            decoded,
            windows,
            job,
            restored,
            allow_model_download=allow_model_download,
        )

    def _transcribe_accelerated(
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

        remaining = windows[completed_count:]
        self.observer.record_value("segments.prefetch_depth", 1)
        job_logger = self.logger.bind(job_id=job.job_id.value)
        with OrderedSegmentPrefetcher(
            materialize=lambda window: self._materialize_segment(
                plan, decoded.path, window, job
            ),
            cleanup=self._cleanup_segment,
            prefetch_depth=1,
        ) as pipeline:
            for materialized in pipeline.iterate(remaining):
                window = materialized.window
                job_logger.info(
                    "transcription_segment_started",
                    segment_id=window.segment_id,
                    segment_index=window.index,
                    segment_count=len(windows),
                    prefetched=True,
                )
                try:
                    with self.observer.span("segment.transcribe"):
                        result = session.transcribe(materialized.path)
                finally:
                    self._cleanup_segment(materialized)
                with self.observer.span("checkpoint.write"):
                    self.checkpoint_store.save_segment(
                        job, plan, windows, window, result
                    )
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

    def _materialize_segment(
        self,
        plan: TranscriptionJobPlan,
        audio_path: Path,
        window: AudioSegmentWindow,
        job: Job,
    ) -> MaterializedAudioSegment:
        with self.observer.span("segment.materialize"):
            return self.audio_segmenter.materialize(
                audio_path,
                window,
                plan.decoder,
                job.workspace_dir,
            )

    def _cleanup_segment(self, segment: MaterializedAudioSegment) -> None:
        with self.observer.span("segment.cleanup"):
            self.audio_segmenter.cleanup(segment)
