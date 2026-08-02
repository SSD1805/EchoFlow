import logging
import sys
from threading import Lock

import structlog

from src.core.config import config
from src.core.ilogger import ILogger


class StructlogAdapter(ILogger):
    """
    Adapter to ensure Structlog logger conforms to ILogger protocol.
    """

    def __init__(self, logger):
        self._logger = logger

    def debug(self, message: str, **kwargs):
        self._logger.debug(message, **kwargs)

    def info(self, message: str, **kwargs):
        self._logger.info(message, **kwargs)

    def warning(self, message: str, **kwargs):
        self._logger.warning(message, **kwargs)

    def error(self, message: str, **kwargs):
        self._logger.error(message, **kwargs)

    def bind(self, **kwargs):
        return StructlogAdapter(self._logger.bind(**kwargs))

    @property
    def context(self) -> dict:
        """Return a copy of the immutable bound context."""
        return dict(self._logger._context)


class ApplicationLogger:
    """
    Singleton Logger using Structlog with an adapter for ILogger conformance.
    """

    _logger = None
    _logger_instance = None  # Backward-compatible alias.
    _lock = Lock()

    @classmethod
    def configure(cls, log_level: str | None = None, env: str | None = None) -> ILogger:
        """
        Configure the logger with the specified log level and environment.
        """
        level_name = (log_level or config.LOG_LEVEL).upper()
        environment = env or config.APP_ENV
        allowed_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if level_name not in allowed_levels:
            raise ValueError(
                f"Invalid LOG_LEVEL: {level_name}. Must be one of {allowed_levels}."
            )

        with cls._lock:
            shared_processors = [
                structlog.contextvars.merge_contextvars,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
            ]
            renderer = (
                structlog.dev.ConsoleRenderer(colors=False)
                if environment == "development"
                else structlog.processors.JSONRenderer()
            )
            formatter = structlog.stdlib.ProcessorFormatter(
                foreign_pre_chain=shared_processors,
                processors=[
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    renderer,
                ],
            )

            root_logger = logging.getLogger()
            root_logger.handlers.clear()
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(formatter)
            root_logger.addHandler(handler)
            root_logger.setLevel(level_name)

            structlog.configure(
                processors=[
                    *shared_processors,
                    structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
                ],
                logger_factory=structlog.stdlib.LoggerFactory(),
                wrapper_class=structlog.stdlib.BoundLogger,
                cache_logger_on_first_use=False,
            )
            cls._logger = StructlogAdapter(structlog.get_logger("echoflow"))
            cls._logger_instance = cls._logger
            return cls._logger

    @classmethod
    def get_logger(cls) -> ILogger:
        """
        Retrieve the configured logger instance.
        """
        if cls._logger is None:
            return cls.configure()
        return cls._logger

    @classmethod
    def bind_context(cls, **kwargs) -> ILogger:
        return cls.get_logger().bind(**kwargs)

    @classmethod
    def add_handler(cls, handler: logging.Handler) -> None:
        """Attach an explicitly configured stdlib handler."""
        logging.getLogger().addHandler(handler)

    @classmethod
    def reset(cls) -> None:
        """Reset global logging state, primarily for isolated tests."""
        with cls._lock:
            cls._logger = None
            cls._logger_instance = None
            logging.getLogger().handlers.clear()
            structlog.reset_defaults()


def log_info(message: str, **kwargs) -> None:
    ApplicationLogger.get_logger().info(message, **kwargs)


def log_warning(message: str, **kwargs) -> None:
    ApplicationLogger.get_logger().warning(message, **kwargs)


def log_error(message: str, **kwargs) -> None:
    ApplicationLogger.get_logger().error(message, **kwargs)
