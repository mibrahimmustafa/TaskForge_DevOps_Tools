import asyncio
import re
import uuid

from taskforge.executors.base import BaseExecutor
from taskforge.executors.process import run_process
from taskforge.jobs.models import Job


class DockerExecutor(BaseExecutor):
    async def execute(self, job: Job, *, cwd=None, env=None, sink=None) -> tuple[int, str]:
        if not job.image or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./:@-]+", job.image):
            raise ValueError("Docker jobs require a valid image field and structured args")
        name = f"taskforge-{uuid.uuid4().hex}"
        argv = [
            "docker",
            "run",
            "--rm",
            "--name",
            name,
            "--init",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--pids-limit=128",
            "--memory=512m",
            "--cpus=1",
            "--network=none",
        ]
        if cwd:
            argv += [
                "--mount",
                f"type=bind,source={cwd.resolve()},target=/workspace",
                "--workdir",
                "/workspace",
            ]
        for key in env or {}:
            argv += ["--env", key]
        argv += [job.image, *(job.args or ["sh", "-c", job.command])]
        try:
            return await run_process(argv, job.timeout_seconds, env=env, sink=sink)
        finally:
            # The CLI process exiting does not guarantee that its container exited.
            cleanup = asyncio.create_task(run_process(["docker", "rm", "-f", name], 30))
            await asyncio.shield(cleanup)
