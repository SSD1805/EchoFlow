import structlog
from threading import Lock
from src.core.ilogger import ILogger


class StructlogAdapter(ILogger):
    """
    Adapter to ensure Structlog logger conforms to ILogger protocol.
    """

    def __init__(self, logger):
        self._logger = logger

    def info(self, message: str, **kwargs):
        self._logger.info(message, **kwargs)

    def warning(self, message: str, **kwargs):
        self._logger.warning(message, **kwargs)

    def error(self, message: str, **kwargs):
        self._logger.error(message, **kwargs)

    def bind(self, **kwargs):
        return StructlogAdapter(self._logger.bind(**kwargs))


class ApplicationLogger:
    """
    Singleton Logger using Structlog with an adapter for ILogger conformance.
    """
    _logger_instance = None
    _lock = Lock()

    @classmethod
    def configure(cls, log_level: str, env: str):
        """
        Configure the logger with the specified log level and environment.
        """
        with cls._lock:
            if cls._logger_instance is not None:
                return  # Logger is already configured

            processors = [
                structlog.processors.TimeStamper(fmt="ISO"),
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
            ]

            if env == "development":
                processors.append(structlog.dev.ConsoleRenderer())
            else:
                processors.append(structlog.processors.JSONRenderer())

            structlog.configure(
                processors=processors,
                logger_factory=structlog.stdlib.LoggerFactory(),
                wrapper_class=structlog.stdlib.BoundLogger,
                cache_logger_on_first_use=True,
            )
            # Wrap the Structlog logger with the adapter
            cls._logger_instance = StructlogAdapter(structlog.get_logger())

    @classmethod
    def get_logger(cls) -> ILogger:
        """
        Retrieve the configured logger instance.
        """
        if cls._logger_instance is None:
            raise RuntimeError("Logger is not configured. Call configure() first.")
        return cls._logger_instance
