from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

JOBS_TOTAL = Counter("taskforge_jobs_total", "Total registered jobs")
JOB_RUNS_TOTAL = Counter(
    "taskforge_job_runs_total", "Total executions of jobs", ["job_id", "status"]
)
JOB_RUN_DURATION = Histogram(
    "taskforge_job_run_duration_seconds", "Job execution duration in seconds", ["job_id"]
)
ACTIVE_JOBS_GAUGE = Gauge("taskforge_active_jobs_count", "Current number of enabled active jobs")


def get_metrics_data() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
