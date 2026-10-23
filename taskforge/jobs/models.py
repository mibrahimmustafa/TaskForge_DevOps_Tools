from datetime import datetime
from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field

class JobStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    RUNNING = "running"
    FAILED = "failed"

class TriggerType(str, Enum):
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
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"

class JobRun(BaseModel):
    id: str
    job_id: str = Field(alias="jobId", default="")
    job_name: str = Field(alias="jobName", default="")
    status: RunStatus = RunStatus.RUNNING
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None
    duration_seconds: float = 0.0
    duration_str: str = "0s"
    trigger_type: str = "manual"
    exit_code: int = 0
    logs: str = ""

    class Config:
        populate_by_name = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "jobId": self.job_id,
            "jobName": self.job_name,
            "status": self.status.value,
            "started": self.started_at.strftime("%Y-%m-%d %H:%M:%S"),
            "finished": self.finished_at.strftime("%Y-%m-%d %H:%M:%S") if self.finished_at else None,
            "duration": self.duration_str,
            "trigger": self.trigger_type,
            "exitCode": self.exit_code,
            "logs": self.logs
        }

class Job(BaseModel):
    id: str
    name: str
    description: str = ""
    trigger: TriggerType = TriggerType.CRON
    trigger_expr: str = "0 0 * * *"
    executor: ExecutorType = ExecutorType.SHELL
    command: str = "echo 'Hello from TaskForge'"
    status: JobStatus = JobStatus.ACTIVE
    tags: list[str] = Field(default_factory=list)
    timeout_seconds: int = 300
    max_retries: int = 3
    retry_delay_seconds: int = 5
    webhook_secret: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    next_run: Optional[str] = None
    last_run: Optional[str] = None
    last_duration: Optional[str] = None
    last_status: Optional[str] = None

    class Config:
        populate_by_name = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "desc": self.description,
            "description": self.description,
            "trigger": self.trigger.value,
            "triggerExpr": self.trigger_expr,
            "trigger_expr": self.trigger_expr,
            "executor": self.executor.value,
            "command": self.command,
            "status": self.status.value,
            "tags": self.tags,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "retry_delay_seconds": self.retry_delay_seconds,
            "webhook_secret": self.webhook_secret,
            "nextRun": self.next_run or "Not scheduled",
            "lastRun": self.last_run or "Never",
            "lastDuration": self.last_duration or "—",
            "lastStatus": self.last_status or "—"
        }
