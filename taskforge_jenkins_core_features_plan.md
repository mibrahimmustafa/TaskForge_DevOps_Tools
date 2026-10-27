# TaskForge — Jenkins Core Feature Conversion Specification & Implementation Plan

This document converts the Jenkins Core requirements defined in `Jenkins_Core_Features_and_Build_Prompt.md` (Features **F01–F22**, domain models, product screens, and acceptance criteria) into concrete engineering specifications for **TaskForge**.

---

## 1. Executive Summary & Architecture Gap Analysis

TaskForge 0.3 currently provides a FastAPI control plane, async SQLAlchemy persistence (SQLite/PostgreSQL), workers with leased execution fences, basic DAG pipelines, and a lightweight dashboard. 

To bridge the gap between TaskForge and a true Jenkins-grade automation platform, TaskForge needs evolution from a single-command job runner into an **extensible, multi-step, multi-node, queue-disciplined automation server**.

### Status Overview Matrix (F01 – F22)

| ID | Feature Name | Current TaskForge Status | Target Architecture in TaskForge |
|---|---|---|---|
| **F01** | First-run Setup & Unlock | ⚠️ **Partial** (CLI `taskforge init` only) | Web Setup Wizard: master secret unlock, admin account creation, base URL config, setup completion flag. |
| **F02** | Job Lifecycle Management | ⚠️ **Partial** (Create/Update/Delete) | Full Freestyle lifecycle: Clone/Copy, Rename with ref updates, Enable/Disable toggle, validation rules, name uniqueness. |
| **F03** | Parameterized Builds | ⚠️ **Partial** (JSON parameters in run payload) | Typed Parameter Definitions (String, Text, Boolean, Choice, Password, File, Run Reference), interactive trigger modal with validation. |
| **F04** | Build Initiation & Scheduling | ⚠️ **Partial** (APScheduler cron/interval/manual) | Jenkins H-notation cron (`H/15 * * * *`), quiet-period delays, upstream/downstream build triggers (ReverseBuildTrigger), structured trigger causes. |
| **F05** | Queue & Concurrency Engine | ⚠️ **Partial** (Flat `tf_work` FIFO queue) | Dedicated Queue model: waiting (quiet period), blocked (labels, concurrency, upstream locks), buildable, and assigned states with queue cancellation & restart persistence. |
| **F06** | Multi-step Build Execution | ⚠️ **Partial** (Single command or DAG step) | Ordered Freestyle build steps (Shell, Windows Batch, Python, Process, HTTP), Build Wrappers (timeouts, env modifiers), and Post-Build Publishers. |
| **F07** | Run Records & Permalinks | ⚠️ **Partial** (UUID run IDs, basic status) | Sequential per-job build numbers (`#1`, `#2`, ...), granular results (`SUCCESS`, `UNSTABLE`, `FAILURE`, `NOT_BUILT`, `ABORTED`), permalinks (`/lastSuccessfulBuild`, etc.). |
| **F08** | Live Console Streaming & Annotations | ⚠️ **Partial** (1.5s DB polling, 2MB cap) | Chunked incremental log reading with byte offsets, ANSI color support, log download, console annotation hooks. |
| **F09** | Workspace Management & Explorer | ⚠️ **Partial** (Local folder on worker) | Path-traversal protected workspace browser, concurrent run directory isolation (`workspace@2`), workspace cleanup actions. |
| **F10** | Artifact Archiving & Patterns | ⚠️ **Partial** (Exact file paths list) | Ant-style glob patterns (`**/*.jar`, `dist/**`), exclude patterns, success-only archiving, empty-archive policy, artifact download API. |
| **F11** | Artifact Fingerprint Tracking | ❌ **Absent** | SHA-256 fingerprint registry tracking upstream build origins and downstream build usages across jobs. |
| **F12** | Build & Artifact Retention | ❌ **Absent** | Discard old builds policy (max count, max days, separate artifact retention limits), "Keep this build forever" toggle. |
| **F13** | Distributed Nodes & Agents | ⚠️ **Partial** (Autonomous worker poll) | Managed Node/Agent registry: labels, executor count, node usage mode (Normal vs Exclusive), connection status, manual offline controls with reasons. |
| **F14** | Agent Health & Capacity Monitors | ❌ **Absent** | Disk space, temp space, memory, response time monitoring, load statistics charts, auto-offline triggers. |
| **F15** | Dashboard, Views & Search | ⚠️ **Partial** (Fixed tabs: Jobs, Pipelines, etc.) | Custom Tabbed Views (All, Regex, Job List), Weather Health Icons (based on last 5 runs), live queue/executor sidebar, instant search bar. |
| **F16** | Users, Profiles & Local Auth | ⚠️ **Partial** (Bearer tokens only) | Username/Password local login, user profile page, named API token generation with 1-time secret reveal and instant revocation. |
| **F17** | Granular Authorization & CSRF | ⚠️ **Partial** (Project viewer/operator/admin) | Item-level RBAC (Job/Read, Job/Build, Job/Configure, Job/Cancel, Administer), CSRF crumb protection for session forms. |
| **F18** | SCM Integration Contracts | ⚠️ **Partial** (Public GitHub clone helper) | Pluggable `SCMProvider` interface (`checkout`, `poll`, `get_changes`), NullSCM, Git SCM adapter with commit change log display. |
| **F19** | Tools & Environment Management | ❌ **Absent** | Named Tool Installations (Python versions, Node.js, JDK), node-specific tool paths, auto-extract installers, global environment variables. |
| **F20** | Plugin Architecture & Extension Registry | ⚠️ **Partial** (Basic entry-point loader) | ExtensionPoint discovery system, plugin descriptor metadata, enable/disable toggle, install progress and restart notices. |
| **F21** | Remote API & CLI Controls | ⚠️ **Partial** (REST API, basic CLI) | Query depth/tree filtering (`/api/jobs?tree=jobs[name,status]`), Job YAML/JSON export & import, rich CLI commands (`build`, `console`, `nodes`). |
| **F22** | Administration & Maintenance Modes | ⚠️ **Partial** (Worker count, audit logs) | Quiet-Down mode (drain running work, block new dispatch), System Information diagnostics, configurable log recorders, safe restart. |

---

## 2. Detailed Feature Specifications (F01 – F22)

### F01 — First-Run Setup & Unlock Flow
- **Current State**: System requires running `taskforge init` in CLI and copying token from `.taskforge/config.env`.
- **Target Specification**:
  - **Storage**: Add `system_state` document in `tf_documents` with flags: `initialized: bool`, `setup_complete: bool`, `unlock_key_hash: str`.
  - **Unlock Flow**: On fresh startup without configuration, server generates a random 32-character unlock key written to `.taskforge/initial_admin_password` and logs it to stdout.
  - **Web Wizard**: If `setup_complete == false`, any web request redirects to `/setup`:
    1. Step 1: Input initial unlock key.
    2. Step 2: Create initial administrator account (username, password, full name, email).
    3. Step 3: Configure Instance URL (`TASKFORGE_URL`, e.g. `http://localhost:8080`).
    4. Step 4: Finish setup, delete initial password file, mark `setup_complete: true`.
  - **Acceptance Criteria**: Fresh instance blocks all operations until unlock; after setup completes and restart occurs, setup wizard never re-triggers and admin account works.

---

### F02 — Freestyle Job Lifecycle Management
- **Current State**: CRUD exists, but lacks Clone/Copy, Rename handling, and Enable/Disable semantics.
- **Target Specification**:
  - **API Endpoints**:
    - `POST /api/jobs/{id}/copy?new_id={new_id}&name={name}`
    - `POST /api/jobs/{id}/rename`: Updates job ID and cascades/checks references in pipelines, triggers, and permissions.
    - `POST /api/jobs/{id}/enable` / `POST /api/jobs/{id}/disable`: Sets `enabled: false` (distinct from paused schedule).
  - **Rules**:
    - Disabled jobs reject manual, webhook, timer, or upstream scheduling.
    - Copy duplicates all steps, parameters, triggers, environment, and retention policies, resetting run counters.
    - Job name validation: alphanumeric, dashes, dots, underscores, unique per project.
  - **Acceptance Criteria**: Copying preserves full configuration; disabling prevents any run; renaming retains all historical runs under new identity.

---

### F03 — Parameterized Builds
- **Current State**: Generic parameters dictionary accepted in submit API, but no parameter schema or validation.
- **Target Specification**:
  - **Schema Definition**: A Job contains `parameters: list[ParameterDefinition]`.
    - Types supported:
      - `string`: default value, trim option.
      - `text`: multiline string.
      - `boolean`: default true/false checkbox.
      - `choice`: options list (select dropdown).
      - `password`: masked input in UI, redacted from logs.
      - `file`: uploaded file saved to workspace inputs before execution.
      - `run_reference`: reference to another job's specific run number.
  - **UI Interaction**: Clicking "Build" on a parameterized job opens a "Build with Parameters" modal with form fields, descriptions, and defaults.
  - **Execution Propagation**: Passed to runners as environment variables `TF_PARAM_<NAME>` and directly in executor scope.
  - **Acceptance Criteria**: Run stores the exact parameters passed; missing required parameters reject build dispatch; password parameters never appear in clear text in logs or API responses.

---

### F04 — Build Initiation, Scheduling & Triggers
- **Current State**: APScheduler cron/interval/manual, GitHub webhook.
- **Target Specification**:
  - **Jenkins H-Notation**: Implement hash-based cron expressions (e.g., `H/15 * * * *`, `H(0-30)/10 * * * *`) hashed by job ID to spread load across time intervals and prevent thundering herds.
  - **Quiet Period**: Optional `quiet_period_seconds` on jobs (default 0). Enqueued jobs wait in the queue until `enqueued_at + quiet_period_seconds <= now`. If triggered again during quiet period, coalesce into a single execution.
  - **Upstream / Downstream Triggers**:
    - Job option: `downstream_triggers: list[DownstreamTrigger]` specifying downstream `job_id` and threshold (`SUCCESS`, `UNSTABLE_OR_BETTER`, `ALWAYS`).
    - Reverse build triggers: Job can listen for upstream job completions.
  - **Trigger Causes**: Structured `cause` object stored on every run:
    - `{"type": "user", "user": "admin"}`
    - `{"type": "timer", "schedule": "H 2 * * *"}`
    - `{"type": "upstream", "job": "build-app", "run": 42}`
    - `{"type": "webhook", "provider": "github", "commit": "a1b2c3"}`
    - `{"type": "cli", "user": "deployer"}`
  - **Acceptance Criteria**: Enqueuing with quiet period delays dispatch; multiple triggers during quiet period collapse to 1 run; upstream success automatically triggers downstream job.

---

### F05 — Advanced Queue & Concurrency Engine
- **Current State**: Flat `tf_work` table claimed immediately by workers.
- **Target Specification**:
  - **Queue Lifecycle States**:
    1. `WAITING`: In quiet period.
    2. `BLOCKED`: Reason recorded (e.g., "Waiting for upstream project", "Waiting for label 'linux-gpu'", "Job concurrency limit reached").
    3. `BUILDABLE`: Ready to be claimed by an available executor matching constraints.
    4. `ASSIGNED`: Claimed by a specific worker/executor.
  - **Concurrency Controls**:
    - `concurrent_builds: bool`: When false, only 1 run of this job may execute at a time. Subsequent triggers wait in `BLOCKED` status.
    - `assigned_node_label: str | None`: Worker claiming item must satisfy label expression.
  - **Queue UI & Management**:
    - Live sidebar widget: "Build Queue (N)" showing item, job, time in queue, and blockage reason.
    - Cancel button on queue items to revoke work before execution starts.
  - **Acceptance Criteria**: Second run of non-concurrent job waits in queue; unmatched node label displays human-readable blockage reason; cancelled queue item never executes.

---

### F06 — Multi-Step Build Execution & Extension Points
- **Current State**: Job has one `command` and one `executor`.
- **Target Specification**:
  - **Ordered Steps**: A Job contains `steps: list[BuildStep]`.
    - Step types:
      - `shell`: Bash/sh command script.
      - `batch`: Windows cmd / powershell script.
      - `python`: Inline Python script execution.
      - `http`: Webhook/API request.
      - `process`: Direct binary invocation.
  - **Execution Engine**:
    - Steps run sequentially inside the same workspace directory.
    - If any step exits non-zero, subsequent build steps abort immediately.
  - **Build Wrappers & Publishers**:
    - Wrappers: Execution timeout, environment injection, secret masking, workspace cleanup before build.
    - Post-Build Publishers: Always-run steps (e.g. Artifact Archiver, Notification, Downstream Trigger) that evaluate even if previous build steps failed.
  - **Acceptance Criteria**: Ordered steps execute in order in same workspace; failing step fails run; post-build publishers run regardless of status.

---

### F07 — Run Records, Results & Permalinks
- **Current State**: UUIDs for runs, statuses: queued, running, success, failed, timed_out, cancelled, lost.
- **Target Specification**:
  - **Sequential Build Numbers**: Each Job maintains an atomic `next_build_number` counter. Runs are numbered `#1`, `#2`, `#3`... per job.
  - **Granular Results**:
    - `SUCCESS`: All steps passed.
    - `UNSTABLE`: Build steps passed, but warnings/test failures logged.
    - `FAILURE`: Step crashed or exited non-zero.
    - `NOT_BUILT`: Skipped or unfulfilled prerequisites.
    - `ABORTED`: Cancelled manually by user or system.
  - **Permalinks API**:
    - `GET /api/jobs/{id}/builds/last`: Latest completed run.
    - `GET /api/jobs/{id}/builds/lastSuccessful`: Latest SUCCESS run.
    - `GET /api/jobs/{id}/builds/lastFailed`: Latest FAILURE run.
    - `GET /api/jobs/{id}/builds/lastStable`: Latest SUCCESS without test failures.
  - **Acceptance Criteria**: Build numbers increment sequentially without gaps; permalinks resolve correctly; history survives restart.

---

### F08 — Live Incremental Console Output & Annotations
- **Current State**: Polls whole log buffer or writes to database log table with 2MB cap.
- **Target Specification**:
  - **Chunked Log Streaming**:
    - Logs written to append-only disk files: `.taskforge/logs/{run_id}.log`.
    - Endpoint: `GET /api/runs/{id}/log?start={byte_offset}` returning `{text: str, next_offset: int, eof: bool}`.
    - Browser dashboard polls only new bytes using `start=last_offset` without reloading entire history.
  - **Console Features**:
    - ANSI color parsing for shell output formatting.
    - Download raw log button (`GET /api/runs/{id}/log/download`).
    - Auto-scroll lock toggle in UI.
  - **Acceptance Criteria**: 50MB log streams efficiently without high memory usage; live output updates while build executes; downloads full raw text.

---

### F09 — Workspaces & Safe Directory Browser
- **Current State**: Worker allocates directory, no browsing or UI visibility.
- **Target Specification**:
  - **Workspace Allocation**:
    - Isolated directory: `.taskforge/workspaces/{job_id}`.
    - For concurrent executions: `.taskforge/workspaces/{job_id}@2`, `@3`.
  - **Workspace Explorer API & UI**:
    - `GET /api/jobs/{id}/workspace/tree?path={subpath}`: Lists directory contents.
    - `GET /api/jobs/{id}/workspace/file?path={subpath}`: Reads file content or downloads it.
    - **Security**: Strict path-traversal validation (`resolved_path.is_relative_to(workspace_root)`). Return 403 on escaping attempts.
    - Action: `POST /api/jobs/{id}/workspace/wipe`: Clean workspace directory.
  - **Acceptance Criteria**: Browsable file tree in dashboard; unauthorized paths outside workspace root strictly rejected with 403; wipe cleanly deletes files.

---

### F10 — Glob-based Artifact Archiving
- **Current State**: Exact relative file path list with 50MB limit.
- **Target Specification**:
  - **Publisher Config**:
    - `artifacts_pattern: str` (e.g., `dist/**/*.whl`, `build/reports/**`).
    - `artifacts_exclude: str | None` (e.g., `**/*.tmp`, `**/*.log`).
    - `allow_empty_archive: bool` (default: false, fails build if no files match).
    - `only_if_successful: bool` (default: true).
  - **Storage & UI**:
    - Retains files in artifact storage linked to the specific run.
    - Run Detail page displays downloadable artifact file tree with sizes and checksums.
  - **Acceptance Criteria**: Glob matching captures nested matching files; excluded files omitted; empty matching pattern fails build if flag is false.

---

### F11 — Artifact Fingerprint Lineage Tracking
- **Current State**: Absent.
- **Target Specification**:
  - **Fingerprint Engine**:
    - Table: `tf_fingerprints` (`sha256`, `filename`, `created_at`, `producer_run_id`, `consumer_runs: list`).
    - When archiving artifacts or recording inputs, calculate SHA-256 and register in `tf_fingerprints`.
  - **Lineage UI**:
    - Run detail displays "Fingerprints Tracked": links to upstream producer run and downstream consumer runs.
  - **Acceptance Criteria**: Downstream job consuming artifact from upstream job shows direct lineage connection in fingerprint view.

---

### F12 — Build & Artifact Retention Policies (LogRotator)
- **Current State**: No automated cleanup or retention limits.
- **Target Specification**:
  - **Job Configuration**:
    - `retention_days: int | None`: Keep runs for N days.
    - `retention_max_builds: int | None`: Keep at most N runs.
    - `artifact_days: int | None`: Prune artifacts after N days while retaining run logs.
    - `artifact_max_builds: int | None`: Keep artifacts for last N runs.
  - **Run Flag**: `keep_forever: bool` toggle on individual runs.
  - **Retention Worker Task**: Background maintenance job runs periodically, evaluating retention rules, skipping running builds and builds marked `keep_forever`.
  - **Acceptance Criteria**: Old builds pruned per count/age limits; "Keep forever" builds preserved indefinitely; artifacts can be pruned independently of logs.

---

### F13 — Distributed Nodes & Agent Management
- **Current State**: Anonymous workers polling central DB.
- **Target Specification**:
  - **Node Entity**:
    - Fields: `id`, `name`, `description`, `executors_count`, `remote_root_dir`, `labels: list[str]`, `usage_mode` (`NORMAL` vs `EXCLUSIVE`), `status` (`ONLINE`, `OFFLINE`, `CONNECTING`), `offline_reason`.
  - **Agent Communication & Registration**:
    - Workers start with node identity: `taskforge worker start --node-id <id>`.
    - Worker heartbeat registers executor capacity and heartbeat timestamp.
  - **Admin Node Controls**:
    - Mark node offline (with custom reason prompt, draining running jobs).
    - Mark node online.
    - Configure executor counts and labels.
  - **Acceptance Criteria**: Jobs requiring label `gpu` only dispatch to nodes labeled `gpu`; offline node accepts no new claims and displays reason.

---

### F14 — Agent Health & Capacity Monitoring
- **Current State**: Basic heartbeat lease only.
- **Target Specification**:
  - **Node Monitors**:
    - Disk Space Monitor: reports free GB on `remote_root_dir`.
    - Memory/Swap Monitor: reports available RAM.
    - Response Time Monitor: round-trip heartbeat latency.
  - **Threshold Actions**: If disk space drops below configured threshold (e.g. < 1GB), node automatically marks itself temporarily offline with reason "Low Disk Space".
  - **Dashboard Node Page**: Displays live progress bars for CPU/RAM/Disk and executor occupancy slots (e.g. 2/4 executors active).
  - **Acceptance Criteria**: Simulated low-disk condition disables node dispatch; executor occupancy displays active running tasks.

---

### F15 — Dashboard, Custom Views & Search
- **Current State**: Fixed static tabs (Overview, Jobs, Pipelines, Runs, Deployments, Integrations, Users, Audit).
- **Target Specification**:
  - **Customizable Views**:
    - View Types: `AllView`, `ListView` (regex pattern or manual job selection).
    - Customizable view columns: Status Icon, Health Weather, Name, Last Success, Last Failure, Last Duration, Action Buttons.
  - **Health Weather Icons**:
    - ☀️ **Sunny**: 5/5 recent runs successful.
    - ⛅ **Partly Cloudy**: 4/5 recent runs successful.
    - ☁️ **Cloudy**: 2-3/5 recent runs successful.
    - 🌧️ **Rainy**: 1/5 recent runs successful.
    - ⛈️ **Stormy**: 0/5 recent runs successful.
  - **Omnibox Search**:
    - Top header search bar with keyboard shortcut `/`.
    - Instant autocomplete dropdown searching jobs, pipelines, runs, nodes, and views.
  - **Acceptance Criteria**: Custom view filters jobs accurately; weather icon reflects recent 5 runs; search instantly finds authorized jobs.

---

### F16 — Users, Profiles & Local Authentication
- **Current State**: Static token or generated tokens with no password/login form.
- **Target Specification**:
  - **Authentication Modes**:
    - Local user accounts with hashed passwords (bcrypt / Argon2).
    - Sign-in page with Username & Password credentials.
  - **User Profile Management**:
    - Change password, update email/display name.
    - Manage personal API tokens: generate named token, reveal secret key once, revoke token.
  - **Acceptance Criteria**: User signs in with username/password; user can create and name an API token; revoking an API token immediately blocks subsequent API requests.

---

### F17 — Granular Authorization & CSRF Security
- **Current State**: Coarse viewer/operator/admin project-level bearer tokens.
- **Target Specification**:
  - **Permission Model**:
    - Permissions: `Overall/Read`, `Overall/Administer`, `Job/Read`, `Job/Build`, `Job/Configure`, `Job/Cancel`, `Job/Workspace`, `Node/Configure`, `Node/Connect`.
    - Matrix / Role mapping: assign permissions to roles or users per project.
  - **CSRF Crumb Protection**:
    - Endpoint: `GET /api/crumbIssuer/api/json` returns `{crumbRequestField: "TF-Crumb", crumb: "hash"}`.
    - All state-mutating POST/PUT/DELETE requests validate crumb header when authenticated via browser session cookie.
  - **Acceptance Criteria**: User without `Job/Build` permission gets 403 on build trigger; missing CSRF crumb on browser POST fails with 403.

---

### F18 — SCM Integration Contracts & Git Adapter
- **Current State**: Hardcoded GitHub clone helper in pipelines.
- **Target Specification**:
  - **SCM Abstraction**:
    - Base Class `SCMProvider`:
      - `poll(job, workspace) -> bool`: Checks if new commits exist.
      - `checkout(job, workspace, target_commit) -> dict`: Clones/fetches and returns changelog.
      - `get_changelog(run) -> list[ChangeLogEntry]`: Returns author, message, commit ID, timestamp.
    - Implementations:
      - `NullSCM`: No-op.
      - `GitSCM`: Clone/fetch git repositories with branch, credentials, submodules, and changelog generation.
  - **Changelog Display**: Run detail page features "Changes" section detailing all commits in this build.
  - **Acceptance Criteria**: Git SCM detects new commit during polling; checkout generates change log; change log rendered on run page.

---

### F19 — Tool Installations & Node Environments
- **Current State**: Relies on runner host pre-installed binaries.
- **Target Specification**:
  - **Tool Entity**:
    - Named tools: e.g. `Python 3.12`, `NodeJS 20`, `Go 1.22`.
    - Node-specific path overrides: Node A has `/usr/bin/python3.12`, Node B has `C:\Python312\python.exe`.
    - Automatic Installers: Command installer or Zip extraction installer from URL.
  - **Job Association**:
    - Job specifies required tools (e.g. `tools: {"python": "Python 3.12"}`).
    - Runner prepends resolved tool `bin` directory to `PATH` environment variable.
  - **Acceptance Criteria**: Same job runs on different OS nodes with correct tool paths resolved automatically.

---

### F20 — Plugins & Extension Registry
- **Current State**: Basic Python entry-point loader.
- **Target Specification**:
  - **Plugin Registry**:
    - Plugins define metadata: `id`, `version`, `title`, `description`, `dependencies`, `enabled`.
    - UI page: `/admin/plugins` showing Installed Plugins, Available Plugins, Updates.
  - **Extension Points**:
    - Defined extension interfaces: `SCMProvider`, `BuildStep`, `Publisher`, `NodeMonitor`, `AuthRealm`.
    - Plugins register classes implementing these extension interfaces.
  - **Acceptance Criteria**: Disabling plugin de-registers its extension steps without crashing; plugin dependencies validated before activation.

---

### F21 — Remote API & CLI Controls
- **Current State**: Standard FastAPI OpenAPI endpoints, basic CLI.
- **Target Specification**:
  - **Depth / Tree API Selection**:
    - Support queries like `GET /api/jobs?tree=jobs[id,name,status,lastRun[duration]]` to minimize payload size for automation scripts.
  - **Job Export / Import**:
    - `GET /api/jobs/{id}/config.yaml` and `POST /api/jobs/import.yaml`.
  - **Dedicated CLI Commands**:
    - `taskforge build <job-id> [-p KEY=VAL] [--follow]`: Triggers build and optionally follows console output.
    - `taskforge console <job-id> [run-number]`: Streams console log.
    - `taskforge nodes list`: Displays active nodes and executor capacity.
    - `taskforge quiet-down` / `cancel-quiet-down`: Toggles maintenance mode.
  - **Acceptance Criteria**: Programmatic build trigger followed via CLI streams live logs to terminal and returns build exit code.

---

### F22 — Administration, Maintenance & Quiet-Down
- **Current State**: System stats endpoint, audit logs.
- **Target Specification**:
  - **Quiet-Down Mode**:
    - `POST /api/admin/quietDown`: Suspends claiming new queue items. Existing running builds continue until completion.
    - UI displays persistent warning banner: *"TaskForge is going to shut down; no new builds will start."*
    - `POST /api/admin/cancelQuietDown`: Resumes normal queue dispatch.
  - **System Diagnostics**:
    - System Info: Python runtime, OS, disk capacity, database status, loaded plugins, thread/async task counts.
    - Log Recorders: Custom log level filters per python package (`taskforge.core: DEBUG`, etc.).
  - **Acceptance Criteria**: In quiet-down mode, queue items remain pending; active builds finish normally; canceling quiet-down resumes processing.

---

## 3. Product Screens Mapping

| Screen Number | Screen Name | Key Features & Elements |
|---|---|---|
| **1** | **Setup & Sign-In** | Unlock token entry, initial admin creation, base URL config, password login, user profile & API token manager. |
| **2** | **Main Dashboard & Views** | View tabs (All + custom views), Weather health badges, Job list table, Live Queue widget, Executor Status sidebar, Top Search bar. |
| **3** | **Job Creation & Config** | General (Name, Description, Project), Parameters builder, Concurrency, Triggers & H-cron, SCM selector, Ordered Steps, Post-build actions, Retention. |
| **4** | **Job Detail Page** | Run button / Build with Parameters, Enable/Disable toggle, Build history timeline, Workspace browser link, Permalinks list. |
| **5** | **Run Detail Page** | Status badge & duration, Trigger cause, Parameters used, Live streaming ANSI console, Download artifacts, Fingerprints, Keep forever toggle. |
| **6** | **Nodes & Agents Page** | Node cards / table, Executor utilization gauges, Disk & RAM monitors, Mark Offline dialog with reason, Connection logs. |
| **7** | **Administration Page** | Quiet-Down toggle, System Information & diagnostics, Tool installations, Plugin manager, Log recorders, System settings. |

---

## 4. Phased Implementation Roadmap & Status

### Phase 1: Working Single-Worker Core (Freestyle & Queue Essentials) — ✅ COMPLETED
- **Features Implemented**:
  - **F01**: Setup Wizard (`/api/system/setup-status`, unlock token, initial admin account, instance URL configuration).
  - **F02 & F03**: Job lifecycle controls (Enable/Disable, Copy, Rename), Parameterized Builds (String, Text, Boolean, Choice, Password, File, Run Reference), and Multi-step ordered Freestyle builds (`taskforge/jobs/models.py`).
  - **F05 & F06**: Queue and Concurrency (`concurrent_builds` serialize vs. concurrent execution locks, quiet periods, multi-step execution in a single step workspace).
  - **F07 & F08**: Sequential build numbers (`#1`, `#2`, ...), granular run results (`SUCCESS`, `UNSTABLE`, `FAILED`, `ABORTED`, `NOT_BUILT`), permalinks (`last`, `lastSuccessful`, `lastFailed`, `lastStable`), and chunked redacted live console log streaming & log downloads.
  - **F09 & F16**: Workspace file tree browser (`/api/jobs/{id}/workspace`) with directory traversal protection, file viewing, and workspace wiping (`/api/jobs/{id}/workspace/wipe`). Local username/password authentication with bearer session tokens (`/api/auth/login`).
- **Tests**: Validated with dedicated integration suite (`tests/integration/test_jenkins_core_phase1.py`).

### Phase 2: Automation, Triggers & Outputs — ✅ COMPLETED
- **Features Implemented**:
  - **F04**: Jenkins H-notation cron parser (`taskforge/triggers/h_cron.py`) with stable pseudo-random hashing across cluster nodes, and Upstream/Downstream build triggers with result thresholds (`SUCCESS`, `UNSTABLE`, `FAILED`).
  - **F10**: Glob-based artifact archiving with inclusion/exclusion patterns (`**/*.whl`, `!*.tmp`), persistent build storage (`/artifacts/{project}/{job_id}/{build_number}/`), and retention after workspace wiping.
  - **F11**: Artifact fingerprint lineage registry (`tf_fingerprints` table, MD5 & SHA-256 tracking, producer/consumer tracking, `/api/fingerprints/{hash}`, `/api/fingerprints/track`).
  - **F12**: LogRotator build & history retention (`taskforge/jobs/retention.py`) evaluating `retention_max_builds` and `retention_days`, respecting `keep_forever` flags, latest builds, and successful/stable runs. Auto-invoked on worker finish and available on demand (`POST /api/jobs/{id}/retention/run`).
  - **F19**: Global Tool Configuration model & API (`/api/tools`), with automatic `PATH` and `<TOOL>_HOME` injection into worker execution environments.
  - **F21**: Remote API Jenkins-compatible `?tree=...` selection filter (`taskforge/api/tree_filter.py`) on list and detail endpoints; CLI additions (`taskforge build <job_id> --follow --param key=value`, `taskforge console`, `taskforge artifacts`).
- **Tests**: Validated with dedicated integration suite (`tests/integration/test_jenkins_core_phase2.py`). 80 unit & integration tests passing.

### Phase 3: Distributed Execution & Node Fleet Management — ⏳ PLANNED
- **Features**: **F13** (Nodes & Agent Registry, Labels, Usage Modes), **F14** (Agent Health, Disk/RAM Monitors, Auto-offline), **F22** (Quiet-Down Maintenance Mode & System Info).
- **Deliverable**: Label-based worker routing across multiple nodes, live executor occupancy displays, proactive low-disk offline handling, and safe maintenance draining.

### Phase 4: Extensibility, Custom Views & Advanced UI — ⏳ PLANNED
- **Features**: **F15** (Custom Views, Weather Icons, Quick Search), **F17** (Granular RBAC Matrix, CSRF Crumbs), **F18** (Pluggable SCM & Git Adapter with Changelog), **F20** (Plugin Management UI & ExtensionPoint Contracts).
- **Deliverable**: Polished enterprise interface with tabbed views, weather icons, Git commit changelogs, fine-grained permission matrices, and modular plugin extension management.

---

## 5. Verification & Quality Gates

- **Total Unit & Integration Tests**: 80 passing, 1 skipped.
- **Integration Test Suites**:
  - `tests/integration/test_jenkins_core_phase1.py` (6 tests passing)
  - `tests/integration/test_jenkins_core_phase2.py` (7 tests passing)
  - `tests/integration/test_api.py`, `test_pipeline_execution.py`, `test_deployments.py`, `test_recovery.py` (67 tests passing)

