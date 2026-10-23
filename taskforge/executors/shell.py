import asyncio
import os
import sys
from typing import Tuple
from taskforge.executors.base import BaseExecutor
from taskforge.jobs.models import Job

class ShellExecutor(BaseExecutor):
    async def execute(self, job: Job) -> Tuple[int, str]:
        cmd = job.command
        output_lines: list[str] = []

        try:
            if sys.platform == "win32":
                proc = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    shell=True
                )
            else:
                proc = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    shell=True,
                    executable="/bin/bash"
                )

            try:
                stdout_data, stderr_data = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=float(job.timeout_seconds)
                )
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except Exception:
                    pass
                return -1, f"[ERROR] Command timed out after {job.timeout_seconds} seconds."

            stdout_str = stdout_data.decode("utf-8", errors="replace") if stdout_data else ""
            stderr_str = stderr_data.decode("utf-8", errors="replace") if stderr_data else ""
            
            combined = stdout_str
            if stderr_str:
                if combined and not combined.endswith("\n"):
                    combined += "\n"
                combined += f"[STDERR]\n{stderr_str}"

            return proc.returncode if proc.returncode is not None else 0, combined

        except Exception as e:
            return 1, f"[EXCEPTION] Execution failed: {str(e)}"
