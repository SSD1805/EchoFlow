import json
from contextlib import suppress
from pathlib import Path
from typing import Protocol

from echoflow.core.file_manager_facade import FileManagerFacade
from echoflow.media.errors import InputChangedError
from echoflow.media.models import MediaInfo
from echoflow.runner.inspector import RunnerInspector
from echoflow.runner.policy import RunnerPolicyPlanner
from echoflow.transcription.audio import DecodedAudio
from echoflow.transcription.errors import ResourceAdmissionError
from echoflow.transcription.models import (
    CanonicalTranscript,
    CpuEngineConfiguration,
    DecodeConfiguration,
    EngineProvenance,
    EngineTranscript,
    TranscriptionExecutionResult,
    TranscriptionJobPlan,
    TranscriptSource,
)
from echoflow.workspace.models import Artifact, ArtifactKind
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


class Transcriber(Protocol):
    def transcribe(
        self,
        audio_path: Path,
        configuration: CpuEngineConfiguration,
        *,
        allow_model_download: bool,
    ) -> EngineTranscript: ...


class TranscriptionExecutor:
    """Claim a plan, normalize its audio, transcribe it, and publish JSON."""

    def __init__(
        self,
        *,
        media_probe: MediaProbe,
        workspace_service: WorkspaceService,
        file_manager: FileManagerFacade,
        runner_inspector: RunnerInspector,
        policy_planner: RunnerPolicyPlanner,
        audio_decoder: AudioDecoder,
        transcriber: Transcriber,
    ):
        self.media_probe = media_probe
        self.workspace_service = workspace_service
        self.file_manager = file_manager
        self.runner_inspector = runner_inspector
        self.policy_planner = policy_planner
        self.audio_decoder = audio_decoder
        self.transcriber = transcriber

    def execute(
        self,
        plan: TranscriptionJobPlan,
        *,
        allow_model_download: bool = False,
    ) -> TranscriptionExecutionResult:
        self._admit(plan)
        verified_media = self.media_probe.probe(plan.job.input_path)
        if verified_media.input != plan.media.input:
            raise InputChangedError(
                "Input changed between transcription planning and execution"
            )

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
            self._admit(plan)
            engine_result = self.transcriber.transcribe(
                decoded.path,
                plan.engine,
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
        except BaseException:
            self._release_failed_artifact(artifact)
            raise
        finally:
            if decoded is not None:
                self.audio_decoder.cleanup(decoded)
        return TranscriptionExecutionResult(job, artifact, transcript)

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
