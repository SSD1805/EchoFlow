# src/core/logger_config.py
import structlog
import sys

def configure_logger(log_level: str, environment: str):
    """
    Configure the structlog logger.

    Args:
        log_level (str): Logging level (e.g., DEBUG, INFO, WARNING).
        environment (str): Application environment (e.g., development, production).

    Returns:
        structlog.BoundLogger: Configured logger instance.
    """
    # Validate log level
    allowed_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if log_level.upper() not in allowed_levels:
        raise ValueError(f"Invalid log_level: {log_level}. Must be one of {allowed_levels}.")

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

    # Add a StreamHandler for stdout to ensure logs are captured
    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Set up the root logger to direct output to stdout
    root_logger = structlog.get_logger()
    if not any(isinstance(handler, structlog.stdlib.StreamHandler) for handler in sys.stdout.handlers):
        stream_handler = structlog.stdlib.StreamHandler(sys.stdout)
        structlog.stdlib.add_logger_handler(root_logger, stream_handler)

    return root_logger
