import pytest

from taskforge.core.yaml_tasks import (
    detect_task_kind,
    dump_yaml,
    job_to_yaml,
    load_yaml,
    parse_and_validate_task,
    pipeline_to_yaml,
)
from taskforge.jobs.models import Job, Pipeline, PipelineStep


def test_load_and_dump_yaml():
    text = "name: taskforge\nenabled: true\ncount: 42\n"
    loaded = load_yaml(text)
    assert loaded == {"name": "taskforge", "enabled": True, "count": 42}
    dumped = dump_yaml(loaded)
    assert "name: taskforge" in dumped
    assert "count: 42" in dumped

    # Loading bytes
    assert load_yaml(b"foo: bar") == {"foo": "bar"}

    # Loading non-dict raises ValueError
    with pytest.raises(ValueError):
        load_yaml("- item1\n- item2")

    # Broken YAML raises ValueError
    with pytest.raises(ValueError):
        load_yaml("broken: [unclosed")


def test_detect_task_kind():
    assert detect_task_kind({"kind": "pipeline", "name": "p"}) == "pipeline"
    assert detect_task_kind({"kind": "job", "name": "j"}) == "job"
    assert detect_task_kind({"steps": [], "name": "p"}) == "pipeline"
    assert detect_task_kind({"executor": "python", "name": "j"}) == "job"


def test_job_to_yaml():
    job = Job(
        id="sample-job",
        project="default",
        name="Sample Job",
        trigger="manual",
        executor="python",
        command="print('hello')",
        webhook_secret="super-secret-do-not-reveal-32-chars-long",
    )
    yaml_out = job_to_yaml(job)
    assert "sample-job" in yaml_out
    assert "Sample Job" in yaml_out
    # Secret must be removed from export
    assert "super-secret-do-not-reveal-32-chars-long" not in yaml_out


def test_pipeline_to_yaml():
    step_job = Job(
        id="s1",
        project="default",
        name="Step 1",
        trigger="manual",
        executor="docker",
        image="python:3.12-alpine",
        command="print('step1')",
    )
    step = PipelineStep(id="s1", needs=[], job=step_job)
    pipe = Pipeline(
        id="sample-pipe",
        project="default",
        name="Sample Pipeline",
        version=0,
        steps=[step],
    )
    yaml_out = pipeline_to_yaml(pipe)
    assert "sample-pipe" in yaml_out
    assert "Sample Pipeline" in yaml_out
    assert "step1" in yaml_out


def test_parse_and_validate_task():
    job_yaml = """id: parsed-job
project: default
name: Parsed Job
trigger: manual
executor: shell
command: echo "ok"
"""
    kind, model = parse_and_validate_task(job_yaml)
    assert kind == "job"
    assert isinstance(model, Job)
    assert model.id == "parsed-job"

    pipe_yaml = """id: parsed-pipe
project: default
name: Parsed Pipeline
version: 0
steps:
  - id: step
    needs: []
    job:
      id: step
      project: default
      name: Step Job
      trigger: manual
      executor: shell
      command: echo "step"
"""
    kind2, model2 = parse_and_validate_task(pipe_yaml)
    assert kind2 == "pipeline"
    assert isinstance(model2, Pipeline)
    assert model2.id == "parsed-pipe"
