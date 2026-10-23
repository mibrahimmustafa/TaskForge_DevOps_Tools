# TaskForge 🔧

> **Open-Source, Production-Grade DevOps Task Scheduler**
>
> Cron jobs, interval tasks, webhook triggers, event-driven pipelines, and more — all managed through a clean REST API and powerful CLI.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688.svg)](https://fastapi.tiangolo.com)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🕐 **Cron Scheduling** | Full 5/6-field cron expressions with timezone support |
| ⏱ **Interval Triggers** | Fixed intervals with optional random jitter |
| 🎯 **One-Shot Jobs** | Fire at a specific datetime, then self-remove |
| 🌐 **Webhook Triggers** | POST to an endpoint to fire a job instantly |
| 🔗 **Event-Driven Pipelines** | Chain jobs via internal EventBus (DAG-style) |
| 🐚 **Shell Executor** | Run any shell command with streaming logs |
| 🐍 **Python Callable Executor** | Call any importable Python async function |
| 🌍 **HTTP Executor** | POST/GET external REST endpoints |
| 🐳 **Docker Executor** | Run jobs as ephemeral Docker containers |
| 🔁 **Retry with Backoff** | Exponential backoff with jitter, configurable per-job |
| 🔔 **Slack Notifications** | Rich Block Kit alerts on success/failure |
| 📧 **Email Notifications** | HTML emails via SMTP/TLS |
| 🪝 **Webhook Notifications** | HMAC-signed POST to any endpoint |
| 🔌 **Plugin System** | Drop a folder in and extend anything |
| 📊 **Prometheus Metrics** | Scrape `/metrics` with any Prometheus instance |
| 🔐 **JWT Authentication** | Secure REST API with Bearer token auth |
| 📖 **OpenAPI Docs** | Auto-generated Swagger UI at `/docs` |
| 🐋 **Docker Ready** | Multi-stage Dockerfile + docker-compose |

---

## 📦 Installation

### From PyPI (coming soon)

```bash
pip install taskforge
# With optional extras:
pip install "taskforge[api,postgres,slack,metrics]"
```

### From Source

```bash
git clone https://github.com/your-org/taskforge.git
cd taskforge
pip install -e ".[dev,api,postgres,slack,metrics]"
```

---

## 🚀 Quick Start

### 1. Start the server

```bash
# Using SQLite (default — great for development)
taskforge server start

# With PostgreSQL
TASKFORGE_STORAGE_URL="postgresql+asyncpg://user:pass@localhost/taskforge" \
taskforge server start --port 8080
```

Open the API docs at: **http://localhost:8080/docs**

### 2. Create your first job

```bash
# Via CLI from a JSON file
taskforge jobs create examples/hello_world_job.json

# Via API
curl -X POST http://localhost:8080/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d @examples/hello_world_job.json
```

### 3. Manage jobs

```bash
taskforge jobs list              # list all jobs
taskforge jobs get <job-id>      # show job details
taskforge jobs run <job-id>      # trigger immediately
taskforge jobs pause <job-id>    # pause scheduling
taskforge jobs resume <job-id>   # resume scheduling
taskforge jobs delete <job-id>   # delete permanently
```

### 4. View logs

```bash
taskforge logs runs <job-id>     # list run history
taskforge logs show <run-id>     # show run logs
taskforge logs tail <run-id>     # tail live logs
```

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        CLIENT LAYER                          │
│            REST API (FastAPI)  │  CLI (Typer + Rich)         │
└──────────────┬──────────────────────────────┬───────────────┘
               │                              │
┌──────────────▼──────────────────────────────▼───────────────┐
│                       CORE ENGINE                            │
│   Scheduler (APScheduler)  │  EventBus  │  Pipeline (DAG)   │
└──────┬─────────────────────────────────────────┬────────────┘
       │                                         │
┌──────▼──────┐  ┌────────────┐  ┌──────────────▼────────────┐
│  TRIGGERS   │  │  EXECUTORS │  │    NOTIFICATIONS           │
│  Cron       │  │  Shell     │  │  Slack / Email / Webhook   │
│  Interval   │  │  Python    │  └───────────────────────────┘
│  Webhook    │  │  HTTP      │
│  OneShot    │  │  Docker    │
│  EventBus   │  └────────────┘
└─────────────┘
       │
┌──────▼──────────────────────────────────────────────────────┐
│                     STORAGE LAYER                            │
│          SQLite (default)  │  PostgreSQL                     │
└─────────────────────────────────────────────────────────────┘
       │
┌──────▼──────────────────────────────────────────────────────┐
│                     PLUGIN SYSTEM                            │
│  Entry-point discovery │  Folder scan  │  Lifecycle hooks    │
└─────────────────────────────────────────────────────────────┘
```

See [`architecture.json`](./architecture.json) for the full structured definition.

---

## ⚙️ Configuration

All configuration is via environment variables (12-factor app pattern).

| Variable | Default | Description |
|----------|---------|-------------|
| `TASKFORGE_STORAGE_URL` | `sqlite+aiosqlite:///taskforge.db` | Database URL |
| `TASKFORGE_SECRET_KEY` | *(required in prod)* | JWT signing secret |
| `TASKFORGE_LOG_LEVEL` | `info` | Log level (`debug/info/warning/error`) |
| `TASKFORGE_METRICS_ENABLED` | `true` | Enable Prometheus metrics |
| `TASKFORGE_CORS_ORIGINS` | `*` | Comma-separated allowed CORS origins |
| `TASKFORGE_SLACK_BOT_TOKEN` | *(optional)* | Slack bot OAuth token |
| `TASKFORGE_SLACK_DEFAULT_CHANNEL` | `#alerts` | Default Slack channel |
| `TASKFORGE_SMTP_HOST` | *(optional)* | SMTP server hostname |
| `TASKFORGE_SMTP_PORT` | `587` | SMTP port |
| `TASKFORGE_SMTP_USER` | *(optional)* | SMTP username |
| `TASKFORGE_SMTP_PASSWORD` | *(optional)* | SMTP password |

Copy `.env.example` to `.env` to get started.

---

## 📋 Job Definition Reference

```json
{
  "name": "my-job",
  "description": "What this job does",
  "tags": ["production", "database"],
  "trigger": {
    "type": "cron",
    "config": {
      "expression": "0 2 * * *",
      "timezone": "UTC"
    }
  },
  "executor": {
    "type": "shell",
    "config": {
      "command": "/opt/scripts/run.sh",
      "timeout_seconds": 3600,
      "env": { "KEY": "value" }
    }
  },
  "retry_policy": {
    "max_attempts": 3,
    "backoff_base": 30,
    "backoff_factor": 2.0,
    "jitter": true
  },
  "notifications": [
    {
      "channel": "slack",
      "on_events": ["job.failed"],
      "config": { "channel": "#ops-alerts" }
    }
  ]
}
```

### Trigger Types

| Type | Config Keys |
|------|-------------|
| `cron` | `expression` (cron string), `timezone` |
| `interval` | `weeks`, `days`, `hours`, `minutes`, `seconds`, `jitter` |
| `oneshot` | `run_at` (ISO-8601 datetime) |
| `webhook` | `secret` (HMAC key), `allowed_ips` (CIDR list) |
| `event` | `event_name`, `filter_job_id`, `filter_status` |

### Executor Types

| Type | Config Keys |
|------|-------------|
| `shell` | `command`, `timeout_seconds`, `env`, `working_dir` |
| `python_callable` | `callable` (dotted.module:function), `kwargs` |
| `http` | `url`, `method`, `headers`, `body`, `expected_status` |
| `docker` | `image`, `command`, `env`, `volumes`, `timeout_seconds` |

---

## 🐳 Docker Deployment

```bash
# Development (SQLite + pgAdmin)
docker compose -f docker/docker-compose.yml --profile dev up

# Production (PostgreSQL + app)
docker compose -f docker/docker-compose.yml up -d taskforge postgres

# With monitoring (Prometheus + Grafana)
docker compose -f docker/docker-compose.yml --profile monitoring up -d
```

---

## 🔌 Writing a Plugin

1. Copy the template:
   ```bash
   cp -r plugins/PLUGIN_TEMPLATE plugins/my_plugin
   ```

2. Edit `plugins/my_plugin/__init__.py`:
   ```python
   from taskforge.plugins.base import BasePlugin, HookContext

   class MyPlugin(BasePlugin):
       name = "my_plugin"
       version = "0.1.0"

       async def on_job_end(self, ctx: HookContext) -> None:
           print(f"Job {ctx.job_id} finished with status {ctx.status}")

   plugin = MyPlugin
   ```

3. Register in `pyproject.toml`:
   ```toml
   [project.entry-points."taskforge.plugins"]
   my_plugin = "plugins.my_plugin:plugin"
   ```

4. Install and restart — TaskForge discovers it automatically.

---

## 🧪 Testing

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# Run with coverage
pytest --cov=taskforge --cov-report=html

# Run only unit tests
pytest tests/unit/

# Run only integration tests
pytest tests/integration/

# Run only e2e tests
pytest tests/e2e/
```

---

## 📂 Project Structure

```
taskforge/
├── taskforge/              # Core Python package
│   ├── core/               # Scheduler, EventBus, Pipeline, logging, metrics
│   ├── jobs/               # Job/Run models, retry logic, log stream
│   ├── triggers/           # Cron, Interval, OneShot, Webhook, Event triggers
│   ├── executors/          # Shell, Python, HTTP, Docker executors
│   ├── plugins/            # Plugin loader and base class
│   ├── storage/            # SQLite and PostgreSQL backends
│   ├── api/                # FastAPI REST API (routers, middleware)
│   ├── notifications/      # Slack, Email, Webhook notifiers
│   ├── cli/                # Typer CLI (jobs, logs, server commands)
│   └── config.py           # Pydantic Settings (env-based config)
├── plugins/                # Drop-in community plugins
│   ├── PLUGIN_TEMPLATE/    # Copy this to create a new plugin
│   ├── k8s_executor/       # Kubernetes Job executor
│   ├── discord_notifier/   # Discord webhook notifications
│   └── git_trigger/        # GitHub/GitLab push trigger
├── tests/
│   ├── unit/               # Unit tests (triggers, models, log stream)
│   ├── integration/        # Integration tests (storage backend)
│   └── e2e/                # End-to-end API tests
├── examples/               # Example job definitions (JSON)
├── docker/                 # Dockerfile, docker-compose, prometheus config
├── .github/workflows/      # GitHub Actions CI/CD
├── pyproject.toml          # PEP 517/518 build, dependencies, tools
├── .env.example            # Environment variable template
├── architecture.json       # Structured architecture definition
└── README.md               # This file
```

---

## 🛡️ Security

- All API endpoints require JWT Bearer token authentication
- Webhook triggers support HMAC-SHA256 signature verification
- Non-root Docker container user
- Secrets are never logged (masked in `taskforge server config`)
- CORS origins are configurable

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/my-feature`
3. Make changes with tests
4. Run: `pre-commit run --all-files && pytest`
5. Open a Pull Request

Please read [CONTRIBUTING.md](./CONTRIBUTING.md) for full guidelines.

---

## 📄 License

MIT — see [LICENSE](./LICENSE) for details.

---

## 🙏 Acknowledgements

Built on the shoulders of these excellent open-source projects:
- [APScheduler](https://github.com/agronholm/apscheduler) — scheduling engine
- [FastAPI](https://fastapi.tiangolo.com) — REST API framework
- [Pydantic](https://docs.pydantic.dev) — data validation
- [SQLAlchemy](https://www.sqlalchemy.org) — async ORM
- [Typer](https://typer.tiangolo.com) + [Rich](https://rich.readthedocs.io) — CLI
