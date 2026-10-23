import asyncio
import sys

import httpx
import pytest

from taskforge.executors.docker import DockerExecutor
from taskforge.executors.http import HTTPExecutor
from taskforge.executors.python_callable import PythonExecutor
from taskforge.executors.shell import ShellExecutor
from taskforge.jobs.models import Job


async def test_shell_executor_success():
    code, logs = await ShellExecutor().execute(
        Job(id="test", name="Test", command="echo TaskForge")
    )
    assert code == 0 and "TaskForge" in logs


async def test_shell_executor_timeout():
    command = f'"{sys.executable}" -c "import time; time.sleep(5)"'
    code, logs = await ShellExecutor().execute(
        Job(id="test", name="Test", command=command, timeout_seconds=1)
    )
    assert code == -1 and "timed out" in logs


async def test_python_executor_success_and_error():
    executor = PythonExecutor()
    code, output = await executor.execute(Job(id="test", name="Test", command="print('hello')"))
    assert code == 0 and "hello" in output
    code, output = await executor.execute(
        Job(id="test", name="Test", command="raise ValueError('intentional')")
    )
    assert code != 0 and "intentional" in output


async def test_python_timeout_prevents_late_side_effect(tmp_path):
    marker = tmp_path / "late"
    command = f"import time; from pathlib import Path; time.sleep(2); Path({str(marker)!r}).touch()"
    code, _ = await PythonExecutor().execute(
        Job(id="test", name="Test", command=command, timeout_seconds=1)
    )
    assert code == -1
    await asyncio.sleep(1.3)
    assert not marker.exists()


async def test_output_is_bounded_and_streamed():
    chunks = []

    async def sink(text):
        chunks.append(text)

    code, output = await PythonExecutor().execute(
        Job(id="test", name="Test", command="print('x' * 3000000)"), sink=sink
    )
    assert code == 0 and len(output) <= 2 * 1024 * 1024
    assert len(chunks) > 1 and "".join(chunks) == output


async def test_http_executor_success(monkeypatch):
    original = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text="verified"))
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: original(transport=transport, **kwargs)
    )
    code, output = await HTTPExecutor().execute(
        Job(id="test", name="Test", command="GET https://example.test/")
    )
    assert code == 0 and "HTTP 200" in output and "verified" in output


async def test_docker_cleanup_and_structured_arguments(monkeypatch, tmp_path):
    calls = []

    async def fake(args, timeout, **kwargs):
        calls.append(args)
        return -1, "timeout"

    monkeypatch.setattr("taskforge.executors.docker.run_process", fake)
    job = Job(id="test", name="Test", image="alpine:3.20", command="echo hello")
    await DockerExecutor().execute(job, cwd=tmp_path)
    assert "--cap-drop=ALL" in calls[0]
    assert calls[0][-3:] == ["sh", "-c", "echo hello"]
    assert calls[-1][:3] == ["docker", "rm", "-f"]
    with pytest.raises(ValueError):
        await DockerExecutor().execute(job.model_copy(update={"image": "alpine; echo bad"}))
