# tests/test_main.py

from unittest.mock import MagicMock, patch

import pytest

from src.main import main


@pytest.fixture
def mock_dependencies():
    """
    Fixture to mock the config, logger, performance tracker, and file manager dependencies.
    """
    mock_config = MagicMock()
    mock_logger = MagicMock()
    mock_performance_tracker = MagicMock()
    mock_file_manager = MagicMock()
    return mock_config, mock_logger, mock_performance_tracker, mock_file_manager


@patch("src.main.HealthCheck")
def test_main_runs_without_errors(mock_health_check, mock_dependencies):
    """
    Ensure the main function executes without errors.
    """
    mock_config, mock_logger, mock_performance_tracker, mock_file_manager = mock_dependencies

    mock_config.APP_ENV = "development"
    mock_config.DEBUG = True

    mock_health_check_instance = MagicMock()
    mock_health_check.return_value = mock_health_check_instance
    mock_health_check_instance.run.return_value = {}

    try:
        main(
            config=mock_config,
            logger=mock_logger,
            performance_tracker=mock_performance_tracker,
            file_manager=mock_file_manager,
        )
    except Exception as e:
        pytest.fail(f"main() raised an exception: {e}")


@patch("src.main.HealthCheck")
def test_main_health_check_usage(mock_health_check, mock_dependencies):
    """
    Ensure that HealthCheck is initialized and used in main.
    """
    mock_config, mock_logger, mock_performance_tracker, mock_file_manager = mock_dependencies

    mock_health_check_instance = MagicMock()
    mock_health_check.return_value = mock_health_check_instance
    mock_health_check_instance.run.return_value = {"logger": "Healthy"}

    main(
        config=mock_config,
        logger=mock_logger,
        performance_tracker=mock_performance_tracker,
        file_manager=mock_file_manager,
    )

    mock_health_check.assert_called_once_with(
        logger=mock_logger,
        config=mock_config,
        performance_tracker=mock_performance_tracker,
    )
    mock_health_check_instance.run.assert_called_once()
    mock_logger.info.assert_any_call("Running health checks...")
    mock_logger.info.assert_any_call("HealthCheck results: {'logger': 'Healthy'}")


@patch("src.main.HealthCheck")
def test_main_file_manager_usage(mock_health_check, mock_dependencies):
    """
    Ensure that FileManagerFacade is used in main.
    """
    _, mock_logger, _, mock_file_manager = mock_dependencies

    mock_health_check_instance = MagicMock()
    mock_health_check.return_value = mock_health_check_instance
    mock_health_check_instance.run.return_value = {}

    main(
        config=MagicMock(),
        logger=mock_logger,
        performance_tracker=MagicMock(),
        file_manager=mock_file_manager,
    )

    critical_dir = "/tmp/echoflow"
    mock_file_manager.ensure_directory_exists.assert_called_once_with(critical_dir)
    mock_logger.info.assert_any_call(f"Critical directory ensured: {critical_dir}")


@patch("src.main.HealthCheck")
def test_main_logger_initialization(mock_health_check, mock_dependencies):
    """
    Test that the logger in main logs the expected messages.
    """
    mock_config, mock_logger, _, mock_file_manager = mock_dependencies

    mock_config.APP_ENV = "development"
    mock_config.DEBUG = True

    mock_health_check_instance = MagicMock()
    mock_health_check.return_value = mock_health_check_instance
    mock_health_check_instance.run.return_value = {}

    main(
        config=mock_config,
        logger=mock_logger,
        performance_tracker=MagicMock(),
        file_manager=mock_file_manager,
    )

    mock_logger.info.assert_any_call("Dependency Injector and Logger are working!")
    mock_logger.info.assert_any_call("Main function initialized correctly.")
    mock_logger.info.assert_any_call("Starting EchoFlow in development mode with debug=True")


@patch("src.main.HealthCheck")
def test_main_performance_tracker(mock_health_check, mock_dependencies):
    """
    Test that the performance tracker is used as expected in main.
    """
    _, _, mock_performance_tracker, mock_file_manager = mock_dependencies

    # Mock HealthCheck to simulate its behavior
    mock_health_check_instance = MagicMock()
    mock_health_check.return_value = mock_health_check_instance
    mock_health_check_instance.run.side_effect = lambda: {
        mock_performance_tracker.track("HealthCheck Operation")
    }

    # Define a side effect for the performance tracker's track method
    tracked_operations = []

    def mock_track(operation):
        tracked_operations.append(operation)

    mock_performance_tracker.track.side_effect = mock_track

    # Run the main function
    main(
        config=MagicMock(),
        logger=MagicMock(),
        performance_tracker=mock_performance_tracker,
        file_manager=mock_file_manager,
    )

    # Ensure specific operations were tracked
    assert "HealthCheck Operation" in tracked_operations, "HealthCheck Operation was not tracked"
    assert "Example Operation" in tracked_operations, "Example Operation was not tracked"
    mock_performance_tracker.log_system_metrics.assert_called_once()


@pytest.mark.parametrize(
    "log_message",
    [
        "Dependency Injector and Logger are working!",
        "Main function initialized correctly.",
        "Running health checks...",
    ],
)
@patch("src.main.HealthCheck")
def test_main_logger_message_content(mock_health_check, mock_dependencies, log_message):
    """
    Test that main logs the correct message content.
    """
    _, mock_logger, _, mock_file_manager = mock_dependencies

    mock_health_check_instance = MagicMock()
    mock_health_check.return_value = mock_health_check_instance
    mock_health_check_instance.run.return_value = {}

    main(
        config=MagicMock(),
        logger=mock_logger,
        performance_tracker=MagicMock(),
        file_manager=mock_file_manager,
    )

    mock_logger.info.assert_any_call(log_message)


@patch("src.main.HealthCheck")
def test_main_error_handling(mock_health_check, mock_dependencies):
    """
    Ensure that main handles errors in logger gracefully.
    """
    _, mock_logger, _, mock_file_manager = mock_dependencies
    mock_logger.info.side_effect = Exception("Logger failed")

    with pytest.raises(Exception, match="Logger failed"):
        main(
            config=MagicMock(),
            logger=mock_logger,
            performance_tracker=MagicMock(),
            file_manager=mock_file_manager,
        )
