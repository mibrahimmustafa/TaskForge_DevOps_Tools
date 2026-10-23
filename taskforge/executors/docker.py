import asyncio
from typing import Tuple
from taskforge.executors.base import BaseExecutor
from taskforge.jobs.models import Job

class DockerExecutor(BaseExecutor):
    async def execute(self, job: Job) -> Tuple[int, str]:
        # command is docker run arguments, e.g. "alpine echo hello"
        cmd = f"docker run --rm {job.command}"
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                shell=True
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=float(job.timeout_seconds))
            stdout_str = stdout.decode("utf-8", errors="replace") if stdout else ""
            stderr_str = stderr.decode("utf-8", errors="replace") if stderr else ""
            return proc.returncode or 0, stdout_str + ("\n" + stderr_str if stderr_str else "")
        except asyncio.TimeoutError:
            return -1, f"[DOCKER TIMEOUT] Job timed out after {job.timeout_seconds}s"
        except Exception as e:
            return 1, f"[DOCKER ERROR] Execution failed: {str(e)}"
