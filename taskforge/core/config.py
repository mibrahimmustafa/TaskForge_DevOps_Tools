import json
import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field


class Settings(BaseModel):
    app_name: str = "TaskForge"
    app_version: str = "0.2.0"
    storage_url: str = "sqlite+aiosqlite:///taskforge.db"
    host: str = "127.0.0.1"
    port: int = 8080
    log_level: str = "info"
    metrics_enabled: bool = True
    cors_origins: list[str] = Field(default_factory=list)
    tokens: list[dict] = Field(default_factory=list, repr=False)
    data_dir: Path = Path(".taskforge")
    worker_concurrency: int = Field(default=2, ge=1, le=32)
    lease_seconds: int = Field(default=30, ge=6)
    allow_host_execution: bool = False
    allowed_http_hosts: list[str] = Field(default_factory=list)
    github_secret: str = Field(default="", repr=False)
    github_repositories: list[str] = Field(default_factory=list)
    deployment_targets: dict[str, dict] = Field(default_factory=dict)
    secrets: dict[str, str] = Field(default_factory=dict, repr=False)
    plugins: list[str] = Field(default_factory=list)
    notification_url: str = ""
    embedded_worker: bool = False  # Explicit development/test option only.


def get_settings() -> Settings:
    # Application factories and tests receive independent settings.
    load_dotenv(Path(".taskforge/config.env"), override=False)
    load_dotenv(override=False)
    values = {}
    for name in Settings.model_fields:
        raw = os.getenv(f"TASKFORGE_{name.upper()}")
        if raw is None:
            continue
        if name in {
            "tokens",
            "cors_origins",
            "allowed_http_hosts",
            "github_repositories",
            "deployment_targets",
            "secrets",
            "plugins",
        }:
            values[name] = json.loads(raw)
        else:
            values[name] = raw
    return Settings.model_validate(values)
