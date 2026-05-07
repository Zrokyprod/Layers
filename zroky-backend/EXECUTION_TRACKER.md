# Zroky Backend Execution Tracker

Last updated: 2026-04-24

## Purpose

This file is the execution single source of truth for backend build progress.

Use this with:

- Product spec: [zroky-blueprint.md](../zroky-blueprint.md)
- Build log: [BUILD_LOG.md](BUILD_LOG.md)
- Runtime/setup guide: [README.md](README.md)

## Current Snapshot

| Workstream | Status | What is already done | What is next |
|---|---|---|---|
| Core API skeleton | Done | FastAPI app, health routes, router wiring | Keep stable while adding features |
| DB and migrations | Done | SQLAlchemy models, Alembic migrations 0001-0009, PostgreSQL RLS policy on diagnosis_jobs plus additional tenant tables (`diagnosis_feedback`, `diagnosis_share_tokens`, `diagnosis_fix_watches`, `project_alerts`, `project_dashboard_configs`), Postgres-only RLS test suite, Alembic env-url hardening for non-default DB targets | Keep Postgres RLS lane green as schema evolves |
| Queue and worker | Done | Celery app, idempotency guard, diagnosis worker task, configurable retry backoff tuning, dead-lettered terminal path, V1 diagnosis engine contract output, fast/pattern queue task split scaffolding, diagnosis outcome/category metrics emission | Monitor retry/dead-letter outcomes in staging and tune retry window if needed |
| Tenant isolation baseline | Done | Header, API-key, JWT-claim resolution, DB-backed membership gate, per-request tenant DB context, transaction re-apply of tenant context, CI-backed Postgres RLS checks | Maintain negative RLS coverage for new tenant tables |
| Project provisioning | Done | Project create/list, API key issue/list/revoke, project membership upsert/list, owner bootstrap membership, role-based authorization matrix for project-scoped routes, diagnosis share token list/revoke admin APIs | Add audit trail for membership changes |
| Security hardening switches | Done | Provisioning token gate, header trust toggle, strict runtime guards, JWT production guardrails, optional DB membership enforcement | Bind production secrets manager values in deployment environments |
| CI/CD | Done | Added `.github/workflows/zroky-backend-ci.yml` with required lanes (`lint-type`, `sqlite-fast`, `postgres-security`) and optional `security-audit-optional` scan lane (`bandit` + `pip-audit` artifact upload); local smoke-validated with 46 fast tests + 2 RLS tests; script-first DB ops (`scripts/db_inspect.py`, `scripts/run_postgres_rls_suite.py`), branch protection automation script (`scripts/configure-branch-protection.ps1`), drift verification script (`scripts/verify-branch-protection.ps1`), and scheduled/manual drift audit workflow (`.github/workflows/zroky-branch-protection-audit.yml`); finalized external enforcement on `zrokylayers/intel` `main` and validated successful audit workflow execution | Keep required-check names in sync between CI jobs and branch-protection scripts/workflow |
| Observability | Done | Structured JSON logs, request-id correlation middleware, `/metrics` endpoint with optional token auth, HTTP + diagnosis metrics instrumentation, health/metrics tests | Add trace export bridge and SLO dashboards |
| Dashboard backend APIs (Phase 0) | In progress | Added new dashboard-focused API routes for Calls, Analytics, Alerts, Onboarding, and Settings; added diagnosis list read API; added alert materialization in worker completion path; added dashboard config + alert tables/migration (`0006`), API parity aliases (`/api/v1/*`, `providers`, `export`, `diagnoses`), phase-0 integration tests, and provider verification hardening with credentialed OpenAI/Anthropic handshake probes plus status-endpoint timeout/cache fallback | Extend credentialed verification coverage to additional providers and optional demo-inference probes where supported |
| Dashboard frontend app (Phase 1 start) | In progress | Created `zroky-dashboard` Next.js App Router project with route-complete UI scaffold (`/home`, `/calls`, `/calls/:id`, `/cost`, `/alerts`, `/settings`, `/auth/login`, `/auth/register`, `/onboarding`), responsive shell, typed API client, and backend proxy route `/api/zroky/*` using env-driven auth headers | Wire production auth flows, SSE live feed, and deep interaction polish to blueprint parity |
| Railway production profile | In progress | Dockerfile, railway config, startup scripts, strict production runtime guard, .env.production.example, go-live checklist, and scripted smoke validator (`scripts/railway_smoke_check.py`) | Execute live cold start, readiness, and rollback drill against Railway domain |
| GCP migration profile | In progress | Config already provider-agnostic | Add Cloud Run + Cloud SQL + Memorystore runbook |

## Step-by-Step Build Plan

| Step | What I will build | Output location | Validation gate | Status | Needs input from you |
|---|---|---|---|---|---|
| 01 | Backend scaffold foundation | [app](app), [alembic](alembic), [scripts](scripts) | `pytest -q`, `alembic upgrade head` | Done | No |
| 02 | Project and API key provisioning APIs | [app/api/routes/projects.py](app/api/routes/projects.py), [app/db/models.py](app/db/models.py) | API tests for create/list/revoke | Done | No |
| 03 | API key based tenant resolution | [app/api/dependencies/tenant.py](app/api/dependencies/tenant.py) | Diagnosis tests with key resolve | Done | No |
| 04 | Security toggles for production hardening | [app/core/config.py](app/core/config.py), [app/api/dependencies/provisioning.py](app/api/dependencies/provisioning.py) | Tests for token guard and header disable | Done | No |
| 05 | Identity integration (JWT/API key policy) | [app/api/dependencies](app/api/dependencies), [app/auth](app/auth), [app/services/membership.py](app/services/membership.py) | Auth contract tests and negative cases | Done | No |
| 06 | Diagnosis engine rule contracts V1 | [app/services/diagnosis_engine.py](app/services/diagnosis_engine.py), [app/worker/tasks.py](app/worker/tasks.py), [tests/test_diagnosis_engine.py](tests/test_diagnosis_engine.py) | Rule unit tests + expected output fixtures | Done | No |
| 07 | Feedback and share-link support | [app/api/routes/diagnosis.py](app/api/routes/diagnosis.py), [app/api/routes/projects.py](app/api/routes/projects.py), [app/db/models.py](app/db/models.py), [alembic/versions/0005_create_diagnosis_feedback_and_share_tokens.py](alembic/versions/0005_create_diagnosis_feedback_and_share_tokens.py), [tests/test_diagnosis.py](tests/test_diagnosis.py) | API tests and permission checks | Done | No |
| 08 | Observability and ops telemetry | [app/core/logging.py](app/core/logging.py), [app/observability/metrics.py](app/observability/metrics.py), [app/observability/middleware.py](app/observability/middleware.py), [app/api/routes/health.py](app/api/routes/health.py), [tests/test_health.py](tests/test_health.py) | Health, metrics, trace correlation checks | Done | No |
| 09 | CI pipeline and quality gates | [../.github/workflows/zroky-backend-ci.yml](../.github/workflows/zroky-backend-ci.yml), [../.github/workflows/zroky-branch-protection-audit.yml](../.github/workflows/zroky-branch-protection-audit.yml), [scripts/configure-branch-protection.ps1](scripts/configure-branch-protection.ps1), [scripts/verify-branch-protection.ps1](scripts/verify-branch-protection.ps1), [BRANCH_PROTECTION.md](BRANCH_PROTECTION.md) | CI green on lint/type/test/migrate + branch protection required checks enforced | Done | No |
| 10 | Railway launch checklist | [RAILWAY_GO_LIVE_CHECKLIST.md](RAILWAY_GO_LIVE_CHECKLIST.md), [scripts/railway_smoke_check.py](scripts/railway_smoke_check.py) | cold start, readiness, rollback drill | In progress | Yes |
| 11 | GCP migration runbook | migration docs + env mapping | Cloud Run smoke checklist | Pending | Yes |
| 12 | Launch hardening and freeze | final checklist docs | zero P0/P1 open, release gate pass | Pending | Yes |
| 13 | Dashboard backend phase 0 APIs | [app/api/routes/calls.py](app/api/routes/calls.py), [app/api/routes/analytics.py](app/api/routes/analytics.py), [app/api/routes/alerts.py](app/api/routes/alerts.py), [app/api/routes/onboarding.py](app/api/routes/onboarding.py), [app/api/routes/settings.py](app/api/routes/settings.py), [alembic/versions/0006_create_project_alerts_and_dashboard_configs.py](alembic/versions/0006_create_project_alerts_and_dashboard_configs.py), [tests/test_dashboard_phase0.py](tests/test_dashboard_phase0.py) | dashboard phase-0 route tests + diagnosis/projects/health regression + alembic head | Done | No |
| 14 | Dashboard frontend phase 1 scaffold | [../zroky-dashboard/src/app](../zroky-dashboard/src/app), [../zroky-dashboard/src/lib/api.ts](../zroky-dashboard/src/lib/api.ts), [../zroky-dashboard/src/app/api/zroky/[...path]/route.ts](../zroky-dashboard/src/app/api/zroky/[...path]/route.ts) | `npm run lint` + `npm run build` in `zroky-dashboard` | Done | No |

## End-to-End Tracking Map

| What you want to track | Where it lives |
|---|---|
| Product requirements and scope | [zroky-blueprint.md](../zroky-blueprint.md) |
| Backend implementation status | [EXECUTION_TRACKER.md](EXECUTION_TRACKER.md) |
| Chronological build history | [BUILD_LOG.md](BUILD_LOG.md) |
| API implementation | [app/api](app/api) |
| Database schema and migrations | [app/db](app/db), [alembic/versions](alembic/versions) |
| Worker/background processing | [app/worker](app/worker) |
| Integration and regression tests | [tests](tests) |
| Deployment runtime files | [Dockerfile](Dockerfile), [railway.toml](railway.toml), [scripts](scripts) |
| Environment contract | [.env.example](.env.example) |

## Update Protocol (How I will keep this trackable)

After every major implementation step, I will do all of the following:

1. Update this tracker with status and next step.
2. Append one line in [BUILD_LOG.md](BUILD_LOG.md) with exact change summary.
3. Run validation commands and record pass/fail in my handoff message.
4. Call out any required input from you immediately before blocking work.

## Immediate Open Inputs (To avoid wrong implementation)

1. Confirm where provisioning admin token will be sourced in production (platform secret manager path/name) before go-live.
