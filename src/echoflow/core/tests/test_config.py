import pytest
from platformdirs import PlatformDirs
from pydantic import ValidationError

from echoflow.core.config import AppConfig, _platform_dirs
from echoflow.core.errors import ConfigurationError
from echoflow.core.privacy import PathDisclosure
from echoflow.runner.models import ProcessingProfile


def test_local_defaults_are_valid():
    config = AppConfig(_env_file=None)
    assert config.APP_ENV == "development"
    assert config.DEBUG is False
    assert config.LOG_LEVEL == "INFO"
    assert config.LOG_PATHS is PathDisclosure.REDACT
    assert config.PROCESSING_PROFILE is ProcessingProfile.BALANCED
    assert config.MAX_CPU_THREADS is None
    assert config.MAX_MEMORY_BYTES is None
    assert config.MEMORY_BUDGET_FRACTION == 0.75
    assert config.MIN_FREE_DISK_BYTES == 512 * 1024 * 1024
    assert config.WARN_FREE_DISK_BYTES == 2 * 1024 * 1024 * 1024
    assert config.FFMPEG_TIMEOUT_SECONDS == 2.0
    assert config.FFPROBE_TIMEOUT_SECONDS == 30.0
    assert config.FFMPEG_PROCESS_TIMEOUT_SECONDS == 3_600.0
    assert config.PYANNOTE_MODEL_ID == "pyannote/speaker-diarization-community-1"
    assert config.PYANNOTE_MODEL_REVISION is None
    assert "FASTER_WHISPER_MODEL_REVISION" not in AppConfig.model_fields
    platform_paths = PlatformDirs("EchoFlow", appauthor=False)
    assert platform_paths.user_state_path == config.STATE_DIR
    assert platform_paths.user_cache_path == config.CACHE_DIR
    assert platform_paths.user_cache_path / "models" == config.MODEL_DIR
    assert platform_paths.user_downloads_path / "EchoFlow" == config.OUTPUT_DIR
    assert config.WARN_FREE_DISK_BYTES >= config.MIN_FREE_DISK_BYTES
    assert _platform_dirs().appauthor is False
    assert AppConfig.model_config["env_file"] is None
    assert AppConfig.model_config["env_ignore_empty"] is True


def test_environment_overrides_local_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("ECHOFLOW_APP_ENV", "production")
    monkeypatch.setenv("ECHOFLOW_DEBUG", "true")
    monkeypatch.setenv("ECHOFLOW_LOG_LEVEL", "warning")
    monkeypatch.setenv("ECHOFLOW_LOG_PATHS", "full")
    monkeypatch.setenv("ECHOFLOW_PROCESSING_PROFILE", "screening")
    monkeypatch.setenv("ECHOFLOW_MAX_CPU_THREADS", "3")
    monkeypatch.setenv("ECHOFLOW_MAX_MEMORY_BYTES", "4096")
    monkeypatch.setenv("ECHOFLOW_MEMORY_BUDGET_FRACTION", "0.5")
    monkeypatch.setenv("ECHOFLOW_FFPROBE_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("ECHOFLOW_FFMPEG_PROCESS_TIMEOUT_SECONDS", "900")
    monkeypatch.setenv("ECHOFLOW_PYANNOTE_MODEL_ID", "example/local-diarizer")
    monkeypatch.setenv("ECHOFLOW_PYANNOTE_MODEL_REVISION", "speaker-revision")
    monkeypatch.setenv("ECHOFLOW_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ECHOFLOW_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("ECHOFLOW_MODEL_DIR", str(tmp_path / "cache" / "models"))
    monkeypatch.setenv("ECHOFLOW_OUTPUT_DIR", str(tmp_path / "output"))
    config = AppConfig(_env_file=None)
    assert config.APP_ENV == "production"
    assert config.DEBUG is True
    assert config.LOG_LEVEL == "WARNING"
    assert config.LOG_PATHS is PathDisclosure.FULL
    assert config.PROCESSING_PROFILE is ProcessingProfile.SCREENING
    assert config.MAX_CPU_THREADS == 3
    assert config.MAX_MEMORY_BYTES == 4096
    assert config.MEMORY_BUDGET_FRACTION == 0.5
    assert config.FFPROBE_TIMEOUT_SECONDS == 45.0
    assert config.FFMPEG_PROCESS_TIMEOUT_SECONDS == 900.0
    assert config.PYANNOTE_MODEL_ID == "example/local-diarizer"
    assert config.PYANNOTE_MODEL_REVISION == "speaker-revision"
    assert tmp_path / "state" == config.STATE_DIR
    assert tmp_path / "cache" == config.CACHE_DIR
    assert tmp_path / "cache" / "models" == config.MODEL_DIR
    assert tmp_path / "output" == config.OUTPUT_DIR


def test_obsolete_asr_revision_environment_override_is_ignored(monkeypatch):
    monkeypatch.setenv("ECHOFLOW_FASTER_WHISPER_MODEL_REVISION", "unmanaged")
    config = AppConfig(_env_file=None)
    assert "FASTER_WHISPER_MODEL_REVISION" not in config.model_fields
    assert "unmanaged" not in config.model_dump().values()


def test_model_directory_follows_an_overridden_cache_by_default(tmp_path):
    config = AppConfig(CACHE_DIR=tmp_path / "cache", _env_file=None)
    assert tmp_path / "cache" / "models" == config.MODEL_DIR


def test_model_directory_follows_environment_cache_override(monkeypatch, tmp_path):
    monkeypatch.setenv("ECHOFLOW_CACHE_DIR", str(tmp_path / "environment-cache"))
    config = AppConfig(_env_file=None)
    assert tmp_path / "environment-cache" / "models" == config.MODEL_DIR


@pytest.mark.parametrize("log_level", ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
def test_each_supported_log_level_is_a_stable_wire_value(log_level):
    assert log_level == AppConfig(LOG_LEVEL=log_level.lower(), _env_file=None).LOG_LEVEL


@pytest.mark.parametrize("log_level", ["TRACE", "", "fatal"])
def test_invalid_log_levels_are_rejected(log_level):
    with pytest.raises(ValidationError) as error:
        AppConfig(LOG_LEVEL=log_level, _env_file=None)
    assert (
        str(error.value.errors()[0]["ctx"]["error"])
        == f"Invalid LOG_LEVEL: {log_level}. Must be one of: "
        "DEBUG, INFO, WARNING, ERROR, CRITICAL"
    )


def test_warning_threshold_cannot_be_lower_than_required_threshold():
    with pytest.raises(ValidationError) as error:
        AppConfig(
            MIN_FREE_DISK_BYTES=20,
            WARN_FREE_DISK_BYTES=19,
            _env_file=None,
        )
    assert str(error.value.errors()[0]["ctx"]["error"]) == (
        "WARN_FREE_DISK_BYTES must be greater than or equal to MIN_FREE_DISK_BYTES"
    )


def test_local_paths_expand_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
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


def test_unprefixed_environment_and_ambient_dotenv_are_ignored(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("ECHOFLOW_LOG_LEVEL=CRITICAL\n")
    monkeypatch.setenv("LOG_LEVEL", "ERROR")
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "wrong-output"))

    config = AppConfig()

    assert config.LOG_LEVEL == "INFO"
    assert tmp_path / "wrong-output" != config.OUTPUT_DIR


def test_empty_namespaced_environment_value_uses_default(monkeypatch):
    monkeypatch.setenv("ECHOFLOW_LOG_LEVEL", "")
    assert AppConfig().LOG_LEVEL == "INFO"


def test_load_without_file_uses_the_same_nonambient_sources(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("ECHOFLOW_LOG_LEVEL=CRITICAL\n")
    assert AppConfig.load().LOG_LEVEL == "INFO"


def test_explicit_dotenv_is_loaded_but_environment_still_wins(monkeypatch, tmp_path):
    config_file = tmp_path / "research.env"
    config_file.write_text(
        "ECHOFLOW_LOG_LEVEL=WARNING\n"
        "ECHOFLOW_PROCESSING_PROFILE=screening\n"
        f"ECHOFLOW_OUTPUT_DIR={tmp_path / 'from-file'}\n"
    )
    monkeypatch.setenv("ECHOFLOW_LOG_LEVEL", "ERROR")

    config = AppConfig.load(config_file)

    assert config.LOG_LEVEL == "ERROR"
    assert config.PROCESSING_PROFILE is ProcessingProfile.SCREENING
    assert tmp_path / "from-file" == config.OUTPUT_DIR


def test_explicit_configuration_file_must_exist(tmp_path):
    with pytest.raises(ConfigurationError) as error:
        AppConfig.load(tmp_path / "missing.env")
    assert str(error.value) == "EchoFlow configuration file is unavailable: missing.env"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("MAX_CPU_THREADS", 0),
        ("MAX_MEMORY_BYTES", 0),
        ("MEMORY_BUDGET_FRACTION", 0),
        ("MEMORY_BUDGET_FRACTION", 1.01),
    ],
)
def test_invalid_resource_policy_values_are_rejected(field, value):
    with pytest.raises(ValidationError):
        AppConfig(**{field: value}, _env_file=None)


def test_resource_and_diagnostic_lower_boundaries_are_exact():
    config = AppConfig(
        MAX_CPU_THREADS=1,
        MAX_MEMORY_BYTES=1,
        MIN_FREE_DISK_BYTES=0,
        WARN_FREE_DISK_BYTES=0,
        FFMPEG_TIMEOUT_SECONDS=0.001,
        FFPROBE_TIMEOUT_SECONDS=0.001,
        FFMPEG_PROCESS_TIMEOUT_SECONDS=0.001,
        _env_file=None,
    )
    assert config.MAX_CPU_THREADS == 1
    assert config.MAX_MEMORY_BYTES == 1
    assert config.MIN_FREE_DISK_BYTES == 0
    assert config.WARN_FREE_DISK_BYTES == 0
    assert config.FFMPEG_TIMEOUT_SECONDS == 0.001
    assert config.FFPROBE_TIMEOUT_SECONDS == 0.001
    assert config.FFMPEG_PROCESS_TIMEOUT_SECONDS == 0.001

    for invalid in (
        {"MIN_FREE_DISK_BYTES": -1},
        {"WARN_FREE_DISK_BYTES": -1, "MIN_FREE_DISK_BYTES": 0},
        {"FFMPEG_TIMEOUT_SECONDS": -0.5},
        {"FFPROBE_TIMEOUT_SECONDS": 0},
        {"FFMPEG_PROCESS_TIMEOUT_SECONDS": 0},
        {"PYANNOTE_MODEL_ID": ""},
        {"PYANNOTE_MODEL_REVISION": ""},
    ):
        with pytest.raises(ValidationError):
            AppConfig(**invalid, _env_file=None)


def test_explicit_model_directory_is_not_replaced_by_cache_default(tmp_path):
    selected = tmp_path / "selected-models"
    config = AppConfig(CACHE_DIR=tmp_path / "cache", MODEL_DIR=selected, _env_file=None)
    assert selected == config.MODEL_DIR


def test_model_validator_returns_the_validated_instance():
    config = AppConfig(_env_file=None)
    assert config.validate_disk_thresholds() is config


def test_configuration_field_descriptions_are_stable_public_schema():
    descriptions = {
        name: field.description for name, field in AppConfig.model_fields.items()
    }
    assert descriptions == {
        "APP_ENV": "Application environment",
        "DEBUG": "Enable debug mode",
        "LOG_LEVEL": "Logging level",
        "LOG_PATHS": "Whether routine logs may disclose local filesystem paths",
        "PROCESSING_PROFILE": "Default processing intent used for resource planning",
        "MAX_CPU_THREADS": (
            "Optional ceiling on CPU threads used by one processing job"
        ),
        "MAX_MEMORY_BYTES": (
            "Optional ceiling on memory budgeted to one processing job"
        ),
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
            "Maximum time allowed for one audio-processing process"
        ),
        "PYANNOTE_MODEL_ID": "Optional local speaker-diarization model identifier",
        "PYANNOTE_MODEL_REVISION": "Optional immutable pyannote model revision",
    }
