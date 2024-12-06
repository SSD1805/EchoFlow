# src/core/logger.py
import logging
import sys
import threading

import structlog


class ApplicationLogger:
    """
    A singleton logger using structlog.
    """
    _instance = None
    _lock = threading.Lock()
    _is_configured = False
    _logger = None

    def __new__(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(ApplicationLogger, cls).__new__(cls)
        return cls._instance

    @classmethod
    def configure(cls, log_level="INFO", environment="development"):
        """
        Configures the structlog logger for the application.
        """
        if cls._is_configured:
            return
        cls._is_configured = True

        # Set up Python's logging
        logging.basicConfig(
            format="%(message)s",
            stream=sys.stdout,
            level=log_level,
        )

        # Add handlers to root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)

        # Configure structlog
        processors = [
            structlog.processors.TimeStamper(fmt="ISO"),
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
        ]

        if environment == "development":
            processors.append(structlog.dev.ConsoleRenderer())
        else:
            processors.append(structlog.processors.JSONRenderer())

        structlog.configure(
            processors=processors,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )

        cls._logger = structlog.get_logger()

    @staticmethod
    def get_logger():
        """
        Returns the singleton logger instance.
        Configures logger if not already configured.
        """
        if ApplicationLogger._logger is None:
            ApplicationLogger.configure()
        return ApplicationLogger._logger

    @staticmethod
    def bind_context(**kwargs):
        """
        Binds additional context to the logger.
        """
        logger = ApplicationLogger.get_logger()
        return logger.bind(**kwargs)

    @classmethod
    def add_handler(cls, handler):
        """
        Adds a custom logging handler to the root logger.
        """
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)


# Convenience functions
def log_info(message):
    logger = ApplicationLogger.get_logger()
    logger.info(message)


def log_error(message):
    logger = ApplicationLogger.get_logger()
    logger.error(message)


def log_warning(message):
    logger = ApplicationLogger.get_logger()
    logger.warning(message)
