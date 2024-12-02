# tests/test_main.py
import pytest
from unittest.mock import MagicMock
from src.main import main


@pytest.fixture
def mock_dependencies():
    """
    Fixture to mock the config, logger, and performance tracker dependencies.
    """
    mock_config = MagicMock()
    mock_logger = MagicMock()
    mock_performance_tracker = MagicMock()
    return mock_config, mock_logger, mock_performance_tracker


def test_main_runs_without_errors(mock_dependencies):
    """
    Ensure the main function executes without errors.
    """
    mock_config, mock_logger, mock_performance_tracker = mock_dependencies

    mock_config.APP_ENV = "development"
    mock_config.DEBUG = True

    try:
        main(
            config=mock_config,
            logger=mock_logger,
            performance_tracker=mock_performance_tracker,
        )
    except Exception as e:
        pytest.fail(f"main() raised an exception: {e}")


def test_main_logger_initialization(mock_dependencies):
    """
    Test that the logger in main logs the expected messages.
    """
    mock_config, mock_logger, _ = mock_dependencies

    mock_config.APP_ENV = "development"
    mock_config.DEBUG = True

    main(
        config=mock_config,
        logger=mock_logger,
        performance_tracker=MagicMock(),
    )

    mock_logger.info.assert_any_call("Dependency Injector and Logger are working!")
    mock_logger.info.assert_any_call("Main function initialized correctly.")
    mock_logger.info.assert_any_call("All systems operational.")
    mock_logger.info.assert_any_call("Starting EchoFlow in development mode with debug=True")


def test_main_performance_tracker(mock_dependencies):
    """
    Test that the performance tracker is used as expected in main.
    """
    _, _, mock_performance_tracker = mock_dependencies

    main(
        config=MagicMock(),
        logger=MagicMock(),
        performance_tracker=mock_performance_tracker,
    )

    mock_performance_tracker.track.assert_called_once_with("Example Operation")
    mock_performance_tracker.log_system_metrics.assert_called_once()


@pytest.mark.parametrize(
    "log_message",
    [
        "Dependency Injector and Logger are working!",
        "Main function initialized correctly.",
        "All systems operational.",
    ],
)
def test_main_logger_message_content(mock_dependencies, log_message):
    """
    Test that main logs the correct message content.
    """
    _, mock_logger, _ = mock_dependencies

    main(
        config=MagicMock(),
        logger=mock_logger,
        performance_tracker=MagicMock(),
    )

    mock_logger.info.assert_any_call(log_message)


def test_main_config_usage(mock_dependencies):
    """
    Test that the config values are logged correctly.
    """
    mock_config, mock_logger, _ = mock_dependencies

    mock_config.APP_ENV = "production"
    mock_config.DEBUG = False

    main(
        config=mock_config,
        logger=mock_logger,
        performance_tracker=MagicMock(),
    )

    mock_logger.info.assert_any_call("Starting EchoFlow in production mode with debug=False")


def test_main_error_handling(mock_dependencies):
    """
    Ensure that main handles errors in logger gracefully.
    """
    _, mock_logger, _ = mock_dependencies
    mock_logger.info.side_effect = Exception("Logger failed")

    with pytest.raises(Exception, match="Logger failed"):
        main(
            config=MagicMock(),
            logger=mock_logger,
            performance_tracker=MagicMock(),
        )
