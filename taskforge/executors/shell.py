import sys
import tempfile
from pathlib import Path

from taskforge.executors.base import BaseExecutor
from taskforge.executors.process import run_process
from taskforge.jobs.models import Job


class ShellExecutor(BaseExecutor):
    async def execute(self, job: Job, *, cwd=None, env=None, sink=None) -> tuple[int, str]:
        if sys.platform == "win32":
            # A batch file preserves nested quotes; list2cmdline escaping is not
            # cmd.exe script escaping. The command is deliberately executable code.
            with tempfile.TemporaryDirectory(prefix="taskforge-shell-") as directory:
                script = Path(directory) / "job.cmd"
                script.write_text("@echo off\n" + job.command + "\n", encoding="utf-8")
                return await run_process(
                    ["cmd.exe", "/d", "/c", str(script)], job.timeout_seconds, cwd, env, sink
                )
        return await run_process(
            ["/bin/bash", "-c", job.command], job.timeout_seconds, cwd, env, sink
        )
