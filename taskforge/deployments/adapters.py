"""Administrator-configured deployment adapters. Workloads select a target, never CLI flags."""

import asyncio
import json
import re
import uuid

import httpx

from taskforge.executors.process import run_process

DIGEST = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:/-]*@sha256:[a-f0-9]{64}$")


def validate_deployment(target: dict, image: str, project: str):
    if target.get("project") != project:
        raise ValueError("Deployment target belongs to another project")
    if target.get("type") not in {"docker", "kubernetes"}:
        raise ValueError("Unsupported deployment target")
    if not DIGEST.fullmatch(image):
        raise ValueError("Deployments require an immutable image@sha256:digest")
    if image.split("@")[0] != target.get("image_repository"):
        raise ValueError("Image repository is not allowed for this target")
    required = (
        {"container", "port", "health_url"}
        if target["type"] == "docker"
        else {"namespace", "deployment", "container", "context"}
    )
    if any(not target.get(key) for key in required):
        raise ValueError("Deployment target configuration is incomplete")


async def deploy(target: dict, image: str, sink):
    async def command(args, timeout=180, check=True):
        env = {}
        if target.get("kubeconfig"):
            env["KUBECONFIG"] = target["kubeconfig"]
        if target.get("docker_host"):
            env["DOCKER_HOST"] = target["docker_host"]
        code, output = await run_process(args, timeout, env=env, sink=sink)
        if code and check:
            raise RuntimeError(f"Deployment command failed (exit {code})")
        return code, output

    if target["type"] == "kubernetes":
        base = ["kubectl", "--context", target["context"], "--namespace", target["namespace"]]
        _, raw = await command([*base, "get", "deployment", target["deployment"], "-o", "json"])
        manifest = json.loads(raw)
        old = next(
            item["image"]
            for item in manifest["spec"]["template"]["spec"]["containers"]
            if item["name"] == target["container"]
        )
        try:
            await command(
                [
                    *base,
                    "set",
                    "image",
                    f"deployment/{target['deployment']}",
                    f"{target['container']}={image}",
                ]
            )
            await command(
                [
                    *base,
                    "rollout",
                    "status",
                    f"deployment/{target['deployment']}",
                    "--timeout=120s",
                ],
                150,
            )
            return {"image": image, "previous_image": old, "verified": True}
        except BaseException:
            await sink("Restoring the previous Kubernetes image.\n")
            await command(
                [
                    *base,
                    "set",
                    "image",
                    f"deployment/{target['deployment']}",
                    f"{target['container']}={old}",
                ]
            )
            await command(
                [
                    *base,
                    "rollout",
                    "status",
                    f"deployment/{target['deployment']}",
                    "--timeout=120s",
                ],
                150,
            )
            raise

    name = target["container"]
    backup = f"{name}-previous-{uuid.uuid4().hex[:10]}"
    # Pull before interrupting the currently running service.
    await command(["docker", "pull", image])
    exists, raw = await command(["docker", "inspect", name], check=False)
    previous = json.loads(raw)[0]["Config"]["Image"] if exists == 0 else None
    renamed = False
    candidate_started = False
    try:
        if previous:
            await command(["docker", "stop", name])
            await command(["docker", "rename", name, backup])
            renamed = True
        candidate_started = True
        await command(
            [
                "docker",
                "run",
                "-d",
                "--name",
                name,
                "--restart",
                "unless-stopped",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--memory",
                target.get("memory", "512m"),
                "--publish",
                target["port"],
                image,
            ]
        )
        healthy = False
        async with httpx.AsyncClient(timeout=3, follow_redirects=False, trust_env=False) as client:
            for _ in range(20):
                try:
                    response = await client.get(target["health_url"])
                    if response.is_success:
                        healthy = True
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(2)
        if not healthy:
            raise RuntimeError("Deployment health check failed")
        if renamed:
            await command(["docker", "rm", backup])
        return {"image": image, "previous_image": previous, "verified": True}
    except BaseException:
        await sink("Restoring the previous Docker container.\n")
        if candidate_started:
            await command(["docker", "rm", "-f", name], check=False)
        if renamed:
            await command(["docker", "rename", backup, name])
        if previous:
            await command(["docker", "start", name])
        raise
