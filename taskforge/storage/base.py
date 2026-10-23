from abc import ABC, abstractmethod

from taskforge.jobs.models import Job, JobRun


class StorageBackend(ABC):
    @abstractmethod
    async def initialize(self) -> None:
        pass

    @abstractmethod
    async def get_all_jobs(self) -> list[Job]:
        pass

    @abstractmethod
    async def get_job(self, job_id: str) -> Job | None:
        pass

    @abstractmethod
    async def save_job(self, job: Job) -> Job:
        pass

    @abstractmethod
    async def delete_job(self, job_id: str) -> bool:
        pass

    @abstractmethod
    async def get_all_runs(self, limit: int = 100) -> list[JobRun]:
        pass

    @abstractmethod
    async def get_run(self, run_id: str) -> JobRun | None:
        pass

    @abstractmethod
    async def save_run(self, run: JobRun) -> JobRun:
        pass
