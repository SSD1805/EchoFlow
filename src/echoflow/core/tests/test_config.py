from pathlib import Path

import pytest
from pydantic import ValidationError

from echoflow.core.config import AppConfig
from echoflow.core.errors import ConfigurationError
from echoflow.core.privacy import PathDisclosure
from echoflow.runner.models import ProcessingProfile


def test_defaults_are_namespaced_and_private_by_default(monkeypatch):
    monkeypatch.delenv("ECHOFLOW_LOG_PATHS", raising=False)
    config = AppConfig()
    assert config.LOG_PATHS is PathDisclosure.REDACT
    assert config.PROCESSING_PROFILE is ProcessingProfile.BALANCED
    assert config.MODEL_DIR == config.CACHE_DIR / "models"


def test_environment_overrides_use_echoflow_prefix(monkeypatch, tmp_path):
    monkeypatch.setenv("ECHOFLOW_LOG_LEVEL", "debug")
    monkeypatch.setenv("ECHOFLOW_LOG_PATHS", "full")
    monkeypatch.setenv("ECHOFLOW_PROCESSING_PROFILE", "accuracy")
    monkeypatch.setenv("ECHOFLOW_MAX_CPU_THREADS", "4")
    monkeypatch.setenv("ECHOFLOW_STATE_DIR", str(tmp_path / "state"))
    config = AppConfig()
    assert config.LOG_LEVEL == "DEBUG"
    assert config.LOG_PATHS is PathDisclosure.FULL
    assert config.PROCESSING_PROFILE is ProcessingProfile.ACCURACY
    assert config.MAX_CPU_THREADS == 4
    assert config.STATE_DIR == (tmp_path / "state").resolve()


def test_cache_override_moves_default_model_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("ECHOFLOW_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("ECHOFLOW_MODEL_DIR", raising=False)
    config = AppConfig()
    assert config.CACHE_DIR == (tmp_path / "cache").resolve()
    assert config.MODEL_DIR == (tmp_path / "cache" / "models").resolve()


def test_explicit_model_directory_is_not_rewritten_by_cache_override(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ECHOFLOW_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("ECHOFLOW_MODEL_DIR", str(tmp_path / "custom-models"))
    config = AppConfig()
    assert config.MODEL_DIR == (tmp_path / "custom-models").resolve()


def test_load_accepts_explicit_dotenv_file(tmp_path):
    config_file = tmp_path / "echoflow.env"
    config_file.write_text("ECHOFLOW_LOG_LEVEL=warning\n")
    config = AppConfig.load(config_file)
    assert config.LOG_LEVEL == "WARNING"


def test_load_rejects_missing_explicit_config_file(tmp_path):
    with pytest.raises(ConfigurationError, match="configuration file is unavailable"):
        AppConfig.load(tmp_path / "missing.env")


def test_invalid_log_level_is_rejected():
    with pytest.raises(ValidationError):
        AppConfig(LOG_LEVEL="verbose")


def test_disk_warning_threshold_cannot_be_below_minimum():
    with pytest.raises(ValidationError):
        AppConfig(MIN_FREE_DISK_BYTES=10, WARN_FREE_DISK_BYTES=9)


def test_resource_limits_validate_positive_values():
    with pytest.raises(ValidationError):
        AppConfig(MAX_CPU_THREADS=0)
    with pytest.raises(ValidationError):
        AppConfig(MAX_MEMORY_BYTES=0)
    with pytest.raises(ValidationError):
        AppConfig(MEMORY_BUDGET_FRACTION=0)
    with pytest.raises(ValidationError):
        AppConfig(MEMORY_BUDGET_FRACTION=1.1)


def test_media_timeouts_validate_positive_values():
    with pytest.raises(ValidationError):
        AppConfig(FFMPEG_TIMEOUT_SECONDS=0)
    with pytest.raises(ValidationError):
        AppConfig(FFPROBE_TIMEOUT_SECONDS=0)
    with pytest.raises(ValidationError):
        AppConfig(FFMPEG_PROCESS_TIMEOUT_SECONDS=0)


def test_paths_expand_user(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    config = AppConfig(
        STATE_DIR="~/state",
        CACHE_DIR="~/cache",
        MODEL_DIR="~/models",
        OUTPUT_DIR="~/output",
    )
    assert config.STATE_DIR == (tmp_path / "state").resolve()
    assert config.CACHE_DIR == (tmp_path / "cache").resolve()
    assert config.MODEL_DIR == (tmp_path / "models").resolve()
    assert config.OUTPUT_DIR == (tmp_path / "output").resolve()


def test_path_fields_accept_path_objects(tmp_path):
    config = AppConfig(
        STATE_DIR=tmp_path / "state",
        CACHE_DIR=tmp_path / "cache",
        MODEL_DIR=tmp_path / "models",
        OUTPUT_DIR=tmp_path / "output",
    )
    assert isinstance(config.STATE_DIR, Path)
    assert isinstance(config.CACHE_DIR, Path)
    assert isinstance(config.MODEL_DIR, Path)
    assert isinstance(config.OUTPUT_DIR, Path)


def test_schema_descriptions_remain_stable():
    descriptions = {
        name: field.description for name, field in AppConfig.model_fields.items()
    }
    assert descriptions == {
        "APP_ENV": "Application environment",
        "DEBUG": "Enable debug mode",
        "LOG_LEVEL": "Logging level",
        "LOG_PATHS": "Whether routine logs may disclose local filesystem paths",
        "PROCESSING_PROFILE": "Default processing intent used for resource planning",
        "MAX_CPU_THREADS": "Optional ceiling on CPU threads used by one processing job",
        "MAX_MEMORY_BYTES": "Optional ceiling on memory budgeted to one processing job",
        "MEMORY_BUDGET_FRACTION": (
            "Fraction of currently available memory a job may budget"
        ),
        "STATE_DIR": "Private application state and job workspace",
        "CACHE_DIR": "Private disposable application cache",
        "MODEL_DIR": "Private downloaded-model cache",
        "OUTPUT_DIR": "Default directory for user-visible artifacts",
        "MIN_FREE_DISK_BYTES": "Required free disk space",
        "WARN_FREE_DISK_BYTES": "Recommended free disk space",
        "FFMPEG_TIMEOUT_SECONDS": None,
        "FFPROBE_TIMEOUT_SECONDS": (
            "Maximum time allowed for dry-run media inspection"
        ),
        "FFMPEG_PROCESS_TIMEOUT_SECONDS": (
            "Maximum time allowed for one audio normalization process"
        ),
        "FASTER_WHISPER_MODEL_REVISION": (
            "Optional immutable model revision requested from the model hub"
        ),
        "PYANNOTE_MODEL_ID": ("Optional local speaker-diarization model identifier"),
        "PYANNOTE_MODEL_REVISION": "Optional immutable pyannote model revision",
    }
