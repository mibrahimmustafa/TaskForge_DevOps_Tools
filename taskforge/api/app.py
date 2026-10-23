from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from taskforge.api.routers import jobs, runs, triggers, system, plugins
from taskforge.core.config import get_settings
from taskforge.core.logging import setup_logging, logger
from taskforge.core.scheduler import TaskScheduler
from taskforge.storage.sqlite_backend import SQLiteStorage

def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)

    storage = SQLiteStorage(settings.storage_url)
    scheduler = TaskScheduler(storage)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("app_starting", version=settings.app_version)
        app.state.scheduler = scheduler
        await scheduler.start()
        yield
        logger.info("app_stopping")
        await scheduler.shutdown()

    app = FastAPI(
        title="TaskForge API",
        version=settings.app_version,
        description="DevOps Task Scheduler REST API & Management Engine",
        lifespan=lifespan
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API Routers
    app.include_router(system.router)
    app.include_router(jobs.router, prefix="/api")
    app.include_router(runs.router, prefix="/api")
    app.include_router(triggers.router, prefix="/api")
    app.include_router(plugins.router, prefix="/api")

    # Static Dashboard
    dashboard_dir = Path(__file__).resolve().parent.parent.parent / "dashboard"
    if dashboard_dir.exists():
        app.mount("/dashboard", StaticFiles(directory=str(dashboard_dir), html=True), name="dashboard")

        @app.get("/", include_in_schema=False)
        async def root_redirect():
            return RedirectResponse(url="/dashboard/")

    return app
