"""One-way, idempotent import; legacy tables remain untouched for recovery."""

import hashlib
import json
import sqlite3
from pathlib import Path

from taskforge.jobs.models import Job
from taskforge.storage.database import Database


async def import_legacy(source: Path, target: Database):
    path = source.resolve()
    if not path.is_file():
        raise ValueError("Legacy SQLite file does not exist")
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        jobs = [dict(row) for row in connection.execute("SELECT * FROM jobs")]
        runs = [dict(row) for row in connection.execute("SELECT * FROM job_runs")]
    finally:
        connection.close()
    await target.initialize()
    imported = 0
    errors = []
    for row in jobs:
        try:
            row["tags"] = json.loads(row.get("tags") or "[]")
            # Require explicit review of legacy schedules before enabling them.
            row["status"] = "paused"
            row["next_run"] = None
            row["max_retries"] = max(0, row.get("max_retries", 0))
            if row.get("webhook_secret"):
                row["webhook_secret"] = (
                    "sha256:" + hashlib.sha256(row["webhook_secret"].encode()).hexdigest()
                )
            job = Job.model_validate(row)
            if not await target.get("job", job.id):
                await target.put("job", job.model_dump(mode="json"))
                imported += 1
        except ValueError:
            errors.append({"id": row.get("id"), "error": "Definition requires manual conversion"})
    for run in runs:
        # Keep legacy history separate, with no old logs automatically exposed.
        identifier = "legacy-" + run["id"]
        if not await target.get("legacy_run", identifier):
            await target.put(
                "legacy_run",
                {
                    "id": identifier,
                    "project": "default",
                    "job_id": run["job_id"],
                    "status": run["status"],
                    "started_at": run["started_at"],
                    "note": "Original logs remain in the preserved source database",
                },
            )
    return {
        "imported_jobs": imported,
        "legacy_runs": len(runs),
        "errors": errors,
        "note": "Imported jobs are paused. Original tables were not modified.",
    }
