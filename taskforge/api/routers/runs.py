from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse

from taskforge.api.auth import Principal, authenticate

router = APIRouter(prefix="/runs", tags=["Runs"])


async def find_run(request: Request, run_id: str, principal: Principal, role="viewer"):
    run = await request.app.state.db.run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    principal.check(run["project"], role)
    return run


def public_run(run):
    definition = run["payload"].get("definition", {})
    return {
        key: run[key]
        for key in ("id", "project", "status", "created", "finished", "result", "cancel")
    } | {
        "kind": run["payload"]["kind"],
        "name": definition.get("name", run["payload"].get("target", "Notification")),
        "definition_id": definition.get("id"),
        "definition_version": definition.get("version"),
        "commit": run["payload"].get("commit"),
        "parameters": run["payload"].get("parameters", {}),
        "image": run["payload"].get("image"),
        "target": run["payload"].get("target"),
        "approved_by": run["payload"].get("approved_by"),
    }


@router.get("")
async def list_runs(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(authenticate),
):
    return [
        public_run(run) for run in await request.app.state.db.runs(principal.scope, limit, offset)
    ]


@router.get("/{run_id}")
async def get_run(run_id: str, request: Request, principal: Principal = Depends(authenticate)):
    return public_run(await find_run(request, run_id, principal))


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


@router.get("/{run_id}/artifacts/{digest}")
async def download_artifact(
    run_id: str, digest: str, request: Request, principal: Principal = Depends(authenticate)
):
    run = await find_run(request, run_id, principal)
    artifact = next(
        (item for item in run["result"].get("artifacts", []) if item["sha256"] == digest), None
    )
    if not artifact:
        raise HTTPException(404, "Artifact not found")
    root = request.app.state.settings.data_dir.resolve() / "artifacts"
    path = (root / run["project"] / run_id / digest).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(404, "Artifact is no longer available")
    return FileResponse(
        path, filename=Path(artifact["name"]).name, media_type="application/octet-stream"
    )


@router.get("/{run_id}/artifacts/{digest}/preview")
async def preview_artifact(
    run_id: str, digest: str, request: Request, principal: Principal = Depends(authenticate)
):
    run = await find_run(request, run_id, principal)
    artifact = next(
        (item for item in run["result"].get("artifacts", []) if item["sha256"] == digest), None
    )
    if not artifact:
        raise HTTPException(404, "Artifact not found")
    root = request.app.state.settings.data_dir.resolve() / "artifacts"
    path = (root / run["project"] / run_id / digest).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(404, "Artifact is no longer available")
    if path.stat().st_size > 256 * 1024:
        raise HTTPException(400, "Artifact too large for inline preview (limit 256 KB)")
    try:
        content = path.read_text(encoding="utf-8")
        return {
            "name": Path(artifact["name"]).name,
            "sha256": digest,
            "size": path.stat().st_size,
            "content": content,
        }
    except UnicodeDecodeError:
        raise HTTPException(400, "Artifact is binary and cannot be previewed as text") from None
