import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from taskforge.api.auth import validate_tokens
from taskforge.api.routers import deployments, jobs, pipelines, plugins, runs, system, triggers
from taskforge.core.config import Settings, get_settings
from taskforge.core.logging import setup_logging
from taskforge.core.scheduler import TaskScheduler
from taskforge.core.worker import Worker
from taskforge.storage.database import ConflictError, Database


def create_app(settings: Settings | None = None, database: Database | None = None) -> FastAPI:
    settings = settings or get_settings()
    validate_tokens(settings.tokens)
    setup_logging(settings.log_level)
    db = database or Database(settings.storage_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await db.initialize()
        worker_task = None
        if settings.embedded_worker:
            worker_task = asyncio.create_task(Worker(db, settings).serve())
        try:
            yield
        finally:
            if worker_task:
                worker_task.cancel()
                await asyncio.gather(worker_task, return_exceptions=True)
            await db.close()

    app = FastAPI(title="TaskForge", version=settings.app_version, lifespan=lifespan)
    app.state.settings = settings
    app.state.db = db
    app.state.scheduler = TaskScheduler(db)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
    )

    @app.exception_handler(ConflictError)
    async def conflict(request: Request, exc: ConflictError):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(ValueError)
    async def invalid(request: Request, exc: ValueError):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.exception_handler(RequestValidationError)
    async def validation(request: Request, exc: RequestValidationError):
        # Never echo submitted secrets through validation errors.
        return JSONResponse(
            {"detail": [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]},
            status_code=422,
        )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        if int(request.headers.get("content-length", "0")) > 1024 * 1024:
            return JSONResponse({"detail": "Request exceeds 1 MiB"}, status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path.startswith("/dashboard"):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'"
            )
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        return response

    app.include_router(system.router)
    for module in (jobs, runs, pipelines, deployments, triggers, plugins):
        app.include_router(module.router, prefix="/api")
    dashboard = Path(__file__).resolve().parents[1] / "dashboard"
    app.mount("/dashboard", StaticFiles(directory=dashboard, html=True), name="dashboard")

    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse("/dashboard/")

    return app
