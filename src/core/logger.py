import logging
import sys
from typing import TextIO

import structlog

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


def configure_logging(
    log_level: str, environment: str, stream: TextIO | None = None
) -> ILogger:
    """Configure Structlog once at the composition root and return its adapter."""
    level_name = log_level.upper()
    allowed_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if level_name not in allowed_levels:
        raise ValueError(f"Invalid LOG_LEVEL: {level_name}")

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
    handler = logging.StreamHandler(stream or sys.stdout)
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
    return StructlogAdapter(structlog.get_logger("echoflow"))


def reset_logging() -> None:
    """Reset process-wide logging state for an isolated application/test lifecycle."""
    logging.getLogger().handlers.clear()
    structlog.reset_defaults()
