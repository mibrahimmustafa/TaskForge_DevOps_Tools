import os
import tempfile

import httpx
import pytest

from taskforge.api.app import create_app


@pytest.fixture
def temp_env_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("TASKFORGE_STORAGE_URL", f"sqlite+aiosqlite:///{path}")
    yield path
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


@pytest.mark.asyncio
async def test_api_full_lifecycle(temp_env_db):
    app = create_app()

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        # 1. Health check
        res = await client.get("/health")
        assert res.status_code == 200
        health_data = res.json()
        assert health_data["service"] == "TaskForge"
        assert "timestamp" in health_data

        # 2. Metrics check
        res = await client.get("/metrics")
        assert res.status_code == 200
        assert "taskforge" in res.text

        # 3. Create a job
        job_payload = {
            "id": "job-api-test-1",
            "name": "API Test Job",
            "description": "Created via test",
            "trigger": "interval",
            "trigger_expr": "every 10m",
            "executor": "shell",
            "command": "echo 'api test ok'",
            "status": "active",
            "tags": ["api", "test"],
            "timeout_seconds": 60,
            "max_retries": 3,
            "retry_delay_seconds": 5,
        }
        res = await client.post("/api/jobs", json=job_payload)
        assert res.status_code == 200
        created = res.json()
        assert created["id"] == "job-api-test-1"
        assert created["name"] == "API Test Job"

        # 4. Get the job
        res = await client.get("/api/jobs/job-api-test-1")
        assert res.status_code == 200
        assert res.json()["name"] == "API Test Job"

        # 5. List jobs
        res = await client.get("/api/jobs")
        assert res.status_code == 200
        jobs_list = res.json()
        assert any(j["id"] == "job-api-test-1" for j in jobs_list)

        # 6. Pause & Resume job
        res = await client.post("/api/jobs/job-api-test-1/pause")
        assert res.status_code == 200
        assert res.json()["status"] == "paused"

        res = await client.post("/api/jobs/job-api-test-1/resume")
        assert res.status_code == 200
        assert res.json()["status"] == "active"

        # 7. Run job manually
        res = await client.post("/api/jobs/job-api-test-1/run")
        assert res.status_code == 200
        run_data = res.json()
        assert run_data["status"] == "success"
        assert "api test ok" in run_data["logs"]

        # 8. List runs
        res = await client.get("/api/runs")
        assert res.status_code == 200
        runs_list = res.json()
        assert len(runs_list) >= 1
        assert runs_list[0]["jobId"] == "job-api-test-1"

        # 9. System stats
        res = await client.get("/api/system/stats")
        assert res.status_code == 200
        stats = res.json()
        assert stats["total_jobs"] >= 1
        assert stats["total_runs"] >= 1

        # 10. Plugins catalog & toggle
        res = await client.get("/api/plugins")
        assert res.status_code == 200
        plugins = res.json()
        assert len(plugins) > 0
        plugin_id = plugins[0]["id"]
        init_enabled = plugins[0]["enabled"]

        toggle_res = await client.post(f"/api/plugins/{plugin_id}/toggle")
        assert toggle_res.status_code == 200
        assert toggle_res.json()["enabled"] == (not init_enabled)

        # 11. Delete job
        res = await client.delete("/api/jobs/job-api-test-1")
        assert res.status_code == 200
        assert res.json()["success"] is True

        res = await client.get("/api/jobs/job-api-test-1")
        assert res.status_code == 404
