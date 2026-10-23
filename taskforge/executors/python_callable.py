import asyncio
import io
import traceback
from contextlib import redirect_stderr, redirect_stdout

from taskforge.executors.base import BaseExecutor
from taskforge.jobs.models import Job


class PythonExecutor(BaseExecutor):
    @staticmethod
    def _run_sync(cmd: str, job: Job) -> tuple[int, str]:
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        try:
            with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
                global_scope = {"job": job}
                exec(cmd, global_scope)
            out = stdout_buf.getvalue()
            err = stderr_buf.getvalue()
            combined = out
            if err:
                combined += f"\n[STDERR]\n{err}"
            return 0, combined or "[SUCCESS] Code executed with no stdout output."
        except Exception:
            err_msg = traceback.format_exc()
            return 1, f"[PYTHON ERROR]\n{err_msg}"

    async def execute(self, job: Job) -> tuple[int, str]:
        cmd = job.command.strip()
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._run_sync, cmd, job), timeout=float(job.timeout_seconds)
            )
        except TimeoutError:
            return -1, f"[TIMEOUT] Python execution exceeded {job.timeout_seconds}s timeout."
        except Exception as e:
            return 1, f"[PYTHON ERROR] Execution failed: {e!s}"
