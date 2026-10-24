import asyncio
import hashlib
import hmac
import json

from taskforge.core.worker import Worker
from tests.conftest import OTHER, REVIEWER, VIEWER


def job_payload(**changes):
    return {
        "id": "example",
        "name": "Example",
        "trigger": "manual",
        "executor": "python",
        "command": "print('verified output')",
        **changes,
    }


async def test_auth_scopes_and_validation(client):
    assert (await client.get("/api/jobs", headers={"Authorization": ""})).status_code == 401
    assert (
        await client.post(
            "/api/jobs", json=job_payload(), headers={"Authorization": "Bearer " + VIEWER}
        )
    ).status_code == 403
    assert (await client.post("/api/jobs", json=job_payload())).status_code == 200
    assert (
        await client.get("/api/jobs", headers={"Authorization": "Bearer " + OTHER})
    ).json() == []
    assert (
        await client.get("/api/jobs/example", headers={"Authorization": "Bearer " + OTHER})
    ).status_code == 404
    assert (await client.post("/api/jobs", json=job_payload())).status_code == 409
    assert (
        await client.post(
            "/api/jobs", json=job_payload(id="bad", trigger="interval", trigger_expr="nonsense")
        )
    ).status_code == 422
    assert (await client.get("/api/jobs/bad")).status_code == 404


async def test_full_queued_execution_logs_artifacts(client, db, settings):
    payload = job_payload(
        command="from pathlib import Path; print('real output'); Path('result.txt').write_text('verified')",
        artifact_paths=["result.txt"],
    )
    saved = (await client.post("/api/jobs", json=payload)).json()
    response = await client.post("/api/jobs/example/run", headers={"Idempotency-Key": "once"})
    assert response.status_code == 202
    identifier = response.json()["id"]
    repeat = await client.post("/api/jobs/example/run", headers={"Idempotency-Key": "once"})
    assert repeat.json()["id"] == identifier
    assert (await client.get(f"/api/runs/{identifier}")).json()["status"] == "queued"
    runner = Worker(db, settings)
    await runner.tick()
    await asyncio.gather(*runner.tasks)
    run = (await client.get(f"/api/runs/{identifier}")).json()
    assert run["status"] == "success"
    records = (await client.get(f"/api/runs/{identifier}/logs")).json()
    assert "real output" in "".join(row["text"] for row in records["records"])
    artifact = run["result"]["artifacts"][0]
    assert (
        await client.get(f"/api/runs/{identifier}/artifacts/{artifact['sha256']}")
    ).text == "verified"
    preview_res = await client.get(f"/api/runs/{identifier}/artifacts/{artifact['sha256']}/preview")
    assert preview_res.status_code == 200
    assert preview_res.json()["content"] == "verified"
    assert preview_res.json()["name"] == "result.txt"
    assert (
        await client.get(f"/api/runs/{identifier}/artifacts/not-exists/preview")
    ).status_code == 404
    assert (
        await client.get(
            f"/api/runs/{identifier}/artifacts/{artifact['sha256']}",
            headers={"Authorization": "Bearer " + OTHER},
        )
    ).status_code == 404
    assert (await client.delete(f"/api/jobs/example?version={saved['version']}")).status_code == 200
    assert (await client.get("/api/jobs/example")).status_code == 404
    assert (await client.get(f"/api/runs/{identifier}")).status_code == 200


async def test_webhook_secret_redaction_and_dedupe(client):
    secret = "secret-" + "s" * 40
    response = await client.post(
        "/api/jobs", json=job_payload(trigger="webhook", webhook_secret=secret)
    )
    assert response.status_code == 200
    assert secret not in response.text and "sha256:" not in response.text
    assert (
        await client.post("/api/triggers/webhook/example", headers={"Idempotency-Key": "event"})
    ).status_code == 403
    headers = {"X-Taskforge-Secret": secret, "Idempotency-Key": "event", "Authorization": ""}
    first = await client.post("/api/triggers/webhook/example", headers=headers)
    assert first.status_code == 202
    second = await client.post("/api/triggers/webhook/example", headers=headers)
    assert second.json()["id"] == first.json()["id"]
    await client.post("/api/jobs/example/pause")
    assert (await client.post("/api/triggers/webhook/example", headers=headers)).status_code == 404


async def test_github_signed_delivery_deduplicates_changed_delivery_id(client, settings):
    settings.github_secret = "github-test-secret"
    settings.github_repositories = ["example/repo"]
    pipeline = {
        "id": "ci",
        "name": "CI",
        "repository": "example/repo",
        "steps": [{"id": "test", "job": job_payload()}],
    }
    assert (await client.post("/api/pipelines", json=pipeline)).status_code == 200
    body = json.dumps(
        {"repository": {"full_name": "example/repo"}, "ref": "refs/heads/main", "after": "a" * 40}
    ).encode()
    headers = {
        "X-GitHub-Event": "push",
        "X-Hub-Signature-256": "sha256="
        + hmac.new(settings.github_secret.encode(), body, hashlib.sha256).hexdigest(),
    }
    first = await client.post("/api/triggers/github", content=body, headers=headers)
    second = await client.post(
        "/api/triggers/github", content=body, headers=headers | {"X-GitHub-Delivery": "changed"}
    )
    assert first.status_code == 202 and first.json() == second.json()
    assert (
        await client.post("/api/triggers/github", content=b"tampered", headers=headers)
    ).status_code == 403


async def test_deployment_provenance_and_separate_approval(client, db, settings):
    image = "example/app@sha256:" + "a" * 64
    settings.deployment_targets = {
        "staging": {
            "type": "docker",
            "project": "default",
            "container": "example",
            "port": "127.0.0.1:18000:80",
            "health_url": "http://127.0.0.1:18000",
            "image_repository": "example/app",
        }
    }
    source = await db.enqueue("default", "build", {"kind": "job", "definition": {}})
    claimed = await db.claim("builder", 30)
    raw = json.dumps({"image": image}).encode()
    digest = hashlib.sha256(raw).hexdigest()
    path = settings.data_dir / "artifacts" / "default" / source["id"] / digest
    path.parent.mkdir(parents=True)
    path.write_bytes(raw)
    await db.finish(
        source["id"],
        claimed["owner"],
        "success",
        {"artifacts": [{"name": "release.json", "sha256": digest, "size": len(raw)}]},
    )
    body = {"target": "staging", "image": image, "source_run": source["id"]}
    response = await client.post("/api/deployments", json=body)
    assert response.status_code == 202
    identifier = response.json()["id"]
    assert (await client.post(f"/api/deployments/{identifier}/approve")).status_code == 403
    assert (
        await client.post(
            f"/api/deployments/{identifier}/approve",
            headers={"Authorization": "Bearer " + REVIEWER},
        )
    ).status_code == 202
    assert (
        await client.post(
            f"/api/deployments/{identifier}/approve",
            headers={"Authorization": "Bearer " + REVIEWER},
        )
    ).status_code == 409
    assert (
        await client.post("/api/deployments", json=body | {"image": "example/app:latest"})
    ).status_code == 422


async def test_health_security_headers_and_no_fake_extensions(client):
    assert (await client.get("/health")).status_code == 200
    assert (await client.get("/ready")).status_code == 200
    dashboard = await client.get("/dashboard/")
    assert dashboard.status_code == 200
    assert "script-src 'self'" in dashboard.headers["content-security-policy"]
    assert "TaskForge" in dashboard.text
    assert (await client.get("/api/runs?limit=-1")).status_code == 422
    assert (await client.get("/api/system/env")).json()["storage"] in {"sqlite", "postgresql"}
    assert (await client.post("/api/plugins/git_trigger/toggle")).status_code == 404


async def test_streaming_request_size_is_bounded(client):
    async def oversized_body():
        for _ in range(17):
            yield b"x" * 65536

    response = await client.post("/api/jobs", content=oversized_body())
    assert response.status_code == 413


async def test_user_management_lifecycle_and_role_enforcement(client):
    # 1. Unauthenticated and non-admin checks
    assert (await client.get("/api/users", headers={"Authorization": ""})).status_code == 401
    assert (
        await client.get("/api/users", headers={"Authorization": "Bearer " + VIEWER})
    ).status_code == 403

    # 2. Admin lists users (starts with static config tokens)
    users_res = await client.get("/api/users")
    assert users_res.status_code == 200
    names = [u["name"] for u in users_res.json()]
    assert "admin" in names
    assert "viewer" in names
    assert all(u["source"] == "config" for u in users_res.json())

    # 3. Create operator user with specific project scope
    create_payload = {
        "name": "charlie-operator",
        "role": "operator",
        "projects": ["default"],
    }
    create_res = await client.post("/api/users", json=create_payload)
    assert create_res.status_code == 200
    data = create_res.json()
    assert data["name"] == "charlie-operator"
    assert data["role"] == "operator"
    assert data["projects"] == ["default"]
    assert data["source"] == "db"
    assert len(data["token"]) >= 32
    operator_token = data["token"]

    # 4. Duplicate creation must fail (409 Conflict)
    dup_res = await client.post("/api/users", json=create_payload)
    assert dup_res.status_code == 409

    # 5. Invalid project format must fail (422)
    invalid_res = await client.post(
        "/api/users", json={"name": "bad-user", "role": "viewer", "projects": ["invalid project!"]}
    )
    assert invalid_res.status_code == 422

    # 6. Verify authentication with new operator token
    session_res = await client.get(
        "/api/session", headers={"Authorization": "Bearer " + operator_token}
    )
    assert session_res.status_code == 200
    assert session_res.json() == {
        "name": "charlie-operator",
        "role": "operator",
        "projects": ["default"],
    }

    # Operator cannot create jobs (requires admin)
    assert (
        await client.post(
            "/api/jobs",
            json=job_payload(id="operator-forbidden"),
            headers={"Authorization": "Bearer " + operator_token},
        )
    ).status_code == 403

    # Operator cannot access /api/users
    assert (
        await client.get("/api/users", headers={"Authorization": "Bearer " + operator_token})
    ).status_code == 403

    # 7. Update user role to viewer via PATCH
    patch_res = await client.patch(
        "/api/users/charlie-operator",
        json={"role": "viewer"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["role"] == "viewer"

    # Authenticate again with same token -> role is now viewer!
    session_res2 = await client.get(
        "/api/session", headers={"Authorization": "Bearer " + operator_token}
    )
    assert session_res2.json()["role"] == "viewer"

    # 8. Regenerate token
    regen_res = await client.post("/api/users/charlie-operator/token")
    assert regen_res.status_code == 200
    new_token = regen_res.json()["token"]
    assert new_token != operator_token

    # Old token must now be rejected (401)
    assert (
        await client.get("/api/session", headers={"Authorization": "Bearer " + operator_token})
    ).status_code == 401

    # New token is accepted
    assert (
        await client.get("/api/session", headers={"Authorization": "Bearer " + new_token})
    ).status_code == 200

    # 9. Delete safety guards:
    # Cannot delete self
    assert (await client.delete("/api/users/admin")).status_code == 400
    # Cannot delete static config user
    assert (await client.delete("/api/users/viewer")).status_code == 400
    # Cannot delete non-existent user
    assert (await client.delete("/api/users/non-existent-user")).status_code == 404

    # 10. Delete the database user
    delete_res = await client.delete("/api/users/charlie-operator")
    assert delete_res.status_code == 200
    assert delete_res.json() == {"success": True}

    # Token is now revoked
    assert (
        await client.get("/api/session", headers={"Authorization": "Bearer " + new_token})
    ).status_code == 401


async def test_job_yaml_endpoints(client):
    yaml_job = """id: yaml-cron-job
project: default
name: YAML Cron Task
trigger: cron
trigger_expr: "0 4 * * *"
timezone: UTC
executor: python
command: print("YAML cron execution")
timeout_seconds: 180
max_retries: 1
retry_delay_seconds: 5
description: Job created from raw YAML endpoint
"""
    # Create job via POST /api/jobs/yaml
    res = await client.post(
        "/api/jobs/yaml",
        content=yaml_job,
        headers={"Content-Type": "application/yaml"},
    )
    assert res.status_code == 200
    job_data = res.json()
    assert job_data["id"] == "yaml-cron-job"
    assert job_data["name"] == "YAML Cron Task"

    # Export job as YAML via GET /api/jobs/{id}/yaml
    yaml_res = await client.get("/api/jobs/yaml-cron-job/yaml")
    assert yaml_res.status_code == 200
    assert "application/yaml" in yaml_res.headers.get("content-type", "")
    assert "yaml-cron-job" in yaml_res.text
    assert "YAML Cron Task" in yaml_res.text

    # Invalid YAML syntax rejected
    bad_syntax = "id: [broken yaml"
    bad_res = await client.post(
        "/api/jobs/yaml",
        content=bad_syntax,
        headers={"Content-Type": "application/yaml"},
    )
    assert bad_res.status_code == 422

    # Invalid job schema rejected
    bad_schema = """id: bad-schema-job
project: default
name: Bad Job
trigger: interval
trigger_expr: not-a-valid-interval
executor: python
command: pass
"""
    schema_res = await client.post(
        "/api/jobs/yaml",
        content=bad_schema,
        headers={"Content-Type": "application/yaml"},
    )
    assert schema_res.status_code == 422


async def test_pipeline_yaml_endpoints(client):
    yaml_pipeline = """id: yaml-pipeline-sample
project: default
name: YAML Sample Pipeline
version: 0
description: Pipeline created via YAML endpoint
steps:
  - id: step-one
    needs: []
    job:
      id: step-one
      project: default
      name: First Step
      trigger: manual
      executor: python
      command: print("step 1")
  - id: step-two
    needs:
      - step-one
    job:
      id: step-two
      project: default
      name: Second Step
      trigger: manual
      executor: python
      command: print("step 2")
"""
    # Create pipeline via POST /api/pipelines/yaml
    res = await client.post(
        "/api/pipelines/yaml",
        content=yaml_pipeline,
        headers={"Content-Type": "application/yaml"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == "yaml-pipeline-sample"
    assert len(data["steps"]) == 2

    # Export pipeline as YAML via GET /api/pipelines/{id}/yaml
    export_res = await client.get("/api/pipelines/yaml-pipeline-sample/yaml")
    assert export_res.status_code == 200
    assert "application/yaml" in export_res.headers.get("content-type", "")
    assert "yaml-pipeline-sample" in export_res.text
    assert "step-two" in export_res.text


async def test_tasks_apply_and_validate(client):
    # 1. Dry run validation: job
    valid_job_yaml = """id: task-validate-job
project: default
name: Validate Me
trigger: manual
executor: shell
command: echo "Validated"
"""
    val_job_res = await client.post(
        "/api/tasks/validate",
        content=valid_job_yaml,
        headers={"Content-Type": "application/yaml"},
    )
    assert val_job_res.status_code == 200
    assert val_job_res.json()["valid"] is True
    assert val_job_res.json()["kind"] == "job"
    assert val_job_res.json()["id"] == "task-validate-job"

    # 2. Dry run validation: pipeline
    valid_pipe_yaml = """id: task-validate-pipe
project: default
name: Validate Pipeline
version: 0
steps:
  - id: s1
    needs: []
    job:
      id: s1
      project: default
      name: Step 1
      trigger: manual
      executor: shell
      command: echo "step1"
"""
    val_pipe_res = await client.post(
        "/api/tasks/validate",
        content=valid_pipe_yaml,
        headers={"Content-Type": "application/yaml"},
    )
    assert val_pipe_res.status_code == 200
    assert val_pipe_res.json()["valid"] is True
    assert val_pipe_res.json()["kind"] == "pipeline"
    assert val_pipe_res.json()["steps_count"] == 1

    # 3. Apply multi-document stream containing both a job and a pipeline
    multi_doc_yaml = """---
id: applied-stream-job
project: default
name: Applied Stream Job
trigger: manual
executor: python
command: print("stream job")
---
id: applied-stream-pipeline
project: default
name: Applied Stream Pipeline
version: 0
steps:
  - id: test
    needs: []
    job:
      id: test
      project: default
      name: Run tests
      trigger: manual
      executor: python
      command: print("stream tests")
"""
    apply_res = await client.post(
        "/api/tasks/apply",
        content=multi_doc_yaml,
        headers={"Content-Type": "application/yaml"},
    )
    assert apply_res.status_code == 200
    apply_data = apply_res.json()
    assert apply_data["total"] == 2
    kinds = [item["kind"] for item in apply_data["applied"]]
    assert "job" in kinds and "pipeline" in kinds

    # Verify both can be queried via their respective endpoints
    assert (await client.get("/api/jobs/applied-stream-job")).status_code == 200
    assert (await client.get("/api/pipelines/applied-stream-pipeline")).status_code == 200
