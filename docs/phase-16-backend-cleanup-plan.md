# Phase 16 Backend Size + Code Cleanup

Status: Phase 16B completed as a production-safe semantic split.

This phase is not a product feature. It is a maintainability pass that should not change customer behavior.

Phase 16A moved the six listed oversized public modules behind stable
compatibility modules. Phase 16B then split those internal implementation
modules by semantic domain. Public import paths, API routers, and explicit
Celery task names remain unchanged.

## Current Gate

The no-Docker capture path, customer dashboard build, admin dashboard build, production config tests, and file-size lint must pass before each split PR.

Current file-size lint state after Phase 16B:

```text
violations: 0
whitelisted oversized files: 9
_internal directories are scanned
```

## Completed Phase 16A/B Splits

These public files are now thin compatibility modules and have been removed from
`.github/file-size-whitelist.txt`:

1. `zroky-backend/app/db/models.py`
   - Implementation: `zroky-backend/app/db/_internal/models_impl.py`
   - Public import path remains `app.db.models`.

2. `zroky-backend/app/worker/tasks.py`
   - Implementation: `zroky-backend/app/worker/_internal/tasks_impl.py`
   - Explicit Celery task names remain `app.worker.tasks.*`.

3. `zroky-backend/app/api/routes/analytics.py`
   - Implementation: `zroky-backend/app/api/routes/_internal/analytics_impl.py`
   - `/v1/analytics/*` contracts remain unchanged.

4. `zroky-backend/app/api/routes/owner.py`
   - Implementation: `zroky-backend/app/api/routes/_internal/owner_impl.py`
   - Owner/admin route gating remains unchanged.

5. `zroky-backend/app/services/replay_executor.py`
   - Implementation: `zroky-backend/app/services/_internal/replay_executor_impl.py`
   - Replay result semantics remain unchanged: stub is never a verified fix.

6. `zroky-backend/app/services/fix_adoption.py`
   - Implementation: `zroky-backend/app/services/_internal/fix_adoption_impl.py`

The six internal implementation files are now compatibility aggregators:

1. `models_impl.py`
   - Split into `model_shared.py`, `model_diagnosis.py`, `model_identity.py`,
     `model_runtime.py`, `model_goldens.py`, `model_growth.py`,
     `model_provider_drift.py`, and `model_reliability.py`.
2. `tasks_impl.py`
   - Split into `tasks_common.py`, `tasks_utils.py`,
     `tasks_loop_detection.py`, `tasks_diagnosis.py`,
     `tasks_maintenance.py`, `tasks_digest.py`, `tasks_integrations.py`,
     `tasks_replay.py`, `tasks_billing.py`, and `tasks_drift.py`.
   - The aggregator executes split task sources in the compatibility namespace
     so existing `app.worker.tasks` monkeypatching and explicit Celery names
     remain stable.
3. `analytics_impl.py`
   - Split into shared analytics helpers plus summary, activity, cost, budget,
     loops, auth, traces, and savings route modules.
4. `owner_impl.py`
   - Split into shared owner schemas/helpers plus health, users/projects,
     pricing/audit, rate-limit/LLM, support/billing, and operations modules.
5. `replay_executor_impl.py`
   - Split into common types, live replay, diff/proof, finalize, grading, and
     run orchestration modules.
6. `fix_adoption_impl.py`
   - Split into common helpers, lifecycle events, resolution, regressions, and
     metrics modules.

Additional cleanup:

- `zroky-backend/app/api/routes/issues.py` schema classes moved to
  `zroky-backend/app/api/routes/issue_schemas.py` so it stays under the
  30 KB limit.
- `scripts/check_file_sizes.py` now scans `_internal/` directories. Moving code
  internal no longer hides oversized files.

## Remaining Whitelisted Oversized Files

These are outside the six-file Phase 16A scope and remain tracked by the
file-size lint whitelist:

```text
zroky-backend/app/services/judge_engine.py
zroky-backend/app/api/routes/settings.py
zroky-backend/app/api/routes/ingest.py
zroky-backend/app/api/routes/diagnosis.py
zroky-sdk/zroky/_async.py
zroky-backend/app/api/routes/calls.py
zroky-backend/app/api/routes/auth.py
zroky-backend/app/services/replay_runs.py
zroky-sdk/zroky/_call.py
```

## Verification

```text
python scripts/check_file_sizes.py
zroky-backend/.venv/Scripts/python.exe -m compileall app
zroky-backend/.venv/Scripts/python.exe -m pytest tests/test_worker_tasks.py -q
zroky-backend/.venv/Scripts/python.exe -m pytest tests/test_replay_executor.py -q
zroky-backend/.venv/Scripts/python.exe -m pytest tests/test_fix_adoption.py -q
zroky-backend/.venv/Scripts/python.exe -m pytest tests/test_dashboard_phase0.py tests/test_product_issues.py tests/test_anomalies.py -q
zroky-backend/.venv/Scripts/python.exe -m pytest tests/test_owner_route_gate.py -q
npm run lint
npm run build
git diff --check
```

## Resolve Output

```text
Codebase maintainable, no giant unstable modules blocking future work.
```
