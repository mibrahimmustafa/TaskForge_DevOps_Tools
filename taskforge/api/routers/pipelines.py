import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from taskforge.api.auth import Principal, authenticate
from taskforge.core.scheduler import validate_job
from taskforge.core.yaml_tasks import load_yaml, pipeline_to_yaml
from taskforge.jobs.models import Pipeline

router = APIRouter(prefix="/pipelines", tags=["Pipelines"])


class PipelineSubmission(BaseModel):
    commit: str | None = None
    parameters: dict[str, str] = Field(default_factory=dict)


async def persist_pipeline(pipeline: Pipeline, request: Request, principal: Principal) -> dict:
    principal.check(pipeline.project, "admin")
    old = await request.app.state.db.get("pipeline", pipeline.id)
    if old:
        principal.check(old["project"], "admin")
        if old["project"] != pipeline.project:
            raise HTTPException(409, "A definition cannot move between projects")
    for step in pipeline.steps:
        # Step triggers are not used; reject hidden webhook credentials.
        if step.job.webhook_secret or step.job.trigger not in {"manual", "cron", "interval"}:
            raise HTTPException(422, "Pipeline steps must not define webhook or one-shot triggers")
        validate_job(step.job)
    value = pipeline.model_dump(mode="json")
    saved = await request.app.state.db.put("pipeline", value, pipeline.version)
    await request.app.state.db.record_audit(
        pipeline.project, principal.name, "pipeline.saved", pipeline.id
    )
    return saved


@router.get("")
async def list_pipelines(request: Request, principal: Principal = Depends(authenticate)):
    values = await request.app.state.db.list("pipeline", principal.scope)
    for value in values:
        for step in value["steps"]:
            step["job"].pop("webhook_secret", None)
    return values


@router.post("")
async def save_pipeline(
    pipeline: Pipeline, request: Request, principal: Principal = Depends(authenticate)
):
    return await persist_pipeline(pipeline, request, principal)


@router.post("/yaml")
async def save_pipeline_yaml(request: Request, principal: Principal = Depends(authenticate)):
    raw = await request.body()
    data = load_yaml(raw)
    data.pop("kind", None)
    pipeline = Pipeline.model_validate(data)
    return await persist_pipeline(pipeline, request, principal)


@router.get("/{pipeline_id}/yaml")
async def get_pipeline_yaml(
    pipeline_id: str, request: Request, principal: Principal = Depends(authenticate)
):
    value = await request.app.state.db.get("pipeline", pipeline_id)
    if not value:
        raise HTTPException(404, "Pipeline not found")
    pipeline = Pipeline.model_validate(value)
    principal.check(pipeline.project, "viewer")
    return Response(content=pipeline_to_yaml(pipeline), media_type="application/yaml")


@router.get("/{pipeline_id}")
async def get_pipeline(
    pipeline_id: str, request: Request, principal: Principal = Depends(authenticate)
):
    value = await request.app.state.db.get("pipeline", pipeline_id)
    if not value:
        raise HTTPException(404, "Pipeline not found")
    pipeline = Pipeline.model_validate(value)
    principal.check(pipeline.project, "viewer")
    pipeline_dict = pipeline.model_dump(mode="json")
    for step in pipeline_dict["steps"]:
        step["job"].pop("webhook_secret", None)
    return pipeline_dict


@router.post("/{pipeline_id}/run", status_code=202)
async def run_pipeline(
    pipeline_id: str,
    body: PipelineSubmission,
    request: Request,
    principal: Principal = Depends(authenticate),
):
    value = await request.app.state.db.get("pipeline", pipeline_id)
    if not value:
        raise HTTPException(404, "Pipeline not found")
    pipeline = Pipeline.model_validate(value)
    principal.check(pipeline.project, "operator")
    if pipeline.repository and (not body.commit or not re.fullmatch(r"[a-f0-9]{40}", body.commit)):
        raise HTTPException(422, "Provide an exact 40-character Git commit SHA")
    run = await request.app.state.scheduler.submit_pipeline(
        pipeline, body.commit, parameters=body.parameters
    )
    await request.app.state.db.record_audit(
        pipeline.project, principal.name, "pipeline.submitted", run["id"]
    )
    return {"id": run["id"], "status": run["status"]}
