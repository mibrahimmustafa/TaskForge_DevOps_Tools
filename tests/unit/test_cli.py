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
