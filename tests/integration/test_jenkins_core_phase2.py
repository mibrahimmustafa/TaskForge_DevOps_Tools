"""Integration tests for Jenkins Core Phase 2 features:
- F04: Jenkins H-notation cron and Upstream/Downstream build triggers
- F10: Artifact archiving with globs and exclusion patterns
- F11: Artifact fingerprint tracking & lineage
- F12: Build & log retention (LogRotator) preserving protected runs
- F19: Global tool configuration & PATH injection
- F21: Remote API tree filter (?tree=...) and authenticated programmatic execution
"""

import asyncio
import hashlib
from pathlib import Path

import httpx
import pytest

from taskforge.api.app import create_app
from taskforge.core.config import Settings
from taskforge.core.scheduler import TaskScheduler
from taskforge.core.worker import Worker
from taskforge.jobs.models import (
    DownstreamTrigger,
    Job,
    ParameterDefinition,
    RunStatus,
)
from taskforge.storage.database import Database
from taskforge.triggers.h_cron import expand_jenkins_cron


@pytest.fixture
def phase2_settings(tmp_path: Path):
    return Settings(
        app_env="test",
        storage_url=f"sqlite+aiosqlite:///{tmp_path / 'phase2.db'}",
        data_dir=tmp_path / "data",
        tokens=[
            {"name": "admin_user", "role": "admin", "projects": ["*"], "token": "a" * 32},
            {"name": "viewer_user", "role": "viewer", "projects": ["*"], "token": "v" * 32},
        ],
        allow_host_execution=True,
    )


@pytest.fixture
async def phase2_ctx(phase2_settings: Settings):
    db = Database(phase2_settings.storage_url)
    await db.initialize()
    app = create_app(phase2_settings, db)
    scheduler = TaskScheduler(db)
    worker = Worker(db, phase2_settings)
    worker.stopping = False
    admin_headers = {"Authorization": "Bearer " + "a" * 32}
    viewer_headers = {"Authorization": "Bearer " + "v" * 32}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield {
            "db": db,
            "settings": phase2_settings,
            "scheduler": scheduler,
            "worker": worker,
            "client": client,
            "admin_headers": admin_headers,
            "viewer_headers": viewer_headers,
        }
    await db.close()


async def run_worker_cycle(worker: Worker):
    await worker.tick()
    if worker.tasks:
        await asyncio.gather(*list(worker.tasks))


@pytest.mark.asyncio
async def test_f04_h_notation_cron():
    """Verify Jenkins H-notation expands into deterministic standard cron syntax."""
    expr1 = expand_jenkins_cron("H/15 * * * *", seed="job-alpha")
    expr2 = expand_jenkins_cron("H/15 * * * *", seed="job-alpha")
    assert expr1 == expr2, "H notation must be deterministic for identical seeds"
    # Should have comma-separated minutes with 15-min intervals
    parts = expr1.split()
    assert len(parts) == 5
    assert parts[1:] == ["*", "*", "*", "*"]
    minutes = [int(m) for m in parts[0].split(",")]
    assert len(minutes) == 4
    for i in range(len(minutes) - 1):
        assert minutes[i + 1] - minutes[i] == 15

    # Test range notation
    expr_range = expand_jenkins_cron("H(0-29)/10 H(0-5) * * 1-5", seed="job-beta")
    r_parts = expr_range.split()
    assert len(r_parts) == 5
    m_vals = [int(m) for m in r_parts[0].split(",")]
    for val in m_vals:
        assert 0 <= val <= 29
    assert 0 <= int(r_parts[1]) <= 5


@pytest.mark.asyncio
async def test_f04_upstream_downstream_trigger(phase2_ctx):
    """Verify downstream job is enqueued with upstream cause and parameters when upstream completes."""
    client = phase2_ctx["client"]
    admin = phase2_ctx["admin_headers"]
    worker = phase2_ctx["worker"]

    # 1. Create downstream job
    downstream_job = Job(
        id="downstream-job",
        project="default",
        name="Downstream Service",
        command="echo 'Downstream execution'",
        parameters=[ParameterDefinition(name="ENV", default_value="staging")],
    )
    res_b = await client.post(
        "/api/jobs", headers=admin, json=downstream_job.model_dump(mode="json")
    )
    assert res_b.status_code == 200

    # 2. Create upstream job configured with downstream trigger
    upstream_job = Job(
        id="upstream-job",
        project="default",
        name="Upstream Service",
        command="echo 'Upstream execution'",
        downstream_triggers=[
            DownstreamTrigger(
                job_id="downstream-job",
                threshold=RunStatus.SUCCESS,
                parameters={"ENV": "production"},
            )
        ],
    )
    res_a = await client.post("/api/jobs", headers=admin, json=upstream_job.model_dump(mode="json"))
    assert res_a.status_code == 200

    # 3. Run upstream job
    run_res = await client.post("/api/jobs/upstream-job/run", headers=admin, json={})
    assert run_res.status_code in {200, 202}
    upstream_run_id = run_res.json()["id"]

    # Execute upstream run
    await run_worker_cycle(worker)

    # Verify upstream completed
    u_info = (await client.get(f"/api/runs/{upstream_run_id}", headers=admin)).json()
    assert u_info["status"] == "success"

    # Verify downstream job was automatically enqueued
    all_runs = (await client.get("/api/runs", headers=admin)).json()
    downstream_runs = [r for r in all_runs if r["definition_id"] == "downstream-job"]
    assert len(downstream_runs) == 1
    d_run = downstream_runs[0]
    assert d_run["status"] == "queued"
    assert d_run["cause"]["type"] == "upstream"
    assert d_run["cause"]["upstream_job"] == "upstream-job"
    assert d_run["cause"]["upstream_run_id"] == upstream_run_id
    assert d_run["parameters"]["ENV"] == "production"


@pytest.mark.asyncio
async def test_f10_artifact_archiving_globs_and_exclusions(phase2_ctx):
    """Verify artifact archiving with globs, exclusions, and persistence after workspace wipe."""
    client = phase2_ctx["client"]
    admin = phase2_ctx["admin_headers"]
    worker = phase2_ctx["worker"]

    # Job creates 3 files: a wheel, a text report, and a temp file
    cmd = (
        'python -c "'
        "import os, pathlib; "
        "pathlib.Path('dist').mkdir(exist_ok=True); "
        "pathlib.Path('dist/myapp-1.0.whl').write_text('WHEEL_BINARY_DATA'); "
        "pathlib.Path('dist/report.txt').write_text('BUILD_REPORT_DATA'); "
        "pathlib.Path('dist/temp.tmp').write_text('TEMP_IGNORE');\""
    )

    job = Job(
        id="archive-job",
        project="default",
        name="Archive Job",
        command=cmd,
        artifact_paths=["dist/*"],
        artifact_exclude_paths=["*.tmp"],
    )
    res = await client.post("/api/jobs", headers=admin, json=job.model_dump(mode="json"))
    assert res.status_code == 200

    # Trigger run
    run_res = await client.post("/api/jobs/archive-job/run", headers=admin, json={})
    assert run_res.status_code in {200, 202}
    run_id = run_res.json()["id"]

    # Execute run
    await run_worker_cycle(worker)

    # Check run status & artifacts
    run_info = (await client.get(f"/api/runs/{run_id}", headers=admin)).json()
    assert run_info["status"] == "success"
    artifacts = run_info.get("artifacts", [])
    artifact_paths = [a["path"] for a in artifacts]

    assert "dist/myapp-1.0.whl" in artifact_paths
    assert "dist/report.txt" in artifact_paths
    assert not any("temp.tmp" in p for p in artifact_paths), "Excluded pattern must not be archived"

    # Verify download before workspace wipe
    dl_res = await client.get(f"/api/runs/{run_id}/artifacts/dist/myapp-1.0.whl", headers=admin)
    assert dl_res.status_code == 200
    assert dl_res.content == b"WHEEL_BINARY_DATA"

    # Permalinks artifact download
    perma_res = await client.get(
        "/api/jobs/archive-job/builds/last/artifacts/dist/myapp-1.0.whl", headers=admin
    )
    assert perma_res.status_code == 200
    assert perma_res.content == b"WHEEL_BINARY_DATA"

    # WIPE WORKSPACE
    wipe_res = await client.post("/api/jobs/archive-job/workspace/wipe", headers=admin)
    assert wipe_res.status_code == 200

    # Verify artifacts REMAIN downloadable after workspace removal (F10 acceptance criterion)
    dl_after_wipe = await client.get(
        f"/api/runs/{run_id}/artifacts/dist/myapp-1.0.whl", headers=admin
    )
    assert dl_after_wipe.status_code == 200
    assert dl_after_wipe.content == b"WHEEL_BINARY_DATA"


@pytest.mark.asyncio
async def test_f11_fingerprint_tracking_and_lineage(phase2_ctx):
    """Verify artifact fingerprints track origin build and consumer build relationships."""
    client = phase2_ctx["client"]
    admin = phase2_ctx["admin_headers"]
    worker = phase2_ctx["worker"]

    cmd = (
        'python -c "'
        "import pathlib; "
        "pathlib.Path('app.whl').write_text('EXACT_FINGERPRINT_CONTENT');\""
    )
    job = Job(
        id="fingerprint-producer",
        project="default",
        name="Fingerprint Producer",
        command=cmd,
        artifact_paths=["app.whl"],
    )
    await client.post("/api/jobs", headers=admin, json=job.model_dump(mode="json"))

    run_res = await client.post("/api/jobs/fingerprint-producer/run", headers=admin, json={})
    assert run_res.status_code in {200, 202}
    producer_run_id = run_res.json()["id"]

    await run_worker_cycle(worker)

    # Query run artifacts
    run_info = (await client.get(f"/api/runs/{producer_run_id}", headers=admin)).json()
    assert run_info["status"] == "success"
    art = run_info["artifacts"][0]
    md5_hash = art["md5"]
    assert md5_hash == hashlib.md5(b"EXACT_FINGERPRINT_CONTENT").hexdigest()

    # Query fingerprint endpoint
    fp_res = await client.get(f"/api/fingerprints/{md5_hash}", headers=admin)
    assert fp_res.status_code == 200
    fp_data = fp_res.json()
    assert fp_data["producer"]["job_id"] == "fingerprint-producer"
    assert fp_data["producer"]["run_id"] == producer_run_id

    # Record consumer usage
    track_res = await client.post(
        "/api/fingerprints/track",
        headers=admin,
        json={
            "hash": md5_hash,
            "file_name": "app.whl",
            "project": "default",
            "job_id": "deploy-service",
            "build_number": 42,
            "run_id": "run-consumer-123",
            "role": "consumer",
        },
    )
    assert track_res.status_code == 200

    # Verify consumer is now tracked in fingerprint lineage
    fp_res_updated = await client.get(f"/api/fingerprints/{md5_hash}", headers=admin)
    assert fp_res_updated.status_code == 200
    usages = fp_res_updated.json()["usages"]
    assert len(usages) == 1
    assert usages[0]["job_id"] == "deploy-service"
    assert usages[0]["build_number"] == 42


@pytest.mark.asyncio
async def test_f12_build_retention_log_rotator(phase2_ctx):
    """Verify retention removes eligible old runs and artifacts while preserving keep_forever and latest builds."""
    client = phase2_ctx["client"]
    admin = phase2_ctx["admin_headers"]
    worker = phase2_ctx["worker"]

    job = Job(
        id="retention-job",
        project="default",
        name="Retention Job",
        command="echo 'Build history retention test'",
        retention_max_builds=2,
    )
    await client.post("/api/jobs", headers=admin, json=job.model_dump(mode="json"))

    # Build 1
    res0 = await client.post("/api/jobs/retention-job/run", headers=admin, json={})
    assert res0.status_code in {200, 202}
    run_id_kept = res0.json()["id"]
    await run_worker_cycle(worker)

    # Mark build 1 as keep_forever
    keep_res = await client.post(f"/api/runs/{run_id_kept}/keep", headers=admin)
    assert keep_res.status_code == 200
    assert keep_res.json()["keep_forever"] is True

    # Now execute 3 more builds (builds 2, 3, 4)
    other_run_ids = []
    for _ in range(3):
        res = await client.post("/api/jobs/retention-job/run", headers=admin, json={})
        assert res.status_code in {200, 202}
        rid = res.json()["id"]
        other_run_ids.append(rid)
        await run_worker_cycle(worker)

    # Trigger manual retention endpoint to verify explicit execution as well
    ret_res = await client.post("/api/jobs/retention-job/retention/run", headers=admin)
    assert ret_res.status_code == 200

    # Build 1 is protected by keep_forever -> MUST NOT be purged and MUST exist
    get_kept = await client.get(f"/api/runs/{run_id_kept}", headers=admin)
    assert get_kept.status_code == 200
    assert get_kept.json()["keep_forever"] is True

    # Latest build (build 4) -> MUST NOT be purged and MUST exist
    latest_id = other_run_ids[-1]
    get_latest = await client.get(f"/api/runs/{latest_id}", headers=admin)
    assert get_latest.status_code == 200

    # Intermediate unkept builds (build 2) should be purged by retention_max_builds=2
    oldest_unkept = other_run_ids[0]
    get_purged = await client.get(f"/api/runs/{oldest_unkept}", headers=admin)
    assert get_purged.status_code == 404


@pytest.mark.asyncio
async def test_f19_global_tool_configuration(phase2_ctx, tmp_path: Path):
    """Verify global tool configuration prepends tool's bin path to PATH."""
    client = phase2_ctx["client"]
    admin = phase2_ctx["admin_headers"]
    worker = phase2_ctx["worker"]

    tool_dir = tmp_path / "mock_custom_tool"
    bin_dir = tool_dir / "bin"
    bin_dir.mkdir(parents=True)

    tool_payload = {
        "id": "mock-python-tool",
        "name": "Custom Python Tool",
        "tool_type": "python",
        "home": str(tool_dir),
    }
    tool_res = await client.post("/api/tools", headers=admin, json=tool_payload)
    assert tool_res.status_code == 200

    # Create job requiring this tool
    job = Job(
        id="tool-check-job",
        project="default",
        name="Tool Check Job",
        command="python -c \"import os; print('TOOL_HOME=' + os.environ.get('PYTHON_HOME', '')); print('IN_PATH=' + str(os.environ.get('PATH', '')))\"",
        tools=["mock-python-tool"],
    )
    await client.post("/api/jobs", headers=admin, json=job.model_dump(mode="json"))

    run_res = await client.post("/api/jobs/tool-check-job/run", headers=admin, json={})
    assert run_res.status_code in {200, 202}
    rid = run_res.json()["id"]

    await run_worker_cycle(worker)

    logs_res = await client.get(f"/api/runs/{rid}/logs", headers=admin)
    assert logs_res.status_code == 200
    all_text = "".join(r["text"] for r in logs_res.json()["records"])

    assert f"TOOL_HOME={tool_dir}" in all_text
    assert str(bin_dir) in all_text


@pytest.mark.asyncio
async def test_f21_remote_api_tree_filter(phase2_ctx):
    """Verify ?tree=... field selection on list and detail API endpoints."""
    client = phase2_ctx["client"]
    admin = phase2_ctx["admin_headers"]
    viewer = phase2_ctx["viewer_headers"]

    job = Job(
        id="tree-test-job",
        project="default",
        name="Tree Test Job",
        description="Testing tree filtering",
        command="echo 'Tree test'",
    )
    await client.post("/api/jobs", headers=admin, json=job.model_dump(mode="json"))

    # Detail query with tree filter
    res = await client.get("/api/jobs/tree-test-job?tree=id,name,status", headers=viewer)
    assert res.status_code == 200
    data = res.json()
    assert set(data.keys()) == {"id", "name", "status"}
    assert data["id"] == "tree-test-job"
    assert "command" not in data
    assert "description" not in data

    # Unauthorized access rejection (Acceptance checklist item)
    unauth_res = await client.get("/api/jobs/tree-test-job")
    assert unauth_res.status_code == 401
