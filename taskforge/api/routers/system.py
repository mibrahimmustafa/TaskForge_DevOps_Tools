import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response

from taskforge.api.auth import Principal, authenticate
from taskforge.core.metrics import get_metrics_data

router = APIRouter(tags=["System"])
START_TIME = time.time()


@router.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "TaskForge",
        "version": "0.2.0",
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/ready")
async def ready(request: Request, response: Response):
    try:
        await request.app.state.db.healthy()
        return {"status": "ready"}
    except Exception:
        response.status_code = 503
        return {"status": "unavailable"}


@router.get("/metrics")
async def metrics(request: Request, principal: Principal = Depends(authenticate)):
    principal.check("default", "admin")
    if not request.app.state.settings.metrics_enabled:
        return Response(status_code=404)
    data, content_type = get_metrics_data()
    return Response(content=data, media_type=content_type)


@router.get("/api/session")
async def session(principal: Principal = Depends(authenticate)):
    return {"name": principal.name, "role": principal.role, "projects": principal.projects}


@router.get("/api/system/stats")
async def system_stats(request: Request, principal: Principal = Depends(authenticate)):
    counts = await request.app.state.db.stats(principal.scope)
    jobs = await request.app.state.db.list("job", principal.scope)
    return {
        "total_jobs": len(jobs),
        "active_jobs": sum(j["status"] == "active" for j in jobs),
        "total_runs": sum(counts.values()),
        "statuses": counts,
        "uptime_seconds": round(time.time() - START_TIME),
    }


@router.get("/api/system/env")
async def system_env(request: Request, principal: Principal = Depends(authenticate)):
    principal.check("default", "admin")
    settings = request.app.state.settings
    return {
        "storage": "postgresql" if settings.storage_url.startswith("postgresql") else "sqlite",
        "metrics_enabled": settings.metrics_enabled,
        "version": settings.app_version,
        "execution": "separate worker",
        "host_execution_enabled": settings.allow_host_execution,
    }


@router.get("/api/audit")
async def audit(request: Request, principal: Principal = Depends(authenticate)):
    if principal.role != "admin":
        from fastapi import HTTPException

        raise HTTPException(403, "Administrator role required")
    return await request.app.state.db.audit_events(principal.scope)
