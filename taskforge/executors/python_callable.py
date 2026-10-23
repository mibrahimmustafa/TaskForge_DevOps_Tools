import sys

from taskforge.executors.base import BaseExecutor
from taskforge.executors.process import run_process
from taskforge.jobs.models import Job


class PythonExecutor(BaseExecutor):
    async def execute(self, job: Job, *, cwd=None, env=None, sink=None) -> tuple[int, str]:
        return await run_process(
            [sys.executable, "-I", "-u", "-c", job.command], job.timeout_seconds, cwd, env, sink
        )
