# src/core/logger_config.py
from src.core.logger import ApplicationLogger


def configure_logger(log_level: str, environment: str):
    """
    Configure the structlog logger.

    Args:
        log_level (str): Logging level (e.g., DEBUG, INFO, WARNING).
        environment (str): Application environment (e.g., development, production).

    Returns:
        structlog.BoundLogger: Configured logger instance.
    """
    try:
        return ApplicationLogger.configure(log_level, environment)
    except ValueError as exc:
        raise ValueError(str(exc).replace("LOG_LEVEL", "log_level")) from exc
