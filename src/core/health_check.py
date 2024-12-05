# src/core/health_check.py
from dependency_injector.wiring import Provide, inject
from typing import Dict, Any
from src.core.logger import ApplicationLogger
from src.core.config import AppConfig
from src.core.performance_tracker import PerformanceTracker


class HealthCheck:
    """
    A class to perform health checks for core components of the application.
    """

    @inject
    def __init__(
        self,
        logger: ApplicationLogger = Provide["AppContainer.logger"],
        config: AppConfig = Provide["AppContainer.config"],
        performance_tracker: PerformanceTracker = Provide["AppContainer.performance_tracker"],
    ):
        self.logger = logger
        self.config = config
        self.performance_tracker = performance_tracker

    def run(self) -> Dict[str, Any]:
        """
        Runs health checks and returns the results.

        Returns:
            Dict[str, Any]: A dictionary containing the health status of core components.
        """
        results = {
            "logger": self._check_logger(),
            "config": self._check_config(),
            "performance_tracker": self._check_performance_tracker(),
        }
        return results

    def _check_logger(self) -> str:
        try:
            self.logger.log_info("HealthCheck: Logger is operational.")
            return "Healthy"
        except Exception as e:
            return f"Unhealthy: {str(e)}"

    def _check_config(self) -> str:
        try:
            env = self.config.APP_ENV
            debug = self.config.DEBUG
            return f"Healthy: APP_ENV={env}, DEBUG={debug}"
        except Exception as e:
            return f"Unhealthy: {str(e)}"

    def _check_performance_tracker(self) -> str:
        try:
            self.performance_tracker.track("HealthCheck Operation")
            self.performance_tracker.log_system_metrics()
            return "Healthy"
        except Exception as e:
            return f"Unhealthy: {str(e)}"
