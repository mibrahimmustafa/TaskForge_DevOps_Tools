from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse

from taskforge.api.auth import Principal, authenticate
from taskforge.api.tree_filter import apply_tree_filter

router = APIRouter(prefix="/runs", tags=["Runs"])


async def find_run(request: Request, run_id: str, principal: Principal, role="viewer"):
    run = await request.app.state.db.run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    principal.check(run["project"], role)
    return run


def public_run(run):
    definition = run["payload"].get("definition", {})
    build_num = run["result"].get("build_number") or run["payload"].get("build_number")
    cause = run["result"].get("cause") or run["payload"].get("cause", {})
    params = run["result"].get("parameters") or run["payload"].get("parameters", {})
    keep = bool(run["result"].get("keep_forever", False))
    artifacts = run["result"].get("artifacts", [])
    return {
        key: run[key]
        for key in ("id", "project", "status", "created", "finished", "result", "cancel")
    } | {
        "kind": run["payload"]["kind"],
        "name": definition.get("name", run["payload"].get("target", "Notification")),
        "definition_id": definition.get("id"),
        "definition_version": definition.get("version"),
        "build_number": build_num,
        "buildNumber": build_num,
        "cause": cause,
        "commit": run["payload"].get("commit"),
        "parameters": params,
        "image": run["payload"].get("image"),
        "target": run["payload"].get("target"),
        "approved_by": run["payload"].get("approved_by"),
        "keep_forever": keep,
        "keepForever": keep,
        "artifacts": artifacts,
    }


@router.get("")
async def list_runs(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    tree: str | None = Query(None),
    principal: Principal = Depends(authenticate),
):
    runs_data = [
        public_run(run) for run in await request.app.state.db.runs(principal.scope, limit, offset)
    ]
    return apply_tree_filter(runs_data, tree)


@router.get("/{run_id}")
async def get_run(
    run_id: str,
    request: Request,
    tree: str | None = Query(None),
    principal: Principal = Depends(authenticate),
):
    run = await find_run(request, run_id, principal)
    return apply_tree_filter(public_run(run), tree)


@router.get("/{run_id}/attempts")
async def attempts(run_id: str, request: Request, principal: Principal = Depends(authenticate)):
    await find_run(request, run_id, principal)
    return await request.app.state.db.attempts(run_id)


@router.post("/{run_id}/cancel", status_code=202)
async def cancel_run(run_id: str, request: Request, principal: Principal = Depends(authenticate)):
    run = await find_run(request, run_id, principal, "operator")
    if run["status"] not in {"queued", "running", "waiting_approval"}:
        raise HTTPException(409, "Run is already finished")
    await request.app.state.db.cancel_run(run_id)
    await request.app.state.db.record_audit(
        run["project"], principal.name, "run.cancel_requested", run_id
    )
    return {"id": run_id, "status": "cancellation_requested"}


@router.get("/{run_id}/logs")
async def get_logs(
    run_id: str,
    request: Request,
    after: int = Query(0, ge=0),
    principal: Principal = Depends(authenticate),
):
    run = await find_run(request, run_id, principal)
    records = await request.app.state.db.read_logs(run_id, after)
    return {
        "records": records,
        "cursor": records[-1]["sequence"] if records else after,
        "status": run["status"],
        "has_more": len(records) == 200,
    }


@router.get("/{run_id}/artifacts")
async def list_run_artifacts(
    run_id: str,
    request: Request,
    tree: str | None = Query(None),
    principal: Principal = Depends(authenticate),
):
    run = await find_run(request, run_id, principal)
    artifacts = run["result"].get("artifacts", [])
    data = {"artifacts": artifacts}
    return apply_tree_filter(data, tree)


@router.get("/{run_id}/artifacts/{digest}/preview")
async def preview_artifact(
    run_id: str,
    digest: str,
    request: Request,
    principal: Principal = Depends(authenticate),
):
    run = await find_run(request, run_id, principal)
    artifact = next(
        (
            item
            for item in run["result"].get("artifacts", [])
            if item.get("sha256") == digest
            or item.get("path") == digest
            or item.get("name") == digest
        ),
        None,
    )
    if not artifact:
        raise HTTPException(404, "Artifact not found")
    root = request.app.state.settings.data_dir.resolve() / "artifacts"
    target_path = None
    job_def = run["payload"].get("definition", {})
    job_id = job_def.get("id")
    build_num = run["result"].get("build_number") or run["payload"].get("build_number")
    build_str = str(build_num) if build_num is not None else run_id
    if job_id and artifact.get("path"):
        candidate = (root / run["project"] / job_id / build_str / artifact["path"]).resolve()
        if candidate.is_file() and candidate.is_relative_to(root):
            target_path = candidate
    if not target_path and artifact.get("sha256"):
        legacy = (root / run["project"] / run_id / artifact["sha256"]).resolve()
        if legacy.is_file() and legacy.is_relative_to(root):
            target_path = legacy
    if not target_path or not target_path.is_file():
        raise HTTPException(404, "Artifact is no longer available")
    if target_path.stat().st_size > 256 * 1024:
        raise HTTPException(400, "Artifact too large for inline preview (limit 256 KB)")
    try:
        content = target_path.read_text(encoding="utf-8")
        return {
            "name": Path(artifact["name"]).name,
            "sha256": artifact.get("sha256", digest),
            "size": target_path.stat().st_size,
            "content": content,
        }
    except UnicodeDecodeError:
        raise HTTPException(400, "Artifact is binary and cannot be previewed as text") from None


@router.get("/{run_id}/artifacts/{subpath:path}")
async def download_artifact(
    run_id: str,
    subpath: str,
    request: Request,
    principal: Principal = Depends(authenticate),
):
    run = await find_run(request, run_id, principal)
    artifacts = run["result"].get("artifacts", [])
    subpath_clean = subpath.strip("/\\").replace("\\", "/")

    # Check match by sha256 or relative path or filename
    artifact = next(
        (
            item
            for item in artifacts
            if item.get("sha256") == subpath
            or item.get("path") == subpath_clean
            or item.get("name") == subpath_clean
        ),
        None,
    )
    root = request.app.state.settings.data_dir.resolve() / "artifacts"
    target_path = None

    if artifact:
        # Check build directory
        job_def = run["payload"].get("definition", {})
        job_id = job_def.get("id")
        build_num = run["result"].get("build_number") or run["payload"].get("build_number")
        build_str = str(build_num) if build_num is not None else run_id
        if job_id:
            candidate = (root / run["project"] / job_id / build_str / artifact["path"]).resolve()
            if candidate.is_file() and candidate.is_relative_to(root):
                target_path = candidate

        # Fallback to legacy sha256 path
        if not target_path:
            legacy = (root / run["project"] / run_id / artifact["sha256"]).resolve()
            if legacy.is_file() and legacy.is_relative_to(root):
                target_path = legacy
    else:
        # Try direct subpath under run_id or build dir
        legacy = (root / run["project"] / run_id / subpath).resolve()
        if legacy.is_file() and legacy.is_relative_to(root):
            target_path = legacy

    if not target_path or not target_path.is_file():
        raise HTTPException(404, "Artifact not found or no longer available")

    filename = artifact["name"] if artifact else target_path.name
    return FileResponse(
        target_path,
        filename=filename,
        media_type="application/octet-stream",
    )


@router.get("/{run_id}/logs/download")
async def download_logs(
    run_id: str, request: Request, principal: Principal = Depends(authenticate)
):
    await find_run(request, run_id, principal)
    records = await request.app.state.db.read_logs(run_id, after=0, limit=100000)
    full_text = "".join(r["text"] for r in records)
    return PlainTextResponse(
        full_text,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{run_id}.log"'},
    )


@router.post("/{run_id}/keep")
async def toggle_keep_forever(
    run_id: str, request: Request, principal: Principal = Depends(authenticate)
):
    run = await find_run(request, run_id, principal, "operator")
    result = dict(run["result"])
    new_keep = not bool(result.get("keep_forever", False))
    result["keep_forever"] = new_keep
    from sqlalchemy import update

    from taskforge.storage.database import work

    async with request.app.state.db.engine.begin() as conn:
        await conn.execute(update(work).where(work.c.id == run_id).values(result=result))
    return {"id": run_id, "keep_forever": new_keep, "keepForever": new_keep}
