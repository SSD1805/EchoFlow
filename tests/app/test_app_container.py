# tests/app/test_app_container.py

from unittest.mock import Mock

import pytest

from src.app.app_container import AppContainer


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


def test_app_container_performance_tracker_exists():
    """
    Ensure the AppContainer provides a performance tracker.
    """
    container = AppContainer()
    performance_tracker = container.performance_tracker()
    assert performance_tracker is not None, "Performance tracker instance should not be None"


def test_app_container_file_manager_exists():
    """
    Ensure the AppContainer provides a file manager facade.
    """
    container = AppContainer()
    file_manager = container.file_manager()
    assert file_manager is not None, "FileManagerFacade instance should not be None"


def test_app_container_file_manager_integration():
    """
    Ensure the FileManagerFacade integrates logger and tracker correctly.
    """
    container = AppContainer()
    file_manager = container.file_manager()
    logger = container.logger()
    tracker = container.performance_tracker()

    assert file_manager.logger is logger, "FileManagerFacade should use the AppContainer's logger"
    assert file_manager.tracker is tracker, "FileManagerFacade should use the AppContainer's performance tracker"


def test_app_container_logger_integration():
    """
    Test the logger integration with AppContainer's providers.
    """
    container = AppContainer()
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


def test_app_container_thread_safety():
    """
    Test the AppContainer's thread safety when accessed from multiple threads.
    """
    from threading import Thread
    errors = []

    def access_container(thread_id):
        try:
            container = AppContainer()
            logger = container.logger()
            logger.info(f"Accessing from thread {thread_id}")
        except Exception as e:
            errors.append(f"Thread {thread_id} error: {e}")

    threads = [Thread(target=access_container, args=(i,)) for i in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors, f"Errors occurred during thread safety test: {errors}"


def test_app_container_file_manager_functionality():
    """
    Test basic functionality of the FileManagerFacade from AppContainer.
    """
    container = AppContainer()
    file_manager = container.file_manager()

    mock_logger = Mock()
    file_manager.logger = mock_logger

    mock_tracker = Mock()
    file_manager.tracker = mock_tracker

    try:
        file_manager.sanitize_filename("unsafe/file*name?.txt")
    except Exception as e:
        assert False, f"FileManagerFacade raised an exception: {e}"
