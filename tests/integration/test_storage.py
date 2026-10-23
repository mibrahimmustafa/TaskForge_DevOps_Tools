import asyncio
import os
import tempfile

import pytest

from taskforge.jobs.models import (
    ExecutorType,
    Job,
    JobRun,
    JobStatus,
    RunStatus,
    TriggerType,
)
from taskforge.storage.sqlite_backend import SQLiteStorage


@pytest.fixture
def temp_db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


@pytest.mark.asyncio
async def test_sqlite_storage_crud(temp_db_path):
    storage = SQLiteStorage(temp_db_path)
    await storage.initialize()

    # 1. Create Job
    job = Job(
        id="test-job-1",
        name="Backup Database",
        description="Daily postgres backup",
        trigger=TriggerType.CRON,
        trigger_expr="0 2 * * *",
        executor=ExecutorType.SHELL,
        command="pg_dump -U postgres dbname",
        status=JobStatus.ACTIVE,
        tags=["database", "backup"],
        timeout_seconds=600,
    )
    saved = await storage.save_job(job)
    assert saved.id == "test-job-1"

    # 2. Get Job
    retrieved = await storage.get_job("test-job-1")
    assert retrieved is not None
    assert retrieved.name == "Backup Database"
    assert retrieved.tags == ["database", "backup"]

    # 3. Update Job
    retrieved.status = JobStatus.PAUSED
    retrieved.description = "Updated description"
    await storage.save_job(retrieved)

    updated = await storage.get_job("test-job-1")
    assert updated is not None
    assert updated.status == JobStatus.PAUSED
    assert updated.description == "Updated description"

    # 4. List Jobs
    all_jobs = await storage.get_all_jobs()
    assert len(all_jobs) == 1
    assert all_jobs[0].id == "test-job-1"

    # 5. Delete Job
    deleted = await storage.delete_job("test-job-1")
    assert deleted is True
    assert await storage.get_job("test-job-1") is None
    assert len(await storage.get_all_jobs()) == 0


@pytest.mark.asyncio
async def test_sqlite_storage_runs(temp_db_path):
    storage = SQLiteStorage(temp_db_path)
    await storage.initialize()

    run = JobRun(
        id="run-101",
        job_id="job-abc",
        job_name="Test Job",
        status=RunStatus.SUCCESS,
        duration_seconds=12.5,
        duration_str="12.5s",
        trigger_type="manual",
        exit_code=0,
        logs="All operations completed successfully.",
    )
    saved_run = await storage.save_run(run)
    assert saved_run.id == "run-101"

    fetched = await storage.get_run("run-101")
    assert fetched is not None
    assert fetched.exit_code == 0
    assert fetched.status == RunStatus.SUCCESS

    all_runs = await storage.get_all_runs(limit=10)
    assert len(all_runs) == 1
    assert all_runs[0].id == "run-101"


@pytest.mark.asyncio
async def test_sqlite_storage_concurrent_access(temp_db_path):
    storage = SQLiteStorage(temp_db_path)
    await storage.initialize()

    async def _insert_job(idx: int):
        j = Job(
            id=f"job-concurrent-{idx}",
            name=f"Concurrent Job {idx}",
            trigger=TriggerType.INTERVAL,
            trigger_expr="every 1m",
            executor=ExecutorType.SHELL,
            command=f"echo {idx}",
        )
        return await storage.save_job(j)

    # Insert 10 jobs concurrently
    results = await asyncio.gather(*[_insert_job(i) for i in range(10)])
    assert len(results) == 10

    all_jobs = await storage.get_all_jobs()
    assert len(all_jobs) == 10
