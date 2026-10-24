import hashlib

from taskforge.jobs.models import Job, JobRun
from taskforge.storage.migrate import import_legacy
from taskforge.storage.sqlite_backend import SQLiteStorage


async def test_legacy_import_is_repeatable_paused_and_preserves_source(db, tmp_path):
    path = tmp_path / "legacy.db"
    legacy = SQLiteStorage(str(path))
    await legacy.initialize()
    secret = "legacy-" + "s" * 40
    await legacy.save_job(Job(id="legacy", name="Legacy", trigger="webhook", webhook_secret=secret))
    await legacy.save_run(JobRun(id="old-run", job_id="legacy", logs="private old output"))
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    result = await import_legacy(path, db)
    assert result["imported_jobs"] == 1 and not result["errors"]
    job = await db.get("job", "legacy")
    assert job["status"] == "paused" and job["next_run"] is None
    assert job["webhook_secret"].startswith("sha256:") and secret not in job["webhook_secret"]
    history = await db.get("legacy_run", "legacy-old-run")
    assert "logs" not in history
    assert (await import_legacy(path, db))["imported_jobs"] == 0
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
