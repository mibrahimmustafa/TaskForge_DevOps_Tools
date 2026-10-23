import asyncio
import json
import os
import secrets
from pathlib import Path

import httpx
import typer

from taskforge.core.config import get_settings

app = typer.Typer(help="TaskForge pipeline operations")
jobs_app = typer.Typer(help="Manage jobs through the authenticated API")
server_app = typer.Typer(help="Run the API and dashboard")
worker_app = typer.Typer(help="Run an independent execution worker")
app.add_typer(jobs_app, name="jobs")
app.add_typer(server_app, name="server")
app.add_typer(worker_app, name="worker")


def request(method: str, path: str, body=None):
    token = os.getenv("TASKFORGE_API_TOKEN", "")
    if not token:
        raise typer.BadParameter("Set TASKFORGE_API_TOKEN")
    base = os.getenv("TASKFORGE_API_URL", "http://127.0.0.1:8080").rstrip("/")
    with httpx.Client(timeout=30, trust_env=False) as client:
        response = client.request(
            method, base + "/api" + path, headers={"Authorization": f"Bearer {token}"}, json=body
        )
    if response.is_error:
        typer.echo(response.text, err=True)
        raise typer.Exit(1)
    typer.echo(json.dumps(response.json(), indent=2))


@server_app.command("start")
def start_server(host: str | None = None, port: int | None = None):
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "taskforge.api.app:create_app",
        factory=True,
        host=host or settings.host,
        port=port or settings.port,
    )


@worker_app.command("start")
def start_worker():
    from taskforge.core.worker import Worker
    from taskforge.storage.database import Database

    settings = get_settings()

    async def serve():
        database = Database(settings.storage_url)
        try:
            await Worker(database, settings).serve()
        finally:
            await database.close()

    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        pass


@jobs_app.command("list")
def list_jobs():
    request("GET", "/jobs")


@jobs_app.command("create")
def create_job(file_path: Path):
    request("POST", "/jobs", json.loads(file_path.read_text(encoding="utf-8")))


@jobs_app.command("run")
def run_job(job_id: str):
    request("POST", f"/jobs/{job_id}/run")


@jobs_app.command("pause")
def pause_job(job_id: str):
    request("POST", f"/jobs/{job_id}/pause")


@jobs_app.command("resume")
def resume_job(job_id: str):
    request("POST", f"/jobs/{job_id}/resume")


@app.command("token")
def token():
    """Generate a cryptographically random access token."""
    typer.echo(secrets.token_urlsafe(48))


@app.command("init")
def initialize():
    """Create local credentials without overwriting existing configuration."""
    root = Path(".taskforge")
    root.mkdir(exist_ok=True)
    config = root / "config.env"
    if config.exists():
        raise typer.BadParameter(".taskforge/config.env already exists; no files changed")
    entries = [
        {"name": name, "role": "admin", "projects": ["*"], "token": secrets.token_urlsafe(48)}
        for name in ("administrator", "release-reviewer")
    ]
    with config.open("x", encoding="utf-8") as handle:
        handle.write("TASKFORGE_TOKENS='" + json.dumps(entries) + "'\n")
    if os.name != "nt":
        config.chmod(0o600)
    typer.echo(
        "Created .taskforge/config.env. Keep it private. It contains separate admin and reviewer tokens."
    )
    typer.echo(
        "Start the API with 'taskforge server start' and a runner with 'taskforge worker start'."
    )


@app.command("migrate-legacy")
def migrate_legacy(source: Path):
    """Import legacy jobs and history into v2 tables, preserving the source database."""
    from taskforge.storage.database import Database
    from taskforge.storage.migrate import import_legacy

    async def migrate():
        database = Database(get_settings().storage_url)
        try:
            result = await import_legacy(source, database)
            typer.echo(json.dumps(result, indent=2))
        finally:
            await database.close()

    asyncio.run(migrate())


@app.command("version")
def version():
    typer.echo("TaskForge 0.2.0")


if __name__ == "__main__":
    app()
