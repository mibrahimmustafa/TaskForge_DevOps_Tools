from typing import Any

import yaml

from taskforge.jobs.models import Job, Pipeline


def load_yaml(content: str | bytes) -> dict[str, Any]:
    """Parse YAML (or JSON) string/bytes into a dictionary safely."""
    if isinstance(content, bytes):
        content = content.decode("utf-8")
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML syntax: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("Task definition must be a YAML mapping (key-value dictionary)")
    return data


def dump_yaml(data: Any) -> str:
    """Format a Python dict/object as clean, readable YAML."""
    return yaml.safe_dump(
        data,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    )


def detect_task_kind(data: dict[str, Any]) -> str:
    """Detect whether a parsed mapping represents a job or a pipeline."""
    explicit_kind = str(data.get("kind", "")).strip().lower()
    if explicit_kind in {"job", "pipeline"}:
        return explicit_kind
    if "steps" in data and isinstance(data["steps"], list):
        if len(data["steps"]) > 0:
            first = data["steps"][0]
            if (
                isinstance(first, dict)
                and ("executor" in first or "command" in first)
                and ("needs" not in first and "job" not in first)
            ):
                return "job"
        return "pipeline"
    return "job"


def job_to_yaml(job: Job | dict[str, Any]) -> str:
    """Convert a Job model or job dict into clean YAML representation."""
    if isinstance(job, Job):
        raw = job.model_dump(mode="json", exclude={"webhook_secret"})
    else:
        raw = dict(job)
        raw.pop("webhook_secret", None)
        raw.pop("desc", None)
        raw.pop("triggerExpr", None)

    # Clean None or internal metadata fields for cleaner YAML output
    for key in (
        "next_run",
        "last_run",
        "last_duration",
        "last_status",
        "nextRun",
        "lastRun",
        "lastDuration",
        "lastStatus",
        "has_webhook_secret",
    ):
        raw.pop(key, None)
    if raw.get("image") is None:
        raw.pop("image", None)

    return dump_yaml(raw)


def pipeline_to_yaml(pipeline: Pipeline | dict[str, Any]) -> str:
    """Convert a Pipeline model or pipeline dict into clean YAML representation."""
    raw = pipeline.model_dump(mode="json") if isinstance(pipeline, Pipeline) else dict(pipeline)

    # Sanitize any hidden webhook secrets in step jobs
    if "steps" in raw and isinstance(raw["steps"], list):
        for step in raw["steps"]:
            if isinstance(step, dict) and "job" in step and isinstance(step["job"], dict):
                step["job"].pop("webhook_secret", None)

    return dump_yaml(raw)


def parse_and_validate_task(content: str | bytes) -> tuple[str, Job | Pipeline]:
    """Parse YAML content and validate against Job or Pipeline models."""
    data = load_yaml(content)
    kind = detect_task_kind(data)
    data.pop("kind", None)

    if kind == "pipeline":
        pipeline = Pipeline.model_validate(data)
        return "pipeline", pipeline
    else:
        job = Job.model_validate(data)
        return "job", job
