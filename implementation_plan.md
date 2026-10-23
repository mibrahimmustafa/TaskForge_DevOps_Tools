# 🚀 TaskForge — Open-Source DevOps Task Scheduler

## Project Identity
| Field | Value |
|-------|-------|
| **Project Name** | TaskForge |
| **Language** | Python 3.11+ |
| **License** | MIT |
| **Primary Goal** | General-purpose, extensible DevOps task scheduler with a clean plugin architecture |

---

## 🎯 System Overview

TaskForge is a production-grade, open-source DevOps task scheduling system built on Python. It supports cron-style scheduling, one-shot jobs, webhook triggers, dependency-chained pipelines, retry policies, alerting, and a REST API — all with a modular plugin system for easy extensibility.

---

## 🏗️ Architecture Summary

```
TaskForge/
├── taskforge/                  # Core Python package
│   ├── core/                   # Scheduler engine, event bus, registry
│   ├── jobs/                   # Job model, runner, retry logic
│   ├── triggers/               # Cron, interval, webhook, event triggers
│   ├── executors/              # Shell, Python callable, HTTP, Docker executors
│   ├── plugins/                # Plugin loader & base class
│   ├── storage/                # SQLite / PostgreSQL backends
│   ├── api/                    # FastAPI REST API
│   ├── notifications/          # Slack, Email, Webhook alert channels
│   └── cli/                    # Rich CLI (Typer)
├── plugins/                    # Community/built-in plugins (drop-in)
│   ├── k8s_executor/
│   ├── discord_notifier/
│   └── git_trigger/
├── tests/                      # pytest test suite
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── docs/                       # Documentation
├── examples/                   # Example job configs & scripts
├── docker/                     # Docker & Compose files
├── .github/                    # CI/CD workflows
├── pyproject.toml              # PEP 517/518 build
├── README.md
└── architecture.json
```

---

## 📋 Implementation Plan — 7 Phases

---

### Phase 1 — Project Scaffold & Tooling Setup
**Goal**: Establish the project foundation, tooling, and quality gates.

| Step | Task | Files/Tools |
|------|------|-------------|
| 1.1 | Create directory structure | `mkdir` commands |
| 1.2 | Initialize `pyproject.toml` | Hatchling / setuptools build backend |
| 1.3 | Configure linting & formatting | `ruff`, `black`, `mypy` |
| 1.4 | Configure pre-commit hooks | `.pre-commit-config.yaml` |
| 1.5 | Set up pytest with coverage | `pytest.ini` / `pyproject.toml` |
| 1.6 | Set up GitHub Actions CI | `.github/workflows/ci.yml` |
| 1.7 | Create `.env.example` | Environment variable template |

**Deliverables**: Runnable project scaffold, all dev tools configured.

---

### Phase 2 — Core Data Models & Storage Layer
**Goal**: Define the foundational data structures and persistence.

| Step | Task | Key Classes/Files |
|------|------|-------------------|
| 2.1 | Define `Job` model | `taskforge/jobs/models.py` |
| 2.2 | Define `JobRun` / `ExecutionLog` | `taskforge/jobs/models.py` |
| 2.3 | Define `Trigger` base model | `taskforge/triggers/base.py` |
| 2.4 | Implement `SQLite` storage backend | `taskforge/storage/sqlite_backend.py` |
| 2.5 | Implement `PostgreSQL` storage backend | `taskforge/storage/postgres_backend.py` |
| 2.6 | Create abstract `StorageBackend` interface | `taskforge/storage/base.py` |
| 2.7 | Alembic DB migrations | `migrations/` |

**Key Design Decisions**:
- All models use **Pydantic v2** for validation + serialization
- Storage is **backend-agnostic** via abstract interface
- `Job` status uses an `Enum`: `PENDING | RUNNING | SUCCESS | FAILED | SKIPPED | CANCELLED`

---

### Phase 3 — Scheduler Engine & Trigger System
**Goal**: Build the scheduling heart — reliable, concurrent job dispatching.

| Step | Task | Key Classes/Files |
|------|------|-------------------|
| 3.1 | Implement `Scheduler` (APScheduler wrapper) | `taskforge/core/scheduler.py` |
| 3.2 | Implement `EventBus` (pub/sub internal) | `taskforge/core/event_bus.py` |
| 3.3 | Implement `CronTrigger` | `taskforge/triggers/cron.py` |
| 3.4 | Implement `IntervalTrigger` | `taskforge/triggers/interval.py` |
| 3.5 | Implement `OneShotTrigger` | `taskforge/triggers/oneshot.py` |
| 3.6 | Implement `WebhookTrigger` | `taskforge/triggers/webhook.py` |
| 3.7 | Implement `EventTrigger` (listen to bus events) | `taskforge/triggers/event_trigger.py` |
| 3.8 | Implement `DependencyChain` (DAG-based pipelines) | `taskforge/core/pipeline.py` |

**Key Design Decisions**:
- Uses **APScheduler 4.x** async scheduler under the hood
- **AsyncIO-native** — all job dispatch is async
- Trigger system is **pluggable** — drop in new trigger types via plugin

---

### Phase 4 — Executor System
**Goal**: Multiple execution backends so jobs can run anywhere.

| Step | Task | Key Classes/Files |
|------|------|-------------------|
| 4.1 | Abstract `BaseExecutor` | `taskforge/executors/base.py` |
| 4.2 | `ShellExecutor` (subprocess + streaming logs) | `taskforge/executors/shell.py` |
| 4.3 | `PythonCallableExecutor` (importable function) | `taskforge/executors/python_callable.py` |
| 4.4 | `HTTPExecutor` (call REST endpoints) | `taskforge/executors/http.py` |
| 4.5 | `DockerExecutor` (run Docker containers) | `taskforge/executors/docker.py` |
| 4.6 | Retry & back-off logic | `taskforge/jobs/retry.py` |
| 4.7 | Timeout enforcement | integrated in `BaseExecutor` |
| 4.8 | Streaming log capture | `taskforge/jobs/log_stream.py` |

**Key Design Decisions**:
- Executors follow **Strategy pattern** — swappable at runtime
- All output is **streamed** line-by-line (not buffered) for real-time logs
- Retry uses **exponential backoff with jitter**

---

### Phase 5 — Plugin System
**Goal**: Zero-friction extensibility — drop a folder in and it works.

| Step | Task | Key Classes/Files |
|------|------|-------------------|
| 5.1 | Define `BasePlugin` interface | `taskforge/plugins/base.py` |
| 5.2 | Implement `PluginLoader` (entry points + folder scan) | `taskforge/plugins/loader.py` |
| 5.3 | Plugin lifecycle hooks (`on_load`, `on_job_start`, `on_job_end`, `on_error`) | `taskforge/plugins/base.py` |
| 5.4 | Built-in plugin: `k8s_executor` | `plugins/k8s_executor/` |
| 5.5 | Built-in plugin: `discord_notifier` | `plugins/discord_notifier/` |
| 5.6 | Built-in plugin: `git_trigger` | `plugins/git_trigger/` |
| 5.7 | Plugin documentation template | `plugins/PLUGIN_TEMPLATE/` |

**Key Design Decisions**:
- Plugins auto-discovered via **Python entry points** (`pyproject.toml` extras)
- Plugins can register new: triggers, executors, notification channels, API routes
- Each plugin is an **independent installable package**

---

### Phase 6 — REST API & CLI
**Goal**: Developer-friendly interfaces for managing the scheduler.

| Step | Task | Key Classes/Files |
|------|------|-------------------|
| 6.1 | FastAPI app factory | `taskforge/api/app.py` |
| 6.2 | `/jobs` CRUD endpoints | `taskforge/api/routers/jobs.py` |
| 6.3 | `/runs` execution history endpoints | `taskforge/api/routers/runs.py` |
| 6.4 | `/triggers` webhook endpoint | `taskforge/api/routers/triggers.py` |
| 6.5 | `/health` & `/metrics` (Prometheus) | `taskforge/api/routers/system.py` |
| 6.6 | OpenAPI docs auto-generated | FastAPI built-in |
| 6.7 | JWT authentication middleware | `taskforge/api/middleware/auth.py` |
| 6.8 | Typer CLI (`taskforge` command) | `taskforge/cli/main.py` |
| 6.9 | CLI: `run`, `list`, `logs`, `pause`, `resume`, `delete` | `taskforge/cli/commands/` |

---

### Phase 7 — Notifications, Observability & Docker
**Goal**: Production-ready monitoring and deployment.

| Step | Task | Key Classes/Files |
|------|------|-------------------|
| 7.1 | Abstract `BaseNotifier` | `taskforge/notifications/base.py` |
| 7.2 | `SlackNotifier` | `taskforge/notifications/slack.py` |
| 7.3 | `EmailNotifier` (SMTP) | `taskforge/notifications/email.py` |
| 7.4 | `WebhookNotifier` | `taskforge/notifications/webhook.py` |
| 7.5 | Structured JSON logging (structlog) | `taskforge/core/logging.py` |
| 7.6 | Prometheus metrics exporter | `taskforge/core/metrics.py` |
| 7.7 | `Dockerfile` (multi-stage, minimal) | `docker/Dockerfile` |
| 7.8 | `docker-compose.yml` (app + PostgreSQL + Redis) | `docker/docker-compose.yml` |
| 7.9 | Helm chart (optional, Phase 2) | `helm/taskforge/` |

---

## 📦 Technology Stack

| Category | Library | Reason |
|----------|---------|--------|
| Scheduling engine | `apscheduler>=4.0` | Mature, async-native, pluggable |
| Data models | `pydantic>=2.0` | Fast validation, serialization, JSON schema |
| API framework | `fastapi` + `uvicorn` | Async, OpenAPI auto-docs |
| CLI | `typer` + `rich` | Beautiful terminal UI |
| ORM / DB | `sqlalchemy>=2.0` + `alembic` | Async ORM, migrations |
| DB drivers | `aiosqlite`, `asyncpg` | Async SQLite & PostgreSQL |
| HTTP client | `httpx` | Async HTTP for HTTP executor |
| Logging | `structlog` | Structured JSON logs |
| Metrics | `prometheus-client` | Standard Prometheus exposition |
| Testing | `pytest` + `pytest-asyncio` + `pytest-cov` | Full async test support |
| Linting | `ruff` + `mypy` | Fast linting + type safety |
| Container | `Docker` + `docker-compose` | Standard deployment |

---

## 🔑 Design Principles (Best Practices)

1. **SOLID principles** — Single responsibility per class, open for extension
2. **Protocol/ABC** for all extension points (executors, triggers, plugins, notifiers)
3. **Async-first** — All I/O is async (no blocking calls on the event loop)
4. **Type-annotated everywhere** — `mypy --strict` compatible
5. **12-factor app** — Config from environment variables, no hardcoded secrets
6. **Structured logging** — Every log entry is JSON with correlation IDs
7. **Idempotent operations** — Safe to retry; job runs are uniquely keyed
8. **Pluggable backends** — Swap SQLite → PostgreSQL with one config change

---

## 📂 Execution Order Summary

```
Phase 1  →  Project scaffold, pyproject.toml, CI/CD, tooling
Phase 2  →  Data models (Pydantic), storage backends (SQLAlchemy)
Phase 3  →  Scheduler engine + all trigger types
Phase 4  →  Executor system (Shell, Python, HTTP, Docker) + retry
Phase 5  →  Plugin loader + 3 built-in plugins
Phase 6  →  FastAPI REST API + Typer CLI
Phase 7  →  Notifications + Prometheus + Docker
Phase 8  →  Web UI Dashboard (SPA Admin Panel) [COMPLETED]
```

---

## ✅ Implementation Status & Checklist

- [x] Python 3.11+ installed & configured in `.venv`
- [x] Package setup via `pyproject.toml` with `pip install -e .`
- [x] Core data models & async SQLite storage (`taskforge/storage/sqlite_backend.py`)
- [x] APScheduler-powered scheduler engine (`taskforge/core/scheduler.py`)
- [x] Triggers subsystem (Cron, Interval, Webhook, OneShot)
- [x] Executors subsystem (Shell, Python, HTTP, Docker)
- [x] Fast REST API with OpenAPI Swagger documentation at `/docs`
- [x] Prometheus metrics exporter at `/metrics`
- [x] Rich CLI application (`taskforge server`, `taskforge jobs`)
- [x] Full Single-Page Admin Dashboard (`dashboard/` SPA) connected live
- [x] Git repository synchronized with remote origin

