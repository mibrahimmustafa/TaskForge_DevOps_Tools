from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class JobStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    RUNNING = "running"  # Legacy read compatibility.
    FAILED = "failed"


class TriggerType(str, Enum):
    MANUAL = "manual"
    CRON = "cron"
    INTERVAL = "interval"
    WEBHOOK = "webhook"
    EVENT = "event"
    ONESHOT = "oneshot"


class ExecutorType(str, Enum):
    SHELL = "shell"
    PYTHON = "python"
    HTTP = "http"
    DOCKER = "docker"


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    LOST = "lost"
    WAITING = "waiting_approval"


class Job(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,99}$")
    project: str = Field(default="default", pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    name: str = Field(min_length=1, max_length=150)
    description: str = Field(default="", max_length=2000)
    trigger: TriggerType = TriggerType.CRON
    trigger_expr: str = "0 0 * * *"
    timezone: str = "UTC"
    executor: ExecutorType = ExecutorType.SHELL
    command: str = Field(default="echo 'Hello from TaskForge'", max_length=100000)
    image: str | None = None
    args: list[str] = Field(default_factory=list)
    secret_refs: list[str] = Field(default_factory=list)
    artifact_paths: list[str] = Field(default_factory=list)
    status: JobStatus = JobStatus.ACTIVE
    tags: list[str] = Field(default_factory=list, max_length=30)
    timeout_seconds: int = Field(default=300, ge=1, le=86400)
    max_retries: int = Field(default=0, ge=0, le=10)
    retry_delay_seconds: int = Field(default=5, ge=1, le=3600)
    webhook_secret: str | None = Field(default=None, min_length=32)
    version: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=utc_now)
    next_run: str | None = None
    last_run: str | None = None
    last_duration: str | None = None
    last_status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = self.model_dump(mode="json", exclude={"webhook_secret"})
        data.update(
            desc=self.description,
            triggerExpr=self.trigger_expr,
            nextRun=self.next_run,
            lastRun=self.last_run,
            lastDuration=self.last_duration,
            lastStatus=self.last_status,
            has_webhook_secret=bool(self.webhook_secret),
        )
        return data


class JobRun(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str
    job_id: str = Field(default="", validation_alias="jobId")
    job_name: str = Field(default="", validation_alias="jobName")
    status: RunStatus = RunStatus.RUNNING
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None
    duration_seconds: float = 0
    duration_str: str = "0s"
    trigger_type: str = "manual"
    exit_code: int = 0
    logs: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "jobId": self.job_id,
            "jobName": self.job_name,
            "status": self.status.value,
            "started": self.started_at.isoformat(),
            "finished": self.finished_at.isoformat() if self.finished_at else None,
            "duration": self.duration_str,
            "trigger": self.trigger_type,
            "exitCode": self.exit_code,
            "logs": self.logs,
        }


class PipelineStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,99}$")
    needs: list[str] = Field(default_factory=list)
    job: Job


class Pipeline(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,99}$")
    project: str = Field(default="default", pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    name: str = Field(min_length=1, max_length=150)
    description: str = ""
    version: int = 0
    repository: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    branch: str = "main"
    steps: list[PipelineStep] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def validate_graph(self):
        ids = {step.id for step in self.steps}
        if len(ids) != len(self.steps):
            raise ValueError("Step IDs must be unique")
        resolved: set[str] = set()
        for step in self.steps:
            if set(step.needs) - ids:
                raise ValueError(f"Unknown dependency in {step.id}")
            if step.job.project != self.project:
                raise ValueError("Step project must match pipeline project")
        while len(resolved) < len(ids):
            ready = {step.id for step in self.steps if set(step.needs) <= resolved} - resolved
            if not ready:
                raise ValueError("Pipeline dependencies contain a cycle")
            resolved.update(ready)
        return self
