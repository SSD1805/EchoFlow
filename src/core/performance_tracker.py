# src/core/performance_tracker.py
import pendulum
from abc import ABC, abstractmethod
from collections.abc import Iterable
from contextlib import contextmanager
from typing import Optional, Dict
import psutil  # For system performance metrics
from tqdm import tqdm
from dependency_injector.wiring import Provide, inject


class TrackerStrategy(ABC):
    """
    Abstract base class for different tracking strategies.
    """

    @abstractmethod
    def track(self, *args, **kwargs):
        pass


class PerformanceTracker(TrackerStrategy):
    """
    Tracks performance metrics like CPU, memory usage, and execution time.
    """

    @inject
    def __init__(self, logger=Provide["AppContainer.logger"]):  # Lazy string reference
        self.logger = logger if not isinstance(logger, Provide) else logger()
        self.metrics: Dict[str, float] = {}

    @contextmanager
    def track_execution(self, operation_name: str):
        """
        Context manager to track the execution time of an operation.
        """
        start_time = pendulum.now()
        self.logger.info("Performance tracking started", operation=operation_name)
        try:
            yield
        finally:
            end_time = pendulum.now()
            elapsed_time = (end_time - start_time).total_seconds()
            self.metrics[operation_name] = elapsed_time
            self.logger.info(
                "Performance tracking completed",
                operation=operation_name,
                duration=elapsed_time,
            )

    def log_system_metrics(self):
        """
        Logs system-level performance metrics (CPU, memory).
        """
        cpu_usage = psutil.cpu_percent(interval=1)
        memory_info = psutil.virtual_memory()
        self.logger.info(
            "System metrics logged",
            cpu_usage=cpu_usage,
            memory_usage=memory_info.percent,
        )

    def get_metric(self, operation_name: str) -> Optional[float]:
        """
        Retrieve a tracked metric by its name.
        """
        return self.metrics.get(operation_name)

    def track(self, operation_name: str):
        """
        Track an operation using the performance tracker.
        """
        with self.track_execution(operation_name):
            pass


class ProgressBarTracker(TrackerStrategy):
    """
    Displays a progress bar while iterating over an iterable.
    """

    @inject
    def __init__(self, logger=Provide["AppContainer.logger"]):  # Lazy string reference
        self.logger = logger if not isinstance(logger, Provide) else logger()

    def wrap(self, iterable: Iterable, description: str = "Processing", **kwargs):
        """
        Wraps an iterable with a progress bar.
        """
        if iterable is None:
            self.logger.warning(
                "Provided iterable is None. Returning an empty iterable.",
                description=description,
            )
            return iter([])

        self.logger.info("Progress bar started", description=description)
        try:
            yield from tqdm(iterable, desc=description, **kwargs)
        finally:
            self.logger.info("Progress bar completed", description=description)

    def track(self, iterable: Iterable, description: str = "Processing", **kwargs):
        """
        Track the progress of an iterable using the progress bar tracker.
        """
        yield from self.wrap(iterable, description, **kwargs)
