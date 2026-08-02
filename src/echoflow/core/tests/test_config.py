import pytest
from platformdirs import PlatformDirs
from pydantic import ValidationError

from echoflow.core.config import AppConfig


def test_local_defaults_are_valid():
    config = AppConfig(_env_file=None)
    assert config.APP_ENV == "development"
    assert config.DEBUG is False
    assert config.LOG_LEVEL == "INFO"
    platform_paths = PlatformDirs("EchoFlow", appauthor=False)
    assert platform_paths.user_state_path == config.STATE_DIR
    assert platform_paths.user_cache_path == config.CACHE_DIR
    assert platform_paths.user_cache_path / "models" == config.MODEL_DIR
    assert platform_paths.user_downloads_path / "EchoFlow" == config.OUTPUT_DIR
    assert config.WARN_FREE_DISK_BYTES >= config.MIN_FREE_DISK_BYTES


def test_environment_overrides_local_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("LOG_LEVEL", "warning")
    monkeypatch.setenv("STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("MODEL_DIR", str(tmp_path / "cache" / "models"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    config = AppConfig(_env_file=None)
    assert config.APP_ENV == "production"
    assert config.DEBUG is True
    assert config.LOG_LEVEL == "WARNING"
    assert tmp_path / "state" == config.STATE_DIR
    assert tmp_path / "cache" == config.CACHE_DIR
    assert tmp_path / "cache" / "models" == config.MODEL_DIR
    assert tmp_path / "output" == config.OUTPUT_DIR


def test_model_directory_follows_an_overridden_cache_by_default(tmp_path):
    config = AppConfig(CACHE_DIR=tmp_path / "cache", _env_file=None)
    assert tmp_path / "cache" / "models" == config.MODEL_DIR


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


def test_local_paths_expand_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    config = AppConfig(
        STATE_DIR="~/state",
        CACHE_DIR="~/cache",
        MODEL_DIR="~/cache/models",
        OUTPUT_DIR="~/Downloads/EchoFlow",
        _env_file=None,
    )
    assert tmp_path / "state" == config.STATE_DIR
    assert tmp_path / "cache/models" == config.MODEL_DIR
    assert tmp_path / "Downloads/EchoFlow" == config.OUTPUT_DIR
