# TaskForge engineering contract

Implement and maintain a generic CI/CD and task automation system for trusted teams with Jenkins Core feature parity. Keep this contract, README.md, architecture.json, and install-steps.txt consistent with the executable code.

## Product scope

Support Jenkins-style Freestyle multi-step builds, artifact-only DAG pipelines, Docker deployment, and Kubernetes deployment through a common queue and approval workflow. Provide real persisted status, logs, artifacts, retries, cancellation, and actionable failures through a responsive dashboard, CLI tools, and authenticated API.

Do not describe planned features as implemented. Do not substitute simulated jobs, random metrics, fake plugin controls, or fallback demo data for working behavior.

## Required architecture

- Separate API/control plane from execution workers; embedded execution is an explicit development/test option.
- PostgreSQL for team operation; SQLite for local development.
- Immutable run snapshots with optimistic definition versions and atomic fenced claims.
- Atomic sequential build numbering (#1, #2, #3...) monotonically allocated per job.
- First-run setup wizard with unlock via `initialAdminPassword`, admin provisioning, and standard tool setup.
- Freestyle multi-step builds: sequential step execution with individual executors/commands within a dedicated workspace directory.
- Parameterized builds with defined types (`choice`, `string`, `boolean`, `text`, `password`), validated at queue time and injected into process environment variables.
- Job execution controls: enable/disable toggle, quiet period delay queuing, and serialized job concurrency mutex (`concurrent_builds: false`).
- Workspace management: tree explorer (`GET /api/jobs/{id}/workspace`), file viewer (`GET /api/jobs/{id}/workspace/file`), and workspace wipe (`POST /api/jobs/{id}/workspace/wipe`).
- Permalinks: direct access to `last`, `lastSuccessful`, `lastFailed`, and `lastStable` runs and archived artifacts.
- Deterministic Jenkins H-cron notation (`H/15 * * * *`, `H(0-29)/10 * * * *`, `H H(0-7) * * *`) hashed by job ID to distribute scheduling load.
- Upstream and downstream build triggers with completion threshold conditions (`SUCCESS`, `UNSTABLE`, `ALWAYS`) and upstream cause lineage tracking.
- Output artifact archiving supporting Ant/Glob patterns and exclusion patterns (`artifact_paths`, `artifact_exclude_paths`) with byte sizes and SHA-256 digests.
- Artifact fingerprint registry recording MD5 and SHA-256 digests for cross-job artifact lineage tracking.
- Automated build retention (LogRotator) enforcing `retention_max_builds` and `retention_days`, while strictly preserving runs flagged `keep_forever` and milestone permalinks.
- Global tool installations (`/api/tools`) with automatic process `PATH` prepending.
- Remote API tree querying supporting Jenkins `?tree=...` selector syntax across jobs and runs endpoints.
- CLI commands: `taskforge build` (with `--param`, `--wait`, `--follow`), `taskforge console` (with `--follow`), and `taskforge artifacts`.
- Durable job retry scheduling; persist attempts and logs. Lost side effects require review rather than automatic replay.
- DAG validation, independent-step concurrency, dependency failure propagation, verified artifact handoff, standard CI environment variables, and runtime parameter injection.
- Secret values configured on the worker; definitions contain references only.
- Explicit repository, HTTP destination, plugin, and deployment target allowlists.
- Host execution opt-in and isolated trusted workers. Never imply Python subprocesses are a security sandbox.
- Release image digests linked to successful-build release.json artifacts. Separate approval identity when required.
- Environment serialization, health/rollout verification, rollback attempts, stale-build rejection, and explicit reconciliation after interrupted deployment.
- Terminal run state and completion notification queue committed in one transaction.
- Dynamic database user provisioning and authentication with role hierarchy (admin, operator, viewer), project scoping, token generation, rotation, and revocation.
- Declarative YAML/JSON task definitions (jobs and multi-step DAG pipelines), multi-document streaming (`---`), sensitive secret redaction on export, dry-run syntax/schema validation, and `taskforge apply` CLI support.
- Docker Compose orchestration (`docker/docker-compose.yml`) coupling API, background execution worker, and PostgreSQL database with shared artifacts volume, environment interpolation fallback (`POSTGRES_PASSWORD`), and directory-local `.env` configuration.

## User experience

Maintain responsive desktop/mobile layouts, dark/light themes, labeled forms, keyboard focus, Escape dismissal, safe text rendering, clear empty/error/loading states, and role-aware controls. Display online-worker status so queued work is understandable. Tokens remain in browser memory only, with support for first-run setup wizard unlocking.

Job editing must preserve optimistic versions and avoid overwriting concurrent changes. Deletion confirms intent and retains history. Declarative YAML import with interactive templates and live syntax validation, 1-click YAML copy and export downloads, visual pipeline dependency DAGs, live streaming logs with auto-scroll and copy controls, attempts, artifact downloads and inline previews, user and token administration with secure copy dialogs, approval, explicit rollback, and reconciliation must have usable entry points.

## Validation and delivery

Run Ruff lint/format, mypy, Bandit, unit/integration tests, real subprocess cancellation/timeout tests, PostgreSQL coordination tests, Chromium desktop/mobile tests, package asset checks, and container smoke tests. Exercise real Docker rollback where Docker is available. Kubernetes simulation is not evidence of a real cluster rollout.

Update all four required documents with behavior, commands, current limits, and operational prerequisites. Review the diff for generated files and secrets. Commit and push only authorized changes; inspect GitHub checks and report failed or pending checks honestly.

## Follow-up milestones

Incremental migration tooling; tested restore/retention; dependency locking and vulnerability checks; OIDC and managed secrets; private repository authentication and GitHub status reporting; external artifact storage and attestation verification; worker capability routing and quotas; pipeline checkpoint recovery; real staging Kubernetes acceptance and load/failure drills.

The source repository cannot supply production credentials, a trusted cluster context, or a configured release environment. Document and validate those deployment prerequisites without claiming an unperformed production rollout.

