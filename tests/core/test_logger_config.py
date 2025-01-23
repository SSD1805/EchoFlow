# tests/core/test_logger_config.py
import pytest
import structlog
from src.core.logger_config import configure_logger


@pytest.fixture
def reset_structlog():
    """
    Fixture to reset Structlog configuration before each test.
    """
    structlog.reset_defaults()


def test_configure_logger_valid_config(reset_structlog):
    """
    Test logger configuration with valid inputs.
    """
    logger = configure_logger("INFO", "development")
    assert logger is not None
    assert isinstance(logger, structlog.BoundLogger), "Logger should be a BoundLogger instance"


def test_configure_logger_invalid_log_level(reset_structlog):
    """
    Test that invalid log levels raise an error.
    """
    with pytest.raises(ValueError, match="Invalid log_level: INVALID"):
        configure_logger("INVALID", "development")


def test_configure_logger_development_env(reset_structlog, capsys):
    """
    Test logger configuration in development environment.
    """
    logger = configure_logger("INFO", "development")
    logger.info("Test development log")
    captured = capsys.readouterr()
    assert "Test development log" in captured.out, "Log output should be visible in console"


def test_configure_logger_production_env(reset_structlog, capsys):
    """
    Test logger configuration in production environment.
    """
    logger = configure_logger("INFO", "production")
    logger.info("Test production log")
    captured = capsys.readouterr()
    assert "Test production log" in captured.out, "Log should be formatted as JSON"


def test_configure_logger_debug_level(reset_structlog, capsys):
    """
    Test logger configuration with DEBUG level.
    """
    logger = configure_logger("DEBUG", "development")
    logger.debug("Test debug log")
    captured = capsys.readouterr()
    assert "Test debug log" in captured.out, "Debug log should be visible at DEBUG level"


def test_configure_logger_runtime_update(reset_structlog, capsys):
    """
    Test reconfiguring the logger at runtime.
    """
    configure_logger("INFO", "development")
    logger = structlog.get_logger()
    logger.info("Initial log")
    configure_logger("DEBUG", "development")  # Reconfigure to DEBUG
    logger.debug("Debug log after reconfiguration")
    captured = capsys.readouterr()
    assert "Debug log after reconfiguration" in captured.out, "Logger should support runtime reconfiguration"
