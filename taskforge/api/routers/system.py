import os
import platform
import time
from datetime import datetime
from fastapi import APIRouter, Request, Response
from taskforge.core.metrics import get_metrics_data
from taskforge.core.config import get_settings
from taskforge.jobs.models import JobStatus

router = APIRouter(tags=["System"])

START_TIME = time.time()

@router.get("/health")
async def health(request: Request):
    scheduler = getattr(request.app.state, "scheduler", None)
    scheduler_running = scheduler._running if scheduler else False
    return {
        "status": "healthy" if scheduler_running else "degraded",
        "service": "TaskForge",
        "version": "0.1.0",
        "scheduler_running": scheduler_running,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "timestamp": datetime.utcnow().isoformat()
    }

@router.get("/metrics")
async def metrics():
    data, content_type = get_metrics_data()
    return Response(content=data, media_type=content_type)

@router.get("/api/system/stats")
async def system_stats(request: Request):
    scheduler = request.app.state.scheduler
    jobs = await scheduler.storage.get_all_jobs()
    runs = await scheduler.storage.get_all_runs(limit=100)
    
    active_jobs = sum(1 for j in jobs if j.status == JobStatus.ACTIVE)
    paused_jobs = sum(1 for j in jobs if j.status == JobStatus.PAUSED)
    failed_runs = sum(1 for r in runs if r.status.value == "failed")
    success_runs = sum(1 for r in runs if r.status.value == "success")

    return {
        "total_jobs": len(jobs),
        "active_jobs": active_jobs,
        "paused_jobs": paused_jobs,
        "total_runs": len(runs),
        "failed_runs": failed_runs,
        "success_runs": success_runs,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "python_version": platform.python_version(),
        "platform": platform.platform()
    }

@router.get("/api/system/env")
async def system_env():
    settings = get_settings()
    return [
        {"key": "TASKFORGE_STORAGE_URL", "value": settings.storage_url, "source": "env"},
        {"key": "TASKFORGE_SECRET_KEY", "value": "***hidden***", "source": "env"},
        {"key": "TASKFORGE_LOG_LEVEL", "value": settings.log_level, "source": "env"},
        {"key": "TASKFORGE_METRICS_ENABLED", "value": str(settings.metrics_enabled).lower(), "source": "env"},
        {"key": "TASKFORGE_HOST", "value": settings.host, "source": "env"},
        {"key": "TASKFORGE_PORT", "value": str(settings.port), "source": "env"}
    ]
