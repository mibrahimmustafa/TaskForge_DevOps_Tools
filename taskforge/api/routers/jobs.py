import hashlib

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from taskforge.api.auth import Principal, authenticate
from taskforge.jobs.models import Job, JobStatus

router = APIRouter(prefix="/jobs", tags=["Jobs"])


async def find_job(request: Request, job_id: str, principal: Principal, role="viewer"):
    value = await request.app.state.db.get("job", job_id)
    if not value:
        raise HTTPException(404, "Job not found")
    principal.check(value["project"], role)
    return Job.model_validate(value)


@router.get("")
async def list_jobs(request: Request, principal: Principal = Depends(authenticate)):
    return [
        Job.model_validate(value).to_dict()
        for value in await request.app.state.db.list("job", principal.scope)
    ]


@router.post("")
async def save_job(job: Job, request: Request, principal: Principal = Depends(authenticate)):
    principal.check(job.project, "admin")
    old = await request.app.state.db.get("job", job.id)
    if old:
        principal.check(old["project"], "admin")
        if old["project"] != job.project:
            raise HTTPException(409, "A definition cannot move between projects")
    if "webhook_secret" not in job.model_fields_set and old:
        job.webhook_secret = old.get("webhook_secret")
    elif job.webhook_secret:
        job.webhook_secret = "sha256:" + hashlib.sha256(job.webhook_secret.encode()).hexdigest()
    saved = await request.app.state.scheduler.add_or_update_job(job)
    await request.app.state.db.record_audit(job.project, principal.name, "job.saved", job.id)
    return saved.to_dict()


@router.get("/{job_id}")
async def get_job(job_id: str, request: Request, principal: Principal = Depends(authenticate)):
    return (await find_job(request, job_id, principal)).to_dict()


@router.delete("/{job_id}")
async def delete_job(
    job_id: str,
    request: Request,
    version: int = Query(ge=1),
    principal: Principal = Depends(authenticate),
):
    job = await find_job(request, job_id, principal, "admin")
    await request.app.state.db.remove("job", job_id, version)
    await request.app.state.db.record_audit(job.project, principal.name, "job.deleted", job.id)
    return {"success": True}


@router.post("/{job_id}/run", status_code=202)
async def run_job(job_id: str, request: Request, principal: Principal = Depends(authenticate)):
    job = await find_job(request, job_id, principal, "operator")
    key = request.headers.get("idempotency-key")
    if key and len(key) > 100:
        raise HTTPException(422, "Idempotency key must not exceed 100 characters")
    run = await request.app.state.scheduler.submit(
        job, dedupe=f"manual:{job.project}:{job.id}:{key}" if key else None
    )
    await request.app.state.db.record_audit(job.project, principal.name, "run.submitted", run["id"])
    return {"id": run["id"], "status": run["status"]}


@router.post("/{job_id}/{action}")
async def change_schedule(
    job_id: str, action: str, request: Request, principal: Principal = Depends(authenticate)
):
    if action not in {"pause", "resume"}:
        raise HTTPException(404, "Unknown action")
    job = await find_job(request, job_id, principal, "operator")
    job.status = JobStatus.PAUSED if action == "pause" else JobStatus.ACTIVE
    saved = await request.app.state.scheduler.add_or_update_job(job)
    await request.app.state.db.record_audit(job.project, principal.name, f"job.{action}", job.id)
    return saved.to_dict()
