import hashlib
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from taskforge.api.auth import Principal, authenticate
from taskforge.api.tree_filter import apply_tree_filter
from taskforge.core.yaml_tasks import job_to_yaml, load_yaml
from taskforge.jobs.models import Job, JobStatus

router = APIRouter(prefix="/jobs", tags=["Jobs"])


async def find_job(request: Request, job_id: str, principal: Principal, role="viewer"):
    value = await request.app.state.db.get("job", job_id)
    if not value:
        raise HTTPException(404, "Job not found")
    principal.check(value["project"], role)
    return Job.model_validate(value)


async def persist_job(job: Job, request: Request, principal: Principal) -> dict:
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


@router.get("")
async def list_jobs(
    request: Request,
    tree: str | None = Query(None),
    principal: Principal = Depends(authenticate),
):
    jobs_data = [
        Job.model_validate(value).to_dict()
        for value in await request.app.state.db.list("job", principal.scope)
    ]
    return apply_tree_filter(jobs_data, tree)


@router.post("")
async def save_job(job: Job, request: Request, principal: Principal = Depends(authenticate)):
    return await persist_job(job, request, principal)


@router.post("/yaml")
async def save_job_yaml(request: Request, principal: Principal = Depends(authenticate)):
    raw = await request.body()
    data = load_yaml(raw)
    data.pop("kind", None)
    job = Job.model_validate(data)
    return await persist_job(job, request, principal)


@router.get("/{job_id}/yaml")
async def get_job_yaml(job_id: str, request: Request, principal: Principal = Depends(authenticate)):
    job = await find_job(request, job_id, principal)
    return Response(content=job_to_yaml(job), media_type="application/yaml")


@router.get("/{job_id}")
async def get_job(
    job_id: str,
    request: Request,
    tree: str | None = Query(None),
    principal: Principal = Depends(authenticate),
):
    job = await find_job(request, job_id, principal)
    return apply_tree_filter(job.to_dict(), tree)


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


class RunJobRequest(BaseModel):
    parameters: dict[str, Any] = Field(default_factory=dict)


@router.post("/{job_id}/run", status_code=202)
async def run_job(
    job_id: str,
    request: Request,
    body: RunJobRequest | None = None,
    principal: Principal = Depends(authenticate),
):
    job = await find_job(request, job_id, principal, "operator")
    if not job.enabled:
        raise HTTPException(400, f"Job '{job_id}' is disabled and cannot be executed")
    key = request.headers.get("idempotency-key")
    if key and len(key) > 100:
        raise HTTPException(422, "Idempotency key must not exceed 100 characters")

    # Validate parameters if defined
    provided_params = (body.parameters if body else {}) or {}
    validated_params: dict[str, Any] = {}
    for p_def in job.parameters:
        val = provided_params.get(p_def.name, p_def.default_value)
        if val is None and p_def.type.value in {"string", "choice"}:
            val = p_def.choices[0] if p_def.choices else ""
        if p_def.type.value == "choice" and p_def.choices and val not in p_def.choices:
            raise HTTPException(
                422,
                f"Invalid value '{val}' for choice parameter '{p_def.name}'. Allowed: {p_def.choices}",
            )
        if p_def.trim and isinstance(val, str):
            val = val.strip()
        validated_params[p_def.name] = val

    # Merge any other custom passed params
    for k, v in provided_params.items():
        if k not in validated_params:
            validated_params[k] = v

    run = await request.app.state.scheduler.submit(
        job,
        dedupe=f"manual:{job.project}:{job.id}:{key}" if key else None,
        parameters=validated_params,
        cause={"type": "user", "user": principal.name},
    )
    await request.app.state.db.record_audit(job.project, principal.name, "run.submitted", run["id"])
    return {
        "id": run["id"],
        "status": run["status"],
        "buildNumber": run["payload"].get("build_number"),
    }


@router.post("/{job_id}/enable")
async def enable_job(job_id: str, request: Request, principal: Principal = Depends(authenticate)):
    job = await find_job(request, job_id, principal, "operator")
    job.enabled = True
    saved = await request.app.state.scheduler.add_or_update_job(job)
    await request.app.state.db.record_audit(job.project, principal.name, "job.enabled", job.id)
    return saved.to_dict()


@router.post("/{job_id}/disable")
async def disable_job(job_id: str, request: Request, principal: Principal = Depends(authenticate)):
    job = await find_job(request, job_id, principal, "operator")
    job.enabled = False
    saved = await request.app.state.scheduler.add_or_update_job(job)
    await request.app.state.db.record_audit(job.project, principal.name, "job.disabled", job.id)
    return saved.to_dict()


@router.post("/{job_id}/copy")
async def copy_job(
    job_id: str,
    request: Request,
    new_id: str = Query(..., pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,99}$"),
    new_name: str | None = Query(None),
    principal: Principal = Depends(authenticate),
):
    job = await find_job(request, job_id, principal, "admin")
    if await request.app.state.db.get("job", new_id):
        raise HTTPException(409, f"A job with ID '{new_id}' already exists")

    data = job.model_dump(mode="json")
    data["id"] = new_id
    data["name"] = new_name or f"{job.name} (Copy)"
    data["version"] = 0
    data.pop("created_at", None)
    data["next_run"] = None
    data["last_run"] = None
    data["last_status"] = None
    data["last_duration"] = None

    new_job = Job.model_validate(data)
    return await persist_job(new_job, request, principal)


@router.post("/{job_id}/rename")
async def rename_job(
    job_id: str,
    request: Request,
    new_id: str = Query(..., pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,99}$"),
    new_name: str | None = Query(None),
    principal: Principal = Depends(authenticate),
):
    job = await find_job(request, job_id, principal, "admin")
    if job.id == new_id:
        return job.to_dict()
    if await request.app.state.db.get("job", new_id):
        raise HTTPException(409, f"A job with ID '{new_id}' already exists")

    data = job.model_dump(mode="json")
    data["id"] = new_id
    if new_name:
        data["name"] = new_name
    data["version"] = 0

    new_job = Job.model_validate(data)
    saved = await persist_job(new_job, request, principal)
    # Remove old job definition
    await request.app.state.db.remove("job", job_id, job.version)
    await request.app.state.db.record_audit(
        job.project, principal.name, "job.renamed", f"{job_id}->{new_id}"
    )
    return saved


@router.get("/{job_id}/builds/{permalink}")
async def get_job_permalink(
    job_id: str,
    permalink: str,
    request: Request,
    tree: str | None = Query(None),
    principal: Principal = Depends(authenticate),
):
    job = await find_job(request, job_id, principal)
    from taskforge.api.routers.runs import public_run

    run = await request.app.state.db.get_job_permalink_run(job.project, job.id, permalink)
    if not run:
        raise HTTPException(
            404, f"No build matching permalink '{permalink}' found for job '{job_id}'"
        )
    return apply_tree_filter(public_run(run), tree)


@router.get("/{job_id}/builds/{permalink}/artifacts")
async def get_job_permalink_artifacts(
    job_id: str,
    permalink: str,
    request: Request,
    tree: str | None = Query(None),
    principal: Principal = Depends(authenticate),
):
    job = await find_job(request, job_id, principal)
    run = await request.app.state.db.get_job_permalink_run(job.project, job.id, permalink)
    if not run:
        raise HTTPException(
            404, f"No build matching permalink '{permalink}' found for job '{job_id}'"
        )
    artifacts = run["result"].get("artifacts", [])
    data = {"artifacts": artifacts}
    return apply_tree_filter(data, tree)


@router.get("/{job_id}/builds/{permalink}/artifacts/{subpath:path}")
async def download_job_permalink_artifact(
    job_id: str,
    permalink: str,
    subpath: str,
    request: Request,
    principal: Principal = Depends(authenticate),
):
    job = await find_job(request, job_id, principal)
    from taskforge.api.routers.runs import download_artifact

    run = await request.app.state.db.get_job_permalink_run(job.project, job.id, permalink)
    if not run:
        raise HTTPException(
            404, f"No build matching permalink '{permalink}' found for job '{job_id}'"
        )
    return await download_artifact(run["id"], subpath, request, principal)


@router.post("/{job_id}/retention/run")
async def run_retention(
    job_id: str,
    request: Request,
    principal: Principal = Depends(authenticate),
):
    job = await find_job(request, job_id, principal, "operator")
    from taskforge.jobs.retention import apply_build_retention

    result = await apply_build_retention(
        request.app.state.db, request.app.state.settings, job.project, job.id
    )
    await request.app.state.db.record_audit(
        job.project,
        principal.name,
        "job.retention_run",
        f"{job_id}:{len(result.get('purged_runs', []))}_purged",
    )
    return result


def _resolve_workspace_dir(settings_data_dir: Path, job: Job, latest_run_id: str | None) -> Path:
    base = settings_data_dir.resolve() / "workspaces"
    if latest_run_id:
        # Check step or job workspace under run
        run_ws = base / latest_run_id / "job"
        if run_ws.exists():
            return run_ws
        run_root = base / latest_run_id
        if run_root.exists():
            return run_root
    # Fallback to persistent job workspace
    job_ws = base / job.id
    job_ws.mkdir(parents=True, exist_ok=True)
    return job_ws


@router.get("/{job_id}/workspace")
async def list_workspace(
    job_id: str,
    request: Request,
    subpath: str = Query("", alias="path"),
    principal: Principal = Depends(authenticate),
):
    job = await find_job(request, job_id, principal)
    latest_run = await request.app.state.db.get_job_permalink_run(job.project, job.id, "last")
    latest_id = latest_run["id"] if latest_run else None
    ws_root = _resolve_workspace_dir(request.app.state.settings.data_dir, job, latest_id)

    target = (ws_root / subpath.lstrip("/\\")).resolve()
    if not target.is_relative_to(ws_root.resolve()):
        raise HTTPException(403, "Access outside workspace directory is forbidden")

    if not target.exists():
        return {"path": subpath, "exists": False, "entries": []}

    if target.is_file():
        return {
            "path": subpath,
            "type": "file",
            "size": target.stat().st_size,
            "modified": target.stat().st_mtime,
        }

    entries = []
    try:
        for item in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            entries.append(
                {
                    "name": item.name,
                    "is_dir": item.is_dir(),
                    "size": item.stat().st_size if item.is_file() else None,
                    "modified": item.stat().st_mtime,
                }
            )
    except PermissionError:
        raise HTTPException(403, "Permission denied accessing directory") from None

    return {"path": subpath, "exists": True, "entries": entries}


@router.get("/{job_id}/workspace/file")
async def get_workspace_file(
    job_id: str,
    request: Request,
    subpath: str = Query(..., alias="path"),
    principal: Principal = Depends(authenticate),
):
    job = await find_job(request, job_id, principal)
    latest_run = await request.app.state.db.get_job_permalink_run(job.project, job.id, "last")
    latest_id = latest_run["id"] if latest_run else None
    ws_root = _resolve_workspace_dir(request.app.state.settings.data_dir, job, latest_id)

    target = (ws_root / subpath.lstrip("/\\")).resolve()
    if not target.is_relative_to(ws_root.resolve()):
        raise HTTPException(403, "Access outside workspace directory is forbidden")
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "File not found in workspace")

    # If small text file, return text; otherwise send file response
    if target.stat().st_size > 10 * 1024 * 1024:
        raise HTTPException(413, "File exceeds 10 MiB preview limit")
    try:
        content = target.read_text(encoding="utf-8")
        return {
            "name": target.name,
            "path": subpath,
            "content": content,
            "size": target.stat().st_size,
        }
    except UnicodeDecodeError:
        from fastapi.responses import FileResponse

        return FileResponse(target, filename=target.name)


@router.post("/{job_id}/workspace/wipe")
async def wipe_workspace(
    job_id: str,
    request: Request,
    principal: Principal = Depends(authenticate),
):
    job = await find_job(request, job_id, principal, "operator")
    latest_run = await request.app.state.db.get_job_permalink_run(job.project, job.id, "last")
    latest_id = latest_run["id"] if latest_run else None
    ws_root = _resolve_workspace_dir(request.app.state.settings.data_dir, job, latest_id)

    if ws_root.exists():
        for child in ws_root.iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
    await request.app.state.db.record_audit(job.project, principal.name, "workspace.wiped", job_id)
    return {"success": True, "message": "Workspace wiped successfully"}


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
