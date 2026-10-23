from abc import ABC, abstractmethod

from taskforge.jobs.models import Job, JobRun


class BaseNotifier(ABC):
    @abstractmethod
    async def notify_job_finished(self, job: Job, run: JobRun) -> None:
        pass
