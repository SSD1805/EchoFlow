# src/main.py

from dependency_injector.wiring import Provide, inject

from src.app.app_container import AppContainer
from src.core.health_check import HealthCheck


@inject
def main(
    config=Provide[AppContainer.config],
    logger=Provide[AppContainer.logger],
    performance_tracker=Provide[AppContainer.performance_tracker],
    file_manager=Provide[AppContainer.file_manager],  # Access via AppContainer
):
    """
    Main function demonstrating the use of config, logger, performance tracker,
    health check, and file manager.
    """
    try:
        # Log startup details
        logger.info(f"Starting EchoFlow in {config.APP_ENV} mode with debug={config.DEBUG}")
        logger.info("Dependency Injector and Logger are working!")
        logger.info("Main function initialized correctly.")

        # Run health checks (keep independent)
        logger.info("Running health checks...")
        health_check = HealthCheck(logger=logger, config=config, performance_tracker=performance_tracker)
        health_status = health_check.run()
        logger.info(f"HealthCheck results: {health_status}")

        # Example usage of FileManagerFacade
        critical_dir = "/tmp/echoflow"
        file_manager.ensure_directory_exists(critical_dir)
        logger.info(f"Critical directory ensured: {critical_dir}")

        # Example operation tracking
        performance_tracker.track("Example Operation")
        performance_tracker.log_system_metrics()

        logger.info("Main function execution completed successfully.")

    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        raise


if __name__ == "__main__":
    # Instantiate and wire the dependency container
    container = AppContainer()
    container.wire(modules=[__name__])  # Wire the container to this module

    # Run the main function
    main()
