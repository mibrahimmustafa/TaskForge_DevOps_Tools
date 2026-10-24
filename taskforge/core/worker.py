"""Lease-fenced runner with bounded logs, explicit retries, pipeline DAGs and recovery."""

import asyncio
import hashlib
import json
import random
import shutil
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from taskforge.core.config import Settings
from taskforge.core.logging import logger
from taskforge.core.scheduler import TaskScheduler
from taskforge.deployments.adapters import deploy, validate_deployment
from taskforge.executors import get_executor
from taskforge.executors.process import run_process
from taskforge.jobs.models import Job, Pipeline
from taskforge.plugins.loader import PluginLoader
from taskforge.storage.database import Database


class RetryScheduled(Exception):
    def __init__(self, result: dict, delay: float):
        self.result, self.delay = result, delay


class RedactedLog:
    def __init__(self, db: Database, run_id: str, owner: str, secrets: list[str]):
        self.db, self.run_id, self.owner = db, run_id, owner
        self.secrets = sorted({value for value in secrets if value}, key=len, reverse=True)
        self.tail = ""
        self.size = 0
        self.lock = asyncio.Lock()

    async def write(self, text: str, final=False):
        async with self.lock:
            text = self.tail + text
            # Hold a raw suffix so secrets split over subprocess reads cannot leak.
            keep = max([len(value) for value in self.secrets] + [1]) - 1
            split = len(text) if final else max(0, len(text) - keep)
            # Do not split a complete secret crossing the boundary.
            for secret in self.secrets:
                start = text.find(secret)
                while start >= 0:
                    if start < split < start + len(secret):
                        split = start
                    start = text.find(secret, start + 1)
            self.tail = text[split:]
            output = text[:split]
            for secret in self.secrets:
                output = output.replace(secret, "***")
            if self.size < 2 * 1024 * 1024:
                output = output[: 2 * 1024 * 1024 - self.size]
                self.size += len(output)
                if output:
                    await self.db.append_log(self.run_id, self.owner, output)


class Worker:
    def __init__(self, db: Database, settings: Settings):
        self.db, self.settings = db, settings
        self.id = uuid.uuid4().hex
        self.tasks: set[asyncio.Task] = set()
        self.stopping = False
        self.scheduler = TaskScheduler(db)
        self.plugins = PluginLoader()

    async def serve(self):
        await self.db.initialize()
        await self.plugins.load(self.settings.plugins, {"worker": self, "database": self.db})
        logger.info("worker_started", worker=self.id)
        try:
            while not self.stopping:
                await self.tick()
                await asyncio.sleep(0.5)
        finally:
            for task in self.tasks:
                task.cancel()
            await asyncio.gather(*self.tasks, return_exceptions=True)
            await self.db.unlock("schedule-controller", self.id)
            await self.db.unlock(f"worker:{self.id}", self.id)
            await self.plugins.close()
            logger.info("worker_stopped", worker=self.id)

    async def tick(self):
        await self.db.lock(f"worker:{self.id}", self.id, self.settings.lease_seconds)
        if await self.db.lock("schedule-controller", self.id, self.settings.lease_seconds):
            await self.db.recover()
            await self.scheduler.tick()
        while len(self.tasks) < self.settings.worker_concurrency:
            # Each claim uses a unique fence, not a reusable worker identity.
            owner = uuid.uuid4().hex
            run = await self.db.claim(owner, self.settings.lease_seconds)
            if not run:
                break
            task = asyncio.create_task(self.execute(run))
            self.tasks.add(task)
            task.add_done_callback(self.task_finished)

    def task_finished(self, task: asyncio.Task):
        self.tasks.discard(task)
        if not task.cancelled() and task.exception():
            logger.error("run_finalization_failed", error=type(task.exception()).__name__)

    async def execute(self, run: dict):
        owner, identifier = run["owner"], run["id"]
        lease = self.settings.lease_seconds
        deployment = run["payload"]["kind"] == "deployment"
        # External deployment APIs cannot honor our DB fence. An interrupted
        # deployment therefore holds its environment until explicit reconciliation.
        lock_ttl = 315360000 if deployment else lease
        if not await self.db.lock(run["resource"], owner, lock_ttl):
            await self.db.owned(
                identifier, owner, status="queued", owner=None, available=time.time() + 1, lease=0
            )
            return
        stream = RedactedLog(self.db, identifier, owner, list(self.settings.secrets.values()))
        current = asyncio.current_task()

        async def heartbeat():
            try:
                await renew_lease()
            except Exception:
                # Losing the coordination database must stop local execution.
                current.cancel()

        async def renew_lease():
            while True:
                await asyncio.sleep(lease / 3)
                fresh = await self.db.run(identifier)
                if (
                    not fresh
                    or fresh["cancel"]
                    or not await self.db.owned(identifier, owner, lease=time.time() + lease)
                    or not await self.db.lock(run["resource"], owner, lock_ttl)
                ):
                    current.cancel()
                    return

        monitor = asyncio.create_task(heartbeat())
        status, result = "failed", {}
        retry = None
        try:
            payload = run["payload"]
            if payload["kind"] == "job":
                result = await self.execute_job(
                    Job.model_validate(payload["definition"]), run, stream, "job"
                )
                status = result["status"]
            elif payload["kind"] == "pipeline":
                result = await self.execute_pipeline(run, stream)
                status = result["status"]
            elif payload["kind"] == "deployment":
                target = self.settings.deployment_targets[payload["target"]]
                # Bind approval to the exact target configuration as well as image.
                if (
                    hashlib.sha256(json.dumps(target, sort_keys=True).encode()).hexdigest()
                    != payload["target_hash"]
                ):
                    raise ValueError("Deployment target changed; request a new approval")
                validate_deployment(target, payload["image"], run["project"])
                if target.get("require_approval", True) and not payload.get("approved_by"):
                    raise ValueError("Approval is required")
                previous = await self.db.get("environment", payload["target"])
                if (
                    previous
                    and payload["source_created"] < previous["source_created"]
                    and not payload.get("rollback")
                ):
                    raise ValueError(
                        "A newer build has already been deployed. Request an explicit rollback."
                    )
                result = await deploy(target, payload["image"], stream.write)
                await self.db.put(
                    "environment",
                    {
                        "id": payload["target"],
                        "project": run["project"],
                        "image": payload["image"],
                        "source_created": payload["source_created"],
                        "source_run": payload["source_run"],
                        "deployment_run": identifier,
                    },
                    previous["version"] if previous else 0,
                )
                status = "success"
            elif payload["kind"] == "notification":
                try:
                    async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
                        response = await client.post(
                            self.settings.notification_url,
                            json=payload["message"],
                            headers={"Idempotency-Key": payload["message"]["run_id"]},
                        )
                        response.raise_for_status()
                except httpx.HTTPError:
                    attempt = run["result"].get("attempt", 0) + 1
                    if attempt < 5:
                        raise RetryScheduled(
                            {"attempt": attempt}, min(300, 5 * 2**attempt)
                        ) from None
                    raise
                status = "success"
        except RetryScheduled as scheduled:
            retry = scheduled
        except asyncio.CancelledError:
            status, result = (
                "cancelled",
                {"error": "Execution cancelled; workload cleanup requested."},
            )
            await stream.write("\n[CANCELLED]\n")
        except Exception as exc:
            await stream.write(f"\n[ERROR] {type(exc).__name__}: {exc}\n")
            result = {"error": "Execution failed. See the redacted run log."}
        finally:
            monitor.cancel()
            await asyncio.gather(monitor, return_exceptions=True)
            await stream.write("", final=True)
            if retry:
                committed = False
                await self.db.owned(
                    identifier,
                    owner,
                    status="queued",
                    owner=None,
                    lease=0,
                    result=retry.result,
                    available=time.time() + retry.delay,
                )
            else:
                committed = await self.db.finish(
                    identifier,
                    owner,
                    status,
                    result,
                    notify=bool(self.settings.notification_url)
                    and run["payload"]["kind"] != "notification",
                )
            if not deployment or status == "success":
                await self.db.unlock(run["resource"], owner)
            if committed:
                await self.db.record_audit(
                    run["project"], f"worker:{self.id}", f"run.{status}", identifier
                )

    async def execute_job(
        self,
        job: Job,
        run: dict,
        stream: RedactedLog,
        step: str,
        source: Path | None = None,
        inputs: dict[str, list[dict]] | None = None,
    ):
        if job.executor in {"shell", "python"} and not self.settings.allow_host_execution:
            raise ValueError(
                "Host execution is disabled. Use Docker or enable it only on a trusted runner."
            )
        if job.executor == "http":
            config = json.loads(job.command) if job.command.strip().startswith("{") else {}
            url = config.get("url", job.command.split(" ", 1)[-1])
            if urlsplit(url).hostname not in self.settings.allowed_http_hosts:
                raise ValueError("HTTP destination is not in the runner allowlist")
        workspace = self.settings.data_dir.resolve() / "workspaces" / run["id"] / step
        workspace.mkdir(parents=True, exist_ok=True)
        if source:
            await asyncio.to_thread(
                shutil.copytree, source, workspace, dirs_exist_ok=True, symlinks=True
            )
        for dependency, artifacts in (inputs or {}).items():
            for artifact in artifacts:
                origin = (
                    self.settings.data_dir.resolve()
                    / "artifacts"
                    / run["project"]
                    / run["id"]
                    / artifact["sha256"]
                )
                raw = await asyncio.to_thread(origin.read_bytes)
                if hashlib.sha256(raw).hexdigest() != artifact["sha256"]:
                    raise ValueError("Dependency artifact checksum does not match")
                destination = (workspace / "inputs" / dependency / artifact["name"]).resolve()
                if not destination.is_relative_to(workspace.resolve()):
                    raise ValueError("Dependency artifact destination escapes the step workspace")
                destination.parent.mkdir(parents=True, exist_ok=True)
                await asyncio.to_thread(destination.write_bytes, raw)
        environment = {}
        for reference in job.secret_refs:
            key = f"{job.project}/{reference}"
            if key not in self.settings.secrets:
                raise ValueError(f"Secret reference not configured: {reference}")
            environment[reference] = self.settings.secrets[key]
        ci_env: dict[str, str] = {
            "CI": "true",
            "TASKFORGE": "true",
            "TASKFORGE_PROJECT": run["project"],
            "TASKFORGE_RUN_ID": run["id"],
            "TASKFORGE_STEP": step,
            "TASKFORGE_WORKSPACE": str(workspace),
        }
        if run["payload"].get("commit"):
            ci_env["TASKFORGE_COMMIT"] = run["payload"]["commit"]
        if run["payload"].get("parameters"):
            for p_key, p_val in run["payload"]["parameters"].items():
                ci_env[f"TASKFORGE_PARAM_{p_key.upper()}"] = str(p_val)
                ci_env[p_key] = str(p_val)
        for key, val in ci_env.items():
            if key not in environment:
                environment[key] = val
        attempts = (
            list(run["result"].get("attempts", [])) if run["payload"]["kind"] == "job" else []
        )
        for attempt in range(len(attempts), job.max_retries + 1):
            await stream.write(f"\n[{step}] Attempt {attempt + 1}/{job.max_retries + 1}\n")
            started = time.time()
            code, _ = await get_executor(job.executor).execute(
                job, cwd=workspace, env=environment, sink=stream.write
            )
            attempts.append(
                {
                    "number": attempt + 1,
                    "exit_code": code,
                    "duration_seconds": round(time.time() - started, 3),
                }
            )
            await self.db.put(
                "attempt",
                {
                    "id": f"{run['id']}.{step}.{attempt + 1}",
                    "project": run["project"],
                    "run_id": run["id"],
                    "step": step,
                    **attempts[-1],
                },
            )
            if code == 0 or attempt == job.max_retries:
                break
            delay = min(3600, job.retry_delay_seconds * 2**attempt)
            await stream.write(f"[{step}] Retrying in approximately {delay}s\n")
            delay += random.uniform(0, delay * 0.1)  # nosec B311 - retry jitter
            if run["payload"]["kind"] == "job":
                raise RetryScheduled({"attempts": attempts}, delay)
            await asyncio.sleep(delay)
        artifacts = []
        if code == 0:
            for relative in job.artifact_paths:
                path = (workspace / relative).resolve()
                if not path.is_relative_to(workspace.resolve()) or not path.is_file():
                    raise ValueError("Artifact must be a regular file inside the step workspace")
                if path.stat().st_size > 50 * 1024 * 1024:
                    raise ValueError("Artifact exceeds the 50 MiB limit")
                raw = await asyncio.to_thread(path.read_bytes)
                digest = hashlib.sha256(raw).hexdigest()
                destination = (
                    self.settings.data_dir.resolve()
                    / "artifacts"
                    / run["project"]
                    / run["id"]
                    / digest
                )
                destination.parent.mkdir(parents=True, exist_ok=True)
                await asyncio.to_thread(destination.write_bytes, raw)
                artifacts.append({"name": path.name, "sha256": digest, "size": len(raw)})
        return {
            "status": "success" if code == 0 else "timed_out" if code == -1 else "failed",
            "attempts": attempts,
            "artifacts": artifacts,
        }

    async def execute_pipeline(self, run: dict, stream: RedactedLog):
        pipeline = Pipeline.model_validate(run["payload"]["definition"])
        source = None
        commit = run["payload"].get("commit")
        if pipeline.repository:
            if pipeline.repository not in self.settings.github_repositories:
                raise ValueError("Repository is not allowlisted on this runner")
            if not commit:
                raise ValueError("Repository pipelines require an exact commit SHA")
            source = self.settings.data_dir.resolve() / "workspaces" / run["id"] / "source"
            source.mkdir(parents=True, exist_ok=True)
            for args in (
                ["git", "init", "."],
                [
                    "git",
                    "fetch",
                    "--depth=1",
                    f"https://github.com/{pipeline.repository}.git",
                    commit,
                ],
                ["git", "checkout", "--detach", "FETCH_HEAD"],
            ):
                code, _ = await run_process(args, 120, source, sink=stream.write)
                if code:
                    raise RuntimeError("Source checkout failed")
            code, actual = await run_process(["git", "rev-parse", "HEAD"], 10, source)
            if code or actual.strip() != commit:
                raise ValueError("Checked-out commit does not match the run snapshot")
        results: dict[str, dict] = {}
        while len(results) < len(pipeline.steps):
            ready = [
                step
                for step in pipeline.steps
                if step.id not in results and all(n in results for n in step.needs)
            ]
            runnable = []
            for step in ready:
                if any(results[n]["status"] != "success" for n in step.needs):
                    results[step.id] = {
                        "status": "skipped",
                        "reason": "A dependency did not succeed",
                    }
                else:
                    runnable.append(step)
            semaphore = asyncio.Semaphore(self.settings.worker_concurrency)

            async def execute_step(step, limiter=semaphore):
                async with limiter:
                    try:
                        return await self.execute_job(
                            step.job,
                            run,
                            stream,
                            step.id,
                            source,
                            {name: results[name].get("artifacts", []) for name in step.needs},
                        )
                    except Exception as exc:
                        await stream.write(f"[{step.id}] {type(exc).__name__}: {exc}\n")
                        return {"status": "failed", "error": "See run log"}

            tasks = [asyncio.create_task(execute_step(step)) for step in runnable]
            try:
                values = await asyncio.gather(*tasks)
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
            for step, value in zip(runnable, values, strict=True):
                results[step.id] = value
            if not await self.db.owned(run["id"], run["owner"], result={"steps": results}):
                raise asyncio.CancelledError
        return {
            "status": "success"
            if all(r["status"] == "success" for r in results.values())
            else "failed",
            "steps": results,
            "commit": commit,
            "artifacts": [
                artifact for r in results.values() for artifact in r.get("artifacts", [])
            ],
        }
