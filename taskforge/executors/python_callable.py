import io
import sys
import traceback
from typing import Tuple
from taskforge.executors.base import BaseExecutor
from taskforge.jobs.models import Job

class PythonExecutor(BaseExecutor):
    async def execute(self, job: Job) -> Tuple[int, str]:
        cmd = job.command.strip()
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        old_stdout = sys.stdout
        old_stderr = sys.stderr

        try:
            sys.stdout = stdout_buf
            sys.stderr = stderr_buf
            # Execute python code
            global_scope = {"job": job}
            exec(cmd, global_scope)
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            out = stdout_buf.getvalue()
            err = stderr_buf.getvalue()
            combined = out
            if err:
                combined += f"\n[STDERR]\n{err}"
            return 0, combined or "[SUCCESS] Code executed with no stdout output."
        except Exception as e:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            err_msg = traceback.format_exc()
            return 1, f"[PYTHON ERROR]\n{err_msg}"
