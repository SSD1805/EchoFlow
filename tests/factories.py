from pathlib import Path

import factory

from src.core.config import AppConfig


class AppConfigFactory(factory.Factory):
    """Create explicit, environment-independent application configurations."""

    class Meta:
        model = AppConfig

    APP_ENV = "test"
    DEBUG = False
    LOG_LEVEL = "INFO"
    WORKSPACE_DIR = Path("/tmp/echoflow-tests")
    MIN_FREE_DISK_BYTES = 0
    WARN_FREE_DISK_BYTES = 0
    FFMPEG_TIMEOUT_SECONDS = 0.1
