from tests.factories import AppConfigFactory


def test_config_factory_builds_isolated_scenarios():
    development = AppConfigFactory(APP_ENV="development", LOG_LEVEL="debug")
    production = AppConfigFactory(APP_ENV="production", DEBUG=True)

    assert development.LOG_LEVEL == "DEBUG"
    assert production.APP_ENV == "production"
    assert production.DEBUG is True
