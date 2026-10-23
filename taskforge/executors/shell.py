import sys

from taskforge.executors.base import BaseExecutor
from taskforge.executors.process import run_process
from taskforge.jobs.models import Job


class ShellExecutor(BaseExecutor):
    async def execute(self, job: Job, *, cwd=None, env=None, sink=None) -> tuple[int, str]:
        argv = (
            ["cmd.exe", "/d", "/s", "/c", job.command]
            if sys.platform == "win32"
            else ["/bin/bash", "-c", job.command]
        )
        return await run_process(argv, job.timeout_seconds, cwd, env, sink)
