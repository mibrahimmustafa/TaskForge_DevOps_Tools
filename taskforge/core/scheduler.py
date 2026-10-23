import time
import uuid
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from taskforge.core.event_bus import event_bus
from taskforge.core.logging import logger
from taskforge.core.metrics import ACTIVE_JOBS_GAUGE, JOB_RUN_DURATION, JOB_RUNS_TOTAL
from taskforge.executors import get_executor
from taskforge.jobs.models import ExecutorType, Job, JobRun, JobStatus, RunStatus, TriggerType
from taskforge.storage.base import StorageBackend
from taskforge.triggers import get_trigger


class TaskScheduler:
    def __init__(self, storage: StorageBackend) -> None:
        self.storage = storage
        self.scheduler = AsyncIOScheduler()
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        await self.storage.initialize()
        self.scheduler.start()
        self._running = True
        logger.info("scheduler_started")

        # Load all jobs and schedule active ones
        jobs = await self.storage.get_all_jobs()
        if not jobs:
            # Seed default demo jobs if DB is brand new
            await self._seed_default_jobs()
            jobs = await self.storage.get_all_jobs()

        active_count = 0
        for job in jobs:
            if job.status == JobStatus.ACTIVE:
                self._schedule_job(job)
                active_count += 1
        ACTIVE_JOBS_GAUGE.set(active_count)

    async def shutdown(self) -> None:
        if self._running:
            self.scheduler.shutdown(wait=False)
            self._running = False
            logger.info("scheduler_shutdown")

    def _schedule_job(self, job: Job) -> None:
        # Remove existing if any
        if self.scheduler.get_job(job.id):
            self.scheduler.remove_job(job.id)

        trigger_obj = get_trigger(job.trigger, job.trigger_expr)
        aps_trigger = trigger_obj.to_apscheduler_trigger()

        if aps_trigger is not None:
            self.scheduler.add_job(
                func=self.execute_job_task,
                trigger=aps_trigger,
                id=job.id,
                name=job.name,
                kwargs={"job_id": job.id, "trigger_type": job.trigger.value},
                replace_existing=True,
            )
            # Update next_run preview
            aps_job = self.scheduler.get_job(job.id)
            if aps_job and aps_job.next_run_time:
                job.next_run = aps_job.next_run_time.strftime("%Y-%m-%d %H:%M:%S")

    async def execute_job_task(self, job_id: str, trigger_type: str = "manual") -> JobRun:
        job = await self.storage.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        run_id = f"run-{uuid.uuid4().hex[:8]}"
        run = JobRun(
            id=run_id,
            job_id=job.id,
            job_name=job.name,
            status=RunStatus.RUNNING,
            started_at=datetime.now(UTC),
            trigger_type=trigger_type,
        )
        await self.storage.save_run(run)

        # Set job status to running
        prev_status = job.status
        job.status = JobStatus.RUNNING
        await self.storage.save_job(job)

        await event_bus.emit("job.started", job=job, run=run)
        start_time = time.time()

        executor = get_executor(job.executor)
        exit_code, output_logs = await executor.execute(job)

        elapsed = time.time() - start_time
        duration_str = (
            f"{elapsed:.1f}s" if elapsed < 60 else f"{int(elapsed // 60)}m {int(elapsed % 60)}s"
        )

        run.finished_at = datetime.now(UTC)
        run.duration_seconds = elapsed
        run.duration_str = duration_str
        run.exit_code = exit_code
        run.logs = output_logs
        run.status = RunStatus.SUCCESS if exit_code == 0 else RunStatus.FAILED

        await self.storage.save_run(run)

        # Restore job status & stats
        job.status = JobStatus.ACTIVE if prev_status != JobStatus.PAUSED else JobStatus.PAUSED
        job.last_run = run.finished_at.strftime("%Y-%m-%d %H:%M:%S")
        job.last_duration = duration_str
        job.last_status = run.status.value

        # Update next_run time
        aps_job = self.scheduler.get_job(job.id)
        if aps_job and aps_job.next_run_time:
            job.next_run = aps_job.next_run_time.strftime("%Y-%m-%d %H:%M:%S")

        await self.storage.save_job(job)

        # Metrics
        JOB_RUNS_TOTAL.labels(job_id=job.id, status=run.status.value).inc()
        JOB_RUN_DURATION.labels(job_id=job.id).observe(elapsed)

        event_name = "job.success" if run.status == RunStatus.SUCCESS else "job.failed"
        await event_bus.emit(event_name, job=job, run=run)

        logger.info(
            "job_executed",
            job_id=job.id,
            status=run.status.value,
            duration=duration_str,
            exit_code=exit_code,
        )
        return run

    async def add_or_update_job(self, job: Job) -> Job:
        saved = await self.storage.save_job(job)
        if saved.status == JobStatus.ACTIVE:
            self._schedule_job(saved)
        else:
            if self.scheduler.get_job(saved.id):
                self.scheduler.remove_job(saved.id)
        jobs = await self.storage.get_all_jobs()
        ACTIVE_JOBS_GAUGE.set(sum(1 for j in jobs if j.status == JobStatus.ACTIVE))
        return saved

    async def delete_job(self, job_id: str) -> bool:
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
        deleted = await self.storage.delete_job(job_id)
        jobs = await self.storage.get_all_jobs()
        ACTIVE_JOBS_GAUGE.set(sum(1 for j in jobs if j.status == JobStatus.ACTIVE))
        return deleted

    async def pause_job(self, job_id: str) -> Job | None:
        job = await self.storage.get_job(job_id)
        if not job:
            return None
        job.status = JobStatus.PAUSED
        if self.scheduler.get_job(job.id):
            self.scheduler.remove_job(job.id)
        await self.storage.save_job(job)
        return job

    async def resume_job(self, job_id: str) -> Job | None:
        job = await self.storage.get_job(job_id)
        if not job:
            return None
        job.status = JobStatus.ACTIVE
        self._schedule_job(job)
        await self.storage.save_job(job)
        return job

    async def _seed_default_jobs(self) -> None:
        defaults = [
            Job(
                id="job-001",
                name="daily-db-backup",
                description="PostgreSQL backup to S3",
                trigger=TriggerType.CRON,
                trigger_expr="0 2 * * *",
                executor=ExecutorType.SHELL,
                command="echo '[BACKUP] Running PostgreSQL database dump... SUCCESS. Uploaded 2.4GB to s3://backups/'",
                status=JobStatus.ACTIVE,
                tags=["production", "database"],
            ),
            Job(
                id="job-002",
                name="cache-invalidation",
                description="Flush Redis cache layers",
                trigger=TriggerType.INTERVAL,
                trigger_expr="every 30m",
                executor=ExecutorType.PYTHON,
                command="print('[REDIS] Cache purged: 14,203 keys invalidated successfully.')",
                status=JobStatus.ACTIVE,
                tags=["production"],
            ),
            Job(
                id="job-003",
                name="health-check-prod",
                description="Ping production service health",
                trigger=TriggerType.INTERVAL,
                trigger_expr="every 5m",
                executor=ExecutorType.SHELL,
                command="echo 'ALL SYSTEMS OPERATIONAL. Latency 14ms.'",
                status=JobStatus.ACTIVE,
                tags=["monitoring", "prod"],
            ),
            Job(
                id="job-004",
                name="cleanup-old-runs",
                description="Prune job runs older than 30 days",
                trigger=TriggerType.CRON,
                trigger_expr="0 1 * * *",
                executor=ExecutorType.SHELL,
                command="echo '[CLEANUP] Deleted 1,280 expired job execution records.'",
                status=JobStatus.ACTIVE,
                tags=["maintenance"],
            ),
        ]
        for j in defaults:
            await self.storage.save_job(j)
