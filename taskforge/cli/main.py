import asyncio
import json
import sys
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table

# Ensure UTF-8 or safe console
console = Console(highlight=False)

app = typer.Typer(help="TaskForge - DevOps Task Scheduler CLI")
jobs_app = typer.Typer(help="Manage scheduled jobs")
server_app = typer.Typer(help="Manage TaskForge server")

app.add_typer(jobs_app, name="jobs")
app.add_typer(server_app, name="server")

@server_app.command("start")
def start_server(
    host: str = typer.Option("0.0.0.0", help="Host to bind to"),
    port: int = typer.Option(8080, help="Port to listen on"),
    reload: bool = typer.Option(False, help="Enable auto-reload")
):
    """Start the TaskForge API and Dashboard server."""
    import uvicorn
    console.print(f"[bold green]Starting TaskForge server on http://{host}:{port}...[/bold green]")
    uvicorn.run("taskforge.api.app:create_app", factory=True, host=host, port=port, reload=reload)

@jobs_app.command("list")
def list_jobs():
    """List all configured jobs."""
    async def _list():
        from taskforge.storage.sqlite_backend import SQLiteStorage
        from taskforge.core.config import get_settings
        storage = SQLiteStorage(get_settings().storage_url)
        await storage.initialize()
        jobs = await storage.get_all_jobs()
        table = Table(title="TaskForge Jobs")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="bold white")
        table.add_column("Trigger", style="magenta")
        table.add_column("Schedule", style="yellow")
        table.add_column("Executor", style="blue")
        table.add_column("Status", style="green")
        table.add_column("Last Run", style="dim")

        for j in jobs:
            table.add_row(
                j.id, j.name, j.trigger.value, j.trigger_expr,
                j.executor.value, j.status.value, j.last_run or "Never"
            )
        console.print(table)

    asyncio.run(_list())

@jobs_app.command("create")
def create_job(file_path: str = typer.Argument(..., help="Path to JSON file with job definition")):
    """Create or update a job from a JSON configuration file."""
    async def _create():
        from taskforge.storage.sqlite_backend import SQLiteStorage
        from taskforge.core.config import get_settings
        from taskforge.jobs.models import Job

        p = Path(file_path)
        if not p.exists():
            console.print(f"[bold red]File not found: {file_path}[/bold red]")
            raise typer.Exit(1)

        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)

        job = Job(**data)
        storage = SQLiteStorage(get_settings().storage_url)
        await storage.initialize()
        saved = await storage.save_job(job)
        console.print(f"[bold green][OK] Job created successfully:[/bold green] {saved.id} ({saved.name})")

    asyncio.run(_create())

@jobs_app.command("run")
def run_job(job_id: str = typer.Argument(..., help="Job ID to run immediately")):
    """Run a job immediately."""
    async def _run():
        from taskforge.storage.sqlite_backend import SQLiteStorage
        from taskforge.core.config import get_settings
        from taskforge.core.scheduler import TaskScheduler

        storage = SQLiteStorage(get_settings().storage_url)
        scheduler = TaskScheduler(storage)
        await scheduler.start()

        console.print(f"[yellow]Triggering job {job_id}...[/yellow]")
        try:
            run = await scheduler.execute_job_task(job_id, trigger_type="cli")
            status_color = "green" if run.status.value == "success" else "red"
            console.print(f"[{status_color}]Result: {run.status.value.upper()} (duration: {run.duration_str})[/{status_color}]")
            if run.logs:
                console.print(f"\n[bold]Output Logs:[/bold]\n{run.logs}")
        except Exception as e:
            console.print(f"[bold red]Execution error: {str(e)}[/bold red]")
        finally:
            await scheduler.shutdown()

    asyncio.run(_run())

@app.command("version")
def version():
    """Print TaskForge version."""
    from taskforge import __version__
    console.print(f"[bold cyan]TaskForge[/bold cyan] version [bold white]{__version__}[/bold white]")

if __name__ == "__main__":
    app()
