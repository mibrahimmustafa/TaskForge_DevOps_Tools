import hashlib
import secrets
import time
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Gauge, generate_latest
from pydantic import BaseModel, Field

from taskforge.api.auth import Principal, authenticate

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
    registry = CollectorRegistry()
    counts = await request.app.state.db.stats(principal.scope)
    runs = Gauge("taskforge_runs", "Persisted executions by status", ["status"], registry=registry)
    for status, count in counts.items():
        runs.labels(status=status).set(count)
    workers = Gauge(
        "taskforge_workers_online", "Workers with a current heartbeat", registry=registry
    )
    workers.set(await request.app.state.db.worker_count())
    return Response(content=generate_latest(registry), media_type=CONTENT_TYPE_LATEST)


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
        "workers_online": await request.app.state.db.worker_count(),
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
        raise HTTPException(403, "Administrator role required")
    return await request.app.state.db.audit_events(principal.scope)


class UnlockRequest(BaseModel):
    key: str


class SetupCompleteRequest(BaseModel):
    setup_token: str
    username: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=6, max_length=128)
    instance_url: str = Field(default="")


class LoginRequest(BaseModel):
    username: str
    password: str


@router.get("/api/system/setup-status")
async def setup_status(request: Request):
    db = request.app.state.db
    is_complete = await db.is_setup_complete()
    if not is_complete:
        users = await db.list("user")
        if users:
            is_complete = True
            await db.complete_setup()

    password_file = Path(request.app.state.settings.data_dir).resolve() / "initial_admin_password"
    if not is_complete and not password_file.exists():
        password_file.parent.mkdir(parents=True, exist_ok=True)
        key = secrets.token_hex(16)
        password_file.write_text(key, encoding="utf-8")

    return {
        "setup_complete": is_complete,
        "requires_unlock": not is_complete,
    }


@router.post("/api/system/setup/unlock")
async def setup_unlock(body: UnlockRequest, request: Request):
    password_file = Path(request.app.state.settings.data_dir).resolve() / "initial_admin_password"
    if not password_file.exists():
        if await request.app.state.db.is_setup_complete():
            raise HTTPException(400, "Setup is already complete")
        raise HTTPException(404, "Initial admin password file not found")

    expected = password_file.read_text(encoding="utf-8").strip()
    if not secrets.compare_digest(body.key.strip(), expected):
        raise HTTPException(401, "Invalid initial admin unlock password")

    setup_token = "setup-" + hashlib.sha256(expected.encode()).hexdigest()
    return {"unlocked": True, "setup_token": setup_token}


@router.post("/api/system/setup/complete")
async def setup_complete(body: SetupCompleteRequest, request: Request):
    password_file = Path(request.app.state.settings.data_dir).resolve() / "initial_admin_password"
    if password_file.exists():
        expected = password_file.read_text(encoding="utf-8").strip()
        expected_token = "setup-" + hashlib.sha256(expected.encode()).hexdigest()
        if not secrets.compare_digest(body.setup_token, expected_token):
            raise HTTPException(401, "Invalid setup token")

    db = request.app.state.db
    token = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    pwd_hash = hashlib.sha256(body.password.encode()).hexdigest()
    preview = f"{token[:6]}...{token[-4:]}"
    now = time.time()

    user_data = {
        "id": body.username,
        "name": body.username,
        "role": "admin",
        "projects": ["*"],
        "password_hash": pwd_hash,
        "token_hash": token_hash,
        "token_preview": preview,
        "created": now,
        "created_by": "setup_wizard",
    }
    await db.put("user", user_data)
    await db.put(
        "user_token",
        {
            "id": token_hash,
            "name": body.username,
            "role": "admin",
            "projects": ["*"],
        },
    )
    await db.complete_setup(body.instance_url)
    if password_file.exists():
        password_file.unlink(missing_ok=True)
    await db.record_audit("*", "setup_wizard", "system.setup_completed", body.username)
    return {
        "success": True,
        "token": token,
        "name": body.username,
        "role": "admin",
        "projects": ["*"],
    }


@router.post("/api/auth/login")
async def login(body: LoginRequest, request: Request):
    db = request.app.state.db
    user = await db.get("user", body.username)
    if not user:
        raise HTTPException(401, "Invalid username or password")

    expected_hash = user.get("password_hash")
    if not expected_hash:
        raise HTTPException(401, "User has no local password configured. Use API token instead.")

    provided_hash = hashlib.sha256(body.password.encode()).hexdigest()
    if not secrets.compare_digest(provided_hash, expected_hash):
        raise HTTPException(401, "Invalid username or password")

    session_token = secrets.token_urlsafe(48)
    session_hash = hashlib.sha256(session_token.encode()).hexdigest()
    await db.put(
        "user_token",
        {
            "id": session_hash,
            "name": user["name"],
            "role": user["role"],
            "projects": user.get("projects", ["*"]),
        },
    )
    return {
        "token": session_token,
        "name": user["name"],
        "role": user["role"],
        "projects": user.get("projects", ["*"]),
    }
