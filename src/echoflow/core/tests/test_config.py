from pathlib import Path

import pytest
from pydantic import ValidationError

from echoflow.core.config import AppConfig


def test_local_defaults_are_valid():
    config = AppConfig(_env_file=None)
    assert config.APP_ENV == "development"
    assert config.DEBUG is False
    assert config.LOG_LEVEL == "INFO"
    assert Path.home() / ".echoflow" == config.WORKSPACE_DIR
    assert config.WARN_FREE_DISK_BYTES >= config.MIN_FREE_DISK_BYTES


def test_environment_overrides_local_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("LOG_LEVEL", "warning")
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path))
    config = AppConfig(_env_file=None)
    assert config.APP_ENV == "production"
    assert config.DEBUG is True
    assert config.LOG_LEVEL == "WARNING"
    assert tmp_path == config.WORKSPACE_DIR


@pytest.mark.parametrize("log_level", ["TRACE", "", "fatal"])
def test_invalid_log_levels_are_rejected(log_level):
    with pytest.raises(ValidationError):
        AppConfig(LOG_LEVEL=log_level, _env_file=None)


def test_warning_threshold_cannot_be_lower_than_required_threshold():
    with pytest.raises(ValidationError, match="WARN_FREE_DISK_BYTES"):
        AppConfig(
            MIN_FREE_DISK_BYTES=20,
            WARN_FREE_DISK_BYTES=19,
            _env_file=None,
        )


def test_workspace_expands_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    config = AppConfig(WORKSPACE_DIR="~/audio", _env_file=None)
    assert tmp_path / "audio" == config.WORKSPACE_DIR
