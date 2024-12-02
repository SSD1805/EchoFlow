# src/main.py
from dependency_injector.wiring import Provide, inject
from src.app.app_container import AppContainer


@inject
def main(
    config=Provide[AppContainer.config],
    logger=Provide[AppContainer.logger],
    performance_tracker=Provide[AppContainer.performance_tracker],
):
    """
    Main function demonstrating the use of config, logger, and performance tracker.
    """
    try:
        logger.info(f"Starting EchoFlow in {config.APP_ENV} mode with debug={config.DEBUG}")
        logger.info("Dependency Injector and Logger are working!")
        logger.info("Main function initialized correctly.")
        logger.info("All systems operational.")

        performance_tracker.track("Example Operation")
        performance_tracker.log_system_metrics()

    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        raise


if __name__ == "__main__":
    container = AppContainer()
    container.wire(modules=[__name__])  # Wire the container to this module
    main()
