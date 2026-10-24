"""Bounded output capture and process-tree termination for runner subprocesses."""

import asyncio
import codecs
import os
import signal
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path

LogSink = Callable[[str], Awaitable[None]]
MAX_OUTPUT = 2 * 1024 * 1024


async def terminate(proc, group=None):
    if sys.platform == "win32":
        if group:
            group.terminate()
        elif proc.returncode is None:
            proc.kill()
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    await proc.wait()


async def run_process(
    argv: list[str],
    timeout: int,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    sink: LogSink | None = None,
):
    safe_env = {
        key: os.environ[key]
        for key in ("PATH", "SystemRoot", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP", "LANG")
        if key in os.environ
    }
    safe_env.update(env or {})
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        env=safe_env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=sys.platform != "win32",
    )
    group = None
    if sys.platform == "win32":
        from taskforge.executors.windows_job import WindowsJob

        try:
            group = WindowsJob(proc.pid)
        except OSError:
            # Fast commands may already have exited before OpenProcess.
            await asyncio.sleep(0)
            if proc.returncode is None:
                await terminate(proc)
                raise
    chunks = []
    size = 0

    async def consume():
        nonlocal size
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        while True:
            chunk = await proc.stdout.read(4096)
            if not chunk:
                break
            text = decoder.decode(chunk)
            remaining = MAX_OUTPUT - size
            if remaining > 0:
                text = text[:remaining]
                size += len(text)
                chunks.append(text)
                if sink:
                    await sink(text)
        tail = decoder.decode(b"", final=True)
        if tail and size < MAX_OUTPUT:
            chunks.append(tail)
            if sink:
                await sink(tail)

    reader = asyncio.create_task(consume())
    try:
        async with asyncio.timeout(timeout):
            await proc.wait()
            await reader
        return proc.returncode or 0, "".join(chunks)
    except TimeoutError:
        await terminate(proc, group)
        await asyncio.gather(reader, return_exceptions=True)
        message = f"\n[TIMEOUT] Workload timed out after {timeout} seconds.\n"
        if sink:
            await sink(message)
        return -1, "".join(chunks) + message
    except BaseException:
        await terminate(proc, group)
        reader.cancel()
        await asyncio.gather(reader, return_exceptions=True)
        raise
    finally:
        # Successful parent exit must not leave detached descendants running.
        await terminate(proc, group)
        if group:
            group.close()
