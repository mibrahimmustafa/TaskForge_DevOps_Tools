import json
from datetime import datetime

import aiosqlite

from taskforge.jobs.models import ExecutorType, Job, JobRun, JobStatus, RunStatus, TriggerType
from taskforge.storage.base import StorageBackend


class SQLiteStorage(StorageBackend):
    def __init__(self, db_path: str = "taskforge.db") -> None:
        if db_path.startswith("sqlite+aiosqlite:///"):
            db_path = db_path.replace("sqlite+aiosqlite:///", "")
        elif db_path.startswith("sqlite:///"):
            db_path = db_path.replace("sqlite:///", "")
        self.db_path = db_path

    async def initialize(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    trigger TEXT NOT NULL,
                    trigger_expr TEXT NOT NULL,
                    executor TEXT NOT NULL,
                    command TEXT NOT NULL,
                    status TEXT NOT NULL,
                    tags TEXT DEFAULT '[]',
                    timeout_seconds INTEGER DEFAULT 300,
                    max_retries INTEGER DEFAULT 3,
                    retry_delay_seconds INTEGER DEFAULT 5,
                    webhook_secret TEXT,
                    created_at TEXT NOT NULL,
                    next_run TEXT,
                    last_run TEXT,
                    last_duration TEXT,
                    last_status TEXT
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS job_runs (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    job_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    duration_seconds REAL DEFAULT 0.0,
                    duration_str TEXT DEFAULT '0s',
                    trigger_type TEXT DEFAULT 'manual',
                    exit_code INTEGER DEFAULT 0,
                    logs TEXT DEFAULT ''
                )
            """)
            await db.commit()

    async def get_all_jobs(self) -> list[Job]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM jobs ORDER BY name ASC")
            rows = await cursor.fetchall()
            jobs = []
            for r in rows:
                jobs.append(
                    Job(
                        id=r["id"],
                        name=r["name"],
                        description=r["description"] or "",
                        trigger=TriggerType(r["trigger"]),
                        trigger_expr=r["trigger_expr"],
                        executor=ExecutorType(r["executor"]),
                        command=r["command"],
                        status=JobStatus(r["status"]),
                        tags=json.loads(r["tags"] or "[]"),
                        timeout_seconds=r["timeout_seconds"],
                        max_retries=r["max_retries"],
                        retry_delay_seconds=r["retry_delay_seconds"],
                        webhook_secret=r["webhook_secret"],
                        created_at=datetime.fromisoformat(r["created_at"]),
                        next_run=r["next_run"],
                        last_run=r["last_run"],
                        last_duration=r["last_duration"],
                        last_status=r["last_status"],
                    )
                )
            return jobs

    async def get_job(self, job_id: str) -> Job | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            r = await cursor.fetchone()
            if not r:
                return None
            return Job(
                id=r["id"],
                name=r["name"],
                description=r["description"] or "",
                trigger=TriggerType(r["trigger"]),
                trigger_expr=r["trigger_expr"],
                executor=ExecutorType(r["executor"]),
                command=r["command"],
                status=JobStatus(r["status"]),
                tags=json.loads(r["tags"] or "[]"),
                timeout_seconds=r["timeout_seconds"],
                max_retries=r["max_retries"],
                retry_delay_seconds=r["retry_delay_seconds"],
                webhook_secret=r["webhook_secret"],
                created_at=datetime.fromisoformat(r["created_at"]),
                next_run=r["next_run"],
                last_run=r["last_run"],
                last_duration=r["last_duration"],
                last_status=r["last_status"],
            )

    async def save_job(self, job: Job) -> Job:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO jobs (
                    id, name, description, trigger, trigger_expr, executor, command,
                    status, tags, timeout_seconds, max_retries, retry_delay_seconds,
                    webhook_secret, created_at, next_run, last_run, last_duration, last_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    description=excluded.description,
                    trigger=excluded.trigger,
                    trigger_expr=excluded.trigger_expr,
                    executor=excluded.executor,
                    command=excluded.command,
                    status=excluded.status,
                    tags=excluded.tags,
                    timeout_seconds=excluded.timeout_seconds,
                    max_retries=excluded.max_retries,
                    retry_delay_seconds=excluded.retry_delay_seconds,
                    webhook_secret=excluded.webhook_secret,
                    next_run=excluded.next_run,
                    last_run=excluded.last_run,
                    last_duration=excluded.last_duration,
                    last_status=excluded.last_status
            """,
                (
                    job.id,
                    job.name,
                    job.description,
                    job.trigger.value,
                    job.trigger_expr,
                    job.executor.value,
                    job.command,
                    job.status.value,
                    json.dumps(job.tags),
                    job.timeout_seconds,
                    job.max_retries,
                    job.retry_delay_seconds,
                    job.webhook_secret,
                    job.created_at.isoformat(),
                    job.next_run,
                    job.last_run,
                    job.last_duration,
                    job.last_status,
                ),
            )
            await db.commit()
            return job

    async def delete_job(self, job_id: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            await db.commit()
            return cursor.rowcount > 0

    async def get_all_runs(self, limit: int = 100) -> list[JobRun]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM job_runs ORDER BY started_at DESC LIMIT ?", (limit,)
            )
            rows = await cursor.fetchall()
            runs = []
            for r in rows:
                runs.append(
                    JobRun(
                        id=r["id"],
                        job_id=r["job_id"],
                        job_name=r["job_name"],
                        status=RunStatus(r["status"]),
                        started_at=datetime.fromisoformat(r["started_at"]),
                        finished_at=datetime.fromisoformat(r["finished_at"])
                        if r["finished_at"]
                        else None,
                        duration_seconds=r["duration_seconds"],
                        duration_str=r["duration_str"],
                        trigger_type=r["trigger_type"],
                        exit_code=r["exit_code"],
                        logs=r["logs"] or "",
                    )
                )
            return runs

    async def get_run(self, run_id: str) -> JobRun | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM job_runs WHERE id = ?", (run_id,))
            r = await cursor.fetchone()
            if not r:
                return None
            return JobRun(
                id=r["id"],
                job_id=r["job_id"],
                job_name=r["job_name"],
                status=RunStatus(r["status"]),
                started_at=datetime.fromisoformat(r["started_at"]),
                finished_at=datetime.fromisoformat(r["finished_at"]) if r["finished_at"] else None,
                duration_seconds=r["duration_seconds"],
                duration_str=r["duration_str"],
                trigger_type=r["trigger_type"],
                exit_code=r["exit_code"],
                logs=r["logs"] or "",
            )

    async def save_run(self, run: JobRun) -> JobRun:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO job_runs (
                    id, job_id, job_name, status, started_at, finished_at,
                    duration_seconds, duration_str, trigger_type, exit_code, logs
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status,
                    finished_at=excluded.finished_at,
                    duration_seconds=excluded.duration_seconds,
                    duration_str=excluded.duration_str,
                    exit_code=excluded.exit_code,
                    logs=excluded.logs
            """,
                (
                    run.id,
                    run.job_id,
                    run.job_name,
                    run.status.value,
                    run.started_at.isoformat(),
                    run.finished_at.isoformat() if run.finished_at else None,
                    run.duration_seconds,
                    run.duration_str,
                    run.trigger_type,
                    run.exit_code,
                    run.logs,
                ),
            )
            await db.commit()
            return run
