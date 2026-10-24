# TaskForge implementation and rollout plan

This plan supersedes the original scaffold checklist. Version 0.2 provides the runnable core for artifact-only, Docker, and Kubernetes delivery. Operational acceptance remains separate from source implementation.

## Implemented engineering work

| Area | Result |
| --- | --- |
| Control plane | Authenticated project-scoped API, role checks, optimistic definition updates, immutable run snapshots |
| Persistence | SQLite/PostgreSQL tables, atomic claims, execution fencing, leases, cancellation, initial schema guard, read-only legacy import |
| Workers | Separate process, schedule leadership, resource locks, durable standalone retries, persisted attempts, process cleanup |
| Pipelines | DAG validation, parallel ready steps, dependency skip behavior, exact public GitHub checkout, verified artifact handoff |
| Security | Host execution opt-in, Docker restrictions, destination allowlists, reference-based secrets, bounded/redacted logs, request-body limits |
| Delivery | Successful-build digest provenance, separate approvals, Docker/Kubernetes adapters, verification/rollback attempts, stale-build guard, reconciliation |
| Operations | Audit records, database readiness, online-worker counts, persisted metrics, transactional completion notifications |
| Dashboard | Real data, responsive themes, job/pipeline/run/deployment controls, logs/artifacts, approvals/reconciliation, keyboard flows |
| Repository CI/CD | Lint/type/security checks, Python/OS matrix, PostgreSQL/UI/container tests, wheel packaging, gated GHCR/tag release |

## Execution steps for rollout

1. **Establish the environment.** Assign an owner for API, PostgreSQL, shared artifact storage, and isolated workers. Configure TLS and least-privilege credentials. Acceptance: API readiness and an online worker, with no secrets in source control.
2. **Validate migration and restore.** Back up the old database, import paused jobs, review conversion errors, restore database and artifacts into a disposable environment. Acceptance: reviewed definitions and matching artifact checksums after restore.
3. **Prove artifact-only delivery.** Run examples/artifact-pipeline.json; inject a failing step; verify dependent steps skip and independent work completes. Acceptance: authorized artifact download, immutable snapshots, durable attempts.
4. **Enable source integration.** Configure a public GitHub repository allowlist and webhook HMAC. Acceptance: exact-commit checkout, trusted-branch filtering, replay deduplication, tampered payload rejection.
5. **Accept Docker staging.** Provision a dedicated worker and target. Deploy a recorded digest, then an unhealthy candidate. Acceptance: verified success, prior-container restoration on failure, explicit reconciliation and audited approval.
6. **Accept Kubernetes staging.** Supply the actual context, namespace, service account, existing Deployment, and readiness probes. Acceptance: rollout success, failed rollout restoration, cancellation/reconciliation, environment serialization. Mock tests alone do not satisfy this step.
7. **Protect release publication.** Configure GitHub's release environment reviewers, tag restrictions, and GHCR permissions. Acceptance: all checks gate a matching-version tag and release contains the immutable manifest, distribution files, checksums, and requested build attestations.
8. **Promote to production.** Reuse the staged digest through a separately approved target; verify service health and retain a tested rollback path. Requires actual infrastructure configuration and a production release decision.

## Next engineering increments

| Priority | Change | Acceptance |
| --- | --- | --- |
| P1 | Incremental migrations and automated restore drill | Upgrade a populated previous schema and verify restore without losing runs/artifacts |
| P1 | Dependency locking, vulnerability checks, image scanning | Reproducible dependency resolution and reviewed vulnerability gate |
| P1 | OIDC and managed secret provider | Expiring identities, role/project policy, rotation without secrets in definitions |
| P1 | Worker capability routing and quotas | Work reaches a compatible runner; bounded aggregate CPU/concurrency per project |
| P1 | Retention and external artifact storage | Dry-run retention, protected referenced releases, checksum-preserving remote downloads |
| P2 | Private GitHub access and commit checks | Scoped installation credentials, exact checkout, visible final commit status |
| P2 | Attestation policy | Verify trusted builder/signature and source provenance before promotion |
| P2 | Pagination at scale and pipeline recovery | No silent definition truncation; safe checkpoints and reviewed replay semantics |
| P2 | Failure/load drills | Database outage, runner termination, target timeout, repeated delivery, and capacity tests |

## Current verification boundary

Automated tests cover API authorization, replay protection, concurrent claims, definition edit races, retry persistence, subprocess cleanup, dependency propagation, artifact integrity, approvals, environment recovery, and UI flows. PostgreSQL and Docker have opt-in real-service tests. Kubernetes tests simulate kubectl; production credentials and target infrastructure are not included.

See install-steps.txt for exact test commands. GitHub's Windows/Linux and Python 3.11-3.14 matrix provides cross-platform evidence after the pushed commit completes its checks. Do not report pending CI or a staged-only test as a production deployment.
