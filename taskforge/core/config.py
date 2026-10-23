import os
from pathlib import Path

from pydantic import BaseModel, Field


class Settings(BaseModel):
    app_name: str = "TaskForge"
    app_version: str = "0.1.0"
    secret_key: str = Field(
        default_factory=lambda: os.getenv(
            "TASKFORGE_SECRET_KEY", "taskforge-insecure-secret-key-change-in-prod"
        )
    )
    storage_url: str = Field(
        default_factory=lambda: os.getenv(
            "TASKFORGE_STORAGE_URL", "sqlite+aiosqlite:///taskforge.db"
        )
    )
    log_level: str = Field(default_factory=lambda: os.getenv("TASKFORGE_LOG_LEVEL", "info"))
    metrics_enabled: bool = Field(
        default_factory=lambda: (
            os.getenv("TASKFORGE_METRICS_ENABLED", "true").lower() in ("true", "1", "yes")
        )
    )
    host: str = Field(default_factory=lambda: os.getenv("TASKFORGE_HOST", "0.0.0.0"))
    port: int = Field(default_factory=lambda: int(os.getenv("TASKFORGE_PORT", "8080")))
    cors_origins: list[str] = ["*"]
    base_dir: Path = Path(__file__).resolve().parent.parent.parent


_settings = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
