import factory

from src.core.config import AppConfig


class AppConfigFactory(factory.Factory):
    """Create explicit, environment-independent application configurations."""

    class Meta:
        model = AppConfig

    APP_ENV = "test"
    DEBUG = False
    LOG_LEVEL = "INFO"
    API_TIMEOUT = 30
    DATABASE_URL = None
    CELERY_BROKER_URL = None
    DJANGO_SECRET_KEY = None
