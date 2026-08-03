from pathlib import Path

from platformdirs import PlatformDirs
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from echoflow.core.errors import ConfigurationError
from echoflow.core.privacy import PathDisclosure
from echoflow.runner.models import ProcessingProfile

APP_NAME = "EchoFlow"
_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def _platform_dirs() -> PlatformDirs:
    return PlatformDirs(APP_NAME, appauthor=False)


def _default_state_dir() -> Path:
    return _platform_dirs().user_state_path


def _default_cache_dir() -> Path:
    return _platform_dirs().user_cache_path


def _default_model_dir() -> Path:
    return _default_cache_dir() / "models"


def _default_output_dir() -> Path:
    return _platform_dirs().user_downloads_path / APP_NAME


class AppConfig(BaseSettings):
    """
    Centralized configuration class for the EchoFlow application.
    Reads explicitly namespaced environment variables or falls back to defaults.
    """

    model_config = SettingsConfigDict(
        env_prefix="ECHOFLOW_",
        env_file=None,
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    # General application settings
    APP_ENV: str = Field(default="development", description="Application environment")
    DEBUG: bool = Field(default=False, description="Enable debug mode")

    # Logging settings
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    LOG_PATHS: PathDisclosure = Field(
        default=PathDisclosure.REDACT,
        description="Whether routine logs may disclose local filesystem paths",
    )

    # Resource-policy settings
    PROCESSING_PROFILE: ProcessingProfile = Field(
        default=ProcessingProfile.BALANCED,
        description="Default processing intent used for resource planning",
    )
    MAX_CPU_THREADS: int | None = Field(
        default=None,
        ge=1,
        description="Optional ceiling on CPU threads used by one processing job",
    )
    MAX_MEMORY_BYTES: int | None = Field(
        default=None,
        ge=1,
        description="Optional ceiling on memory budgeted to one processing job",
    )
    MEMORY_BUDGET_FRACTION: float = Field(
        default=0.75,
        gt=0,
        le=1,
        description="Fraction of currently available memory a job may budget",
    )

    # Local application settings
    STATE_DIR: Path = Field(
        default_factory=_default_state_dir,
        description="Private application state and job workspace",
    )
    CACHE_DIR: Path = Field(
        default_factory=_default_cache_dir,
        description="Private disposable application cache",
    )
    MODEL_DIR: Path = Field(
        default_factory=_default_model_dir,
        description="Private downloaded-model cache",
    )
    OUTPUT_DIR: Path = Field(
        default_factory=_default_output_dir,
        description="Default directory for user-visible artifacts",
    )
    MIN_FREE_DISK_BYTES: int = Field(
        default=512 * 1024 * 1024, ge=0, description="Required free disk space"
    )
    WARN_FREE_DISK_BYTES: int = Field(
        default=2 * 1024 * 1024 * 1024,
        description="Recommended free disk space",
    )
    FFMPEG_TIMEOUT_SECONDS: float = Field(default=2.0, gt=0)
    FFPROBE_TIMEOUT_SECONDS: float = Field(
        default=30.0,
        gt=0,
        description="Maximum time allowed for dry-run media inspection",
    )

    @field_validator("LOG_LEVEL")
    def validate_log_level(cls, value: str) -> str:
        """Validate that the log level is one of the allowed options."""
        if value.upper() not in _LOG_LEVELS:
            raise ValueError(
                f"Invalid LOG_LEVEL: {value}. Must be one of: {', '.join(_LOG_LEVELS)}"
            )
        return value.upper()

    @field_validator("STATE_DIR", "CACHE_DIR", "MODEL_DIR", "OUTPUT_DIR", mode="before")
    @classmethod
    def expand_local_path(cls, value: str | Path) -> Path:
        return Path(value).expanduser().resolve(strict=False)

    @model_validator(mode="after")
    def validate_disk_thresholds(self) -> "AppConfig":
        if (
            "CACHE_DIR" in self.model_fields_set
            and "MODEL_DIR" not in self.model_fields_set
        ):
            self.MODEL_DIR = (self.CACHE_DIR / "models").resolve(strict=False)
        if self.WARN_FREE_DISK_BYTES < self.MIN_FREE_DISK_BYTES:
            raise ValueError(
                "WARN_FREE_DISK_BYTES must be greater than or equal to "
                "MIN_FREE_DISK_BYTES"
            )
        return self

    @classmethod
    def load(cls, config_file: str | Path | None = None) -> "AppConfig":
        """Load defaults and environment, plus one explicitly selected dotenv file."""
        if config_file is None:
            return cls()
        path = Path(config_file).expanduser().resolve(strict=False)
        if not path.is_file():
            raise ConfigurationError(
                f"EchoFlow configuration file is unavailable: {path.name}"
            )
        return cls(_env_file=path)  # type: ignore[call-arg]
