from fastapi import APIRouter, HTTPException, Request, Header
from typing import Optional

router = APIRouter(prefix="/triggers", tags=["Triggers"])

@router.post("/webhook/{job_id}")
async def trigger_webhook(job_id: str, request: Request, x_taskforge_secret: Optional[str] = Header(None)):
    scheduler = request.app.state.scheduler
    job = await scheduler.storage.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.webhook_secret and job.webhook_secret != x_taskforge_secret:
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    run = await scheduler.execute_job_task(job_id, trigger_type="webhook")
    return {"status": "triggered", "run": run.to_dict()}
