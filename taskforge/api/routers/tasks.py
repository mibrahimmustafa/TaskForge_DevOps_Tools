import yaml
from fastapi import APIRouter, Depends, HTTPException, Request

from taskforge.api.auth import Principal, authenticate
from taskforge.api.routers.jobs import persist_job
from taskforge.api.routers.pipelines import persist_pipeline
from taskforge.core.yaml_tasks import detect_task_kind
from taskforge.jobs.models import Job, Pipeline

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.post("/apply")
async def apply_tasks(request: Request, principal: Principal = Depends(authenticate)):
    """Apply one or more declarative YAML or JSON task definitions (jobs or pipelines)."""
    raw_body = (await request.body()).decode("utf-8")
    if not raw_body.strip():
        raise HTTPException(422, "Task definition body cannot be empty")

    try:
        docs = list(yaml.safe_load_all(raw_body))
    except yaml.YAMLError as exc:
        raise HTTPException(422, f"Invalid YAML syntax: {exc}") from exc

    docs = [d for d in docs if d is not None]
    if not docs:
        raise HTTPException(422, "No valid YAML mappings found in submission")

    applied = []
    for doc in docs:
        if not isinstance(doc, dict):
            raise HTTPException(
                422, "Each document in the YAML stream must be a mapping (key-value dictionary)"
            )
        kind = detect_task_kind(doc)
        doc.pop("kind", None)

        if kind == "pipeline":
            pipeline = Pipeline.model_validate(doc)
            saved = await persist_pipeline(pipeline, request, principal)
            applied.append({"kind": "pipeline", "id": pipeline.id, "definition": saved})
        else:
            job = Job.model_validate(doc)
            saved = await persist_job(job, request, principal)
            applied.append({"kind": "job", "id": job.id, "definition": saved})

    return {"applied": applied, "total": len(applied)}


@router.post("/validate")
async def validate_tasks(request: Request, principal: Principal = Depends(authenticate)):
    """Dry-run validation for any YAML or JSON task definition without saving."""
    raw_body = (await request.body()).decode("utf-8")
    if not raw_body.strip():
        raise HTTPException(422, "Task definition body cannot be empty")

    try:
        data = yaml.safe_load(raw_body)
    except yaml.YAMLError as exc:
        raise HTTPException(422, f"Invalid YAML syntax: {exc}") from exc

    if not isinstance(data, dict):
        raise HTTPException(422, "Task definition must be a YAML mapping")

    kind = detect_task_kind(data)
    data.pop("kind", None)

    if kind == "pipeline":
        pipeline = Pipeline.model_validate(data)
        return {
            "valid": True,
            "kind": "pipeline",
            "id": pipeline.id,
            "name": pipeline.name,
            "project": pipeline.project,
            "steps_count": len(pipeline.steps),
        }
    else:
        job = Job.model_validate(data)
        return {
            "valid": True,
            "kind": "job",
            "id": job.id,
            "name": job.name,
            "project": job.project,
            "executor": job.executor.value,
            "trigger": job.trigger.value,
        }
