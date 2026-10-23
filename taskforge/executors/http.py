import asyncio
import json
from urllib.parse import urlsplit

import httpx

from taskforge.executors.base import BaseExecutor
from taskforge.jobs.models import Job


class HTTPExecutor(BaseExecutor):
    async def execute(self, job: Job, *, cwd=None, env=None, sink=None) -> tuple[int, str]:
        cmd = job.command.strip()
        if cmd.startswith("{"):
            config = json.loads(cmd)
        elif " " in cmd:
            method, url = cmd.split(" ", 1)
            config = {"method": method, "url": url}
        else:
            config = {"url": cmd}
        if urlsplit(config["url"]).scheme not in {"http", "https"}:
            raise ValueError("Only HTTP(S) URLs are supported")
        try:
            async with (
                asyncio.timeout(job.timeout_seconds),
                httpx.AsyncClient(
                    timeout=job.timeout_seconds, follow_redirects=False, trust_env=False
                ) as client,
                client.stream(
                    config.get("method", "GET").upper(),
                    config["url"],
                    headers=config.get("headers", {}),
                    json=config.get("body"),
                ) as response,
            ):
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk[: max(0, 65536 - len(data))])
                    if len(data) >= 65536:
                        break
                output = f"HTTP {response.status_code}\n" + data.decode("utf-8", "replace")
                if sink:
                    await sink(output)
                return (0 if response.is_success else 1), output
        except TimeoutError:
            return -1, "[TIMEOUT] HTTP request timed out"
