import hashlib
import json

import pytest

from taskforge.core.worker import Worker
from tests.conftest import VIEWER


@pytest.mark.parametrize("fail", [False, True])
async def test_environment_fencing_and_explicit_reconciliation(
    client, db, settings, monkeypatch, fail
):
    target = {
        "type": "docker",
        "project": "default",
        "image_repository": "example/app",
        "container": "app",
        "port": "127.0.0.1:18000:80",
        "health_url": "http://127.0.0.1:18000",
        "require_approval": False,
    }
    settings.deployment_targets = {"staging": target}
    image = "example/app@sha256:" + "a" * 64
    payload = {
        "kind": "deployment",
        "target": "staging",
        "image": image,
        "source_created": 10,
        "source_run": "build",
        "target_hash": hashlib.sha256(json.dumps(target, sort_keys=True).encode()).hexdigest(),
    }
    calls = []

    async def adapter(*args):
        calls.append(1)
        if fail:
            raise RuntimeError("health verification failed")
        return {"verified": True}

    monkeypatch.setattr("taskforge.core.worker.deploy", adapter)
    run = await db.enqueue("default", "deploy:staging", payload)
    await Worker(db, settings).execute(await db.claim("fence", 30))
    assert (await db.run(run["id"]))["status"] == ("failed" if fail else "success")
    if fail:
        assert not await db.lock("deploy:staging", "another", 30)
        endpoint = f"/api/deployments/{run['id']}/reconcile"
        assert (
            await client.post(
                endpoint,
                json={"confirmed_stopped": True},
                headers={"Authorization": "Bearer " + VIEWER},
            )
        ).status_code == 403
        assert (await client.post(endpoint, json={"confirmed_stopped": False})).status_code == 422
        assert (await client.post(endpoint, json={"confirmed_stopped": True})).status_code == 200
        assert await db.lock("deploy:staging", "another", 30)
    else:
        assert (await db.get("environment", "staging"))["image"] == image
        older = await db.enqueue("default", "deploy:staging", payload | {"source_created": 9})
        await Worker(db, settings).execute(await db.claim("older-fence", 30))
        assert (await db.run(older["id"]))["status"] == "failed"
        assert len(calls) == 1  # Old builds cannot overwrite a newer environment.
        await db.unlock("deploy:staging", "older-fence")
        rollback = await db.enqueue(
            "default", "deploy:staging", payload | {"source_created": 9, "rollback": True}
        )
        await Worker(db, settings).execute(await db.claim("rollback-fence", 30))
        assert (await db.run(rollback["id"]))["status"] == "success"
        assert len(calls) == 2
