"""Build and log retention (LogRotator) preserving protected runs."""

from __future__ import annotations

import shutil
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from taskforge.core.config import Settings
    from taskforge.storage.database import Database


async def apply_build_retention(
    db: Database, settings: Settings, project: str, job_id: str
) -> dict[str, Any]:
    """Evaluate retention rules for a job and remove eligible older run records and artifacts."""
    job_doc = await db.get("job", job_id)
    if not job_doc:
        return {"purged_runs": []}

    retention_days = job_doc.get("retention_days")
    retention_max_builds = job_doc.get("retention_max_builds")
    if retention_days is None and retention_max_builds is None:
        return {"purged_runs": []}

    runs = await db.get_completed_job_runs(project, job_id)
    if not runs:
        return {"purged_runs": []}

    protected_ids: set[str] = set()

    # Rule 1: Always protect the latest run
    protected_ids.add(runs[0]["id"])

    # Rule 2: Protect lastSuccessful and lastStable runs
    last_successful_found = False
    last_stable_found = False
    for r in runs:
        status = r.get("status")
        if not last_successful_found and status == "success":
            protected_ids.add(r["id"])
            last_successful_found = True
        if not last_stable_found and status in {"success", "unstable"}:
            protected_ids.add(r["id"])
            last_stable_found = True
        if last_successful_found and last_stable_found:
            break

    # Rule 3: Protect any run marked keep_forever
    for r in runs:
        payload = r.get("payload", {})
        result = r.get("result", {})
        if payload.get("keep_forever") or result.get("keep_forever") or r.get("keep_forever"):
            protected_ids.add(r["id"])

    # Determine eligible runs to purge
    to_purge: set[str] = set()

    # Apply retention_max_builds: keep at most retention_max_builds runs
    if retention_max_builds is not None and retention_max_builds > 0:
        kept_count = 0
        for r in runs:
            if r["id"] in protected_ids:
                kept_count += 1
            else:
                if kept_count >= retention_max_builds:
                    to_purge.add(r["id"])
                else:
                    kept_count += 1

    # Apply retention_days: purge runs older than retention_days
    if retention_days is not None and retention_days > 0:
        cutoff = time.time() - (retention_days * 86400)
        for r in runs:
            if r["id"] not in protected_ids:
                created = r.get("created", 0)
                if created < cutoff:
                    to_purge.add(r["id"])

    # Execute purging for eligible runs
    purged: list[str] = []
    for r in runs:
        rid = r["id"]
        if rid in to_purge and rid not in protected_ids:
            # Delete DB records
            await db.delete_run(rid)
            # Remove artifacts from disk
            payload = r.get("payload", {})
            build_num = payload.get("build_number")
            identifier_str = str(build_num) if build_num is not None else rid
            art_dir = settings.data_dir.resolve() / "artifacts" / project / job_id / identifier_str
            if art_dir.exists():
                shutil.rmtree(art_dir, ignore_errors=True)
            # Remove legacy artifact path if present
            legacy_art_dir = settings.data_dir.resolve() / "artifacts" / project / rid
            if legacy_art_dir.exists():
                shutil.rmtree(legacy_art_dir, ignore_errors=True)
            # Remove workspace from disk
            ws_dir = settings.data_dir.resolve() / "workspaces" / rid
            if ws_dir.exists():
                shutil.rmtree(ws_dir, ignore_errors=True)
            purged.append(rid)

    return {"purged_runs": purged}
