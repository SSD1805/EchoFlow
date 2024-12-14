# src/core/config.py
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class AppConfig(BaseSettings):
    """
    Centralized configuration class for the EchoFlow application.
    Reads environment variables or falls back to defaults.
    """

    # General application settings
    APP_ENV: str = Field(default="development", description="Application environment")
    DEBUG: bool = Field(default=False, description="Enable debug mode")

    # Database configuration
    DATABASE_URL: str | None = Field(default=None, description="Database connection URL")

    # Task queue configuration
    CELERY_BROKER_URL: str | None = Field(default=None, description="Celery broker URL")

    # Django settings
    DJANGO_SECRET_KEY: str | None = Field(default=None, description="Django secret key")

    # Logging settings
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")

    @field_validator("LOG_LEVEL")
    def validate_log_level(cls, value: str) -> str:
        """Validate that the log level is one of the allowed options."""
        allowed_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if value.upper() not in allowed_levels:
            raise ValueError(f"Invalid LOG_LEVEL: {value}. Must be one of {allowed_levels}.")
        return value.upper()

    # Extra configuration (if needed)
    API_TIMEOUT: int = Field(default=30, description="Default timeout for API requests in seconds")

    class Config:
        env_file = ".env"  # Load values from a .env file
        env_file_encoding = "utf-8"  # Specify encoding for the .env file


# Instantiate and expose the configuration object
config = AppConfig()
