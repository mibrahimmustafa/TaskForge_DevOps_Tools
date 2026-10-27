"""Lease-fenced runner with bounded logs, explicit retries, pipeline DAGs and recovery."""

import asyncio
import fnmatch
import hashlib
import json
import os
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


def collect_matching_files(
    workspace: Path, include_patterns: list[str], exclude_patterns: list[str]
) -> list[Path]:
    """Find all files in workspace matching include_patterns and not excluded by exclude_patterns."""
    matched: set[Path] = set()
    ws_resolved = workspace.resolve()
    for pattern in include_patterns:
        pattern_norm = pattern.replace("\\", "/").strip()
        if not pattern_norm:
            continue
        if any(c in pattern_norm for c in ["*", "?", "["]):
            for p in workspace.glob(pattern_norm):
                if p.is_file() and p.resolve().is_relative_to(ws_resolved):
                    matched.add(p)
        else:
            p = (workspace / pattern_norm).resolve()
            if p.is_file() and p.is_relative_to(ws_resolved):
                matched.add(p)

    final_files: list[Path] = []
    for file_path in sorted(matched, key=lambda x: str(x)):
        rel = file_path.relative_to(workspace).as_posix()
        excluded = False
        for ex in exclude_patterns:
            ex_norm = ex.replace("\\", "/").strip()
            if fnmatch.fnmatch(rel, ex_norm) or fnmatch.fnmatch(file_path.name, ex_norm):
                excluded = True
                break
        if not excluded:
            final_files.append(file_path)
    return final_files


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
        lock_resource = run["resource"]
        if run["payload"]["kind"] == "job":
            job_def = run["payload"].get("definition", {})
            concurrent = job_def.get("concurrent_builds", True)
            lock_resource = f"run-exec:{identifier}" if concurrent else run["resource"]

        if not await self.db.lock(lock_resource, owner, lock_ttl):
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
                if current is not None:
                    current.cancel()

        async def renew_lease():
            while True:
                await asyncio.sleep(lease / 3)
                fresh = await self.db.run(identifier)
                if (
                    not fresh
                    or fresh["cancel"]
                    or not await self.db.owned(identifier, owner, lease=time.time() + lease)
                    or not await self.db.lock(lock_resource, owner, lock_ttl)
                ):
                    if current is not None:
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
                await self.db.unlock(lock_resource, owner)
            if committed:
                await self.db.record_audit(
                    run["project"], f"worker:{self.id}", f"run.{status}", identifier
                )
                if run["payload"]["kind"] == "job":
                    job_def = run["payload"].get("definition", {})
                    # 1. Downstream Triggers (F04)
                    triggers = job_def.get("downstream_triggers", [])
                    for dt in triggers:
                        target_id = dt.get("job_id")
                        thresh = dt.get("threshold", "success")
                        met = False
                        if (
                            thresh == "success"
                            and status == "success"
                            or thresh == "unstable"
                            and status in {"success", "unstable"}
                            or thresh == "failed"
                            and status in {"success", "unstable", "failed"}
                        ):
                            met = True
                        if met and target_id:
                            try:
                                target_doc = await self.db.get("job", target_id)
                                if target_doc:
                                    target_job = Job.model_validate(target_doc)
                                    if target_job.enabled:
                                        build_num = run["payload"].get(
                                            "build_number"
                                        ) or result.get("build_number")
                                        cause = {
                                            "type": "upstream",
                                            "upstream_project": run["project"],
                                            "upstream_job": job_def.get("id"),
                                            "upstream_build": build_num,
                                            "upstream_run_id": identifier,
                                        }
                                        await self.scheduler.submit(
                                            target_job,
                                            trigger_type="upstream",
                                            parameters=dt.get("parameters", {}),
                                            cause=cause,
                                        )
                            except Exception as trigger_err:
                                logger.error("downstream_trigger_failed", error=str(trigger_err))
                    # 2. Build Retention (F12)
                    try:
                        from taskforge.jobs.retention import apply_build_retention

                        await apply_build_retention(
                            self.db, self.settings, run["project"], job_def.get("id")
                        )
                    except Exception as ret_err:
                        logger.error("retention_cleanup_failed", error=str(ret_err))

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
                # Track consumer fingerprint (F11)
                await self.db.record_fingerprint(
                    artifact.get("md5") or hashlib.md5(raw).hexdigest(),
                    artifact["name"],
                    run["project"],
                    job.id,
                    run["payload"].get("build_number"),
                    run["id"],
                    role="consumer",
                )
        environment = {}
        for reference in job.secret_refs:
            key = f"{job.project}/{reference}"
            if key not in self.settings.secrets:
                raise ValueError(f"Secret reference not configured: {reference}")
            environment[reference] = self.settings.secrets[key]
        # Global Tool PATH Injection (F19)
        if job.tools:
            for tool_name in job.tools:
                tool_doc = await self.db.get("tool", tool_name)
                if not tool_doc:
                    all_tools = await self.db.list("tool")
                    tool_doc = next(
                        (
                            t
                            for t in all_tools
                            if t.get("name") == tool_name or t.get("id") == tool_name
                        ),
                        None,
                    )
                if tool_doc:
                    tool_home = tool_doc.get("home", "")
                    tool_bin = Path(tool_home) / "bin"
                    bin_dir = str(tool_bin) if tool_bin.exists() else tool_home
                    current_path = environment.get("PATH", os.environ.get("PATH", ""))
                    environment["PATH"] = f"{bin_dir}{os.pathsep}{current_path}"
                    ttype = tool_doc.get("tool_type", "").upper()
                    if ttype:
                        environment[f"{ttype}_HOME"] = tool_home
                        if ttype == "GO":
                            environment["GOROOT"] = tool_home
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
            if job.steps:
                code = 0
                for idx, bstep in enumerate(job.steps):
                    s_name = bstep.name or f"Step {idx + 1}"
                    await stream.write(
                        f"\n[{step}] Step {idx + 1}/{len(job.steps)}: {s_name} ({bstep.executor.value})\n"
                    )
                    if (
                        bstep.executor in {"shell", "python"}
                        and not self.settings.allow_host_execution
                    ):
                        raise ValueError(
                            f"Host execution is disabled for step '{s_name}'. Enable it only on a trusted runner."
                        )
                    step_job = Job(
                        id=f"{job.id}-step-{idx}",
                        project=job.project,
                        name=s_name,
                        executor=bstep.executor,
                        command=bstep.command,
                        args=bstep.args,
                        image=bstep.image,
                        timeout_seconds=job.timeout_seconds,
                    )
                    code, _ = await get_executor(bstep.executor).execute(
                        step_job, cwd=workspace, env=environment, sink=stream.write
                    )
                    if code != 0:
                        await stream.write(
                            f"\n[{step}] Step {idx + 1} exited with code {code}. Aborting build.\n"
                        )
                        break
            else:
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
        if code == 0 and job.artifact_paths:
            include_patterns = job.artifact_paths
            exclude_patterns = job.artifact_exclude_paths
            matched_files = collect_matching_files(workspace, include_patterns, exclude_patterns)
            build_num_str = str(run["payload"].get("build_number") or run["id"])
            for path in matched_files:
                if path.stat().st_size > 50 * 1024 * 1024:
                    raise ValueError("Artifact exceeds the 50 MiB limit")
                raw = await asyncio.to_thread(path.read_bytes)
                sha_digest = hashlib.sha256(raw).hexdigest()
                md5_digest = hashlib.md5(raw).hexdigest()
                rel_path = path.relative_to(workspace).as_posix()
                # Store in build-specific artifact directory (F10)
                dest = (
                    self.settings.data_dir.resolve()
                    / "artifacts"
                    / run["project"]
                    / job.id
                    / build_num_str
                    / rel_path
                )
                dest.parent.mkdir(parents=True, exist_ok=True)
                await asyncio.to_thread(dest.write_bytes, raw)
                # Store in legacy run-id artifact storage for pipeline step inputs
                legacy_dest = (
                    self.settings.data_dir.resolve()
                    / "artifacts"
                    / run["project"]
                    / run["id"]
                    / sha_digest
                )
                legacy_dest.parent.mkdir(parents=True, exist_ok=True)
                await asyncio.to_thread(legacy_dest.write_bytes, raw)
                # Record fingerprint producer (F11)
                await self.db.record_fingerprint(
                    md5_digest,
                    path.name,
                    run["project"],
                    job.id,
                    run["payload"].get("build_number"),
                    run["id"],
                    role="producer",
                )
                artifacts.append(
                    {
                        "path": rel_path,
                        "name": path.name,
                        "sha256": sha_digest,
                        "md5": md5_digest,
                        "size": len(raw),
                    }
                )
        return {
            "status": "success" if code == 0 else "timed_out" if code == -1 else "failed",
            "build_number": run["payload"].get("build_number"),
            "parameters": run["payload"].get("parameters", {}),
            "cause": run["payload"].get("cause", {}),
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
