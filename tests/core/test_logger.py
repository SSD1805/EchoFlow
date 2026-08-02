# tests/core/test_logger.py

# tests/core/test_logger.py

import logging
import threading

import pytest

from src.core.config import config
from src.core.logger import (
    ApplicationLogger,
    log_error,
    log_info,
    log_warning,
)


@pytest.fixture(autouse=True)
def mock_config(monkeypatch):
    """
    Mock configuration values for testing.
    """
    monkeypatch.setattr(config, "LOG_LEVEL", "INFO")
    monkeypatch.setattr(config, "APP_ENV", "development")


@pytest.fixture(autouse=True)
def reset_logger():
    """
    Ensures the ApplicationLogger is reset between tests.
    """
    ApplicationLogger.reset()
    yield
    ApplicationLogger.reset()


def test_logger_configuration():
    ApplicationLogger.configure()
    logger = ApplicationLogger.get_logger()
    assert logger is not None
    assert ApplicationLogger._logger is logger


def test_log_info(capsys):
    ApplicationLogger.configure()
    log_info("Test info message")
    assert "Test info message" in capsys.readouterr().out


def test_log_warning(capsys):
    ApplicationLogger.configure()
    log_warning("Test warning message")
    assert "Test warning message" in capsys.readouterr().out


def test_log_error(capsys):
    ApplicationLogger.configure()
    log_error("Test error message")
    assert "Test error message" in capsys.readouterr().out


def test_context_binding():
    ApplicationLogger.configure()
    logger = ApplicationLogger.bind_context(user_id="123", action="test_action")
    assert logger.context == {"user_id": "123", "action": "test_action"}


def test_logger_singleton():
    logger1 = ApplicationLogger.get_logger()
    logger2 = ApplicationLogger.get_logger()
    assert logger1 is logger2


def test_thread_safety():
    errors = []

    def configure_logger():
        try:
            ApplicationLogger.get_logger()
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=configure_logger) for _ in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors, (
        f"Errors occurred during threaded logger initialization: {errors}"
    )


def test_add_custom_handler(tmp_path):
    """
    Test adding a custom logging handler and ensure logs are written to the file.
    """
    log_file = tmp_path / "test_log.log"
    handler = logging.FileHandler(log_file)

    # Ensure logger is properly configured
    ApplicationLogger.configure()
    ApplicationLogger.add_handler(handler)

    logger = ApplicationLogger.get_logger()
    logger.info("Logging to file handler")

    # Flush and close the handler
    handler.flush()
    handler.close()

    assert log_file.exists(), "Log file should exist"
    with open(log_file) as f:
        file_content = f.read()
        assert "Logging to file handler" in file_content, (
            f"Expected log not found in file. Content: {file_content}"
        )


def test_invalid_log_level(monkeypatch):
    monkeypatch.setattr(config, "LOG_LEVEL", "INVALID")
    with pytest.raises(ValueError, match="Invalid LOG_LEVEL"):
        ApplicationLogger.configure()
