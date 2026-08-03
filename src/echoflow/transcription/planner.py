import math
from pathlib import Path
from typing import Protocol

from echoflow.media.models import MediaInfo
from echoflow.runner.inspector import RunnerInspector
from echoflow.runner.models import ExecutionPolicy, ModelTier, ProcessingProfile
from echoflow.runner.policy import RunnerPolicyPlanner
from echoflow.transcription.models import (
    CpuEngineConfiguration,
    DecodeConfiguration,
    DecodeStrategy,
    ResourceEstimate,
    TranscriptionJobPlan,
)
from echoflow.workspace.models import ArtifactKind
from echoflow.workspace.service import WorkspaceService

_MIB = 1024**2
_ENGINE_MODELS = {
    ModelTier.COMPACT: "tiny",
    ModelTier.STANDARD: "small",
    ModelTier.LARGE: "medium",
}
_MODEL_CACHE_BYTES = {
    "tiny": 150 * _MIB,
    "small": 750 * _MIB,
    "medium": 2_500 * _MIB,
}
_MODEL_PEAK_MEMORY_BYTES = {
    "tiny": 1_024 * _MIB,
    "small": 2_048 * _MIB,
    "medium": 4_096 * _MIB,
}
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
    ):
        self.media_probe = media_probe
        self.workspace_service = workspace_service
        self.runner_inspector = runner_inspector
        self.policy_planner = policy_planner

    def plan(
        self,
        input_path: str | Path,
        *,
        output_dir: str | Path | None = None,
        profile: ProcessingProfile = ProcessingProfile.BALANCED,
    ) -> TranscriptionJobPlan:
        job = self.workspace_service.plan_job(input_path, output_dir=output_dir)
        media = self.media_probe.probe(job.input_path)
        runner = self.runner_inspector.inspect()
        policy = self.policy_planner.plan(runner, profile)
        engine = self._engine(policy)
        decoder = self._decoder(media)
        artifact = self.workspace_service.plan_artifact(
            job, ArtifactKind.CANONICAL_JSON
        )
        resources = self._resources(media, decoder, engine, policy)
        warnings = ["paths_are_unreserved"]
        if policy.provisional:
            warnings.append("screening_output_is_provisional")
        if not resources.fits_memory_budget:
            warnings.append("estimated_peak_memory_exceeds_budget")
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
        )

    def _engine(self, policy: ExecutionPolicy) -> CpuEngineConfiguration:
        model = _ENGINE_MODELS[policy.recommended_model_tier]
        return CpuEngineConfiguration(
            engine="faster-whisper",
            model=model,
            device="cpu",
            compute_type="int8",
            cpu_threads=policy.cpu_threads,
            beam_size=1 if policy.provisional else 5,
            language=None,
            model_cache_path=(
                self.workspace_service.paths.model_dir / "faster-whisper" / model
            ),
        )

    @staticmethod
    def _decoder(media: MediaInfo) -> DecodeConfiguration:
        audio = media.primary_audio_stream
        direct = (
            audio.codec == "pcm_s16le"
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
        engine: CpuEngineConfiguration,
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
        private_workspace = normalized_audio + 16 * _MIB
        public_output = max(64 * 1024, math.ceil(media.duration_seconds * 512))
        peak_memory = _MODEL_PEAK_MEMORY_BYTES[engine.model] + 256 * _MIB
        return ResourceEstimate(
            private_workspace_bytes=private_workspace,
            public_output_bytes=public_output,
            model_cache_bytes=_MODEL_CACHE_BYTES[engine.model],
            estimated_peak_memory_bytes=peak_memory,
            memory_budget_bytes=policy.memory_budget_bytes,
            fits_memory_budget=peak_memory <= policy.memory_budget_bytes,
        )
