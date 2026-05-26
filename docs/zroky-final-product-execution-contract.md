# Zroky Final Product Execution Contract

Date: 2026-05-24

Role assigned for this audit: Principal Product Architect plus Production Systems Engineer.

This document is the final build contract for turning the current Zroky repo into a production-grade product that a team building complex AI agents can run directly, trust in production, and use daily without reading raw traces first.

## 1. Final Product Definition

Zroky is not a generic observability dashboard. Zroky is the production reliability loop for AI agents:

1. Capture every model, tool, retrieval, memory, and outcome event.
2. Group raw telemetry into plain-English Issues.
3. Diagnose root cause with evidence.
4. Create replay from an Issue, Trace, or Call.
5. Verify fixes with replay modes that are honest about their proof level.
6. Promote proven traces into Goldens.
7. Block risky deploys in CI.
8. Monitor post-deploy recurrence and auto-resolve when stable.

The user should not think "I have 50,000 traces." The user should think "These are the top 5 production problems my agents have, here is the evidence, here is the safest next action, and here is whether the fix is verified."

## 2. Current Audit Verdict

The current repo has a strong engine and the core local product loop is now code-level verified.

Bold items in this document are the implementation or verification scope. Non-bold text is context, product intent, or explanation.

Strong:

1. JS SDK contract tests pass.
2. JS SDK has durable browser and Node buffering.
3. Backend capture health exists and detects missing tool spans, missing outcomes, and missing prompt versions.
4. Issues API already exposes severity, impact, evidence, replay coverage, and recommended next action.
5. Replay from call and issue exists.
6. Replay detail surfaces verified_fix, output diff, tool behavior diff, cost delta, and latency delta.
7. Agent reliability backend exists.
8. Goldens backend and dashboard page exist.
9. Ask Zroky exists with evidence-oriented answers.

Resolved in current branch:

1. Gateway Go tests pass, including `internal/proxy`.
2. Local Python runtime and backend virtual environment are usable.
3. Full no-Docker capture E2E passes.
4. ClickHouse sync reads token, cost, status, and error fields from `Call` columns.
5. Dashboard primary nav exposes Agents, Issues, Replay, Goldens, Drift, Calls, Cost, Alerts, and Settings.
6. Customer-facing product wording uses Issues; `/v1/issues` is backed by the canonical problem model.
7. API contract has no `MagicMock`, `Magicmock`, or fake-summary leakage.
8. Core CI gates are strict; optional benchmark and chaos jobs remain intentionally non-blocking.
9. Repo-local binaries/generated artifacts were removed and ignored.

Still not proven until external production smoke runs:

1. Managed Postgres and Redis boot with production secrets.
2. Real provider proxy traffic flows through the deployed gateway.
3. Fresh signup can create a project/key and capture the first production event.
4. Issue -> replay -> golden -> CI proof works against deployed services.

## 2.1 Bold Action Scope

These items are the implementation and verification scope. Resolved items remain listed for audit traceability; unresolved items must stay bold until their proof gate is green.

1. **Repair Python runtime and recreate the backend virtual environment.**
2. **Fix Gateway Go `internal/proxy` test failures.**
3. **Run and pass no-Docker capture smoke.**
4. **Run and pass full no-Docker capture E2E.**
5. **Fix ClickHouse sync field mapping from `Call` columns.**
6. **Clean dirty tree without reverting real product work.**
7. **Remove local binaries, installers, generated coverage, stale logs, and scratch files.**
8. **Regenerate OpenAPI and remove every `Magicmock` summary.**
9. **Make CI strict for core lint, tests, type checks, security audit, and replay honesty checks.**
10. **Add `/agents` Launchpad and make it the default product landing page.**
11. **Update dashboard primary nav to Agents, Issues, Replay, Goldens, Drift, Calls, Cost, Alerts, Settings.**
12. **Move Calibration/Judge under Settings -> Evaluation.**
13. **Keep Trace as deep-linked debug surface, not primary nav.**
14. **Merge Root Cause into Issue detail and remove standalone product dependency.**
15. **Move `/owner/*` into a separate `zroky-admin` app.**
16. **Consolidate Issue and Anomaly into one canonical backend concept while keeping `/issues` user-facing.**
17. **Align frontend replay modes with backend, including `real_llm`.**
18. **Feature-gate replay modes by proof level instead of deleting modes blindly.**
19. **Guarantee stub replay is never shown as a verified fix.**
20. **Add Promote Replay to Golden flow.**
21. **Add Issue inline CTAs: Create Replay, Assign, Accepted Risk, Resolve, Ignore/Mute, Link Deploy/PR.**
22. **Add Ask Zroky action buttons backed by real APIs.**
23. **Build Drift tabs for Provider Drift, Judge Drift, and Outcome Drift.**
24. **Use Agents first-run capture setup when no events exist.**
25. **Fix dashboard lint warnings that indicate dead code or unstable hook dependencies.**
26. **Fix file-size lint violations or split oversized backend modules.**
27. **Verify JS SDK, Python SDK, Gateway, Backend, Replay Worker, Dashboard, and Regression CI as one closed loop.**
28. **Pass the final acceptance matrix with no `fail`, `skipped`, or `not verified` items.**

## 3. Verification Snapshot

Commands run during this audit:

1. `npm.cmd test` in `zroky-sdk-js`: passed, 29 tests.
2. `npm.cmd run lint` in `zroky-dashboard`: passed with 0 errors and 26 warnings.
3. `go test ./...` in `zroky-gateway` with workspace `GOCACHE`: failed 2 proxy tests.
4. `python scripts/run_capture_smoke_no_docker.py`: could not run because `python` is not installed on PATH.
5. `py scripts/check_file_sizes.py`: could not run because `py` is not installed on PATH.
6. Direct venv Python failed: it points to missing `C:\Users\user\AppData\Local\Programs\Python\Python311\python.exe`.

Gateway failing tests:

1. `TestHandlerProxiesAndEmitsDirectHTTPBatch`: emitted event lost expected project/trace context in the test assertion.
2. `TestHandlerStreamsSSEAndEmitsCapturedTelemetry`: emitted streaming usage did not match expected total usage in the test assertion.

These failures make Gateway a P0 blocker.

## 4. Target Architecture

Final production architecture:

1. Python SDK and JS SDK emit `IngestEventV2`.
2. Gateway Go captures provider traffic and emits the same `IngestEventV2`.
3. Backend ingest writes canonical `Call` rows and linked metadata.
4. Capture health validates first-run instrumentation quality.
5. Detectors group raw calls into Issues.
6. Issues page becomes the product center.
7. Replay runs from Issue, Trace, or Call.
8. Real comparison replay can become verified; stub replay cannot.
9. Passing replay traces can be promoted to Goldens.
10. Regression CI runs Goldens on PR/deploy and posts pass/fail evidence.
11. Drift monitors provider, judge, and outcome changes.
12. Alerts and digests notify humans.
13. Ask Zroky answers only with evidence links and action buttons.

Production services:

1. `zroky-backend`: FastAPI API and control plane.
2. `zroky-dashboard`: customer dashboard.
3. `zroky-gateway`: standalone Go proxy/capture service.
4. `zroky-sdk`: Python SDK.
5. `zroky-sdk-js`: JS/TS SDK.
6. `zroky-replay-worker`: real replay executor.
7. `zroky-regression-ci-action`: GitHub CI gate.
8. Postgres: canonical transactional store.
9. Redis: queues, stream consumer, cache, Celery broker.
10. ClickHouse: optional analytics acceleration, only after sync is fixed.

No-Docker stance:

1. Docker is not required for local verification.
2. Production can run on managed Postgres, managed Redis, managed ClickHouse, Railway/Fly/Render services, and Vercel/Railway dashboard.
3. Gateway should build into a normal Go binary.
4. Replay sandbox mode must use an external sandbox worker URL when Docker is unavailable.

## 5. Final Dashboard Information Architecture

Default landing should become `/agents`, not `/home`.

Primary nav:

1. Agents
2. Issues
3. Replay
4. Goldens
5. Drift
6. Calls
7. Cost
8. Alerts
9. Settings

Secondary or hidden routes:

1. `/home`: keep as Command Center, but not default.
2. `/trace`: keep deep-linked from Calls and Issues, not primary nav.
3. `/calibration`: move under Settings -> Evaluation.
4. `/reliability`: merge into `/agents` or keep as an advanced subpage.
5. `/outcomes`: fold into Cost and Issue impact unless a paid reporting module needs it.
6. `/root-cause`: merge into Issue Detail and remove as a standalone product route.
7. `/judge`: keep redirect only, or replace with Settings -> Evaluation.
8. `/owner/*`: move to separate `zroky-admin` app.

## 6. Dashboard Modules, Exact Behavior

### 6.1 Agents Launchpad

Route: `/agents`

Purpose: simple first screen for vibe-coding developers and agent teams.

Show one row per agent:

1. Agent name.
2. Health pill.
3. Success rate.
4. Cost per successful task.
5. Replay coverage percent.
6. Latest open Issue title.
7. Last deploy impact.
8. Last event time.
9. Recommended next action.

Actions:

1. Open Issues for this agent.
2. Create Replay for latest failing trace.
3. View Calls.
4. View Trace tree.
5. Generate Fix Queue recommendation.

Do not show:

1. Raw JSON.
2. Full trace tables.
3. Internal detector names as the primary label.

Backend data:

1. `/v1/reliability/leaderboard`
2. `/v1/reliability/summary`
3. `/v1/issues?agent_name=...`
4. `/v1/capture/health`

Required backend addition:

1. A compact `/v1/agents/launchpad` endpoint can reduce frontend fan-out. It should join reliability, latest Issue, replay coverage, and recent Call data.

### 6.2 Issues

Route: `/issues`

Purpose: product center. Raw telemetry is converted into grouped production problems.

List view must show:

1. Plain-English title.
2. Severity.
3. Affected agent.
4. Affected workflow.
5. Root cause summary.
6. Evidence trace count.
7. Cost impact.
8. User/outcome impact.
9. Replay coverage status.
10. Recommended next action.

Inline actions:

1. Create Replay.
2. Assign owner.
3. Mark accepted risk.
4. Resolve.
5. Ignore or mute.
6. Link deploy or PR.

Detail view must show:

1. Root cause.
2. Evidence traces.
3. Impact.
4. Suggested fix path.
5. Replay coverage.
6. Create Replay with mode selector.
7. Related Calls and Trace tree.
8. Ask Zroky question scoped to this Issue.

Do not show:

1. "Detector enum" as the main user-facing title.
2. Raw payload first.
3. Stub replay as verified.

Current state:

1. `/v1/issues` already has product-level response fields.
2. `/v1/anomalies` is canonical in comments, while `/v1/issues` is legacy.
3. Final product should pick one canonical internal model but keep `/issues` as the user-facing route.

### 6.3 Replay

Route: `/replay`

Purpose: proof engine.

List view must show:

1. Run status.
2. Replay mode.
3. Source: Issue, Trace, Call, Golden, CI.
4. Verification status.
5. Pass/fail/error counts.
6. Cost delta.
7. Latency delta.
8. Created by.
9. Linked PR/deploy.

Detail view must show:

1. Reproduced original failure: yes/no/unknown.
2. Fix passed: yes/no/unknown.
3. Verified fix: yes/no.
4. Output diff.
5. Tool behavior diff.
6. Cost delta.
7. Latency delta.
8. Replay mode warning.
9. Promote to Golden button.

Replay modes:

1. `stub`: cheap sanity check only. Never verified.
2. `real_llm`: real model comparison. Can be verified if comparison evidence exists.
3. `mocked-tool`: real model with frozen captured tool outputs. Can be verified only if tool snapshots exist.
4. `live-sandbox`: real model plus sandbox tool runtime. Enabled only when sandbox worker is configured.
5. `shadow`: candidate config side-by-side. Not a verified fix unless full baseline/candidate comparison exists.

Do not remove replay modes blindly. Instead, feature-gate each mode and show its availability and proof level.

Current gap:

1. UI type `ReplayMode` is missing `real_llm`; backend supports it. Align frontend type and mode selector.
2. Replay detail does not yet have a visible Promote to Golden button.

### 6.4 Goldens

Route: `/goldens`

Purpose: production memory.

Show:

1. Golden sets.
2. Trace count.
3. Owner.
4. Last run.
5. Pass/fail trend.
6. Critical release-blocking flag.
7. Flaky status.
8. Coverage by agent/workflow.

Actions:

1. Create Golden Set.
2. Add trace from Call, Issue, Replay.
3. Run Golden Set.
4. Mark flaky.
5. Promote replay trace to Golden.
6. Open CI history.

Do not show:

1. Calibration-specific UI as the default Goldens experience.
2. Raw golden trace IDs as the primary content.

Current state:

1. Backend `/v1/goldens` exists.
2. Dashboard `/goldens` exists but is not in primary nav.

### 6.5 Drift

Route: `/drift`

Purpose: detect model/provider/judge/outcome shifts.

Tabs:

1. Provider Drift: model behavior, latency, cost, output length, schema failures.
2. Judge Drift: judge calibration, verdict drift, dimension drift.
3. Outcome Drift: business outcome success, retries, refund/failure costs.

Show:

1. Breached dimension.
2. Baseline vs current.
3. Affected agents/workflows.
4. Evidence traces.
5. Recommended next action.
6. Replay or Golden to run.

Current state:

1. Dashboard `/drift` currently focuses heavily on judge health.
2. Provider drift backend exists.
3. Outcome backend exists.
4. UI should merge them coherently.

### 6.6 Calls

Route: `/calls`

Purpose: raw debug and export, not the main product.

Show:

1. Filterable calls table.
2. Provider, model, agent, user, type, status, tokens, cost, latency.
3. Export CSV/JSON.
4. Row detail with payload, output, trace tree, replay button.

Do not show Calls before Issues in the main user journey.

### 6.7 Cost

Route: `/cost`

Purpose: cost per outcome and waste reduction.

Show:

1. Spend trend.
2. Cost by model/provider/agent.
3. Cost per successful task.
4. Cost by failure/outcome.
5. Wasted cost from failed retries.
6. What-if calculator.
7. Top expensive calls.

Fold `/outcomes` into this route unless a separate reporting module is justified.

### 6.8 Alerts

Route: `/alerts`

Purpose: human notification workflow.

Show:

1. Alerts queue.
2. Severity.
3. Category.
4. Status.
5. Linked Issue/Call/Replay.
6. Channel delivery state.
7. Ack/resolve/reopen.

Do not re-add a top-level notification bell until there is a complete notification center.

### 6.9 Settings

Route: `/settings`

Sections:

1. Project.
2. API keys.
3. Provider keys.
4. Gateway.
5. Team.
6. Integrations.
7. Notifications.
8. PII and retention.
9. Billing.
10. Evaluation: Judge and Calibration.
11. Advanced: rollback drill, pricing validation, internal diagnostics.

Remove from primary nav:

1. Calibration.
2. Judge.
3. Owner.

### 6.10 Ask Zroky

Keep as floating assistant.

Must do:

1. Answer only from evidence.
2. Say "not enough data" when evidence is missing.
3. Show evidence links.
4. Convert suggested actions into buttons:
   - Create Replay
   - Open Issue
   - Promote Golden
   - Open Call
   - Open Trace
   - Assign owner

Do not let it invent root causes without evidence.

### 6.11 First-Run Capture Setup

This is mandatory for vibe-coding developers.

Show on `/agents` and `/home` when no data exists:

1. Pick capture method: JS SDK, Python SDK, Gateway.
2. Copy install command.
3. Copy minimal code snippet.
4. Run no-Docker smoke check.
5. Show last event.
6. Show validation warnings:
   - Tool spans missing
   - Outcome missing
   - Prompt version missing
7. Open last captured Call.

Current state:

1. Backend `/v1/capture/health` exists.
2. `CaptureConnectPanel` exists and already displays validation warnings.
3. This must become the default empty state in `/agents`.

## 7. Codebase Keep, Remove, Move

### Keep

1. `zroky-backend`
2. `zroky-dashboard`
3. `zroky-gateway`
4. `zroky-sdk`
5. `zroky-sdk-js`
6. `zroky-replay-worker`
7. `zroky-regression-ci-action`
8. `api-contracts`, after regeneration
9. `scripts/run_capture_smoke_no_docker.py`
10. `scripts/run_capture_e2e_local.py`
11. `docs/zroky-exact-product-blueprint.md`
12. `docs/zroky-build-operating-protocol.md`

### Remove from repo root

These are local artifacts and should not live in product source:

1. `DockerDesktopInstaller.exe`
2. `jenkins.war`
3. `docfx_new.zip`
4. `sentry-cli.exe`
5. `_patch_models.py`
6. `progress.txt`
7. `claude-code-page.md`
8. `claude-code-readme.txt`
9. `claude-code-snapshot.txt`

### Remove generated artifacts

1. `zroky-regression-ci-action/coverage`
2. `zroky-dashboard/lint_output.txt`
3. `zroky-backend/test_results.txt`
4. Any generated `.gocache`, `.next`, `.pytest_cache`, `node_modules`, and coverage reports from git tracking.

### Remove vendored binaries

1. `prometheus/prometheus-3.1.0.windows-amd64/prometheus.exe`
2. `prometheus/prometheus-3.1.0.windows-amd64/promtool.exe`

Keep only:

1. Prometheus config.
2. Alert rules.
3. Grafana dashboards.

### Rewrite or supersede stale docs

1. `docs/dashboard-build-contract.md` is stale because it locks V1 to 5 pages and says no multi-agent UI. Final product now needs Agents, Issues, Replay, Goldens, Drift, Calls, Cost, Alerts, Settings.
2. Replace it with a short pointer to this document and the blueprint, or rewrite it fully.

### Regenerate API contract

1. `api-contracts/zroky-api-v1.openapi.json` has no `MagicMock`, `Magicmock`, or fake-summary leakage.
2. Regenerate it only through the real FastAPI export path.
3. CI fails if `MagicMock`, `Magicmock`, or fake-summary text appears again.

### Dirty tree cleanup protocol

Current state: the repo has product changes, generated files, local binaries, stale docs, and broken verification environment mixed in one dirty worktree. Do not fix this with `git reset` or broad revert. The cleanup must preserve real product work and remove only proven junk/generated artifacts.

Required cleanup order:

1. Create a safety branch before any cleanup, for example `codex/stabilize-dirty-tree`.
2. Do not revert user changes unless the user explicitly asks.
3. Remove only local/generated artifacts first.
4. Split real product changes into reviewable buckets.
5. Fix broken verification gates.
6. Commit or stage only coherent buckets.

Cleanup buckets:

1. Capture layer: Python SDK, JS SDK, Gateway, backend ingest, capture health.
2. Replay layer: replay run API, replay executor, replay worker, replay dashboard, replay tests.
3. Issues product object: issues API, issue grouping, issue detail UI, issue CTAs.
4. Dashboard IA: shell nav, Agents Launchpad, Home, Calls, Goldens, Drift, Alerts, Settings.
5. Digest cleanup: weekly impact removal, digest engine, digest routes, worker tasks.
6. Docs/contracts: blueprint, operating protocol, final execution contract.
7. Repo hygiene: `.gitignore`, generated coverage removal, stale logs, large binary removal.

Files to remove or untrack before product work continues:

1. Root local binaries/installers: `DockerDesktopInstaller.exe`, `jenkins.war`, `docfx_new.zip`, `sentry-cli.exe`.
2. Root scratch files: `_patch_models.py`, `claude-code-page.md`, `claude-code-readme.txt`, `claude-code-snapshot.txt`.
3. Generated reports: `zroky-regression-ci-action/coverage`, `zroky-dashboard/lint_output.txt`, `zroky-backend/test_results.txt`.
4. Cache/build directories: `.gocache`, `.next`, `.pytest_cache`, `node_modules`, coverage reports.

Real product files must be kept and verified, not deleted:

1. New capture routes/services/tests.
2. New Ask Zroky service/UI.
3. New replay run capability and tests.
4. Gateway tests and gateway capture changes.
5. SDK durable buffer and contract tests.
6. Final docs in `docs/`.

Line-ending and formatting rule:

1. Add or confirm `.gitattributes` rules so code files use consistent LF.
2. Do not accept large diffs caused only by CRLF/LF churn.
3. Formatting-only changes must be isolated from behavior changes.

Dirty tree is considered clean only when:

1. `git status --short` contains only intentional product files.
2. Generated artifacts and local binaries are gone or ignored.
3. `npm.cmd test` passes in `zroky-sdk-js`.
4. `npm.cmd run lint` passes in `zroky-dashboard`.
5. `go test ./...` passes in `zroky-gateway`.
6. Backend focused tests pass after Python runtime is repaired.
7. No-Docker capture smoke passes.

### Move admin out

Move:

1. `zroky-dashboard/src/app/owner/*`

To:

1. `zroky-admin`

Then:

1. Set `FEATURE_LEGACY_OWNER=false` in production.
2. Keep owner APIs only for the admin app.
3. Do not ship founder/admin pages inside customer dashboard or OSS dashboard.

### Consolidate models/routes

Issue and Anomaly must become one canonical internal concept.

Recommended final shape:

1. User-facing route remains `/issues`.
2. Backend canonical model can be `Anomaly` or `Issue`, but not both long term.
3. Keep legacy aliases for one release only.
4. Migrate UI to one API surface.
5. Add a deprecation test that prevents new code from using the old route after migration.

### Legacy replay surface

Current:

1. `/v1/replay/jobs` legacy single-fix replay.
2. `/v1/replay/runs` modern replay run surface.

Final:

1. Dashboard should use `/v1/replay/runs`.
2. Legacy jobs route should be retained only if existing SDKs or customers use it.
3. Otherwise deprecate and remove after migration.

## 8. P0 Fixes Before Product Can Be Called Production-Ready

### P0.1 Repair Python runtime

Required:

1. Install Python 3.11 or 3.12.
2. Put `python` on PATH or update all scripts to use a repo-local configured interpreter.
3. Recreate `zroky-backend/.venv`.
4. Verify:
   - `python --version`
   - `python -m pytest --collect-only -q`
   - `python scripts/run_capture_smoke_no_docker.py`

Without this, backend tests and no-Docker E2E cannot be trusted.

### P0.2 Fix Gateway tests

Required:

1. Fix emitted event context in direct HTTP batch path.
2. Fix SSE usage extraction/total token emission.
3. Ensure gateway emits canonical fields:
   - project_id
   - call_id
   - trace_id
   - parent_call_id
   - agent_name
   - workflow_name
   - prompt_version
   - model
   - provider
   - prompt_tokens
   - completion_tokens
   - total_tokens
   - tool_calls
   - outcome
4. Verify `go test ./...` passes.

### P0.3 Run no-Docker capture E2E

Required:

1. `scripts/run_capture_e2e_local.py` must pass.
2. It must verify SDK/Gateway -> backend ingest -> persisted Call -> capture health.
3. This becomes the daily local smoke check.

### P0.4 Fix ClickHouse sync

Current bug:

1. `clickhouse_sync.py` reads usage from `payload_json["usage"]`.
2. It also references `call.cost_usd`, `call.status_code`, and `call.failure_code`, but the `Call` model has `cost_total`, `status`, and `error_code`.

Required:

1. Use `Call.input_tokens`.
2. Use `Call.output_tokens`.
3. Use `Call.total_tokens`.
4. Use `Call.cost_total`.
5. Use `Call.status`.
6. Use `Call.error_code`.
7. Put `status_code` in metadata only if available.
8. Add a unit test with empty `payload_json`.

### P0.5 Clean repo artifacts

Required:

1. Remove local binaries.
2. Remove generated coverage.
3. Remove stale logs.
4. Update `.gitignore`.
5. Keep repo small enough for normal clone and CI.

### P0.6 Make CI strict

Current verification:

1. Backend `mypy` and `pip-audit` gates in `.github/workflows/ci.yml` fail the build.
2. Backend `mypy` and security-audit gates in `.github/workflows/zroky-backend-ci.yml` fail the build.
3. Core static guards no longer use `|| true`; they explicitly distinguish "no matches" from scan failure.
4. `|| true` remains only in optional benchmark/chaos flows, where non-blocking behavior is intentional.

Required:

1. Core lint/test/type/security gates fail the build.
2. Experimental benchmark/chaos jobs can remain non-blocking.
3. Replay honesty lint must fail on user-facing verified claims without real comparison.

## 9. Execution Roadmap

### Phase 0: Stabilize the repo and runtime

Goal: make verification reliable.

Tasks:

1. Repair Python runtime.
2. Remove local binaries/generated artifacts.
3. Fix gateway tests.
4. Fix ClickHouse sync.
5. Regenerate OpenAPI.
6. Make CI strict for core paths.
7. Run no-Docker capture E2E.

Exit criteria:

1. JS SDK tests pass.
2. Gateway tests pass.
3. Backend collect-only passes.
4. Focused backend capture/replay/issues tests pass.
5. Dashboard lint has 0 errors.
6. No-Docker capture smoke passes.

### Phase 1: Build the product dashboard loop

Goal: user sees the closed loop without knowing internals.

Tasks:

1. Add `/agents` Launchpad.
2. Make `/agents` default landing.
3. Update primary nav.
4. Move Calibration under Settings.
5. Hide Trace from primary nav.
6. Put Goldens, Drift, Calls, Alerts into nav.
7. Add first-run capture setup to Agents.
8. Add issue inline CTAs.
9. Add Promote to Golden on Replay detail.
10. Add Ask Zroky action buttons.

Exit criteria:

1. A new user can connect SDK/Gateway from the dashboard.
2. A captured issue can produce replay in one click.
3. Replay result can become Golden in one click.
4. Raw calls are available but not the product center.

### Phase 2: Make Issues canonical

Goal: one product object, no duplicate mental model.

Tasks:

1. Choose canonical DB model.
2. Migrate Issue/Anomaly duplication.
3. Keep `/issues` as customer route.
4. Deprecate old route/model.
5. Add auto-resolve cron for stale non-recurring issues.
6. Add Assign and Accepted Risk fields.

Exit criteria:

1. User sees Issues only.
2. Backend has one canonical grouping pipeline.
3. Old route cannot receive new product features.

### Phase 3: Replay and Goldens hardening

Goal: no false verification.

Tasks:

1. Add `real_llm` to frontend replay mode type.
2. Show mode capability status.
3. Gate live-sandbox on sandbox worker config.
4. Gate mocked-tool on captured tool snapshots.
5. Never mark stub as verified.
6. Promote replay trace to Golden.
7. CI action runs Goldens and comments evidence.

Exit criteria:

1. Stub says sanity only.
2. Real comparison says verified only when evidence exists.
3. CI can block deploy on critical Goldens.

### Phase 4: Production operations

Goal: direct production run without Docker.

Tasks:

1. Backend service deploy.
2. Worker service deploy.
3. Beat/scheduler deploy.
4. Gateway binary deploy.
5. Replay worker deploy.
6. Dashboard deploy.
7. Managed Postgres and Redis configured.
8. ClickHouse configured only after sync test passes.
9. Health, metrics, logs, alerts configured.
10. Rollback drill verified.

Exit criteria:

1. Fresh project can capture first event.
2. Gateway can proxy real provider request.
3. Issue appears from captured failure.
4. Replay can run.
5. Golden can run.
6. Dashboard shows connected health.

### Phase 5: Admin and OSS split

Goal: customer product is clean and open-source safe.

Tasks:

1. Create `zroky-admin`.
2. Move owner pages.
3. Disable legacy owner routes for customer deploys.
4. Remove admin code from customer dashboard.
5. Prepare OSS license and publish checklist.

Exit criteria:

1. Customer dashboard has no founder/admin screens.
2. OSS repo does not leak owner operations.

## 10. Strict Build Protocol For Codex/Windsurf

Use this prompt when another agent continues the work:

```text
You are building Zroky using docs/zroky-final-product-execution-contract.md as the source of truth.

Rules:
1. Do not invent product behavior. Verify with rg and file reads before editing.
2. Do not say complete unless the relevant tests pass or you explicitly list the blocker.
3. Do not rebuild solved contract surfaces unless tests prove they are broken.
4. Keep the product loop first: Capture -> Issues -> Replay -> Goldens -> CI -> Monitor.
5. Raw Calls and Traces are debug surfaces, not the main product.
6. Stub replay is never a verified fix.
7. Before edits, state which files will change and why.
8. After edits, run the smallest relevant tests first, then broader tests.
9. Never remove user changes or unrelated dirty files.
10. For no-Docker work, use local processes and managed-service compatible configuration.

Current P0 order:
1. Repair Python runtime.
2. Fix zroky-gateway go test failures.
3. Run no-Docker capture E2E.
4. Fix ClickHouse sync field mapping.
5. Clean generated artifacts and stale binaries.
6. Update dashboard IA with Agents as default.
```

## 11. End-to-End Acceptance Testing

This is the final product acceptance script. Run it after the P0 blockers are fixed and before calling the product production-ready.

Every step has a correct expected output. If any expected output is missing, the product is not ready.

### 11.1 Runtime readiness

Command:

```powershell
python --version
npm.cmd --version
go version
```

Expected:

1. Python prints a supported version, preferably 3.11 or 3.12.
2. npm prints a version.
3. Go prints `go version go1.22.4 windows/amd64` or a compatible newer Go 1.22+ version.

Failure means:

1. Do not continue to product testing.
2. Fix local runtime first.

### 11.2 Backend health

Action:

1. Start backend.
2. Open `/api/health/live`.
3. Open `/api/health/ready`.

Expected live output:

```json
{
  "status": "ok"
}
```

Expected ready output:

1. HTTP 200 when required dependencies are configured.
2. If Redis/Postgres checks are disabled for local no-Docker mode, ready must still clearly report which checks were skipped.
3. No stack trace.

### 11.3 Signup

UI path:

1. Open dashboard.
2. Go to `/auth/register`.
3. Enter email, password, confirm password.
4. Submit.

API:

```http
POST /v1/auth/register
```

Expected HTTP status:

```text
201 Created
```

Expected response shape:

```json
{
  "access_token": "<jwt>",
  "refresh_token": "<jwt>",
  "access_expires_in_seconds": 3600,
  "refresh_expires_in_seconds": 604800,
  "token_type": "bearer",
  "user_id": "<user-id>",
  "email": "user@example.com",
  "email_verified": false
}
```

Expected database side effect:

1. A `User` row exists.
2. A default `Project` row exists with name `My Project`.
3. A `ProjectMembership` row exists with role `owner`.

Expected UI:

1. User is logged in.
2. Dashboard can load project context.
3. If email verification is enforced, UI shows a verify-email notice but does not break project setup.

Wrong output:

1. 500 error.
2. Dashboard loads without project context.
3. No default project after signup.
4. Token response missing refresh token.

### 11.4 Email verification

API:

```http
GET /v1/auth/verify-email?token=<token>
```

Expected success:

```json
{
  "detail": "Email verified successfully."
}
```

Expected repeat call:

```json
{
  "detail": "Email already verified."
}
```

Expected invalid token:

```json
{
  "detail": "Invalid or expired verification link."
}
```

Correct behavior:

1. Invalid token returns HTTP 400.
2. Valid token sets `email_verified_at`.
3. Repeated valid verification is safe and idempotent.

### 11.5 Login and session refresh

API:

```http
POST /v1/auth/login
```

Expected success:

```json
{
  "access_token": "<jwt>",
  "refresh_token": "<jwt>",
  "token_type": "bearer",
  "user_id": "<user-id>",
  "email": "user@example.com"
}
```

Expected wrong password:

```json
{
  "detail": "Invalid credentials."
}
```

API:

```http
POST /v1/auth/refresh
```

Expected:

1. New access token.
2. New refresh token.
3. Old expired/invalid refresh token is rejected.

UI expected:

1. Refresh happens silently.
2. User is not randomly logged out while using the dashboard.

### 11.6 Project and API key setup

UI path:

1. Go to Settings -> API Keys.
2. Create a key named `Production Server`.

API:

```http
POST /v1/projects/{project_id}/api-keys
```

Expected status:

```text
201 Created
```

Expected response:

```json
{
  "key_id": "<key-id>",
  "project_id": "<project-id>",
  "name": "Production Server",
  "key_prefix": "zk_...",
  "api_key": "zk_...",
  "created_at": "<iso-datetime>"
}
```

Correct behavior:

1. Raw `api_key` is shown only once.
2. List API keys later returns prefix and metadata, not the full raw secret.
3. Revoke changes `revoked` to true.

### 11.7 First-run capture setup

UI path:

1. Open `/agents`.
2. If no calls exist, first-run capture setup must appear.

Expected UI:

1. Status says `Waiting for first event` or equivalent no-data state.
2. JS SDK, Python SDK, and Gateway setup options are visible.
3. Copy buttons work.
4. Smoke-check command is visible.
5. No raw trace table is shown as the first screen.

Correct after first event:

1. Status becomes `Integration verified`.
2. Last event age is visible.
3. Last source is visible.
4. Last Call link opens `/calls/{id}`.

### 11.8 No-Docker capture smoke

Command:

```powershell
python scripts/run_capture_smoke_no_docker.py
```

Expected final line:

```text
[capture-smoke] passed: status=connected source=gateway_http_direct calls_24h=1
```

Correct behavior:

1. Backend starts locally.
2. Gateway starts locally.
3. Mock OpenAI upstream receives request.
4. Zroky internal headers do not leak upstream.
5. Backend capture health sees the gateway event.

Wrong output:

1. `capture health did not observe gateway event`.
2. `zroky headers leaked upstream`.
3. Gateway process exits early.
4. Backend process exits early.

### 11.9 Full no-Docker capture E2E

Command:

```powershell
python scripts/run_capture_e2e_local.py
```

Expected final line:

```text
[capture-e2e] All local capture checks passed.
```

Expected step outputs:

1. `[capture-e2e] passed: Gateway Go contract tests`
2. `[capture-e2e] passed: Python SDK capture context tests`
3. `[capture-e2e] passed: Backend capture ingest tests`
4. `[capture-e2e] passed: JS SDK capture tests`
5. `[capture-e2e] passed: JS SDK build`
6. `[capture-e2e] passed: JS SDK size gate`
7. `[capture-e2e] passed: Dashboard capture lint`
8. `[capture-e2e] passed: Live no-Docker capture smoke`

Failure means:

1. Product cannot be called capture-complete.
2. Fix the failed step before continuing.

### 11.10 JS SDK capture

Command:

```powershell
npm.cmd test
```

Working directory:

```text
zroky-sdk-js
```

Expected:

```text
pass 29
fail 0
```

Product-level expected behavior:

1. SDK emits backend-compatible `IngestBatchRequest`.
2. `completion_tokens` is canonical.
3. Legacy `output_tokens` is converted.
4. `tool_calls_made` is converted to `tool_calls`.
5. Browser buffered events survive reload.
6. Node buffered events survive restart.
7. `outcome()` posts to API base correctly.

### 11.11 Gateway capture

Command:

```powershell
$env:GOCACHE='D:\Zroky AI\zroky-gateway\.gocache'
go test ./...
```

Working directory:

```text
zroky-gateway
```

Expected:

```text
ok  	github.com/zroky-ai/zroky-gateway/internal/config
ok  	github.com/zroky-ai/zroky-gateway/internal/emit
ok  	github.com/zroky-ai/zroky-gateway/internal/proxy
```

Gateway event expected fields:

```json
{
  "schema_version": "v2",
  "project_id": "proj_gateway",
  "call_id": "call_gateway",
  "trace_id": "trace_gateway",
  "agent_name": "planner",
  "workflow_name": "support-resolution",
  "prompt_version": "support-v42",
  "provider": "openai",
  "model": "gpt-4o-mini",
  "prompt_tokens": 5,
  "completion_tokens": 2,
  "total_tokens": 7,
  "metadata": {
    "source": "gateway_http_direct",
    "status_code": 200
  }
}
```

Correct behavior:

1. Non-streaming responses capture usage.
2. SSE streaming responses capture final output and usage.
3. Zroky headers are stripped before upstream provider request.
4. Gateway auth token is enforced when configured.
5. Internal capture failure does not block provider response.

### 11.12 Capture health validation

API:

```http
GET /v1/capture/health
```

Expected connected response:

```json
{
  "status": "connected",
  "last_call_id": "<call-id>",
  "last_source": "gateway_http_direct",
  "calls_24h": 1,
  "gateway_events_24h": 1,
  "validation_warnings": []
}
```

Expected warning response when instrumentation is weak:

```json
{
  "validation_warnings": [
    {
      "code": "tool_spans_missing",
      "label": "Tool spans missing"
    },
    {
      "code": "outcome_missing",
      "label": "Outcome missing"
    },
    {
      "code": "prompt_version_missing",
      "label": "Prompt version missing"
    }
  ]
}
```

Correct UI:

1. Shows exact missing signals.
2. Does not say integration is perfect when warnings exist.
3. Links to last captured Call.

### 11.13 Calls page

UI path:

1. Open `/calls`.
2. Filter by agent/model/status.
3. Open latest Call.

Expected list row:

1. Provider.
2. Model.
3. Agent.
4. User, if captured.
5. Tokens.
6. Cost.
7. Latency.
8. Status.
9. Created time.

Expected detail:

1. Request/response evidence.
2. Output content.
3. Token/cost breakdown.
4. Trace tree if `trace_id` exists.
5. Create Replay action.

Correct product behavior:

1. Calls page is debug surface.
2. It must not be the main landing page.

### 11.14 Issue generation and Issues page

Precondition:

1. Ingest enough failed or suspicious calls to trigger detectors.
2. Run detector/issue grouping task if not automatic.

UI path:

1. Open `/issues`.

Expected issue row:

```text
Title: Refund agent is selecting wrong tool
Severity: high
Affected agent: refund-agent
Affected workflow: refund-resolution
Root cause: Tool selection drift or schema mismatch
Evidence traces: >= 1
Cost impact: $...
Replay coverage: not_covered | sanity_replay_passed | real_replay_passed
Recommended next action: Create replay from evidence trace...
```

Correct behavior:

1. Title is plain English.
2. Raw detector enum is not the main title.
3. Evidence traces link to Calls/Trace.
4. Top 5 problems are visible without opening raw telemetry.

### 11.15 Issue detail

UI path:

1. Open `/issues/{id}`.

Expected:

1. Root cause summary.
2. Evidence traces.
3. Affected agent/workflow.
4. Cost/user impact.
5. Replay coverage.
6. Recommended next action.
7. Create Replay button.
8. Resolve/ignore/accepted-risk actions.

Wrong:

1. Empty detail page for a real issue.
2. No evidence trace.
3. No replay action.

### 11.16 Create Replay from Issue

UI path:

1. Open an Issue.
2. Select replay mode.
3. Click Create Replay.

API:

```http
POST /v1/replay/runs/from-issue/{issue_id}
```

Expected status:

```text
202 Accepted
```

Expected response:

```json
{
  "id": "<replay-run-id>",
  "project_id": "<project-id>",
  "golden_set_id": "<golden-set-id>",
  "trigger": "issue",
  "status": "pending",
  "summary_url": "/replay/<replay-run-id>",
  "replay_mode": "stub"
}
```

Correct UI:

1. User lands on `/replay/{id}` or sees a link to it.
2. Pending state is clear.
3. Stub mode banner is visible when mode is stub.

### 11.17 Create Replay from Call or Trace

API:

```http
POST /v1/replay/runs/from-call/{call_id}
```

Expected status:

```text
202 Accepted
```

Expected:

1. Replay run created.
2. Source Call linked.
3. Trace detail can create replay from root call.

### 11.18 Replay result

UI path:

1. Open `/replay/{id}`.

Expected summary:

```json
{
  "reproduced_original_failure": true,
  "fix_passed": true,
  "verified_fix": false,
  "verification_status": "sanity_check_only",
  "output_diff": {},
  "tool_behavior_diff": {},
  "cost_delta_usd": 0.0,
  "latency_delta_ms": 0
}
```

For stub mode:

1. `verified_fix` must be false.
2. UI must say `Stub replay is a sanity check, not a verified fix.`
3. It must not show a green "verified fix" claim.

For real comparison mode:

Expected verified case:

```json
{
  "reproduced_original_failure": true,
  "fix_passed": true,
  "verified_fix": true,
  "verification_status": "verified_fix"
}
```

Expected unverified case:

```json
{
  "verified_fix": false,
  "verification_status": "real_comparison_failed"
}
```

Correct behavior:

1. Output diff is visible.
2. Tool behavior diff is visible.
3. Cost/latency delta is visible.
4. Missing tool proof is shown as warning, not silently passed.

### 11.19 Promote Replay to Golden

UI path:

1. Open a passing replay detail.
2. Click Promote to Golden.
3. Choose or create Golden Set.

Expected:

1. Golden trace created.
2. `/goldens` shows trace count increased.
3. Golden trace links back to source Call/Replay.
4. If replay was stub-only, UI labels it as sanity coverage, not verified production proof.

### 11.20 Run Golden Set

API:

```http
POST /v1/goldens/{golden_set_id}/run
```

Expected status:

```text
202 Accepted
```

Expected:

1. ReplayRun row created with `trigger` tied to Golden Set.
2. `/replay` list shows the run.
3. Run eventually becomes `pass`, `fail`, or `error`.

Correct result:

1. Critical Golden fail blocks release.
2. Flaky Golden is visible and not treated as a hard production proof until stabilized.

### 11.21 Agents Launchpad

UI path:

1. Open `/agents`.

Expected row per agent:

1. Agent name.
2. Health pill.
3. Success rate.
4. Cost per successful task.
5. Replay coverage percent.
6. Latest open Issue.
7. Last deploy impact.
8. Recommended next action.

Correct empty state:

1. Shows first-run capture setup.
2. Does not show an empty raw data table.

Correct after traffic:

1. Agents are sorted by risk/impact, not alphabetical only.
2. Clicking an agent scopes Issues, Calls, and Replay.

### 11.22 Ask Zroky

Question:

```text
What are the top problems with my agents today?
```

Expected answer when data exists:

1. Lists top Issues.
2. References evidence links.
3. Gives confidence.
4. Offers action buttons.

Expected answer when data is missing:

```text
Not enough data to answer this yet.
```

Correct action buttons:

1. Create Replay.
2. Open Issue.
3. Open Call.
4. Open Trace.
5. Promote Golden, where applicable.

Wrong:

1. Invented root cause.
2. No evidence.
3. "AI fixed it" claim without replay proof.

### 11.23 Drift

UI path:

1. Open `/drift`.

Expected tabs:

1. Provider Drift.
2. Judge Drift.
3. Outcome Drift.

Expected per drift item:

1. Baseline.
2. Current value.
3. Delta.
4. Affected agent/workflow.
5. Evidence traces.
6. Recommended replay/golden action.

Correct:

1. Provider drift is not mixed with judge calibration as one vague number.
2. Outcome drift links to business impact.

### 11.24 Alerts and notifications

UI path:

1. Open `/alerts`.

Expected:

1. Alert queue loads.
2. Severity and category are visible.
3. Acknowledge works.
4. Resolve works.
5. Reopen works.
6. Linked Issue/Call/Replay is visible when available.

Correct channel test:

1. Slack/Teams/email test returns success or clear configuration error.
2. No silent pass.

### 11.25 Cost and outcome impact

UI path:

1. Open `/cost`.

Expected:

1. Spend trend.
2. Spend by model/provider/agent.
3. Cost per outcome.
4. Wasted cost from failures/retries.
5. Top expensive calls.
6. What-if calculator.

Correct:

1. Cost totals come from `Call.cost_total`.
2. Token totals come from `Call.input_tokens`, `Call.output_tokens`, and `Call.total_tokens`.
3. ClickHouse analytics match Postgres source for sampled rows.

### 11.26 Regression CI

Action:

1. Open a PR with changed prompt/config/model.
2. Run Zroky regression CI action.

Expected PR comment:

1. Golden traces run count.
2. Pass/fail/error count.
3. Output diff summary.
4. Cost delta.
5. Latency delta.
6. Blocking decision.
7. Link to replay run.

Correct:

1. Critical Golden failure blocks merge.
2. Stub-only run cannot approve production fix.
3. Missing evidence gives a warning or failure, not a false pass.

### 11.27 Admin separation

Customer dashboard expected:

1. No `/owner/*` route in customer dashboard production build.
2. No founder/admin nav in customer UI.

Admin app expected:

1. Owner routes live in `zroky-admin`.
2. Owner APIs are gated by owner/admin auth.
3. `FEATURE_LEGACY_OWNER=false` for customer deployments.

### 11.28 Final test pass output

The product is ready only when this combined status is true:

```text
AUTH: pass
PROJECT_SETUP: pass
API_KEY: pass
SDK_CAPTURE_JS: pass
SDK_CAPTURE_PYTHON: pass
GATEWAY_CAPTURE_NON_STREAMING: pass
GATEWAY_CAPTURE_STREAMING: pass
CAPTURE_HEALTH: pass
CALLS: pass
ISSUES: pass
REPLAY_FROM_ISSUE: pass
REPLAY_FROM_CALL: pass
REPLAY_HONESTY: pass
GOLDENS: pass
AGENTS_LAUNCHPAD: pass
ASK_ZROKY_EVIDENCE: pass
DRIFT: pass
ALERTS: pass
COST: pass
REGRESSION_CI: pass
ADMIN_SEPARATION: pass
NO_DOCKER_E2E: pass
```

Any `fail`, `skipped`, or `not verified` means the product is not production-ready yet.

## 12. Final Definition of Done

Zroky is production-ready only when all of these are true:

1. A fresh user can create a project and key.
2. User can connect Python SDK, JS SDK, or Gateway.
3. Dashboard shows Integration Verified with last event.
4. Capture health warns when tool spans, outcomes, or prompt versions are missing.
5. Calls persist with canonical token/cost/status fields.
6. Raw calls group into Issues.
7. Issues show plain-English title, evidence, impact, root cause, replay coverage, and next action.
8. User can create Replay from Issue, Trace, or Call.
9. Replay result clearly says reproduced original failure, fix passed, verified fix, output diff, tool diff, cost delta, latency delta.
10. Stub replay is never called verified.
11. Real comparison replay is verified only with real comparison evidence.
12. User can promote passing replay trace to Golden.
13. CI can run Goldens and block risky deploys.
14. Agents Launchpad is the default dashboard.
15. Ask Zroky answers with evidence and creates actions.
16. Gateway tests pass.
17. Backend focused tests pass.
18. JS SDK tests pass.
19. Dashboard lint/build pass.
20. No-Docker capture smoke passes.
21. Production services run without local Docker dependency.
22. Repo has no local installers, generated coverage, stale logs, or fake OpenAPI summaries.

Until every item above is true, the honest status is: strong prototype with real engine pieces, not fully production-complete.
