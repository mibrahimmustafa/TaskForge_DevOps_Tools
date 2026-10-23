from fastapi import APIRouter, HTTPException, Request
from taskforge.jobs.models import Job

router = APIRouter(prefix="/jobs", tags=["Jobs"])

@router.get("")
async def list_jobs(request: Request):
    scheduler = request.app.state.scheduler
    jobs = await scheduler.storage.get_all_jobs()
    return [j.to_dict() for j in jobs]

@router.post("")
async def create_or_update_job(job: Job, request: Request):
    scheduler = request.app.state.scheduler
    saved = await scheduler.add_or_update_job(job)
    return saved.to_dict()

@router.get("/{job_id}")
async def get_job(job_id: str, request: Request):
    scheduler = request.app.state.scheduler
    job = await scheduler.storage.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()

@router.delete("/{job_id}")
async def delete_job(job_id: str, request: Request):
    scheduler = request.app.state.scheduler
    deleted = await scheduler.delete_job(job_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"success": True, "job_id": job_id}

@router.post("/{job_id}/run")
async def run_job(job_id: str, request: Request):
    scheduler = request.app.state.scheduler
    job = await scheduler.storage.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    run = await scheduler.execute_job_task(job_id, trigger_type="manual")
    return run.to_dict()

@router.post("/{job_id}/pause")
async def pause_job(job_id: str, request: Request):
    scheduler = request.app.state.scheduler
    job = await scheduler.pause_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()

@router.post("/{job_id}/resume")
async def resume_job(job_id: str, request: Request):
    scheduler = request.app.state.scheduler
    job = await scheduler.resume_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()
