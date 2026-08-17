import math
from dataclasses import replace
from pathlib import Path
from typing import Protocol

from echoflow.media.models import MediaInfo
from echoflow.media.selection import AudioStreamSelector
from echoflow.runner.inspector import RunnerInspector
from echoflow.runner.models import ExecutionPolicy, ModelTier, ProcessingProfile
from echoflow.runner.policy import RunnerPolicyPlanner
from echoflow.runner.topology import HardwareTopology, HardwareTopologyInspector
from echoflow.transcription.capabilities import (
    EngineCapabilities,
    EngineCapabilityRegistry,
)
from echoflow.transcription.checkpoint import ResumeSettings
from echoflow.transcription.errors import CheckpointError, ResourceAdmissionError
from echoflow.transcription.models import (
    AutoLanguageMode,
    CpuEngineConfiguration,
    DecodeConfiguration,
    DecodeStrategy,
    ResourceEstimate,
    SegmentationConfiguration,
    TranscriptionJobPlan,
    TranscriptSource,
)
from echoflow.transcription.strategy import (
    StrategyAssessment,
    StrategyCatalog,
    StrategyDefinition,
    StrategyEvaluator,
    faster_whisper_cpu_catalog,
)
from echoflow.workspace.models import ArtifactKind, Job, JobId
from echoflow.workspace.service import WorkspaceService

_MIB = 1024**2
_TARGET_SAMPLE_RATE_HZ = 16_000
_TARGET_CHANNELS = 1
_TARGET_BYTES_PER_SAMPLE = 2


class MediaProbe(Protocol):
    def probe(self, input_path: str | Path) -> MediaInfo: ...


class ResumeCheckpointStore(Protocol):
    def resume_settings(self, job: Job) -> ResumeSettings: ...


class TranscriptionJobPlanner:
    """Compose media, topology, and engine decisions into one immutable plan."""

    def __init__(
        self,
        *,
        media_probe: MediaProbe,
        workspace_service: WorkspaceService,
        runner_inspector: RunnerInspector,
        policy_planner: RunnerPolicyPlanner,
        strategy_catalog: StrategyCatalog | None = None,
        strategy_evaluator: StrategyEvaluator | None = None,
        topology_inspector: HardwareTopologyInspector | None = None,
        capability_registry: EngineCapabilityRegistry | None = None,
        audio_stream_selector: AudioStreamSelector | None = None,
        model_revision: str | None = None,
        checkpoint_store: ResumeCheckpointStore | None = None,
    ):
        self.media_probe = media_probe
        self.workspace_service = workspace_service
        self.runner_inspector = runner_inspector
        self.policy_planner = policy_planner
        self.strategy_catalog = strategy_catalog or faster_whisper_cpu_catalog()
        self.strategy_evaluator = strategy_evaluator or StrategyEvaluator()
        self.topology_inspector = topology_inspector
        self.capability_registry = capability_registry or EngineCapabilityRegistry()
        self.audio_stream_selector = audio_stream_selector or AudioStreamSelector()
        self.model_revision = model_revision
        self.checkpoint_store = checkpoint_store

    def plan(
        self,
        input_path: str | Path,
        *,
        output_dir: str | Path | None = None,
        profile: ProcessingProfile = ProcessingProfile.BALANCED,
        strategy_id: str | None = None,
        audio_stream_index: int | None = None,
        job_id: JobId | None = None,
    ) -> TranscriptionJobPlan:
        job = self.workspace_service.plan_job(
            input_path, output_dir=output_dir, job_id=job_id
        )
        media = self.audio_stream_selector.select(
            self.media_probe.probe(job.input_path),
            requested_index=audio_stream_index,
        )
        topology = self._topology()
        runner = topology.resources
        policy = self.policy_planner.plan(runner, profile)
        assessments = self._assess(topology, policy)
        selected = self.strategy_evaluator.select(
            assessments,
            profile=profile,
            requested_strategy_id=strategy_id,
        )
        engine = self._engine(policy, selected.strategy)
        decoder = self._decoder(media)
        segmentation = SegmentationConfiguration()
        artifact = self.workspace_service.plan_artifact(
            job, ArtifactKind.CANONICAL_JSON
        )
        resources = self._resources(
            media,
            decoder,
            segmentation,
            selected.strategy.model_cache_bytes,
            selected.peak_system_memory_bytes,
            policy,
        )
        warnings = ["paths_are_unreserved"]
        if policy.provisional:
            warnings.append("screening_output_is_provisional")
        if selected.strategy.accelerated:
            warnings.extend(
                ("accelerator_strategy_selected", "accelerator_estimate_is_heuristic")
            )
        return TranscriptionJobPlan(
            job=job,
            artifact=artifact,
            media=media,
            runner=runner,
            policy=policy,
            engine=engine,
            decoder=decoder,
            resources=resources,
            warnings=tuple(warnings),
            segmentation=segmentation,
            schema_version=2,
        )

    def plan_resume(
        self,
        input_path: str | Path,
        *,
        job_id: JobId,
        output_dir: str | Path | None = None,
    ) -> TranscriptionJobPlan:
        """Restore the original execution contract and re-admit it locally."""
        if self.checkpoint_store is None:
            raise CheckpointError("Checkpoint resume is not configured")

        job = self.workspace_service.plan_job(
            input_path, output_dir=output_dir, job_id=job_id
        )
        settings = self.checkpoint_store.resume_settings(job)
        media = self.audio_stream_selector.select(
            self.media_probe.probe(job.input_path),
            requested_index=settings.source.audio_stream_index,
        )
        if TranscriptSource.from_media(media) != settings.source:
            raise CheckpointError("Input does not match the interrupted job checkpoint")

        topology = self._topology()
        runner = topology.resources
        current_policy = self.policy_planner.plan(runner, settings.profile)
        if settings.engine.cpu_threads > current_policy.cpu_threads:
            raise ResourceAdmissionError(
                "Current CPU capacity is below the interrupted job requirement"
            )
        if settings.estimated_peak_memory_bytes > current_policy.memory_budget_bytes:
            raise ResourceAdmissionError(
                "Current memory budget is below the interrupted job requirement"
            )

        policy = ExecutionPolicy(
            profile=settings.profile,
            provisional=settings.provisional,
            cpu_threads=settings.engine.cpu_threads,
            memory_budget_bytes=current_policy.memory_budget_bytes,
            recommended_model_tier=(
                ModelTier.COMPACT
                if settings.profile is ProcessingProfile.SCREENING
                else ModelTier.STRATEGY_SPECIFIC
            ),
            constraints=current_policy.constraints,
        )
        engine = settings.engine.configuration(
            self.workspace_service.paths.model_dir / "faster-whisper"
        )
        engine = replace(
            engine,
            auto_language_mode=(
                AutoLanguageMode.JOB_LATCHED
                if settings.job_plan_schema_version == 1
                else AutoLanguageMode.NATIVE_MULTILINGUAL
            ),
        )
        self._admit_resume_accelerator(engine, topology, policy)
        artifact = self.workspace_service.plan_artifact(
            job, ArtifactKind.CANONICAL_JSON
        )
        resources = self._resources(
            media,
            settings.decoder,
            settings.segmentation,
            settings.model_cache_bytes,
            settings.estimated_peak_memory_bytes,
            policy,
        )
        warnings = ["paths_are_unreserved", "resume_contract_restored"]
        if settings.provisional:
            warnings.append("screening_output_is_provisional")
        if engine.device != "cpu":
            warnings.append("accelerator_strategy_restored")
        return TranscriptionJobPlan(
            job=job,
            artifact=artifact,
            media=media,
            runner=runner,
            policy=policy,
            engine=engine,
            decoder=settings.decoder,
            resources=resources,
            warnings=tuple(warnings),
            segmentation=settings.segmentation,
            schema_version=settings.job_plan_schema_version,
        )

    def assess_strategies(
        self, *, profile: ProcessingProfile = ProcessingProfile.BALANCED
    ) -> tuple[dict[str, object], ...]:
        """Describe all strategies against fresh CPU, RAM, and accelerator evidence."""

        topology = self._topology()
        policy = self.policy_planner.plan(topology.resources, profile)
        assessments = self._assess(topology, policy)
        feasible = tuple(
            assessment for assessment in assessments if assessment.feasible
        )
        selected = (
            self.strategy_evaluator.select(feasible, profile=profile)
            if feasible
            else None
        )
        return tuple(
            {
                **assessment.to_dict(),
                "recommended": assessment is selected,
                "cpu_threads": policy.cpu_threads,
                "profile": profile.value,
            }
            for assessment in assessments
        )

    def _topology(self) -> HardwareTopology:
        if self.topology_inspector is not None:
            return self.topology_inspector.inspect()
        return HardwareTopology(resources=self.runner_inspector.inspect())

    def _capabilities(
        self, topology: HardwareTopology
    ) -> tuple[EngineCapabilities, ...]:
        return tuple(
            self.capability_registry.inspect(engine, topology)
            for engine in self.strategy_catalog.engines
        )

    def _assess(
        self, topology: HardwareTopology, policy: ExecutionPolicy
    ) -> tuple[StrategyAssessment, ...]:
        return self.strategy_evaluator.assess(
            self.strategy_catalog,
            memory_budget_bytes=policy.memory_budget_bytes,
            accelerators=topology.accelerators,
            capabilities=self._capabilities(topology),
        )

    def _admit_resume_accelerator(
        self,
        engine: CpuEngineConfiguration,
        topology: HardwareTopology,
        policy: ExecutionPolicy,
    ) -> None:
        if engine.device == "cpu":
            return
        strategy = self.strategy_catalog.find_configuration(
            engine=engine.engine,
            model=engine.model,
            device=engine.device,
            compute_type=engine.compute_type,
        )
        if strategy is None:
            raise ResourceAdmissionError(
                "Interrupted job accelerator strategy is no longer supported"
            )
        assessment = self.strategy_evaluator.assess(
            StrategyCatalog((strategy,), version=self.strategy_catalog.version),
            memory_budget_bytes=policy.memory_budget_bytes,
            accelerators=topology.accelerators,
            capabilities=self._capabilities(topology),
        )[0]
        if not assessment.feasible:
            raise ResourceAdmissionError(
                "Current accelerator capacity is below the interrupted job requirement"
            )

    def _engine(
        self, policy: ExecutionPolicy, strategy: StrategyDefinition
    ) -> CpuEngineConfiguration:
        return CpuEngineConfiguration(
            engine=strategy.engine,
            model=strategy.model,
            device=strategy.device,
            compute_type=strategy.compute_type,
            cpu_threads=policy.cpu_threads,
            beam_size=1 if policy.provisional else 5,
            language=None,
            model_cache_path=(
                self.workspace_service.paths.model_dir / "faster-whisper"
            ),
            model_revision=self.model_revision,
            auto_language_mode=AutoLanguageMode.NATIVE_MULTILINGUAL,
        )

    @staticmethod
    def _decoder(media: MediaInfo) -> DecodeConfiguration:
        audio = media.primary_audio_stream
        containers = {part.strip() for part in media.container_format.split(",")}
        direct = (
            "wav" in containers
            and audio.codec == "pcm_s16le"
            and audio.sample_rate_hz == _TARGET_SAMPLE_RATE_HZ
            and audio.channels == _TARGET_CHANNELS
        )
        return DecodeConfiguration(
            strategy=(
                DecodeStrategy.DIRECT if direct else DecodeStrategy.FFMPEG_NORMALIZE
            ),
            output_codec="pcm_s16le",
            sample_rate_hz=_TARGET_SAMPLE_RATE_HZ,
            channels=_TARGET_CHANNELS,
        )

    @staticmethod
    def _resources(
        media: MediaInfo,
        decoder: DecodeConfiguration,
        segmentation: SegmentationConfiguration,
        model_cache_bytes: int,
        estimated_peak_memory_bytes: int,
        policy: ExecutionPolicy,
    ) -> ResourceEstimate:
        normalized_audio = 0
        if decoder.strategy is DecodeStrategy.FFMPEG_NORMALIZE:
            normalized_audio = math.ceil(
                media.duration_seconds
                * decoder.sample_rate_hz
                * decoder.channels
                * _TARGET_BYTES_PER_SAMPLE
            )
        largest_segment_seconds = min(
            media.duration_seconds, float(segmentation.segment_duration_seconds)
        )
        largest_segment_audio = math.ceil(
            largest_segment_seconds
            * decoder.sample_rate_hz
            * decoder.channels
            * _TARGET_BYTES_PER_SAMPLE
        )
        private_workspace = normalized_audio + largest_segment_audio + 16 * _MIB
        public_output = max(64 * 1024, math.ceil(media.duration_seconds * 512))
        return ResourceEstimate(
            private_workspace_bytes=private_workspace,
            public_output_bytes=public_output,
            model_cache_bytes=model_cache_bytes,
            estimated_peak_memory_bytes=estimated_peak_memory_bytes,
            memory_budget_bytes=policy.memory_budget_bytes,
            fits_memory_budget=(
                estimated_peak_memory_bytes <= policy.memory_budget_bytes
            ),
        )
