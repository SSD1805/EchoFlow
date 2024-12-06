# tests/core/test_performance_tracker.py

from unittest.mock import MagicMock, patch

import pytest

from src.core.performance_tracker import PerformanceTracker


@pytest.fixture
def mock_logger():
    """
    Fixture to provide a mock logger for testing.
    """
    return MagicMock()


@pytest.fixture
def performance_tracker(mock_logger):
    """
    Fixture to provide a performance tracker instance with a mock logger.
    """
    return PerformanceTracker(logger=mock_logger)


def test_track_execution(performance_tracker, mock_logger):
    """
    Test that track_execution logs start and end messages and records elapsed time.
    """
    operation_name = "test_operation"

    with performance_tracker.track_execution(operation_name):
        pass

    # Verify logger calls
    mock_logger.info.assert_any_call("Performance tracking started", operation=operation_name)
    assert any(
        call[1].get("operation") == operation_name and "duration" in call[1]
        for call in mock_logger.info.call_args_list
    ), "Logger should record duration at the end of tracking."

    # Verify metric recorded
    assert performance_tracker.get_metric(operation_name) is not None
    assert performance_tracker.get_metric(operation_name) > 0, "Elapsed time should be greater than 0."


@patch("psutil.cpu_percent", return_value=25.0)
@patch("psutil.virtual_memory", return_value=MagicMock(percent=50.0))
def test_log_system_metrics(mock_cpu, mock_memory, performance_tracker, mock_logger):
    """
    Test that log_system_metrics logs CPU and memory usage.
    """
    performance_tracker.log_system_metrics()

    mock_logger.info.assert_any_call(
        "System metrics logged", cpu_usage=25.0, memory_usage=50.0
    )


def test_get_metric(performance_tracker):
    """
    Test get_metric returns the correct metric value.
    """
    operation_name = "test_operation"
    performance_tracker.metrics[operation_name] = 1.23
    assert performance_tracker.get_metric(operation_name) == 1.23


def test_track(performance_tracker, mock_logger):
    """
    Test the track method calls track_execution and logs appropriately.
    """
    operation_name = "test_track_operation"

    performance_tracker.track(operation_name)

    # Verify logger calls
    mock_logger.info.assert_any_call("Performance tracking started", operation=operation_name)
    assert any(
        call[1].get("operation") == operation_name and "duration" in call[1]
        for call in mock_logger.info.call_args_list
    )


def test_no_logger_errors(performance_tracker):
    """
    Test that logger calls do not raise any unexpected errors.
    """
    try:
        performance_tracker.log_system_metrics()
    except Exception as e:
        pytest.fail(f"Logger interaction raised an exception: {e}")
