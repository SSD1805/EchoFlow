# tests/test_application_logger.py

from src.core.logger import ApplicationLogger, log_info
from logging import FileHandler
import threading


def test_log_info():
    """
    Test the log_info method of ApplicationLogger.
    """
    logger = ApplicationLogger.get_logger()
    assert logger is not None, "Logger instance should not be None"

    # Bind context to logger (optional)
    logger = logger.bind(test="value")

    # Call log_info
    log_info("This is a test informational message")


def test_log_warning():
    """
    Test the log_warning method of ApplicationLogger.
    """
    logger = ApplicationLogger.get_logger()
    assert logger is not None, "Logger instance should not be None"

    logger = logger.bind(test="warning")

    # Call log_warning
    logger.warning("This is a test warning message")


def test_log_error():
    """
    Test the log_error method of ApplicationLogger.
    """
    logger = ApplicationLogger.get_logger()
    assert logger is not None, "Logger instance should not be None"

    logger = logger.bind(test="error")

    # Call log_error
    logger.error("This is a test error message")


def test_context_binding():
    """
    Test that logger binds context correctly.
    """
    logger = ApplicationLogger.bind_context(user_id=123, operation="test_context")
    assert logger is not None, "Logger instance should not be None"

    # Log with context
    logger.info("Testing context binding")


def test_logger_reconfiguration():
    """
    Ensure that logger does not reconfigure multiple times.
    """
    ApplicationLogger.configure(log_level="DEBUG")
    logger = ApplicationLogger.get_logger()
    assert logger is not None, "Logger instance should not be None"

    # Reconfigure and verify no errors
    ApplicationLogger.configure(log_level="INFO")
    logger.info("Logger reconfigured successfully")


def test_add_custom_handler(tmp_path):
    """
    Test adding a custom logging handler.
    """
    log_file = tmp_path / "test_log.log"
    handler = FileHandler(log_file)

    ApplicationLogger.add_handler(handler)
    logger = ApplicationLogger.get_logger()

    # Log the test message
    logger.info("Test message to file handler")

    # Flush the handler to ensure the message is written
    handler.flush()

    # Verify log file content
    assert log_file.exists(), "Log file should exist"
    with open(log_file, "r") as f:
        log_content = f.read()
        assert "Test message to file handler" in log_content, "Log content should include the message"


def test_production_mode():
    """
    Test logger behavior in production mode.
    """
    ApplicationLogger.configure(environment="production")
    logger = ApplicationLogger.get_logger()

    # Log a test message
    logger.info("Test message in production mode")

    # Production logs should be in JSON format
    # Here you might use a mock or capture output to verify JSON structure


def test_thread_safety():
    """
    Test logger initialization in a multi-threaded environment.
    """
    errors = []

    def log_in_thread():
        try:
            logger = ApplicationLogger.get_logger()
            logger.info("Logging from a thread")
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=log_in_thread) for _ in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors, f"Errors occurred during threaded logging: {errors}"


def test_logging_without_configuration():
    """
    Test that logging works without explicit configuration.
    """
    logger = ApplicationLogger.get_logger()
    assert logger is not None, "Logger instance should not be None"

    logger.info("Test logging without explicit configuration")
