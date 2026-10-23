import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from taskforge.api.auth import Principal, authenticate
from taskforge.api.routers.runs import find_run, public_run
from taskforge.deployments.adapters import validate_deployment

router = APIRouter(prefix="/deployments", tags=["Deployments"])


class DeploymentRequest(BaseModel):
    target: str
    image: str
    source_run: str


@router.get("/targets")
async def targets(request: Request, principal: Principal = Depends(authenticate)):
    return [
        {
            "id": name,
            "type": target["type"],
            "project": target["project"],
            "environment": target.get("environment", name),
            "require_approval": target.get("require_approval", True),
            "image_repository": target["image_repository"],
        }
        for name, target in request.app.state.settings.deployment_targets.items()
        if principal.scope is None or target["project"] in principal.scope
    ]


@router.post("", status_code=202)
async def request_deployment(
    body: DeploymentRequest, request: Request, principal: Principal = Depends(authenticate)
):
    target = request.app.state.settings.deployment_targets.get(body.target)
    if not target:
        raise HTTPException(404, "Deployment target not found")
    principal.check(target["project"], "operator")
    source = await find_run(request, body.source_run, principal)
    if source["project"] != target["project"] or source["status"] != "success":
        raise HTTPException(422, "Source run must be successful and belong to this project")
    validate_deployment(target, body.image, source["project"])
    # A build publishes release.json as an immutable artifact. Verify the selected
    # digest belongs to that successful build before requesting an approval.
    manifests = [
        item for item in source["result"].get("artifacts", []) if item["name"] == "release.json"
    ]
    proven = False
    for item in manifests:
        path = (
            request.app.state.settings.data_dir.resolve()
            / "artifacts"
            / source["project"]
            / source["id"]
            / item["sha256"]
        )
        if path.is_file():
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() == item["sha256"]:
                try:
                    proven = json.loads(raw).get("image") == body.image
                except (ValueError, AttributeError):
                    pass
        if proven:
            break
    if not proven:
        raise HTTPException(
            422, "Image must match a release.json artifact from the successful source run"
        )
    payload = {
        "kind": "deployment",
        "target": body.target,
        "image": body.image,
        "source_run": body.source_run,
        "requested_by": principal.name,
        "target_hash": hashlib.sha256(json.dumps(target, sort_keys=True).encode()).hexdigest(),
    }
    status = "waiting_approval" if target.get("require_approval", True) else "queued"
    run = await request.app.state.db.enqueue(
        source["project"], f"deploy:{body.target}", payload, status=status
    )
    await request.app.state.db.record_audit(
        source["project"], principal.name, "deployment.requested", run["id"]
    )
    return public_run(run)


@router.post("/{run_id}/approve", status_code=202)
async def approve(run_id: str, request: Request, principal: Principal = Depends(authenticate)):
    run = await find_run(request, run_id, principal, "admin")
    if run["payload"]["kind"] != "deployment":
        raise HTTPException(422, "Only deployments require approval")
    if run["payload"]["requested_by"] == principal.name:
        raise HTTPException(403, "A different administrator must approve this deployment")
    await request.app.state.db.approve(run_id, principal.name)
    await request.app.state.db.record_audit(
        run["project"], principal.name, "deployment.approved", run_id
    )
    return {"id": run_id, "status": "queued"}
