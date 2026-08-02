from dependency_injector import containers, providers

from src.core.config import AppConfig
from src.core.file_manager_facade import FileManagerFacade
from src.core.health_check import HealthCheck
from src.core.health_probes import (
    DiskSpaceProbe,
    FfmpegProbe,
    SystemResourcesProbe,
    WorkspaceProbe,
)
from src.core.logger import configure_logging
from src.core.performance_tracker import PerformanceTracker
from src.interfaces.local_file_manager import LocalFileManager


def _create_logger(config: AppConfig):
    """Build the application logger from the same configuration instance."""
    return configure_logging(config.LOG_LEVEL, config.APP_ENV)


def _create_health_check(config: AppConfig) -> HealthCheck:
    return HealthCheck(
        (
            WorkspaceProbe(config.WORKSPACE_DIR),
            DiskSpaceProbe(
                config.WORKSPACE_DIR,
                config.MIN_FREE_DISK_BYTES,
                config.WARN_FREE_DISK_BYTES,
            ),
            FfmpegProbe(config.FFMPEG_TIMEOUT_SECONDS),
            SystemResourcesProbe(),
        )
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
    health_check = providers.Factory(_create_health_check, config=config)
