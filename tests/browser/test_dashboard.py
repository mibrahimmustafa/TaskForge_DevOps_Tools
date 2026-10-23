import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("TASKFORGE_BROWSER_TESTS") != "1", reason="Run with TASKFORGE_BROWSER_TESTS=1"
)
TOKEN = "browser-test-token-" + "x" * 40


@pytest.fixture(scope="module")
def live_server(tmp_path_factory):
    directory = tmp_path_factory.mktemp("browser-server")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env = os.environ | {
        "TASKFORGE_TOKENS": json.dumps([{"token": TOKEN, "name": "browser-admin", "role": "admin", "projects": ["default"]}]),
        "TASKFORGE_STORAGE_URL": f"sqlite+aiosqlite:///{directory / 'test.db'}",
        "TASKFORGE_DATA_DIR": str(directory / "data"),
        "TASKFORGE_ALLOW_HOST_EXECUTION": "true",
        "TASKFORGE_EMBEDDED_WORKER": "true",
    }
    with (directory / "server.log").open("w") as output:
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "taskforge.api.app:create_app", "--factory",
             "--host", "127.0.0.1", "--port", str(port)],
            env=env, stdout=output, stderr=subprocess.STDOUT,
        )
        url = f"http://127.0.0.1:{port}"
        try:
            for _ in range(120):
                try:
                    if httpx.get(url + "/ready", timeout=1, trust_env=False).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.5)
            else:
                pytest.fail("Browser test server failed to start")
            yield url
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


@pytest.fixture
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        options = {"headless": True}
        channel = os.getenv("TASKFORGE_BROWSER_CHANNEL")
        if channel:
            options["channel"] = channel
        browser = playwright.chromium.launch(**options)
        yield browser
        browser.close()


def test_desktop_job_workflow_and_real_logs(browser, live_server):
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(live_server)
    page.get_by_label("Access token").fill(TOKEN)
    page.get_by_role("button", name="Open workspace").click()
    page.get_by_role("heading", name="Overview", exact=True).wait_for()
    page.get_by_role("link", name="Jobs", exact=True).click()
    page.get_by_role("button", name="+ Create job", exact=True).click()
    page.get_by_label("Name", exact=True).fill("Browser verified")
    page.get_by_label("ID", exact=True).fill("browser-verified")
    page.get_by_label("Executor", exact=True).select_option("python")
    page.get_by_label("Command / Python code / HTTP request", exact=True).fill("print('REAL_BROWSER_OUTPUT')")
    page.get_by_role("dialog").get_by_role("button", name="Create job", exact=True).click()
    row = page.get_by_role("row").filter(has_text="Browser verified")
    row.wait_for()
    row.get_by_role("button", name="Run", exact=True).click()
    page.get_by_label("Execution log").get_by_text("REAL_BROWSER_OUTPUT", exact=False).wait_for(timeout=30000)
    page.get_by_role("dialog").get_by_text("success", exact=True).wait_for(timeout=30000)
    Path("test-results").mkdir(exist_ok=True)
    page.screenshot(path="test-results/desktop-live-run.png", full_page=True)
    page.get_by_role("button", name="Close dialog").click()
    page.get_by_role("link", name="Overview", exact=True).click()
    page.screenshot(path="test-results/desktop-overview.png", full_page=True)
    page.get_by_role("button", name="Light mode").click()
    page.screenshot(path="test-results/desktop-light.png", full_page=True)
    assert not errors
    page.close()


def test_mobile_layout_keyboard_and_literal_untrusted_text(browser, live_server):
    headers = {"Authorization": "Bearer " + TOKEN}
    response = httpx.post(live_server + "/api/jobs", headers=headers, json={
        "id": "literal-text", "name": "<img src=x onerror=alert(1)>", "trigger": "manual",
        "executor": "python", "command": "print('safe')",
    }, trust_env=False)
    assert response.status_code == 200
    page = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True)
    page.goto(live_server)
    page.get_by_label("Access token").fill("wrong-" + "w" * 40)
    page.get_by_role("button", name="Open workspace").click()
    page.get_by_role("alert").filter(has_text="valid access token").wait_for()
    page.get_by_label("Access token").fill(TOKEN)
    page.get_by_role("button", name="Open workspace").click()
    page.get_by_role("link", name="Jobs", exact=True).click()
    page.get_by_text("<img src=x onerror=alert(1)>", exact=True).wait_for()
    assert page.locator("img").count() == 0
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth") is True
    page.get_by_role("button", name="+ Create job", exact=True).click()
    page.get_by_role("dialog").wait_for()
    page.keyboard.press("Escape")
    assert not page.get_by_role("dialog").is_visible()
    Path("test-results").mkdir(exist_ok=True)
    page.screenshot(path="test-results/mobile-jobs.png", full_page=True)
    page.get_by_role("button", name="Sign out").click()
    assert page.get_by_label("Access token").input_value() == ""
    page.close()

