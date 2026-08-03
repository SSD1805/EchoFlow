import logging
import sys
from typing import TextIO

import structlog
from structlog.typing import Processor

from echoflow.core.ilogger import ILogger


class StructlogAdapter(ILogger):
    """
    Adapter to ensure Structlog logger conforms to ILogger protocol.
    """

    def __init__(
        self,
        logger: structlog.stdlib.BoundLogger,
        context: dict[str, object] | None = None,
    ):
        self._logger = logger
        self._bound_context = dict(context or {})

    def debug(self, message: str, **kwargs: object) -> None:
        self._logger.debug(message, **kwargs)

    def info(self, message: str, **kwargs: object) -> None:
        self._logger.info(message, **kwargs)

    def warning(self, message: str, **kwargs: object) -> None:
        self._logger.warning(message, **kwargs)

    def error(self, message: str, **kwargs: object) -> None:
        self._logger.error(message, **kwargs)

    def bind(self, **kwargs: object) -> "StructlogAdapter":
        return StructlogAdapter(
            self._logger.bind(**kwargs), {**self._bound_context, **kwargs}
        )

    @property
    def context(self) -> dict[str, object]:
        """Return a copy of the immutable bound context."""
        return dict(self._bound_context)


def configure_logging(
    log_level: str, environment: str, stream: TextIO | None = None
) -> ILogger:
    """Configure Structlog once at the composition root and return its adapter."""
    level_name = log_level.upper()
    allowed_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if level_name not in allowed_levels:
        raise ValueError(f"Invalid LOG_LEVEL: {level_name}")

    shared_processors: list[Processor] = [
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

    app_logger = logging.getLogger("echoflow")
    app_logger.handlers.clear()
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(formatter)
    app_logger.addHandler(handler)
    app_logger.setLevel(level_name)
    app_logger.propagate = False

    logger = structlog.wrap_logger(
        app_logger,
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
    )
    return StructlogAdapter(logger)


def reset_logging() -> None:
    """Reset EchoFlow logging state for an isolated application/test lifecycle."""
    app_logger = logging.getLogger("echoflow")
    app_logger.handlers.clear()
    app_logger.propagate = True
