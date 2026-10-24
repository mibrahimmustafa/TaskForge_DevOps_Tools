import json

from dotenv import dotenv_values
from typer.testing import CliRunner

from taskforge.api.auth import validate_tokens
from taskforge.cli.main import app


def test_init_creates_distinct_private_credentials_and_never_overwrites(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    path = tmp_path / ".taskforge" / "config.env"
    original = path.read_bytes()
    tokens = json.loads(dotenv_values(path)["TASKFORGE_TOKENS"])
    validate_tokens(tokens)
    assert tokens[0]["name"] != tokens[1]["name"]
    assert all(entry["token"] not in result.output for entry in tokens)
    assert runner.invoke(app, ["init"]).exit_code != 0
    assert path.read_bytes() == original


def test_api_cli_requires_token(monkeypatch):
    monkeypatch.delenv("TASKFORGE_API_TOKEN", raising=False)
    result = CliRunner().invoke(app, ["jobs", "list"])
    assert result.exit_code != 0 and "TASKFORGE_API_TOKEN" in result.output
    user_result = CliRunner().invoke(app, ["users", "list"])
    assert user_result.exit_code != 0 and "TASKFORGE_API_TOKEN" in user_result.output
    yaml_job_result = CliRunner().invoke(app, ["jobs", "yaml", "job-123"])
    assert yaml_job_result.exit_code != 0 and "TASKFORGE_API_TOKEN" in yaml_job_result.output
    yaml_pipe_result = CliRunner().invoke(app, ["pipelines", "yaml", "pipe-123"])
    assert yaml_pipe_result.exit_code != 0 and "TASKFORGE_API_TOKEN" in yaml_pipe_result.output


def test_cli_apply_requires_token(tmp_path, monkeypatch):
    monkeypatch.delenv("TASKFORGE_API_TOKEN", raising=False)
    test_file = tmp_path / "task.yaml"
    test_file.write_text("id: demo\nname: Demo\n")
    result = CliRunner().invoke(app, ["apply", str(test_file)])
    assert result.exit_code != 0 and "TASKFORGE_API_TOKEN" in result.output
