# src/app/app_container.py
from dependency_injector import containers, providers
from src.core.logger import ApplicationLogger
from src.core.performance_tracker import PerformanceTracker
from src.core.config import AppConfig


class AppContainer(containers.DeclarativeContainer):
    """
    Dependency Injection container for managing application services.
    """
    config = providers.Singleton(AppConfig)
    logger = providers.Singleton(ApplicationLogger.get_logger)
    performance_tracker = providers.Singleton(PerformanceTracker, logger=logger)
