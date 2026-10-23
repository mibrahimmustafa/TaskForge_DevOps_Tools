import hashlib
import hmac
import json
import re

from fastapi import APIRouter, Header, HTTPException, Request

from taskforge.jobs.models import Job, Pipeline

router = APIRouter(prefix="/triggers", tags=["Triggers"])


@router.post("/webhook/{job_id}", status_code=202)
async def trigger_webhook(
    job_id: str, request: Request, x_taskforge_secret: str = Header(default="")
):
    value = await request.app.state.db.get("job", job_id)
    if not value or value["trigger"] != "webhook" or value["status"] != "active":
        raise HTTPException(404, "Active webhook job not found")
    job = Job.model_validate(value)
    supplied = "sha256:" + hashlib.sha256(x_taskforge_secret.encode()).hexdigest()
    if not job.webhook_secret or not hmac.compare_digest(job.webhook_secret, supplied):
        raise HTTPException(403, "Invalid webhook secret")
    key = request.headers.get("idempotency-key")
    if not key or len(key) > 100:
        raise HTTPException(422, "Supply an Idempotency-Key of at most 100 characters")
    run = await request.app.state.scheduler.submit(job, "webhook", f"hook:{job.id}:{key}")
    return {"id": run["id"], "status": run["status"]}


@router.post("/github", status_code=202)
async def github(request: Request):
    settings = request.app.state.settings
    if not settings.github_secret:
        raise HTTPException(503, "GitHub webhook integration is not configured")
    raw = await request.body()
    if len(raw) > 1024 * 1024:
        raise HTTPException(413, "Webhook payload is too large")
    expected = (
        "sha256=" + hmac.new(settings.github_secret.encode(), raw, hashlib.sha256).hexdigest()
    )
    if not hmac.compare_digest(request.headers.get("x-hub-signature-256", ""), expected):
        raise HTTPException(403, "Invalid webhook signature")
    if request.headers.get("x-github-event") == "ping":
        return {"status": "ready"}
    if request.headers.get("x-github-event") != "push":
        raise HTTPException(422, "Only trusted push events are supported")
    data = json.loads(raw)
    repository = data.get("repository", {}).get("full_name")
    commit = data.get("after", "")
    if repository not in settings.github_repositories:
        raise HTTPException(403, "Repository is not allowlisted")
    if not re.fullmatch(r"[a-f0-9]{40}", commit) or commit == "0" * 40:
        raise HTTPException(422, "Push must contain a valid commit")
    # Body hash prevents a captured delivery being replayed with a different delivery ID.
    digest = hashlib.sha256(raw).hexdigest()
    runs = []
    for value in await request.app.state.db.list("pipeline", limit=10000):
        pipeline = Pipeline.model_validate(value)
        if pipeline.repository == repository and data.get("ref") == f"refs/heads/{pipeline.branch}":
            run = await request.app.state.scheduler.submit_pipeline(
                pipeline, commit, f"github:{pipeline.id}:{digest}"
            )
            runs.append(run["id"])
            await request.app.state.db.record_audit(
                pipeline.project, "github", "pipeline.webhook", run["id"]
            )
    return {"runs": runs}
