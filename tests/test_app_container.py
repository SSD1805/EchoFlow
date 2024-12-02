# tests/test_app_container.py

from src.app.app_container import AppContainer
import pytest


def test_app_container_initialization():
    """
    Ensure the AppContainer initializes without errors.
    """
    container = AppContainer()
    assert container is not None, "AppContainer instance should not be None"


def test_app_container_logger_exists():
    """
    Ensure the AppContainer provides a logger.
    """
    container = AppContainer()
    logger = container.logger()
    assert logger is not None, "Logger instance should not be None"


def test_app_container_logger_logging():
    """
    Ensure the logger provided by AppContainer can log messages.
    """
    container = AppContainer()
    logger = container.logger()

    try:
        logger.info("Test log message from AppContainer logger")
    except Exception as e:
        assert False, f"Logger raised an exception: {e}"


def test_app_container_logger_context_binding():
    """
    Test that the logger can bind and log context.
    """
    container = AppContainer()
    logger = container.logger()

    # Bind context
    logger_with_context = logger.bind(user_id=123, operation="test_context")
    assert logger_with_context is not None, "Logger with context binding should not be None"

    # Log with context
    try:
        logger_with_context.info("Testing context binding")
    except Exception as e:
        assert False, f"Logger raised an exception while logging with context: {e}"


def test_app_container_singleton_behavior():
    """
    Ensure the AppContainer provides a singleton logger.
    """
    container = AppContainer()
    logger1 = container.logger()
    logger2 = container.logger()

    assert logger1 is logger2, "AppContainer should provide a singleton logger instance"


def test_app_container_logger_integration():
    """
    Test the logger integration with AppContainer's providers.
    """
    container = AppContainer()

    # Access logger via providers
    logger = container.logger()
    assert logger is not None, "Logger instance should not be None"

    try:
        logger.info("Testing logger integration with AppContainer")
    except Exception as e:
        assert False, f"Logger raised an exception during integration test: {e}"


@pytest.mark.parametrize("log_message", [
    "Test log 1",
    "Another test log",
    "Edge case: special characters !@#$%^&*()",
    "Unicode test: こんにちは世界"
])
def test_app_container_logger_with_various_messages(log_message):
    """
    Test logging with various messages.
    """
    container = AppContainer()
    logger = container.logger()

    try:
        logger.info(log_message)
    except Exception as e:
        assert False, f"Logger raised an exception for message '{log_message}': {e}"


def test_app_container_logger_thread_safety():
    """
    Test the logger's thread safety when accessed from multiple threads.
    """
    from threading import Thread
    errors = []

    def log_in_thread(thread_id):
        try:
            container = AppContainer()
            logger = container.logger()
            logger.info(f"Logging from thread {thread_id}")
        except Exception as e:
            errors.append(f"Thread {thread_id} failed: {e}")

    threads = [Thread(target=log_in_thread, args=(i,)) for i in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors, f"Errors occurred during thread safety test: {errors}"


def test_app_container_logger_production_mode():
    """
    Test the logger in production mode (JSON output).
    """
    from src.core.logger import ApplicationLogger

    ApplicationLogger.configure(environment="production")
    container = AppContainer()
    logger = container.logger()

    try:
        logger.info("Test log in production mode")
    except Exception as e:
        assert False, f"Logger raised an exception in production mode: {e}"
