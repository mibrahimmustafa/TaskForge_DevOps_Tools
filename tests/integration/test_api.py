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
