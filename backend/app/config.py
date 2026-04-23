from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/videosync"

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"

    # Storage
    storage_base: str = "./storage"

    # Upload limits
    max_upload_size_mb: int = 500

    # Expected camera count per session (can also be set per-session in DB)
    default_camera_count: int = 3

    # Security
    secret_key: str = "change-me-in-production"

    # CORS
    cors_origins: str | list[str] = ["*"]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
