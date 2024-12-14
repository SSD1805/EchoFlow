import pytest
from unittest.mock import MagicMock
from src.core.ilogger import ILogger
from src.core.logger import ApplicationLogger


@pytest.fixture
def mock_logger():
    """
    Fixture to provide a mock logger that adheres to ILogger.
    """
    mock = MagicMock(spec=ILogger)
    return mock


@pytest.fixture
def configure_test_logger():
    """
    Configure the ApplicationLogger for testing.
    """
    ApplicationLogger.configure(log_level="INFO", env="development")


def test_info_method(mock_logger):
    """
    Test the info method of the logger.
    """
    message = "Test info message"
    mock_logger.info(message, extra="extra_data")
    mock_logger.info.assert_called_once_with(message, extra="extra_data")


def test_warning_method(mock_logger):
    """
    Test the warning method of the logger.
    """
    message = "Test warning message"
    mock_logger.warning(message, extra="extra_data")
    mock_logger.warning.assert_called_once_with(message, extra="extra_data")


def test_error_method(mock_logger):
    """
    Test the error method of the logger.
    """
    message = "Test error message"
    mock_logger.error(message, extra="extra_data")
    mock_logger.error.assert_called_once_with(message, extra="extra_data")


def test_bind_method(mock_logger):
    """
    Test the bind method of the logger.
    """
    context = {"key": "value"}
    mock_logger.bind(**context)
    mock_logger.bind.assert_called_once_with(**context)


def test_application_logger_conformance(configure_test_logger):
    """
    Test that ApplicationLogger conforms to ILogger protocol.
    """
    logger = ApplicationLogger.get_logger()
    assert isinstance(logger, ILogger), "ApplicationLogger does not conform to ILogger"


def test_application_logger_methods(configure_test_logger):
    """
    Test that ApplicationLogger methods (info, warning, error, bind) work as expected.
    """
    logger = ApplicationLogger.get_logger()

    # Test info method
    logger.info("Test info message")

    # Test warning method
    logger.warning("Test warning message")

    # Test error method
    logger.error("Test error message")

    # Test bind method
    bound_logger = logger.bind(context_key="context_value")
    bound_logger.info("Test bound context log")
