# src/core/logger_factory.py
import structlog
from src.core.ilogger import ILogger

class LoggerFactory:
    @staticmethod
    def create_logger(context: dict = None) -> ILogger:
        logger = structlog.get_logger()
        if context:
            logger = logger.bind(**context)
        return logger
