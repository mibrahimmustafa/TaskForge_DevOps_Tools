import asyncio
import hashlib
import time

import pytest
from sqlalchemy import update

from taskforge.core.scheduler import TaskScheduler
from taskforge.core.worker import RedactedLog, Worker
from taskforge.jobs.models import Job, Pipeline, TriggerType
from taskforge.storage.database import ConflictError, work


def make_job(**changes):
    return Job(
        id="job", name="Test", trigger="manual", executor="python", command="print('ok')", **changes
    )


async def test_claim_is_atomic_and_stale_owner_cannot_write(db):
    run = await db.enqueue("default", "job", {"kind": "job"})
    claims = await asyncio.gather(*(db.claim(str(i), 30) for i in range(8)))
    winners = [item for item in claims if item]
    assert len(winners) == 1
    owner = winners[0]["owner"]
    assert not await db.finish(run["id"], "wrong", "success", {})
    async with db.engine.begin() as connection:
        await connection.execute(
            update(work).where(work.c.id == run["id"]).values(lease=time.time() - 1)
        )
    await db.recover()
    assert (await db.run(run["id"]))["status"] == "lost"
    assert not await db.finish(run["id"], owner, "success", {})


@pytest.mark.parametrize("operation", ["pause", "delete", "edit"])
async def test_finishing_run_preserves_concurrent_definition_changes(
    db, settings, monkeypatch, operation
):
    scheduler = TaskScheduler(db)
    saved = await scheduler.add_or_update_job(make_job())
    run = await scheduler.submit(saved)
    started, release = asyncio.Event(), asyncio.Event()

    class Executor:
        async def execute(self, *args, **kwargs):
            started.set()
            await release.wait()
            return 0, "done"

    monkeypatch.setattr("taskforge.core.worker.get_executor", lambda executor: Executor())
    claimed = await db.claim("fence", 30)
    task = asyncio.create_task(Worker(db, settings).execute(claimed))
    await asyncio.wait_for(started.wait(), 5)
    if operation == "delete":
        await db.remove("job", saved.id, saved.version)
    else:
        value = saved.model_dump(mode="json")
        value["status" if operation == "pause" else "name"] = (
            "paused" if operation == "pause" else "Edited"
        )
        await db.put("job", value, saved.version)
    release.set()
    await task
    assert (await db.run(run["id"]))["status"] == "success"
    current = await db.get("job", saved.id)
    if operation == "delete":
        assert current is None
    elif operation == "pause":
        assert current["status"] == "paused"
    else:
        assert current["name"] == "Edited"


async def test_exception_finalizes_run_and_retry_count(db, settings, monkeypatch):
    scheduler = TaskScheduler(db)
    job = make_job(max_retries=2, retry_delay_seconds=1)
    calls = []

    class Executor:
        async def execute(self, *args, **kwargs):
            calls.append(1)
            return (0 if len(calls) == 3 else 1), ""

    monkeypatch.setattr("taskforge.core.worker.get_executor", lambda executor: Executor())
    run = await scheduler.submit(job)
    for attempt in range(3):
        claimed = await db.claim(f"fence-{attempt}", 30)
        await Worker(db, settings).execute(claimed)
        async with db.engine.begin() as connection:
            await connection.execute(update(work).where(work.c.id == run["id"]).values(available=0))
    result = await db.run(run["id"])
    assert result["status"] == "success" and len(result["result"]["attempts"]) == 3

    class Broken:
        async def execute(self, *args, **kwargs):
            raise RuntimeError("executor failed")

    monkeypatch.setattr("taskforge.core.worker.get_executor", lambda executor: Broken())
    run = await scheduler.submit(job)
    await Worker(db, settings).execute(await db.claim("next", 30))
    assert (await db.run(run["id"]))["status"] == "failed"
    assert await db.get("job", job.id) is None


async def test_queued_cancellation_and_concurrent_update_conflict(db):
    value = make_job().model_dump(mode="json")
    saved = await db.put("job", value)
    await db.put("job", saved, saved["version"])
    with pytest.raises(ConflictError):
        await db.put("job", saved, saved["version"])
    run = await db.enqueue("default", "job", {"kind": "job"})
    await db.cancel_run(run["id"])
    assert await db.claim("worker", 30) is None
    assert (await db.run(run["id"]))["status"] == "cancelled"


async def test_live_cancellation_stops_process(db, settings, tmp_path):
    marker = tmp_path / "must-not-exist"
    job = make_job(timeout_seconds=20).model_copy(
        update={
            "command": f"import time; from pathlib import Path; print('started', flush=True); time.sleep(8); Path({str(marker)!r}).touch()"
        }
    )
    run = await TaskScheduler(db).submit(job)
    task = asyncio.create_task(Worker(db, settings).execute(await db.claim("fence", 30)))
    await asyncio.sleep(0.5)
    await db.cancel_run(run["id"])
    await asyncio.wait_for(task, 6)
    assert (await db.run(run["id"]))["status"] == "cancelled"
    assert not marker.exists()


async def test_secret_redaction_crosses_chunks(db):
    run = await db.enqueue("default", "job", {"kind": "job"})
    await db.claim("fence", 30)
    sink = RedactedLog(db, run["id"], "fence", ["super-secret-value"])
    for value in ["hello su", "per-secret", "-value and ", "end"]:
        await sink.write(value)
    await sink.write("", final=True)
    output = "".join(item["text"] for item in await db.read_logs(run["id"]))
    assert output == "hello *** and end"


async def test_pipeline_failure_skips_dependants_and_independent_work_completes(db, settings):
    pipeline = Pipeline(
        id="ci",
        name="CI",
        steps=[
            {
                "id": "bad",
                "job": make_job().model_copy(update={"command": "raise RuntimeError('failure')"}),
            },
            {"id": "good", "job": make_job()},
            {"id": "blocked", "needs": ["bad"], "job": make_job()},
        ],
    )
    run = await TaskScheduler(db).submit_pipeline(pipeline)
    await Worker(db, settings).execute(await db.claim("fence", 30))
    result = (await db.run(run["id"]))["result"]
    assert result["status"] == "failed"
    assert result["steps"]["good"]["status"] == "success"
    assert result["steps"]["blocked"]["status"] == "skipped"


async def test_schedule_once_and_invalid_definitions_are_not_saved(db):
    scheduler = TaskScheduler(db)
    job = make_job().model_copy(
        update={"trigger": TriggerType.ONESHOT, "trigger_expr": "2020-01-01T00:00:00+00:00"}
    )
    await scheduler.add_or_update_job(job)
    await scheduler.tick()
    await scheduler.tick()
    assert len(await db.runs(None)) == 1
    assert (await db.get("job", job.id))["status"] == "paused"
    invalid = make_job().model_copy(
        update={"id": "invalid", "trigger": "interval", "trigger_expr": "oops"}
    )
    with pytest.raises(ValueError):
        await scheduler.add_or_update_job(invalid)
    assert await db.get("job", "invalid") is None


async def test_pipeline_hands_verified_artifacts_to_dependants(db, settings):
    pipeline = Pipeline(
        id="handoff",
        name="Artifact handoff",
        steps=[
            {
                "id": "build",
                "job": make_job().model_copy(
                    update={
                        "command": "from pathlib import Path; Path('package.txt').write_text('immutable')",
                        "artifact_paths": ["package.txt"],
                    }
                ),
            },
            {
                "id": "verify",
                "needs": ["build"],
                "job": make_job().model_copy(
                    update={
                        "command": "from pathlib import Path; assert Path('inputs/build/package.txt').read_text() == 'immutable'"
                    }
                ),
            },
        ],
    )
    run = await TaskScheduler(db).submit_pipeline(pipeline)
    await Worker(db, settings).execute(await db.claim("fence", 30))
    final = await db.run(run["id"])
    assert final["status"] == "success"
    assert final["result"]["steps"]["verify"]["status"] == "success"


async def test_completion_and_notification_are_atomic_and_idempotent(db):
    run = await db.enqueue("default", "job", {"kind": "job"})
    await db.claim("fence", 30)
    assert await db.finish(run["id"], "fence", "success", {}, notify=True)
    assert not await db.finish(run["id"], "fence", "success", {}, notify=True)
    deliveries = [r for r in await db.runs(None) if r["payload"]["kind"] == "notification"]
    assert len(deliveries) == 1
    assert deliveries[0]["payload"]["message"]["run_id"] == run["id"]


async def test_database_heartbeat_failure_cancels_execution(db, settings, monkeypatch):
    started, stopped = asyncio.Event(), asyncio.Event()

    class Executor:
        async def execute(self, *args, **kwargs):
            started.set()
            try:
                await asyncio.sleep(20)
            finally:
                stopped.set()

    async def unavailable(identifier):
        raise ConnectionError("coordination unavailable")

    monkeypatch.setattr("taskforge.core.worker.get_executor", lambda executor: Executor())
    await TaskScheduler(db).submit(make_job())
    claimed = await db.claim("fence", 30)
    task = asyncio.create_task(Worker(db, settings).execute(claimed))
    await started.wait()
    monkeypatch.setattr(db, "run", unavailable)
    await asyncio.wait_for(task, 5)
    assert stopped.is_set()


async def test_dependency_artifact_cannot_escape_workspace(db, settings):
    job = make_job()
    run = await TaskScheduler(db).submit(job)
    claimed = await db.claim("fence", 30)
    raw = b"artifact"
    digest = hashlib.sha256(raw).hexdigest()
    origin = settings.data_dir / "artifacts" / "default" / run["id"] / digest
    origin.parent.mkdir(parents=True)
    origin.write_bytes(raw)
    stream = RedactedLog(db, run["id"], "fence", [])
    with pytest.raises(ValueError, match="escapes"):
        await Worker(db, settings).execute_job(
            job,
            claimed,
            stream,
            "step",
            inputs={"dependency": [{"name": "../../../../outside", "sha256": digest}]},
        )
    assert not (settings.data_dir / "workspaces" / "outside").exists()
