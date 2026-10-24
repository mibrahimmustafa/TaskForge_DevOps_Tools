"""Opt-in tests against a disposable service on the developer's Docker engine."""

import json
import os
import socket
import uuid

import httpx
import pytest

from taskforge.deployments.adapters import deploy
from taskforge.executors.docker import DockerExecutor
from taskforge.executors.process import run_process
from taskforge.jobs.models import Job

pytestmark = pytest.mark.skipif(
    os.getenv("TASKFORGE_DOCKER_TESTS") != "1",
    reason="Requires TASKFORGE_DOCKER_TESTS=1 and Docker",
)


async def test_real_docker_executor_and_deployment_rollback(tmp_path):
    code, output = await run_process(["docker", "pull", "python:3.12-alpine"], 180)
    assert code == 0, output
    code, output = await run_process(["docker", "image", "inspect", "python:3.12-alpine"], 30)
    assert code == 0, output
    image = json.loads(output)[0]["RepoDigests"][0]
    job = Job(
        id="docker-test",
        name="Docker test",
        trigger="manual",
        executor="docker",
        image=image,
        args=[
            "python",
            "-c",
            "from pathlib import Path; Path('artifact.txt').write_text('verified'); print('DOCKER_OK')",
        ],
    )
    code, output = await DockerExecutor().execute(job, cwd=tmp_path)
    assert code == 0 and "DOCKER_OK" in output
    assert (tmp_path / "artifact.txt").read_text() == "verified"
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    name = "taskforge-test-" + uuid.uuid4().hex[:12]
    # Deployment requires a registry digest; use python's default interactive
    # command as an unhealthy candidate against a known healthy existing service.
    code, output = await run_process(
        [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--publish",
            f"127.0.0.1:{port}:8080",
            image,
            "python",
            "-m",
            "http.server",
            "8080",
        ],
        30,
    )
    assert code == 0, output
    target = {
        "type": "docker",
        "container": name,
        "port": f"127.0.0.1:{port}:8080",
        "health_url": f"http://127.0.0.1:{port}",
    }
    messages = []

    async def sink(text):
        messages.append(text)

    try:
        with pytest.raises(RuntimeError, match="health check failed"):
            await deploy(target, image, sink)
        code, output = await run_process(["docker", "inspect", name], 30)
        assert code == 0 and json.loads(output)[0]["State"]["Running"]
        async with httpx.AsyncClient(trust_env=False) as client:
            assert (await client.get(target["health_url"])).is_success
        assert any("Restoring the previous" in text for text in messages)
    finally:
        await run_process(["docker", "rm", "-f", name], 30)
