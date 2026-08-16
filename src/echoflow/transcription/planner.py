import math
from pathlib import Path
from typing import Protocol

from echoflow.media.models import MediaInfo
from echoflow.runner.inspector import RunnerInspector
from echoflow.runner.models import ExecutionPolicy, ProcessingProfile
from echoflow.runner.policy import RunnerPolicyPlanner
from echoflow.transcription.models import (
    CpuEngineConfiguration,
    DecodeConfiguration,
    DecodeStrategy,
    ResourceEstimate,
    SegmentationConfiguration,
    TranscriptionJobPlan,
)
from echoflow.transcription.strategy import (
    StrategyCatalog,
    StrategyDefinition,
    StrategyEvaluator,
    faster_whisper_cpu_catalog,
)
from echoflow.workspace.models import ArtifactKind
from echoflow.workspace.service import WorkspaceService

_MIB = 1024**2
_TARGET_SAMPLE_RATE_HZ = 16_000
_TARGET_CHANNELS = 1
_TARGET_BYTES_PER_SAMPLE = 2


class MediaProbe(Protocol):
    def probe(self, input_path: str | Path) -> MediaInfo: ...


class TranscriptionJobPlanner:
    """Compose media, workspace, runner, and engine decisions into one plan."""

    def __init__(
        self,
        *,
        media_probe: MediaProbe,
        workspace_service: WorkspaceService,
        runner_inspector: RunnerInspector,
        policy_planner: RunnerPolicyPlanner,
        strategy_catalog: StrategyCatalog | None = None,
        strategy_evaluator: StrategyEvaluator | None = None,
        model_revision: str | None = None,
    ):
        self.media_probe = media_probe
        self.workspace_service = workspace_service
        self.runner_inspector = runner_inspector
        self.policy_planner = policy_planner
        self.strategy_catalog = strategy_catalog or faster_whisper_cpu_catalog()
        self.strategy_evaluator = strategy_evaluator or StrategyEvaluator()
        self.model_revision = model_revision

    def plan(
        self,
        input_path: str | Path,
        *,
        output_dir: str | Path | None = None,
        profile: ProcessingProfile = ProcessingProfile.BALANCED,
        strategy_id: str | None = None,
    ) -> TranscriptionJobPlan:
        job = self.workspace_service.plan_job(input_path, output_dir=output_dir)
        media = self.media_probe.probe(job.input_path)
        runner = self.runner_inspector.inspect()
        policy = self.policy_planner.plan(runner, profile)
        assessments = self.strategy_evaluator.assess(
            self.strategy_catalog, memory_budget_bytes=policy.memory_budget_bytes
        )
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
            media, decoder, segmentation, selected.strategy, policy
        )
        warnings = ["paths_are_unreserved"]
        if policy.provisional:
            warnings.append("screening_output_is_provisional")
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
        )

    def assess_strategies(
        self, *, profile: ProcessingProfile = ProcessingProfile.BALANCED
    ) -> tuple[dict[str, object], ...]:
        """Describe all local strategies against a fresh process-visible budget."""

        runner = self.runner_inspector.inspect()
        policy = self.policy_planner.plan(runner, profile)
        assessments = self.strategy_evaluator.assess(
            self.strategy_catalog, memory_budget_bytes=policy.memory_budget_bytes
        )
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

    def _engine(
        self, policy: ExecutionPolicy, strategy: StrategyDefinition
    ) -> CpuEngineConfiguration:
        return CpuEngineConfiguration(
            engine="faster-whisper",
            model=strategy.model,
            device="cpu",
            compute_type="int8",
            cpu_threads=policy.cpu_threads,
            beam_size=1 if policy.provisional else 5,
            language=None,
            model_cache_path=(
                self.workspace_service.paths.model_dir / "faster-whisper"
            ),
            model_revision=self.model_revision,
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
        strategy: StrategyDefinition,
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
            model_cache_bytes=strategy.model_cache_bytes,
            estimated_peak_memory_bytes=strategy.estimated_peak_memory_bytes,
            memory_budget_bytes=policy.memory_budget_bytes,
            fits_memory_budget=(
                strategy.estimated_peak_memory_bytes <= policy.memory_budget_bytes
            ),
        )
