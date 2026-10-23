import json
from typing import Tuple
import httpx
from taskforge.executors.base import BaseExecutor
from taskforge.jobs.models import Job

class HTTPExecutor(BaseExecutor):
    async def execute(self, job: Job) -> Tuple[int, str]:
        # format can be: METHOD URL or just URL or JSON configuration
        cmd = job.command.strip()
        method = "GET"
        url = cmd
        headers = {}
        payload = None

        if cmd.startswith("{"):
            try:
                cfg = json.loads(cmd)
                method = cfg.get("method", "GET").upper()
                url = cfg.get("url", "")
                headers = cfg.get("headers", {})
                payload = cfg.get("body")
            except Exception:
                pass
        elif " " in cmd:
            parts = cmd.split(" ", 1)
            if parts[0].upper() in ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"):
                method = parts[0].upper()
                url = parts[1].strip()

        try:
            async with httpx.AsyncClient(timeout=float(job.timeout_seconds)) as client:
                resp = await client.request(method=method, url=url, headers=headers, json=payload)
                log = f"HTTP {method} {url} -> {resp.status_code}\n\nResponse:\n{resp.text[:2000]}"
                exit_code = 0 if resp.is_success else 1
                return exit_code, log
        except Exception as e:
            return 1, f"[HTTP ERROR] Request failed: {str(e)}"
