from dependency_injector import containers, providers

from echoflow.benchmarking.runner import BenchmarkRunner
from echoflow.core.config import AppConfig
from echoflow.core.file_manager_facade import FileManagerFacade
from echoflow.core.health_check import HealthCheck
from echoflow.core.health_probes import (
    DiskSpaceProbe,
    FfmpegProbe,
    SystemResourcesProbe,
    WorkspaceProbe,
)
from echoflow.core.ilogger import ILogger
from echoflow.core.logger import configure_logging
from echoflow.core.performance_tracker import PerformanceTracker
from echoflow.interfaces.local_file_manager import LocalFileManager
from echoflow.media.probe import FfprobeMediaProbe
from echoflow.media.selection import AudioStreamSelector
from echoflow.runner.inspector import RunnerInspector
from echoflow.runner.policy import RunnerPolicyPlanner
from echoflow.transcription.assembly import TranscriptAssembler
from echoflow.transcription.audio import FfmpegAudioDecoder
from echoflow.transcription.backend import FasterWhisperTranscriber
from echoflow.transcription.checkpoint import LocalCheckpointStore
from echoflow.transcription.executor import TranscriptionExecutor
from echoflow.transcription.export import TranscriptExporter
from echoflow.transcription.planner import TranscriptionJobPlanner
from echoflow.transcription.segmentation import WaveAudioSegmenter
from echoflow.transcription.storage import StorageAdmissionPolicy
from echoflow.workspace.models import WorkspacePaths
from echoflow.workspace.service import WorkspaceService


def _create_logger(config: AppConfig) -> ILogger:
    """Build the application logger from the same configuration instance."""
    return configure_logging(config.LOG_LEVEL, config.APP_ENV)


def _create_health_check(
    config: AppConfig, runner_inspector: RunnerInspector
) -> HealthCheck:
    return HealthCheck(
        (
            WorkspaceProbe(config.STATE_DIR),
            DiskSpaceProbe(
                config.STATE_DIR,
                config.MIN_FREE_DISK_BYTES,
                config.WARN_FREE_DISK_BYTES,
            ),
            FfmpegProbe(config.FFMPEG_TIMEOUT_SECONDS),
            SystemResourcesProbe(runner_inspector),
        )
    )


def _create_workspace_paths(config: AppConfig) -> WorkspacePaths:
    return WorkspacePaths(
        state_dir=config.STATE_DIR,
        cache_dir=config.CACHE_DIR,
        model_dir=config.MODEL_DIR,
        output_dir=config.OUTPUT_DIR,
    )


def _create_runner_policy_planner(config: AppConfig) -> RunnerPolicyPlanner:
    return RunnerPolicyPlanner(
        memory_budget_fraction=config.MEMORY_BUDGET_FRACTION,
        max_cpu_threads=config.MAX_CPU_THREADS,
        max_memory_bytes=config.MAX_MEMORY_BYTES,
    )


def _create_media_probe(config: AppConfig) -> FfprobeMediaProbe:
    return FfprobeMediaProbe(timeout_seconds=config.FFPROBE_TIMEOUT_SECONDS)


def _create_audio_decoder(config: AppConfig) -> FfmpegAudioDecoder:
    return FfmpegAudioDecoder(timeout_seconds=config.FFMPEG_PROCESS_TIMEOUT_SECONDS)


class AppContainer(containers.DeclarativeContainer):
    """
    Dependency Injection container for managing application services.
    """

    config = providers.Singleton(AppConfig)
    logger = providers.Singleton(_create_logger, config=config)
    local_file_manager = providers.Singleton(LocalFileManager)
    performance_tracker = providers.Singleton(PerformanceTracker)
    file_manager = providers.Singleton(
        FileManagerFacade,
        file_manager=local_file_manager,
        logger=logger,
        tracker=performance_tracker,
        path_disclosure=config.provided.LOG_PATHS,
    )
    runner_inspector = providers.Singleton(RunnerInspector)
    runner_policy_planner = providers.Singleton(
        _create_runner_policy_planner, config=config
    )
    media_probe = providers.Singleton(_create_media_probe, config=config)
    audio_stream_selector = providers.Singleton(AudioStreamSelector)
    workspace_paths = providers.Singleton(_create_workspace_paths, config=config)
    workspace_service = providers.Singleton(
        WorkspaceService,
        paths=workspace_paths,
        file_manager=file_manager,
    )
    storage_admission = providers.Singleton(
        StorageAdmissionPolicy,
        minimum_free_bytes=config.provided.MIN_FREE_DISK_BYTES,
    )
    checkpoint_store = providers.Factory(
        LocalCheckpointStore, file_manager=file_manager
    )
    transcription_planner = providers.Singleton(
        TranscriptionJobPlanner,
        media_probe=media_probe,
        workspace_service=workspace_service,
        runner_inspector=runner_inspector,
        policy_planner=runner_policy_planner,
        audio_stream_selector=audio_stream_selector,
        model_revision=config.provided.FASTER_WHISPER_MODEL_REVISION,
        checkpoint_store=checkpoint_store,
    )
    audio_decoder = providers.Factory(_create_audio_decoder, config=config)
    audio_segmenter = providers.Factory(WaveAudioSegmenter)
    transcriber = providers.Factory(FasterWhisperTranscriber)
    transcript_assembler = providers.Factory(TranscriptAssembler)
    transcription_executor = providers.Factory(
        TranscriptionExecutor,
        media_probe=media_probe,
        workspace_service=workspace_service,
        file_manager=file_manager,
        runner_inspector=runner_inspector,
        policy_planner=runner_policy_planner,
        audio_decoder=audio_decoder,
        audio_segmenter=audio_segmenter,
        transcriber=transcriber,
        transcript_assembler=transcript_assembler,
        checkpoint_store=checkpoint_store,
        storage_admission=storage_admission,
        logger=logger,
    )
    transcript_exporter = providers.Factory(
        TranscriptExporter,
        workspace_service=workspace_service,
        file_manager=file_manager,
    )
    benchmark_runner = providers.Factory(
        BenchmarkRunner,
        file_manager=file_manager,
        workspace_service=workspace_service,
    )
    health_check = providers.Factory(
        _create_health_check, config=config, runner_inspector=runner_inspector
    )
