from dependency_injector import containers, providers

from src.core.config import AppConfig
from src.core.file_manager_facade import FileManagerFacade
from src.core.logger import ApplicationLogger
from src.core.performance_tracker import PerformanceTracker
from src.interfaces.local_file_manager import LocalFileManager
from src.utils.file_utils import LocalFileUtility


def _create_logger(config: AppConfig):
    """Build the application logger from the same configuration instance."""
    return ApplicationLogger.configure(config.LOG_LEVEL, config.APP_ENV)


class AppContainer(containers.DeclarativeContainer):
    """
    Dependency Injection container for managing application services.
    """

    config = providers.Singleton(AppConfig)
    logger = providers.Singleton(_create_logger, config=config)
    file_utility = providers.Singleton(LocalFileUtility)
    local_file_manager = providers.Singleton(
        LocalFileManager,
        file_utility=file_utility,
        logger=logger,
    )
    performance_tracker = providers.Singleton(PerformanceTracker, logger=logger)
    file_manager = providers.Singleton(
        FileManagerFacade,
        file_manager=local_file_manager,
        logger=logger,
        tracker=performance_tracker,
    )
