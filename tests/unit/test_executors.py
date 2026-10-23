from unittest.mock import AsyncMock, patch

import httpx
import pytest

from taskforge.executors.http import HTTPExecutor
from taskforge.executors.python_callable import PythonExecutor
from taskforge.executors.shell import ShellExecutor
from taskforge.jobs.models import ExecutorType, Job


@pytest.mark.asyncio
async def test_shell_executor_success():
    executor = ShellExecutor()
    cmd = "echo TaskForge"
    job = Job(
        id="job-shell-test",
        name="shell-test",
        executor=ExecutorType.SHELL,
        command=cmd,
        timeout_seconds=10,
    )
    exit_code, logs = await executor.execute(job)
    assert exit_code == 0
    assert "TaskForge" in logs


@pytest.mark.asyncio
async def test_shell_executor_timeout():
    executor = ShellExecutor()
    # sleep for 5 seconds with a 1 second timeout
    cmd = 'python -c "import time; time.sleep(5)"'
    job = Job(
        id="job-shell-timeout",
        name="shell-timeout",
        executor=ExecutorType.SHELL,
        command=cmd,
        timeout_seconds=1,
    )
    exit_code, logs = await executor.execute(job)
    assert exit_code == -1
    assert "timed out" in logs.lower()


@pytest.mark.asyncio
async def test_python_executor_success():
    executor = PythonExecutor()
    job = Job(
        id="job-py-test",
        name="python-test",
        executor=ExecutorType.PYTHON,
        command="print('Hello from PythonExecutor')",
        timeout_seconds=5,
    )
    exit_code, logs = await executor.execute(job)
    assert exit_code == 0
    assert "Hello from PythonExecutor" in logs


@pytest.mark.asyncio
async def test_python_executor_error():
    executor = PythonExecutor()
    job = Job(
        id="job-py-err",
        name="python-err",
        executor=ExecutorType.PYTHON,
        command="raise ValueError('Intentional failure')",
        timeout_seconds=5,
    )
    exit_code, logs = await executor.execute(job)
    assert exit_code == 1
    assert "ValueError: Intentional failure" in logs


@pytest.mark.asyncio
async def test_python_executor_timeout():
    executor = PythonExecutor()
    job = Job(
        id="job-py-timeout",
        name="python-timeout",
        executor=ExecutorType.PYTHON,
        command="import time\ntime.sleep(5)",
        timeout_seconds=1,
    )
    exit_code, logs = await executor.execute(job)
    assert exit_code == -1
    assert "timeout" in logs.lower()


@pytest.mark.asyncio
async def test_http_executor_success():
    executor = HTTPExecutor()
    job = Job(
        id="job-http-test",
        name="http-test",
        executor=ExecutorType.HTTP,
        command="GET https://httpbin.org/get",
        timeout_seconds=10,
    )

    mock_resp = httpx.Response(
        200, text='{"success": true}', request=httpx.Request("GET", "https://httpbin.org/get")
    )
    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_request:
        mock_request.return_value = mock_resp
        exit_code, logs = await executor.execute(job)
        assert exit_code == 0
        assert "HTTP GET https://httpbin.org/get -> 200" in logs
