# Zroky Backend Scaffold

Production-grade backend scaffold for Zroky V1 with Railway-first deployment and GCP migration-ready architecture.

Tracking documents:

- Execution status and next steps: [EXECUTION_TRACKER.md](EXECUTION_TRACKER.md)
- Chronological changes: [BUILD_LOG.md](BUILD_LOG.md)
- Secret locations and naming: [DEPLOYMENT_SECRETS.md](DEPLOYMENT_SECRETS.md)
- Railway release playbook: [RAILWAY_GO_LIVE_CHECKLIST.md](RAILWAY_GO_LIVE_CHECKLIST.md)

## Stack

- FastAPI API server
- PostgreSQL via SQLAlchemy + Alembic migrations
- Redis for readiness checks and idempotency guard
- Celery worker for async diagnosis tasks

## Quick Start (Local)

1. Create env file:

```bash
cp .env.example .env
```

2. Install dependencies:

```bash
python -m venv .venv
. .venv/Scripts/activate
pip install -r requirements.txt
```

3. Start API:

```bash
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

4. Start worker (new terminal):

```bash
celery -A app.worker.celery_app.celery_app worker --loglevel=INFO
```

5. Start scheduler (new terminal):

```bash
celery -A app.worker.celery_app.celery_app beat --loglevel=INFO
```

## Production Build (Railway-first)

1. Use production template as reference:

```bash
cp .env.production.example .env
```

2. Store secrets in platform secret manager (do not keep real secrets in files):

- `DATABASE_URL`
- `REDIS_URL`
- `PROVISIONING_TOKEN`
- `INTERNAL_DEBUG_TOKEN` (required only if internal debug endpoint is enabled)
- `JWT_JWKS_URL` or `JWT_SIGNING_KEY` (if JWT auth is enabled)
- `GITHUB_PR_BOT_TOKEN` (optional fallback for diagnosis Generate PR flow)
- `GITHUB_CLIENT_ID` + `GITHUB_CLIENT_SECRET` (required for per-user GitHub connect flow)
- `GITHUB_TOKEN_ENCRYPTION_KEY` (required for per-user GitHub token storage)
- `OAUTH_STATE_SECRET` (recommended dedicated OAuth state signing key)

3. Keep these locked in production:

- `APP_ENV=production`
- `ALLOW_PROJECT_HEADER_CONTEXT=false`
- `REQUIRE_PROVISIONING_TOKEN=true`
- `ENABLE_READY_DB_CHECK=true`
- `ENABLE_READY_REDIS_CHECK=true`
- `ENABLE_INTERNAL_DEBUG_ENDPOINT=true` (recommended for FX diagnostics; keep token-protected)
- `ENFORCE_JWT_PROJECT_MEMBERSHIP=true` (when JWT auth is enabled)

4. Start commands:

- API service: `sh scripts/start-api.sh`
- Worker service: `sh scripts/start-worker.sh`
- Beat service: `sh scripts/start-beat.sh`

Both scripts now run a strict runtime config validation before starting.

Retention enforcement controls:

- `RETENTION_ENFORCEMENT_ENABLED=true|false` enables scheduled purge runs.
- `RETENTION_ENFORCEMENT_CRON_HOUR` and `RETENTION_ENFORCEMENT_CRON_MINUTE` set daily UTC schedule.
- `RETENTION_PURGE_BATCH_SIZE` controls per-table delete batch size.
- `RETENTION_PURGE_DRY_RUN=true` records counts without deleting rows.

Exchange-rate live refresh controls:

- `EXCHANGE_RATE_ENABLE_LIVE_FETCH=true|false` enables cached live USD->INR refresh.
- `EXCHANGE_RATE_PROVIDER_URL` sets live FX endpoint (USD base, INR symbol expected).
- `EXCHANGE_RATE_PROVIDER_SOURCE` labels live source in audit fields.
- `EXCHANGE_RATE_REFRESH_INTERVAL_MINUTES` controls beat refresh cadence.
- `EXCHANGE_RATE_CACHE_TTL_SECONDS` controls live rate cache lifetime.
- `EXCHANGE_RATE_FAILURE_CACHE_TTL_SECONDS` throttles repeated failed fetch attempts.
- `EXCHANGE_RATE_MAX_STALE_SECONDS` rejects stale cached live rates and falls back.
- `ZROKY_EXCHANGE_RATE_USD_TO_INR` and `ZROKY_EXCHANGE_RATE_SOURCE` are static fallback values.

Internal debug endpoint controls:

- `ENABLE_INTERNAL_DEBUG_ENDPOINT=true|false` toggles internal diagnostics routes.
- `INTERNAL_DEBUG_TOKEN_HEADER_NAME` sets the auth header name (default `x-zroky-internal-token`).
- `INTERNAL_DEBUG_TOKEN` is required when internal debug endpoint is enabled.

Manual one-off retention run:

```bash
celery -A app.worker.celery_app.celery_app call app.worker.tasks.run_retention_enforcement --kwargs='{"dry_run":true}'
```

Manual one-off exchange-rate refresh:

```bash
celery -A app.worker.celery_app.celery_app call app.worker.tasks.refresh_exchange_rate_cache --kwargs='{"force":true}'
```

## Docker Compose

```bash
docker compose up --build
```

API health endpoints:

- `GET /health/live`
- `GET /health/ready`
- `GET /metrics` (Prometheus format; optional token guard)

Observability behavior:

- API middleware emits structured request logs with `request_id`, tenant header context, path template, status, and latency.
- Every API response returns `X-Request-Id` (generated if caller did not provide one).
- Diagnosis worker emits structured completion/failure logs with diagnosis categories.

Metrics endpoint controls:

- `ENABLE_METRICS_ENDPOINT=true|false` toggles `/metrics` exposure.
- `METRICS_TOKEN` (optional) enables header-based protection for `/metrics`.
- `METRICS_TOKEN_HEADER_NAME` sets the expected header name (default `x-zroky-metrics-token`).

Internal debug endpoint:

- `GET /internal/exchange-rate` (requires internal debug token header; intended for ops-only diagnostics)

Internal exchange-rate diagnostics quick check:

```bash
curl -i https://<api-domain>/internal/exchange-rate \
	-H "X-Zroky-Internal-Token: <INTERNAL_DEBUG_TOKEN>"
```

Look for these fields in the response:

- `resolved_default.mode` (`live_cached`, `configured_static`, or `missing`)
- `cache.status` (`ok`, `error`, `empty`, or `disabled`)
- `cache.is_stale` and `cache.cache_age_seconds`
- `configured_fallback.is_available`

Diagnosis endpoints (tenant scoped):

- `POST /v1/diagnosis/submit`
- `GET /v1/diagnosis/{diagnosis_id}`
- `POST /v1/diagnosis/{diagnosis_id}/feedback`
- `POST /v1/diagnosis/{diagnosis_id}/share`
- `GET /v1/diagnosis/share/{token}` (read-only shared view)
- `POST /v1/diagnosis/{diagnosis_id}/generate-pr` (creates branch + commit + PR using GitHub API)
- `GET /v1/diagnosis/{diagnosis_id}/prs` (lists PR links created from this diagnosis)

Generate PR configuration:

- preferred: user GitHub OAuth connection via Settings (`/v1/settings/github/*`)
- optional fallback: `GITHUB_PR_BOT_TOKEN`
- required for user connect flow: `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_CONNECT_OAUTH_REDIRECT_URL`, `GITHUB_TOKEN_ENCRYPTION_KEY`
- optional defaults: `GITHUB_PR_DEFAULT_OWNER`, `GITHUB_PR_DEFAULT_REPO`, `GITHUB_PR_DEFAULT_BASE_BRANCH` (default `main`)
- request body can override repository owner/name/base branch and branch/title/body/commit metadata per diagnosis

GitHub repo connection endpoints (tenant admin + authenticated user token required):

- `GET /v1/settings/github/connection`
- `GET /v1/settings/github/connect/start` (redirects to GitHub OAuth)
- `POST /v1/settings/github/connect/callback` (exchanges code and stores encrypted token)
- `POST /v1/settings/github/disconnect`

Pricing validation launch gate (tenant admin):

- `GET /v1/settings/pricing-validation` now includes launch gate fields (`unique_developer_count`, `required_interviews`, `missing_interviews`, `launch_gate_passed`, `blockers`)
- pricing lock requires at least 5 unique `developer_ref` entries and a non-`undecided` launch model
- rollback drill cannot be marked `passed` until pricing launch gate is complete

Rollback drill automation (tenant admin):

- `POST /v1/settings/rollback-drill/verify` runs automated readiness checks and updates `deploy_test_passed` or `rollback_test_passed` based on verification result
- deploy verification requires `phase=deploy` and `deploy_revision`
- rollback verification requires `phase=rollback` and `rollback_revision`
- operator script: `python scripts/rollback_drill_verify.py --base-url <url> --project-id <project_id> --phase deploy --deploy-revision <rev> --access-token <jwt>`
- GitHub Actions workflow `.github/workflows/zroky-staging-rollout-verify.yml` can run smoke + deploy/rollback verification in staging via `workflow_dispatch`
- required workflow secrets: `ZROKY_STAGING_ADMIN_JWT`, `ZROKY_STAGING_PROVISIONING_TOKEN`

Retention data erasure endpoint (tenant admin):

- `DELETE /v1/settings/retention/data` (supports `dry_run=true|false` and `batch_size` query params)
- response includes per-table deleted counts and `total_deleted`

Diagnosis route role policy:

- submit requires tenant role `member` or higher
- status read requires tenant role `viewer` or higher
- feedback submit requires tenant role `viewer` or higher
- share link create requires tenant role `viewer` or higher

Share link contract:

- share links are read-only
- default expiry uses `READ_ONLY_SHARE_TOKEN_TTL_SECONDS` (24h by default)
- token values are returned only at creation and stored as SHA-256 hashes
- revoked or expired links return `410 Gone`

Required header for diagnosis routes:

- `X-Project-Id: <project_id>`

The header name is configurable using `TENANT_HEADER_NAME`.

Alternative authentication for diagnosis routes:

- `X-Api-Key: <issued_api_key>`
- `Authorization: Bearer <issued_api_key>` (optional fallback)
- `Authorization: Bearer <jwt_token>` (JWT with `project_id` or `projects` claims)

Hardening switches:

- `ALLOW_PROJECT_HEADER_CONTEXT=false` disables direct `X-Project-Id` trust and forces API-key/token-based resolution.
- `REQUIRE_PROVISIONING_TOKEN=true` protects `/v1/projects*` routes with `X-Zroky-Admin-Token`.
- `ALLOW_JWT_PROVISIONING_ACCESS=true` lets admin JWTs access provisioning routes when the token contains `roles` with `zroky_admin`.
- `ENFORCE_JWT_PROJECT_MEMBERSHIP=true` requires JWT users to be mapped in `project_memberships` for the selected project.

JWT identity claims contract:

- `sub` required (user identity)
- `project_id` single-project scope or `projects` multi-project scope
- `roles` includes `zroky_admin` for admin provisioning access
- recommended client setup: managed OIDC provider with `JWT_JWKS_URL` + `JWT_ISSUER` + `JWT_AUDIENCE` pinned

Project and API key provisioning endpoints:

- `POST /v1/projects` to create a project and get `project_id`
- `GET /v1/projects` to list projects
- `POST /v1/projects/{project_id}/api-keys` to issue key (plaintext key returned once)
- `GET /v1/projects/{project_id}/api-keys` to list key metadata
- `POST /v1/projects/{project_id}/api-keys/{key_id}/revoke` to revoke key
- `POST /v1/projects/{project_id}/memberships` to add or update project membership
- `GET /v1/projects/{project_id}/memberships` to list project memberships
- `GET /v1/projects/{project_id}/diagnosis-shares` to list diagnosis share tokens
- `POST /v1/projects/{project_id}/diagnosis-shares/{share_id}/revoke` to revoke diagnosis share token

Project route authorization matrix:

- `POST /v1/projects`, `GET /v1/projects`: provisioning credentials required
- project-scoped management routes (`api-keys`, `memberships`, `diagnosis-shares`): `admin`/`owner` membership or provisioning credentials

Membership model notes:

- roles: `owner`, `admin`, `member`, `viewer`
- creating a project with `owner_ref` automatically bootstraps an `owner` membership

Database tenant isolation safety net:

- PostgreSQL RLS policy is enabled on `diagnosis_jobs`
- tenant context is bound per request via `app.current_tenant_id`

API key defaults:

- Default API key name: `Zroky API`
- Raw key format: `zroky_api_live_<random_secret>`

## Railway Deployment

- `Dockerfile` builds API+worker+beat image.
- `railway.toml` defines web start command and healthcheck path.
- For background processing, create two additional Railway services from same repo with these commands:

```bash
sh scripts/start-worker.sh
sh scripts/start-beat.sh
```

Post-deploy smoke validation:

```bash
python scripts/railway_smoke_check.py \
	--base-url https://<api-domain> \
	--provisioning-token <PROVISIONING_TOKEN>
```

This verifies liveness/readiness and provisioning-token enforcement with a single pass/fail command.

## CI Validation Lanes

Backend CI workflow:

- `lint-type`: runs `ruff` lint and `mypy` type checks
- `sqlite-fast`: runs `pytest -m "not postgres_rls"` and `alembic upgrade head`
- `postgres-security`: runs `alembic upgrade head` on PostgreSQL and executes `tests/test_postgres_rls.py`
- `security-audit-optional`: runs `bandit` + `pip-audit` and uploads findings artifacts (non-blocking lane)

Branch protection automation:

- Script: `scripts/configure-branch-protection.ps1`
- Required checks target: `lint-type`, `sqlite-fast`, `postgres-security`
- Setup guide: `BRANCH_PROTECTION.md`

Local lint and type commands:

- `pip install -r requirements-dev.txt`
- `ruff check app tests alembic`
- `mypy --config-file mypy.ini`

Safe local DB troubleshooting commands (recommended over ad-hoc one-liners):

- `python scripts/db_inspect.py --database-url "postgresql+psycopg://postgres:postgres@localhost:5432/zroky_rls_ci8"`
- `python scripts/run_postgres_rls_suite.py --target-db-name zroky_rls_ci_local`

These scripts keep SQL inside Python and avoid shell quoting/escaping failures.

Local Postgres RLS suite toggle:

- set `RUN_POSTGRES_RLS_TESTS=1`
- set `DATABASE_URL` to a PostgreSQL DSN
- run `pytest -q -m postgres_rls tests/test_postgres_rls.py`

Integration test coverage (Blueprint 14.2):

- file: `tests/test_ingest_integration.py`
- `test_sdk_ingest_to_ui_full_path_with_real_celery_worker`: SDK ingest -> queue -> DB -> diagnosis -> calls UI API path with a real Celery worker
- `test_ingest_flood_accepts_and_queues_high_volume_batch`: high-volume ingest flood that validates batching + queue scheduling semantics
- `test_live_calls_sse_uses_requested_poll_delay`: SSE stream poll delay behavior for `/v1/live/calls`

Run only this integration module:

- `python -m pytest -q tests/test_ingest_integration.py`

## GCP Migration Path

This scaffold is compatible with migration to Cloud Run + Cloud SQL + Memorystore by swapping env vars:

- `DATABASE_URL`
- `REDIS_URL`
- `DEPLOY_TARGET=gcp`
- `GCP_PROJECT_ID`, `GCP_REGION`

No provider-specific code is hardcoded in application logic.

## Pattern Scaling Notes

- LOOP_DETECTED pattern enrichment is Redis-first using identity-scoped TTL windows (90s repeat, 120s progress) with DB fallback for cold cache scenarios.
- Worker writes 10-minute cooldown markers for LOOP_DETECTED into Redis to suppress duplicate alerts.
- Ingest path enriches payload with pre-aggregated 15-minute cost buckets from Redis before diagnosis evaluation.
