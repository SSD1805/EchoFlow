# src/core/logger_factory.py
from src.core.ilogger import ILogger
from src.core.logger import ApplicationLogger


class LoggerFactory:
    @staticmethod
    def create_logger(context: dict | None = None) -> ILogger:
        logger = ApplicationLogger.get_logger()
        if context:
            logger = logger.bind(**context)
        return logger
