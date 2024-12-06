# tests/core/test_health_check.py

from unittest.mock import Mock, PropertyMock

import pytest

from src.core.config import AppConfig
from src.core.health_check import HealthCheck
from src.core.logger import ApplicationLogger
from src.core.performance_tracker import PerformanceTracker


@pytest.fixture
def mock_logger():
    """
    Fixture for mocking the ApplicationLogger.
    """
    logger = Mock(spec=ApplicationLogger)
    logger.log_info = Mock()  # Mock the `log_info` method
    return logger


@pytest.fixture
def mock_config():
    """
    Fixture for mocking the AppConfig.
    """
    config = Mock(spec=AppConfig)
    config.APP_ENV = "test"
    config.DEBUG = True
    return config


@pytest.fixture
def mock_performance_tracker():
    """
    Fixture for mocking the PerformanceTracker.
    """
    tracker = Mock(spec=PerformanceTracker)
    tracker.track = Mock()
    tracker.log_system_metrics = Mock()
    return tracker


@pytest.fixture
def health_check(mock_logger, mock_config, mock_performance_tracker):
    """
    Fixture for creating a HealthCheck instance with mocked dependencies.
    """
    return HealthCheck(
        logger=mock_logger,
        config=mock_config,
        performance_tracker=mock_performance_tracker
    )


def test_logger_is_operational(health_check):
    """
    Test that the logger is operational and does not raise errors.
    """
    result = health_check.run()
    assert result["logger"] == "Healthy"


def test_logger_raises_exception(health_check, mock_logger):
    """
    Test that the HealthCheck handles logger exceptions correctly.
    """
    mock_logger.log_info.side_effect = Exception("Logger error")
    result = health_check.run()
    assert result["logger"] == "Unhealthy: Logger error"


def test_config_is_healthy(health_check):
    """
    Test that the configuration is correctly marked as healthy.
    """
    result = health_check.run()
    assert result["config"] == "Healthy: APP_ENV=test, DEBUG=True"


def test_config_raises_exception(health_check, mock_config):
    """
    Test that an exception raised during config access is handled correctly.
    """
    # Mock the APP_ENV attribute to raise an exception
    type(mock_config).APP_ENV = PropertyMock(side_effect=Exception("Config error"))

    result = health_check.run()
    assert result["config"] == "Unhealthy: Config error"


def test_performance_tracker_is_healthy(health_check):
    """
    Test that the performance tracker is operational and marked as healthy.
    """
    result = health_check.run()
    assert result["performance_tracker"] == "Healthy"


def test_performance_tracker_raises_exception(health_check, mock_performance_tracker):
    """
    Test that the HealthCheck handles performance tracker exceptions correctly.
    """
    mock_performance_tracker.track.side_effect = Exception("Performance tracker error")
    result = health_check.run()
    assert result["performance_tracker"] == "Unhealthy: Performance tracker error"
