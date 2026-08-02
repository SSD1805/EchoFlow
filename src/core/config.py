# src/core/config.py
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    """
    Centralized configuration class for the EchoFlow application.
    Reads environment variables or falls back to defaults.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # General application settings
    APP_ENV: str = Field(default="development", description="Application environment")
    DEBUG: bool = Field(default=False, description="Enable debug mode")

    # Logging settings
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")

    # Local application settings
    WORKSPACE_DIR: Path = Field(
        default=Path("~/.echoflow"), description="Local EchoFlow workspace"
    )
    MIN_FREE_DISK_BYTES: int = Field(
        default=512 * 1024 * 1024, ge=0, description="Required free disk space"
    )
    WARN_FREE_DISK_BYTES: int = Field(
        default=2 * 1024 * 1024 * 1024,
        ge=0,
        description="Recommended free disk space",
    )
    FFMPEG_TIMEOUT_SECONDS: float = Field(default=2.0, gt=0)

    @field_validator("LOG_LEVEL")
    def validate_log_level(cls, value: str) -> str:
        """Validate that the log level is one of the allowed options."""
        allowed_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if value.upper() not in allowed_levels:
            raise ValueError(
                f"Invalid LOG_LEVEL: {value}. Must be one of {allowed_levels}."
            )
        return value.upper()

    @field_validator("WORKSPACE_DIR", mode="before")
    @classmethod
    def expand_workspace(cls, value: str | Path) -> Path:
        return Path(value).expanduser()

    @model_validator(mode="after")
    def validate_disk_thresholds(self) -> "AppConfig":
        if self.WARN_FREE_DISK_BYTES < self.MIN_FREE_DISK_BYTES:
            raise ValueError(
                "WARN_FREE_DISK_BYTES must be greater than or equal to "
                "MIN_FREE_DISK_BYTES"
            )
        return self
