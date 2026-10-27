# Jenkins Core — Feature Specification and AI Build Prompt

Repository: https://github.com/jenkinsci/jenkins

Reviewed snapshot: `c5f59e8b565d91ba7e9a209337a49e1fbb19f1db` (shallow clone of `master`, reviewed 27 October 2026).

## Purpose and scope

Use this document as a prompt for a coding assistant to build a Jenkins-like automation server. It maps the major user-facing capabilities and extension contracts found in the reviewed core source to implementation requirements. This is a source-guided feature inventory, not an exhaustive method-by-method audit, a running-system verification, or a claim of complete Jenkins/plugin compatibility. No Jenkins build or test suite was executed for this review.

**Core** means implemented in this repository. **Extension contract** means core supplies an integration interface but a concrete external provider may be required. **Optional ecosystem feature** means a separate project supplies the capability. Acceptance criteria and implementation phases below are proposed requirements for the new system, not claims that those exact tests were run against Jenkins.

## Copy-ready master prompt

You are the lead engineer building a persistent, working automation server inspired by Jenkins core. Implement the feature groups F01–F22 below, using the source links to resolve behavior and the acceptance criteria to verify the new system.

Build real job execution, durable state, a scheduler, an agent/worker boundary, live logs, artifact storage, authentication, authorization, and an extensible integration architecture. Deliver functioning backend behavior and UI workflows; do not replace build execution with mocked status changes.

Treat this as a phased project. First inspect the existing application if one exists. Select a coherent stack when none is specified, record the choice, and implement the first milestone end to end before expanding. Preserve the feature IDs in the backlog and completion report. Describe each group as implemented, partial, or deferred, with evidence and remaining gaps.

Keep core features and optional integrations distinct. Do not silently claim Jenkinsfile support, Git checkout, cloud agents, test reports, or deployment integrations merely because extension hooks exist. A Jenkinsfile in this repository builds Jenkins itself; it does not mean the Pipeline runtime is implemented here.

Use permission checks on the server for every protected operation. Execute user jobs through workers with explicit filesystem/process boundaries. Protect secret material and prevent artifact/workspace traversal. Implement cancellation and failure paths as well as successful runs. Persist configuration and completed runs across restart, and define honest behavior for work interrupted by a crash; do not promise freestyle build resumption.

Deliver application source, repeatable local startup instructions, configuration documentation, meaningful automated tests, sample jobs, and a feature-to-test checklist. Any new API design or database schema is an implementation choice, not an assertion that Jenkins uses that design. Unless explicitly requested, functional similarity is sufficient: binary compatibility with Jenkins Java plugins, exact REST paths, XML schemas, and its remoting protocol are separate projects.

## Feature requirements


### F01 — First-run setup

**Build requirements:** Provide an initial unlock flow, initial administrator creation, instance URL configuration, plugin selection/install progress, and persistent setup completion state.

**Acceptance:** A fresh instance requires setup; after completing setup and restarting, normal login appears and existing configuration remains.

**Source:** [SetupWizard](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/jenkins/install/SetupWizard.java), [InstallState](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/jenkins/install/InstallState.java).


### F02 — Job lifecycle

**Build requirements:** Create, configure, copy, rename, disable, enable, and delete freestyle jobs. Store name, display name, description, build configuration, and history. Validate names and enforce operation-specific permissions.

**Acceptance:** Create and copy a job, disable it to prevent execution, re-enable it, rename it, and verify configuration survives restart.

**Source:** [FreeStyleProject](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/model/FreeStyleProject.java), [AbstractItem](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/model/AbstractItem.java), [Job](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/model/Job.java).


### F03 — Parameterized builds

**Build requirements:** Support string, multiline text, boolean, choice, password, uploaded-file, and build-reference parameter definitions. Show defaults and descriptions, collect values at scheduling time, and make supported values available to execution. Treat password inputs as sensitive; a password parameter is not a full credentials vault.

**Acceptance:** A parameterized job receives the selected values, preserves their association with its run, and rejects invalid choices.

**Source:** [ParametersDefinitionProperty](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/model/ParametersDefinitionProperty.java), [StringParameterDefinition](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/model/StringParameterDefinition.java), [TextParameterDefinition](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/model/TextParameterDefinition.java), [BooleanParameterDefinition](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/model/BooleanParameterDefinition.java), [ChoiceParameterDefinition](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/model/ChoiceParameterDefinition.java), [PasswordParameterDefinition](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/model/PasswordParameterDefinition.java), [FileParameterDefinition](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/model/FileParameterDefinition.java), [RunParameterDefinition](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/model/RunParameterDefinition.java).


### F04 — Build initiation and scheduling

**Build requirements:** Support manual and authenticated remote builds, cron-like schedules including Jenkins hashed H notation, SCM polling hooks, and upstream/downstream build triggers with result thresholds. Record the triggering cause and apply configurable quiet periods. SCM polling requires an SCM implementation.

**Acceptance:** Manual, timer, and upstream completion triggers each enqueue a run with the correct cause; a quiet period delays dispatch.

**Source:** [TimerTrigger](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/triggers/TimerTrigger.java), [SCMTrigger](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/triggers/SCMTrigger.java), [CronTab](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/scheduler/CronTab.java), [BuildTrigger](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/tasks/BuildTrigger.java), [ReverseBuildTrigger](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/jenkins/triggers/ReverseBuildTrigger.java).


### F05 — Queue and concurrency

**Build requirements:** Implement waiting, blocked, buildable, and assigned work handling. Report why work cannot run. Respect available executors, node labels, offline nodes, job concurrency settings, and upstream/downstream blocking settings. Permit authorized queue cancellation and preserve queued work across normal restart.

**Acceptance:** With one executor, a second run waits; an unmatched label produces an explanation; canceled queued work never starts.

**Source:** [Queue](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/model/Queue.java), [Executor](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/model/Executor.java), [AbstractProject](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/model/AbstractProject.java), [LoadBalancer](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/model/LoadBalancer.java).


### F06 — Build execution

**Build requirements:** Execute ordered freestyle build steps in a workspace: Unix shell, Windows batch, and Maven invocation. Supply build environment and parameters. Support build wrappers and post-build publisher extension points, process exit handling, and authorized stop/cancel actions. Maven invocation here is distinct from the external Maven project-type plugin.

**Acceptance:** Run two ordered commands, capture their output, turn a failing command into a failed result, and stop a long-running build.

**Source:** [AbstractBuild](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/model/AbstractBuild.java), [FreeStyleBuild](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/model/FreeStyleBuild.java), [Shell](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/tasks/Shell.java), [BatchFile](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/tasks/BatchFile.java), [Maven](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/tasks/Maven.java), [BuildWrapper](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/tasks/BuildWrapper.java), [Publisher](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/tasks/Publisher.java).


### F07 — Run records and results

**Build requirements:** Persist build numbers, timestamps, durations, causes, descriptions, display names, assigned execution context, and results. Represent SUCCESS, UNSTABLE, FAILURE, NOT_BUILT, and ABORTED separately from running/queued lifecycle state. Provide history, individual run pages, and last-build/last-success style permalinks.

**Acceptance:** Completed runs remain browsable after restart; aborted and failed results differ; last-success resolves to the latest successful run.

**Source:** [Run](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/model/Run.java), [Result](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/model/Result.java), [Cause](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/model/Cause.java), [PermalinkProjectAction](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/model/PermalinkProjectAction.java).


### F08 — Live console output

**Build requirements:** Provide incremental console output while a build runs, plain-text download, persisted completed logs, and an annotation extension mechanism. Read large logs incrementally instead of loading the full file for every refresh.

**Acceptance:** A running command becomes visible before completion; subsequent reads continue from an offset without duplicating output.

**Source:** [Run](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/model/Run.java), [AnnotatedLargeText](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/console/AnnotatedLargeText.java), [ConsoleAnnotator](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/console/ConsoleAnnotator.java).


### F09 — Workspaces

**Build requirements:** Allocate workspaces on the execution node, avoid collisions between concurrent runs, browse authorized workspace files, support workspace cleanup, and abstract local/remote filesystem operations. Prevent path traversal and enforce access checks.

**Acceptance:** Concurrent runs do not overwrite each other; authorized users can browse files; traversal outside the allowed root fails.

**Source:** [DirectoryBrowserSupport](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/model/DirectoryBrowserSupport.java), [WorkspaceList](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/slaves/WorkspaceList.java), [WorkspaceCleanupThread](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/model/WorkspaceCleanupThread.java), [FilePath](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/FilePath.java).


### F10 — Artifact archiving

**Build requirements:** Archive selected workspace files using include/exclude patterns. Expose downloadable artifacts on run pages. Support empty-archive behavior, success-only archiving, default excludes, case sensitivity, symlink behavior, and optional fingerprinting. Provide an artifact-storage extension point.

**Acceptance:** A build archives matching output files, excludes unwanted files, and retains downloads after its workspace is removed.

**Source:** [ArtifactArchiver](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/tasks/ArtifactArchiver.java), [ArtifactManager](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/jenkins/model/ArtifactManager.java), [StandardArtifactManager](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/jenkins/model/StandardArtifactManager.java).


### F11 — Artifact fingerprint tracking

**Build requirements:** Track file fingerprints and build usage/origin relationships. Show which builds produced or used tracked files and maintain fingerprint records with cleanup. Treat fingerprints as lineage identifiers rather than cryptographic authenticity guarantees.

**Acceptance:** Two builds using the same tracked file can be connected through a fingerprint record.

**Source:** [Fingerprinter](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/tasks/Fingerprinter.java), [Fingerprint](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/model/Fingerprint.java), [FingerprintMap](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/model/FingerprintMap.java).


### F12 — Build retention

**Build requirements:** Configure history retention by age and count, with separate limits for artifacts. Allow users to keep individual runs. Respect running builds and applicable last-success/last-stable preservation rules; expose the option that changes last-build preservation.

**Acceptance:** Retention removes eligible old records/artifacts while keeping a run marked for retention and leaving active work intact.

**Source:** [LogRotator](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/tasks/LogRotator.java), [BuildDiscarder](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/jenkins/model/BuildDiscarder.java), [Run](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/model/Run.java).


### F13 — Nodes and agents

**Build requirements:** Manage permanent agent definitions, remote filesystem roots, executor counts, labels and label expressions, node usage mode, launch configuration, environment properties, and retention strategies. Support inbound agents over supported TCP/WebSocket transports. Show connection state/logs and permit connect, disconnect, and temporary-offline actions. Actual remoting uses a separate Jenkins dependency.

**Acceptance:** A labeled job runs on a matching online agent; taking that agent offline stops new assignments and displays the offline reason.

**Source:** [Node](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/model/Node.java), [Computer](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/model/Computer.java), [DumbSlave](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/slaves/DumbSlave.java), [JNLPLauncher](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/slaves/JNLPLauncher.java), [RetentionStrategy](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/slaves/RetentionStrategy.java).


### F14 — Agent health and capacity

**Build requirements:** Display disk, temporary storage, swap, response time, clock, and architecture information through node monitors. Show executor/load statistics. Support monitor-driven offline handling and cloud provisioning extension points; cloud-provider implementations are separate.

**Acceptance:** A simulated low-disk condition is visible and can make a node unavailable according to configuration; executor occupancy reflects active runs.

**Source:** [DiskSpaceMonitor](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/node_monitors/DiskSpaceMonitor.java), [TemporarySpaceMonitor](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/node_monitors/TemporarySpaceMonitor.java), [SwapSpaceMonitor](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/node_monitors/SwapSpaceMonitor.java), [ClockMonitor](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/node_monitors/ClockMonitor.java), [ResponseTimeMonitor](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/node_monitors/ResponseTimeMonitor.java), [LoadStatistics](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/model/LoadStatistics.java), [NodeProvisioner](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/slaves/NodeProvisioner.java), [Cloud](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/slaves/Cloud.java).


### F15 — Dashboard, views, and search

**Build requirements:** Provide an all-jobs dashboard, configurable list views, personal views, job selection/filtering, and extensible columns. Show status, health, recent success/failure, duration, queue, and executor activity. Support object search and suggestions plus available build-history feeds.

**Acceptance:** Create a filtered view and verify its jobs and columns; search finds an authorized job; restricted objects are not exposed.

**Source:** [ListView](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/model/ListView.java), [AllView](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/model/AllView.java), [MyView](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/model/MyView.java), [MyViewsProperty](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/model/MyViewsProperty.java), [ListViewColumn](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/views/ListViewColumn.java), [Search](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/search/Search.java).


### F16 — Users and authentication

**Build requirements:** Provide user profiles, local account authentication, configurable signup behavior, user properties, and extensible security realms. Let users manage named API tokens, including generation, rename, and revocation. External identity-provider implementations remain adapters/plugins.

**Acceptance:** A user logs in and uses a token for an authorized API call; revoking the token immediately prevents subsequent authentication.

**Source:** [User](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/model/User.java), [HudsonPrivateSecurityRealm](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/security/HudsonPrivateSecurityRealm.java), [SecurityRealm](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/security/SecurityRealm.java), [ApiTokenProperty](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/jenkins/security/ApiTokenProperty.java).


### F17 — Authorization and web security

**Build requirements:** Enforce permissions for reading/configuring jobs, triggering/canceling builds, viewing workspaces, managing nodes, and administration. Provide authorization strategy extension points and built-in simple policies. Include CSRF protection, safe rendering/content handling, and protected secret storage mechanisms. Matrix and role-based configuration interfaces are external plugins.

**Acceptance:** A user without build permission cannot enqueue through UI or API; forbidden mutations are rejected server-side; invalid CSRF requests fail when protection applies.

**Source:** [AuthorizationStrategy](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/security/AuthorizationStrategy.java), [Permission](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/security/Permission.java), [ACL](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/security/ACL.java), [FullControlOnceLoggedInAuthorizationStrategy](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/security/FullControlOnceLoggedInAuthorizationStrategy.java), [DefaultCrumbIssuer](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/security/csrf/DefaultCrumbIssuer.java), [ResourceDomainConfiguration](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/jenkins/security/ResourceDomainConfiguration.java).


### F18 — SCM integration contracts

**Build requirements:** Provide pluggable checkout and polling operations, revision state, change-log parsing/display, repository-browser links, and checkout strategy/retry configuration. Include a no-SCM option. Do not claim native Git, GitHub pull-request discovery, or webhooks without their implementations.

**Acceptance:** A fake SCM adapter can report a change, initiate a build through polling, perform checkout, and expose a change log.

**Source:** [SCM](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/scm/SCM.java), [NullSCM](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/scm/NullSCM.java), [ChangeLogSet](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/scm/ChangeLogSet.java), [RepositoryBrowser](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/scm/RepositoryBrowser.java), [SCMCheckoutStrategy](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/jenkins/scm/SCMCheckoutStrategy.java).


### F19 — Tools and environment

**Build requirements:** Configure named tools, node-specific locations, installer extension points, archive/command-based installation, global/node environment properties, and environment filtering hooks. Resolve appropriate tool paths on each execution node.

**Acceptance:** The same job resolves a configured tool to different paths on two nodes and receives the expected node environment.

**Source:** [ToolInstallation](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/tools/ToolInstallation.java), [ToolInstaller](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/tools/ToolInstaller.java), [ZipExtractionInstaller](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/tools/ZipExtractionInstaller.java), [CommandInstaller](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/tools/CommandInstaller.java), [JDK](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/model/JDK.java), [EnvironmentVariablesNodeProperty](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/slaves/EnvironmentVariablesNodeProperty.java), [EnvVarsFilterRule](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/jenkins/tasks/filters/EnvVarsFilterRule.java).


### F20 — Plugins and update center

**Build requirements:** List installed/available plugins and updates; install plugin archives or update-center releases; resolve dependencies and version requirements; enable, disable, and uninstall where supported. Display install progress, failures, warnings, and restart requirements. Provide extension discovery, descriptors, and lifecycle hooks.

**Acceptance:** Installing a test extension exposes a new supported capability; missing/incompatible dependencies produce a clear failure; required restart is communicated.

**Source:** [PluginManager](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/PluginManager.java), [PluginWrapper](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/PluginWrapper.java), [UpdateCenter](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/model/UpdateCenter.java), [UpdateSite](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/model/UpdateSite.java), [Extension](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/Extension.java), [ExtensionPoint](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/ExtensionPoint.java).


### F21 — Remote API and CLI

**Build requirements:** Provide authenticated structured object APIs, including JSON/XML representations and supported selection/depth controls. Expose job configuration import/export and authorized build/queue/node operations. Supply CLI commands for jobs, builds, console logs, views, nodes, plugins, identity, and maintenance. Match permissions across UI/API/CLI.

**Acceptance:** Create and configure a job programmatically, start it, follow output, inspect its result, and reject the same operations for an unauthorized account.

**Source:** [Api](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/model/Api.java), [CLICommand](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/cli/CLICommand.java), [BuildCommand](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/cli/BuildCommand.java), [ConsoleCommand](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/cli/ConsoleCommand.java), [CreateJobCommand](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/cli/CreateJobCommand.java), [GetJobCommand](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/cli/GetJobCommand.java), [UpdateJobCommand](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/cli/UpdateJobCommand.java).


### F22 — Administration and maintenance

**Build requirements:** Provide system settings, server URL, proxy settings, system information, configurable log recorders, administrative warnings, configuration reload, quiet-down/cancel-quiet-down, and supported shutdown/restart/safe-restart operations. Core includes an administrator script console; keep it restricted to full administration.

**Acceptance:** Quiet-down prevents new dispatch while current work drains; canceling it resumes dispatch; configuration and completed histories survive restart.

**Source:** [Jenkins](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/jenkins/model/Jenkins.java), [LogRecorder](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/logging/LogRecorder.java), [AdministrativeMonitor](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/model/AdministrativeMonitor.java), [ProxyConfiguration](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/hudson/ProxyConfiguration.java), [SystemInfoLink](https://github.com/jenkinsci/jenkins/blob/c5f59e8b565d91ba7e9a209337a49e1fbb19f1db/core/src/main/java/jenkins/management/SystemInfoLink.java).


## Optional ecosystem features: separate implementation scope

These are useful for a full CI/CD product, but must not be represented as already implemented by this core repository. The linked projects identify the separate implementation scope; their source was not audited for this document.

| Capability | Separate project examples | Build instruction |
|---|---|---|
| Jenkinsfile pipelines, stages, parallel steps, durable workflow execution | [Pipeline](https://github.com/jenkinsci/workflow-aggregator-plugin), [Declarative Pipeline](https://github.com/jenkinsci/pipeline-model-definition-plugin) | Add a workflow engine as its own milestone; do not equate ordered freestyle steps with Pipeline compatibility. |
| Git checkout and repository credentials integration | [Git plugin](https://github.com/jenkinsci/git-plugin) | Implement a concrete SCM adapter, authentication, revision selection, and checkout failure handling. |
| Multibranch jobs and pull-request discovery | [Branch API](https://github.com/jenkinsci/branch-api-plugin), [GitHub Branch Source](https://github.com/jenkinsci/github-branch-source-plugin) | Add branch indexing, branch job lifecycle, and provider events separately. |
| Folder hierarchy | [CloudBees Folder](https://github.com/jenkinsci/cloudbees-folder-plugin) | Core item-group abstractions do not by themselves supply the familiar folder product feature. |
| Shared credential store and secret binding | [Credentials](https://github.com/jenkinsci/credentials-plugin), [Credentials Binding](https://github.com/jenkinsci/credentials-binding-plugin) | Add scopes, credential types, secure retrieval, and controlled binding separately. |
| Matrix/role-based authorization UI | [Matrix Authorization](https://github.com/jenkinsci/matrix-auth-plugin), [Role Strategy](https://github.com/jenkinsci/role-strategy-plugin) | Implement a policy provider and administration interface beyond the core simple strategies. |
| Structured test reports and trends | [JUnit](https://github.com/jenkinsci/junit-plugin) | Running a test command is core-capable; parsing test reports and displaying test history requires a publisher. |
| Email notifications | [Mailer](https://github.com/jenkinsci/mailer-plugin), [Email Extension](https://github.com/jenkinsci/email-ext-plugin) | Add delivery settings, recipient rules, templates, and result-based triggers. |
| Kubernetes provisioning and container workflows | [Kubernetes](https://github.com/jenkinsci/kubernetes-plugin), [Docker Pipeline](https://github.com/jenkinsci/docker-workflow-plugin) | Implement concrete provisioning/execution adapters and cleanup; core Cloud is an extension contract. |
| YAML configuration as code | [Configuration as Code](https://github.com/jenkinsci/configuration-as-code-plugin) | Add declarative import/export and validation separately from core persisted configuration. |
| Maven-specific project type | [Maven Integration](https://github.com/jenkinsci/maven-plugin) | Distinguish its project/reporting model from core's Maven build-step invocation. |
| Deployment, chat notifications, code-quality reports | Provider-specific integrations | Shell commands can invoke external tools; dedicated integrations and rich reporting require more implementation. |

## Required product screens

1. Setup and sign-in: unlock, administrator creation, server configuration, login, profile, API tokens.
2. Dashboard: views, job status/health, recent activity, queue, executor activity, search.
3. Job creation/configuration: general settings, parameters, execution node, concurrency, triggers, SCM adapter, steps, publishers, retention.
4. Job detail: run action, enable/disable, configuration access, build history, workspace, dependency information.
5. Run detail: status, cause, timing, parameters, console, artifacts, fingerprint relationships, description, keep/delete/stop actions.
6. Nodes: agent list, configuration, labels, capacity, connection logs, health, offline controls.
7. Administration: security, tools, plugins, system settings/info/logs, warnings, reload and maintenance controls.

These screens are a proposed organization of the verified capabilities, not a pixel-accurate reconstruction of every Jenkins page. Include loading, empty, validation, forbidden, offline, and failure states.

## Suggested domain model

This is a design aid for the new implementation, not Jenkins' literal storage schema.

| Entity | Essential information |
|---|---|
| User / Token / Policy | Identity, password hash or identity-provider link, token metadata/hash, permissions. |
| Job | Name, type, description, enabled state, parameters, steps, triggers, node requirements, concurrency and retention policy. |
| QueueItem | Job reference, parameter values, trigger cause, enqueue/eligible times, blockage reason, assignment. |
| Run | Job, build number, queue reference, lifecycle state, result, times, node/workspace, log reference, retention flag. |
| Node / Executor | Agent identity, labels, root directory, capacity, connection/offline state, current assignment. |
| Artifact / Fingerprint | Run, relative path, storage reference, size, fingerprint, usage relationships. |
| View | Owner or global scope, job selection/filter rules, display columns. |
| Trigger / Dependency | Schedule or upstream relationship, condition, associated job. |
| Tool / Plugin / SystemConfiguration | Tool locations, extension identity/version/dependencies, global configuration. |

Keep mutable queue state separate from durable completed run history. Distinguish a queue ID from a per-job build number. Store large logs/artifacts outside small metadata records. Design atomic state transitions so two workers cannot claim the same queue item.

## Suggested implementation phases

### Phase 1 — Working single-worker core

Deliver F01–F03, essential F05–F09, basic F15–F17, and durable configuration/history. Demonstrate login → create parameterized shell job → enqueue → execute → stream logs → inspect result → restart → inspect preserved history. Include failure and cancellation cases.

### Phase 2 — Automation and outputs

Add F04 and F10–F12, tool configuration from F19, and API/CLI essentials from F21. Demonstrate a scheduled build, upstream trigger, downloadable artifact, fingerprint relationship, retention cleanup, and authenticated programmatic execution.

### Phase 3 — Distributed execution and operations

Complete F13–F14, expand security and agent environments, and add F22. Demonstrate label-based dispatch to two workers, agent loss/offline behavior, visible queue blockage, and maintenance draining. Document what happens to running jobs if a worker or controller fails.

### Phase 4 — Extensibility and advanced UI

Complete F15 and F18–F21, including a functioning example SCM adapter and extension lifecycle. If implementing a new plugin system, label it as that; Jenkins plugin compatibility requires Jenkins' Java APIs and dependency model.

### Phase 5 — Explicitly chosen ecosystem additions

Prioritize Git, credentials, test reporting, and Pipeline/workflow support if the target product needs mainstream CI/CD workflows. These are separate deliverables and must not be counted as completed core features without working implementations.

## Cross-feature acceptance checklist

- [ ] Job configuration and completed history survive a clean restart.
- [ ] A user without permission cannot bypass UI restrictions through API or CLI.
- [ ] Parameter values remain associated with the correct queued item and run.
- [ ] Two workers never execute the same queue item simultaneously.
- [ ] Executor limits, label constraints, and nonconcurrent job settings are enforced.
- [ ] A disabled job does not start new builds.
- [ ] A canceled queue item never starts; an aborted run receives an appropriate result.
- [ ] Live logs work for large output without repeated full-file loading.
- [ ] Agent disconnection produces a visible, defined failure/blockage state.
- [ ] Artifacts remain downloadable independently of workspace lifetime until retention removes them.
- [ ] Retention preserves explicitly kept and currently running builds.
- [ ] Workspace/artifact downloads cannot escape their permitted paths.
- [ ] Revoked API tokens no longer authenticate.
- [ ] Maintenance draining allows active work to finish and prevents new dispatch.
- [ ] Plugin/adapter failures are visible and do not silently report successful work.
- [ ] Optional ecosystem features are reported honestly as implemented, partial, or absent.

## Source review notes

The inventory was derived from the cloned Java source tree, targeted implementation reads, API/method inspection, and repository structure. Source links are pinned to the reviewed commit so later changes to master do not change the reference. Core also contains compatibility code, extension plumbing, internationalized resources, and implementation utilities beyond this product-level inventory.

The repository contains relevant tests including `test/src/test/java/hudson/model/QueueTest.java`, `hudson/model/FreeStyleProjectTest.java`, `hudson/model/ListViewTest.java`, `hudson/tasks/ArtifactArchiverTest.java`, `hudson/tasks/LogRotatorTest.java`, `hudson/cli/BuildCommandTest.java`, and `jenkins/security/ApiTokenPropertyTest.java` (the latter six paths are relative to `test/src/test/java/`). These are useful starting points for a deeper behavior audit; their presence is not a claim that they were executed here.
