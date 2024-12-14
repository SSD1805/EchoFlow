# tests/core/test_config.py

import pytest
from pydantic import ValidationError
from src.core.config import AppConfig, config


def test_config_defaults():
    """
    Test that default values are correctly set when no environment variables are provided.
    """
    assert config.APP_ENV == "development"
    assert config.DEBUG is False
    assert config.DATABASE_URL is None
    assert config.CELERY_BROKER_URL is None
    assert config.DJANGO_SECRET_KEY is None
    assert config.LOG_LEVEL == "INFO"
    assert config.API_TIMEOUT == 30


def test_config_env_override(monkeypatch):
    """
    Test that environment variables override default values.
    """
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEBUG", "1")  # `1` translates to True
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    monkeypatch.setenv("API_TIMEOUT", "60")

    overridden_config = AppConfig()  # Explicitly instantiate a new config instance

    assert overridden_config.APP_ENV == "production"
    assert overridden_config.DEBUG is True
    assert overridden_config.LOG_LEVEL == "WARNING"
    assert overridden_config.API_TIMEOUT == 60


def test_config_invalid_log_level():
    """
    Test that invalid log levels raise a ValidationError.
    """
    with pytest.raises(ValidationError):
        AppConfig(LOG_LEVEL="INVALID")


def test_config_partial_override(monkeypatch):
    """
    Test that partial environment variables override defaults while others remain.
    """
    monkeypatch.setenv("LOG_LEVEL", "ERROR")

    overridden_config = AppConfig()  # Explicitly instantiate a new config instance

    assert overridden_config.LOG_LEVEL == "ERROR"
    assert overridden_config.APP_ENV == "development"  # Default
    assert overridden_config.DEBUG is False  # Default
    assert overridden_config.API_TIMEOUT == 30  # Default


def test_env_file_loading(tmp_path, monkeypatch):
    """
    Test that values from a .env file are correctly loaded.
    """
    # Create a temporary .env file
    env_file = tmp_path / ".env"
    env_file.write_text(
        "APP_ENV=testing\nDEBUG=true\nLOG_LEVEL=CRITICAL\nAPI_TIMEOUT=120"
    )

    # Instantiate a new config instance, explicitly specifying the env_file
    env_config = AppConfig(_env_file=str(env_file))

    # Assert the values from the .env file
    assert env_config.APP_ENV == "testing"
    assert env_config.DEBUG is True
    assert env_config.LOG_LEVEL == "CRITICAL"
    assert env_config.API_TIMEOUT == 120

