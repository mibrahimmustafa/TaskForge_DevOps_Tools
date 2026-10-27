import asyncio

from taskforge.core.worker import Worker


async def test_setup_wizard_unlock_and_completion(client, settings):
    # 1. Setup status initial check
    status_resp = await client.get("/api/system/setup-status")
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert data["setup_complete"] is False
    assert data["requires_unlock"] is True

    # 2. Key file generated in data_dir
    key_file = settings.data_dir / "initial_admin_password"
    assert key_file.exists()
    unlock_key = key_file.read_text(encoding="utf-8").strip()

    # 3. Invalid unlock attempt
    bad_resp = await client.post("/api/system/setup/unlock", json={"key": "wrong_password"})
    assert bad_resp.status_code == 401

    # 4. Valid unlock attempt
    unlock_resp = await client.post("/api/system/setup/unlock", json={"key": unlock_key})
    assert unlock_resp.status_code == 200
    setup_token = unlock_resp.json()["setup_token"]

    # 5. Complete setup with new admin account
    complete_resp = await client.post(
        "/api/system/setup/complete",
        json={
            "setup_token": setup_token,
            "username": "wizard_admin",
            "password": "StrongPassword123!",
            "instance_url": "http://127.0.0.1:8080",
        },
    )
    assert complete_resp.status_code == 200
    admin_token = complete_resp.json()["token"]
    assert admin_token
    assert not key_file.exists()

    # 6. Verify setup is marked complete
    status_after = (await client.get("/api/system/setup-status")).json()
    assert status_after["setup_complete"] is True
    assert status_after["requires_unlock"] is False

    # 7. Local password login
    bad_login = await client.post(
        "/api/auth/login",
        json={"username": "wizard_admin", "password": "WrongPassword"},
    )
    assert bad_login.status_code == 401

    login_resp = await client.post(
        "/api/auth/login",
        json={"username": "wizard_admin", "password": "StrongPassword123!"},
    )
    assert login_resp.status_code == 200
    session_token = login_resp.json()["token"]

    # 8. Authenticated request using new session token
    sess_resp = await client.get(
        "/api/session", headers={"Authorization": f"Bearer {session_token}"}
    )
    assert sess_resp.status_code == 200
    assert sess_resp.json()["name"] == "wizard_admin"
    assert sess_resp.json()["role"] == "admin"


async def test_job_lifecycle_enable_disable_copy_rename(client):
    job_def = {
        "id": "lifecycle-job",
        "name": "Lifecycle Job",
        "trigger": "manual",
        "executor": "python",
        "command": "print('running lifecycle')",
    }
    create_resp = await client.post("/api/jobs", json=job_def)
    assert create_resp.status_code == 200
    assert create_resp.json()["enabled"] is True

    # Disable job
    disable_resp = await client.post("/api/jobs/lifecycle-job/disable")
    assert disable_resp.status_code == 200
    assert disable_resp.json()["enabled"] is False

    # Triggering disabled job must fail
    run_attempt = await client.post("/api/jobs/lifecycle-job/run")
    assert run_attempt.status_code == 400
    assert "disabled" in run_attempt.json()["detail"].lower()

    # Enable job
    enable_resp = await client.post("/api/jobs/lifecycle-job/enable")
    assert enable_resp.status_code == 200
    assert enable_resp.json()["enabled"] is True

    # Copy job
    copy_resp = await client.post(
        "/api/jobs/lifecycle-job/copy?new_id=lifecycle-job-copy&new_name=Copied+Job"
    )
    assert copy_resp.status_code == 200
    assert copy_resp.json()["id"] == "lifecycle-job-copy"
    assert copy_resp.json()["name"] == "Copied Job"

    # Rename job
    rename_resp = await client.post("/api/jobs/lifecycle-job/rename?new_id=lifecycle-job-renamed")
    assert rename_resp.status_code == 200
    assert rename_resp.json()["id"] == "lifecycle-job-renamed"

    # Old job id must be gone
    assert (await client.get("/api/jobs/lifecycle-job")).status_code == 404
    assert (await client.get("/api/jobs/lifecycle-job-renamed")).status_code == 200


async def test_parameterized_build_and_validation(client, db, settings):
    job_def = {
        "id": "param-job",
        "name": "Parameterized Job",
        "trigger": "manual",
        "executor": "python",
        "command": 'import os; print(f\'TARGET={os.environ.get("TARGET_ENV")},MSG={os.environ.get("MESSAGE")}\')',
        "parameters": [
            {
                "name": "TARGET_ENV",
                "type": "choice",
                "description": "Deployment target environment",
                "default_value": "staging",
                "choices": ["staging", "production"],
            },
            {
                "name": "MESSAGE",
                "type": "string",
                "description": "Commit message",
                "default_value": "default message",
                "trim": True,
            },
        ],
    }
    assert (await client.post("/api/jobs", json=job_def)).status_code == 200

    # Invalid choice validation
    invalid_resp = await client.post(
        "/api/jobs/param-job/run",
        json={"parameters": {"TARGET_ENV": "invalid_environment"}},
    )
    assert invalid_resp.status_code == 422
    assert "invalid value" in invalid_resp.json()["detail"].lower()

    # Valid run with trimmed string
    run_resp = await client.post(
        "/api/jobs/param-job/run",
        json={"parameters": {"TARGET_ENV": "production", "MESSAGE": "  deploy v1.0  "}},
    )
    assert run_resp.status_code == 202
    run_id = run_resp.json()["id"]
    assert run_resp.json()["buildNumber"] == 1

    # Execute with worker
    worker = Worker(db, settings)
    await worker.tick()
    await asyncio.gather(*worker.tasks)

    run_data = (await client.get(f"/api/runs/{run_id}")).json()
    assert run_data["status"] == "success"
    assert run_data["buildNumber"] == 1
    assert run_data["parameters"]["TARGET_ENV"] == "production"
    assert run_data["parameters"]["MESSAGE"] == "deploy v1.0"
    assert run_data["cause"]["type"] == "user"

    # Second run allocates build number 2
    run_resp_2 = await client.post("/api/jobs/param-job/run")
    assert run_resp_2.json()["buildNumber"] == 2


async def test_ordered_multistep_execution(client, db, settings):
    job_def = {
        "id": "multistep-job",
        "name": "Multi-Step Job",
        "trigger": "manual",
        "steps": [
            {
                "id": "s1",
                "name": "Step 1 Create File",
                "executor": "python",
                "command": "from pathlib import Path; Path('file1.txt').write_text('step 1')",
            },
            {
                "id": "s2",
                "name": "Step 2 Append File",
                "executor": "python",
                "command": "from pathlib import Path; f = Path('file1.txt'); f.write_text(f.read_text() + ' -> step 2')",
            },
        ],
    }
    assert (await client.post("/api/jobs", json=job_def)).status_code == 200

    run_resp = await client.post("/api/jobs/multistep-job/run")
    assert run_resp.status_code == 202
    run_id = run_resp.json()["id"]

    worker = Worker(db, settings)
    await worker.tick()
    await asyncio.gather(*worker.tasks)

    run_data = (await client.get(f"/api/runs/{run_id}")).json()
    assert run_data["status"] == "success"


async def test_workspace_browser_and_permalinks(client, db, settings):
    job_def = {
        "id": "ws-job",
        "name": "Workspace Job",
        "trigger": "manual",
        "executor": "python",
        "command": "from pathlib import Path; Path('output.txt').write_text('verified workspace file'); (Path('sub') / 'deep').mkdir(parents=True); Path('sub/deep/inner.txt').write_text('deep content')",
    }
    assert (await client.post("/api/jobs", json=job_def)).status_code == 200

    run_resp = await client.post("/api/jobs/ws-job/run")
    run_id = run_resp.json()["id"]

    worker = Worker(db, settings)
    await worker.tick()
    await asyncio.gather(*worker.tasks)

    # 1. Permalinks
    last_resp = await client.get("/api/jobs/ws-job/builds/last")
    assert last_resp.status_code == 200
    assert last_resp.json()["id"] == run_id

    last_succ = await client.get("/api/jobs/ws-job/builds/lastSuccessful")
    assert last_succ.status_code == 200
    assert last_succ.json()["id"] == run_id

    # 2. Workspace directory listing
    ws_resp = await client.get("/api/jobs/ws-job/workspace")
    assert ws_resp.status_code == 200
    assert ws_resp.json()["exists"] is True
    names = [e["name"] for e in ws_resp.json()["entries"]]
    assert "output.txt" in names
    assert "sub" in names

    # 3. Read workspace file content
    file_resp = await client.get("/api/jobs/ws-job/workspace/file?path=output.txt")
    assert file_resp.status_code == 200
    assert file_resp.json()["content"] == "verified workspace file"

    # 4. Strict directory traversal protection
    traversal = await client.get("/api/jobs/ws-job/workspace/file?path=../../some_file")
    assert traversal.status_code == 403

    # 5. Wipe workspace
    wipe_resp = await client.post("/api/jobs/ws-job/workspace/wipe")
    assert wipe_resp.status_code == 200
    ws_after = (await client.get("/api/jobs/ws-job/workspace")).json()
    assert len(ws_after["entries"]) == 0


async def test_log_download_and_keep_forever(client, db, settings):
    job_def = {
        "id": "log-keep-job",
        "name": "Log Keep Job",
        "trigger": "manual",
        "executor": "python",
        "command": "print('LOG_LINE_1'); print('LOG_LINE_2')",
    }
    assert (await client.post("/api/jobs", json=job_def)).status_code == 200

    run_resp = await client.post("/api/jobs/log-keep-job/run")
    run_id = run_resp.json()["id"]

    worker = Worker(db, settings)
    await worker.tick()
    await asyncio.gather(*worker.tasks)

    # 1. Download logs
    download_resp = await client.get(f"/api/runs/{run_id}/logs/download")
    assert download_resp.status_code == 200
    assert "LOG_LINE_1" in download_resp.text
    assert "LOG_LINE_2" in download_resp.text
    assert "attachment" in download_resp.headers.get("content-disposition", "").lower()

    # 2. Toggle keep forever
    keep_resp = await client.post(f"/api/runs/{run_id}/keep")
    assert keep_resp.status_code == 200
    assert keep_resp.json()["keepForever"] is True

    run_data = (await client.get(f"/api/runs/{run_id}")).json()
    assert run_data["keepForever"] is True

    # Toggle off
    keep_resp2 = await client.post(f"/api/runs/{run_id}/keep")
    assert keep_resp2.status_code == 200
    assert keep_resp2.json()["keepForever"] is False
