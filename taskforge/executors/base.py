from abc import ABC, abstractmethod

from taskforge.jobs.models import Job


class BaseExecutor(ABC):
    @abstractmethod
    async def execute(self, job: Job) -> tuple[int, str]:
        """
        Executes a job.
        Returns: (exit_code, output_logs)
        """
