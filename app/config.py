"""Application settings loaded from environment variables.

Uses pydantic-settings BaseSettings to read from .env file and
environment variables. Settings are cached via @lru_cache so the
.env file is only read once per process.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration.

    Attributes:
        DATABASE_URL: Async PostgreSQL connection string.
        LOG_LEVEL: Python logging level name. Defaults to "INFO".
        API_KEY: Secret key for X-API-Key header authentication. Defaults to "changeme".
        SIGNING_SECRET: HMAC-SHA256 key for signed URL tokens. Required.
        UPLOAD_DIR: Directory path for storing uploaded files. Defaults to "./uploads".
        MAX_FILE_SIZE: Maximum allowed upload size in bytes. Defaults to 10 MB.
    """

    DATABASE_URL: str
    LOG_LEVEL: str = "INFO"
    API_KEY: str = "changeme"
    SIGNING_SECRET: str
    UPLOAD_DIR: str = "./uploads"
    MAX_FILE_SIZE: int = 10485760

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings.

    Returns:
        Settings: The application settings instance, loaded once and cached.
    """
    return Settings()
