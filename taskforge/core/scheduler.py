"""Submission and persisted schedule calculation; never execute workloads in the API."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfoNotFoundError

from taskforge.jobs.models import Job, JobStatus, Pipeline, TriggerType
from taskforge.storage.database import ConflictError, Database
from taskforge.triggers import get_trigger


def validate_job(job: Job):
    if job.status not in {JobStatus.ACTIVE, JobStatus.PAUSED}:
        raise ValueError("Job status must be active or paused")
    try:
        get_trigger(job.trigger, job.trigger_expr, job.timezone).to_apscheduler_trigger()
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise ValueError(f"Invalid schedule: {exc}") from exc
    if job.executor == "docker" and not job.image:
        raise ValueError("Docker jobs require an image")
    if job.trigger == TriggerType.WEBHOOK and not job.webhook_secret:
        raise ValueError("Webhook jobs require a secret of at least 32 characters")


def next_occurrence(job: Job, after: datetime | None = None):
    trigger = get_trigger(job.trigger, job.trigger_expr, job.timezone).to_apscheduler_trigger()
    if trigger is None:
        return None
    now = datetime.now(UTC)
    fire = trigger.get_next_fire_time(
        after, now if after is None else max(now, after + timedelta(microseconds=1))
    )
    return fire.isoformat() if fire else None


class TaskScheduler:
    def __init__(self, storage: Database):
        self.storage = storage

    async def add_or_update_job(self, job: Job):
        validate_job(job)
        job.next_run = next_occurrence(job) if job.status == JobStatus.ACTIVE else None
        saved = await self.storage.put("job", job.model_dump(mode="json"), job.version)
        return Job.model_validate(saved)

    async def submit(self, job: Job, trigger_type: str = "manual", dedupe: str | None = None):
        snapshot = job.model_dump(mode="json", exclude={"webhook_secret"})
        return await self.storage.enqueue(
            job.project,
            f"job:{job.project}:{job.id}",
            {"kind": "job", "definition": snapshot, "trigger": trigger_type},
            dedupe,
        )

    async def submit_pipeline(
        self, pipeline: Pipeline, commit: str | None = None, dedupe: str | None = None
    ):
        return await self.storage.enqueue(
            pipeline.project,
            f"pipeline:{pipeline.project}:{pipeline.id}",
            {"kind": "pipeline", "definition": pipeline.model_dump(mode="json"), "commit": commit},
            dedupe,
        )

    async def tick(self):
        for value in await self.storage.list("job", limit=10000):
            job = Job.model_validate(value)
            if job.status != JobStatus.ACTIVE or not job.next_run:
                continue
            due = datetime.fromisoformat(job.next_run)
            if due > datetime.now(UTC):
                continue
            # Enqueue first with a unique occurrence key. A crash before advancing the
            # schedule repeats the enqueue safely. Downtime coalesces to one occurrence.
            await self.submit(
                job, job.trigger.value, f"schedule:{job.id}:{job.version}:{due.isoformat()}"
            )
            job.next_run = next_occurrence(job, due)
            if job.trigger == TriggerType.ONESHOT:
                job.status = JobStatus.PAUSED
            try:
                await self.storage.put("job", job.model_dump(mode="json"), job.version)
            except ConflictError:
                pass  # A newer user edit wins.
