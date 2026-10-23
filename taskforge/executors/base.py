from abc import ABC, abstractmethod

from taskforge.jobs.models import Job


class BaseExecutor(ABC):
    @abstractmethod
    async def execute(self, job: Job, *, cwd=None, env=None, sink=None) -> tuple[int, str]:
        """Execute in a runner, returning an exit code and bounded output."""
