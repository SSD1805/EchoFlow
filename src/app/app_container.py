from dependency_injector import containers, providers
from src.core.logger import ApplicationLogger
from src.core.performance_tracker import PerformanceTracker
from src.core.config import AppConfig
from src.core.file_manager import FileManagerFacade


class AppContainer(containers.DeclarativeContainer):
    """
    Dependency Injection container for managing application services.
    """
    config = providers.Singleton(AppConfig)
    logger = providers.Singleton(ApplicationLogger.get_logger)
    performance_tracker = providers.Singleton(PerformanceTracker, logger=logger)
    file_manager = providers.Singleton(
        FileManagerFacade,
        logger=logger,
        tracker=performance_tracker
    )
