import json

import pytest

from taskforge.deployments.adapters import deploy, validate_deployment

IMAGE = "example/app@sha256:" + "a" * 64


def test_digest_project_repository_checks():
    target = {
        "type": "kubernetes",
        "project": "default",
        "image_repository": "example/app",
        "namespace": "apps",
        "deployment": "app",
        "container": "app",
        "context": "test",
    }
    validate_deployment(target, IMAGE, "default")
    for image, project in [
        ("example/app:latest", "default"),
        (IMAGE, "other"),
        (IMAGE.replace("example", "evil"), "default"),
    ]:
        with pytest.raises(ValueError):
            validate_deployment(target, image, project)


@pytest.mark.parametrize("fail", [False, True])
async def test_kubernetes_verifies_rollout_and_restores_previous_image(monkeypatch, fail):
    calls = []
    target = {
        "type": "kubernetes",
        "namespace": "apps",
        "deployment": "app",
        "container": "app",
        "context": "test",
    }
    old = "example/app@sha256:" + "b" * 64

    async def command(args, timeout, **kwargs):
        calls.append(args)
        if "get" in args:
            return 0, json.dumps(
                {"spec": {"template": {"spec": {"containers": [{"name": "app", "image": old}]}}}}
            )
        if fail and "rollout" in args and sum("rollout" in call for call in calls) == 1:
            return 1, "unhealthy"
        return 0, ""

    async def sink(value):
        pass

    monkeypatch.setattr("taskforge.deployments.adapters.run_process", command)
    if fail:
        with pytest.raises(RuntimeError):
            await deploy(target, IMAGE, sink)
        assert any(f"app={old}" in call for call in calls)
    else:
        result = await deploy(target, IMAGE, sink)
        assert result["verified"] and result["previous_image"] == old
    assert any("rollout" in call for call in calls)
