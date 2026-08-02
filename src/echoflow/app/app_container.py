from dependency_injector import containers, providers

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
from echoflow.workspace.models import WorkspacePaths
from echoflow.workspace.service import WorkspaceService


def _create_logger(config: AppConfig) -> ILogger:
    """Build the application logger from the same configuration instance."""
    return configure_logging(config.LOG_LEVEL, config.APP_ENV)


def _create_health_check(config: AppConfig) -> HealthCheck:
    return HealthCheck(
        (
            WorkspaceProbe(config.STATE_DIR),
            DiskSpaceProbe(
                config.STATE_DIR,
                config.MIN_FREE_DISK_BYTES,
                config.WARN_FREE_DISK_BYTES,
            ),
            FfmpegProbe(config.FFMPEG_TIMEOUT_SECONDS),
            SystemResourcesProbe(),
        )
    )


def _create_workspace_paths(config: AppConfig) -> WorkspacePaths:
    return WorkspacePaths(
        state_dir=config.STATE_DIR,
        cache_dir=config.CACHE_DIR,
        model_dir=config.MODEL_DIR,
        output_dir=config.OUTPUT_DIR,
    )


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
    )
    workspace_paths = providers.Singleton(_create_workspace_paths, config=config)
    workspace_service = providers.Singleton(
        WorkspaceService,
        paths=workspace_paths,
        file_manager=file_manager,
    )
    health_check = providers.Factory(_create_health_check, config=config)
