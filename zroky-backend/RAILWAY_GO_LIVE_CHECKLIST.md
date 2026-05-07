# Railway Go-Live Checklist

Last updated: 2026-04-21

## Goal

Deploy Zroky backend to Railway with safe production defaults, working API/worker split, and post-deploy validation.

## Inputs You Need Before Start

1. Git repository connected to Railway.
2. PostgreSQL service available (Railway plugin or external managed DB).
3. Redis service available (Railway Redis or external managed Redis).
4. Provisioning admin token ready (long random secret).

## Service Topology (Railway)

Create two Railway services from the same codebase:

1. API service:
- Start command: `sh scripts/start-api.sh`

2. Worker service:
- Start command: `sh scripts/start-worker.sh`

Both services must use the same env variable contract.

## Step-by-Step Deployment

### Step 1: Create API Service

1. Railway Dashboard -> New Project (or open existing project).
2. Add Service -> Deploy from GitHub repo.
3. Confirm service builds with Dockerfile.
4. Set start command to `sh scripts/start-api.sh`.

### Step 2: Create Worker Service

1. In same Railway project, add a second service from same repo.
2. Set start command to `sh scripts/start-worker.sh`.
3. Disable public domain for worker service (internal only).

### Step 3: Provision Database and Redis

1. Add PostgreSQL service and capture connection URL.
2. Add Redis service and capture connection URL.
3. Ensure both API and worker can access these URLs.

### Step 4: Configure API Service Variables

Set these variables on API service:

- `APP_ENV=production`
- `LOG_LEVEL=INFO`
- `PORT=8000`
- `DATABASE_URL=<postgres-connection-url>`
- `REDIS_URL=<redis-connection-url>`
- `ENABLE_READY_DB_CHECK=true`
- `ENABLE_READY_REDIS_CHECK=true`
- `ALLOW_PROJECT_HEADER_CONTEXT=false`
- `ACCEPT_LEGACY_TENANT_HEADER=false`
- `REQUIRE_PROVISIONING_TOKEN=true`
- `PROVISIONING_TOKEN=<secret-value>`
- `DEPLOY_TARGET=railway`

If using GitHub per-user PR connect flow, also set:

- `GITHUB_CLIENT_ID=<secret-value>`
- `GITHUB_CLIENT_SECRET=<secret-value>`
- `GITHUB_CONNECT_OAUTH_REDIRECT_URL=https://<dashboard-domain>/auth/github/connect/callback`
- `GITHUB_TOKEN_ENCRYPTION_KEY=<fernet-key>`
- `OAUTH_STATE_SECRET=<secret-value>`
- `GITHUB_PR_BOT_TOKEN=<optional-fallback-token>`

### Step 5: Configure Worker Service Variables

Set same core variables on worker service:

- `APP_ENV=production`
- `LOG_LEVEL=INFO`
- `DATABASE_URL=<postgres-connection-url>`
- `REDIS_URL=<redis-connection-url>`
- `ENABLE_READY_DB_CHECK=true`
- `ENABLE_READY_REDIS_CHECK=true`
- `ALLOW_PROJECT_HEADER_CONTEXT=false`
- `REQUIRE_PROVISIONING_TOKEN=true`
- `PROVISIONING_TOKEN=<secret-value>`
- `DEPLOY_TARGET=railway`

### Step 6: Deploy and Observe

1. Trigger deploy for API service.
2. Verify logs include migration success and API startup.
3. Trigger deploy for worker service.
4. Verify worker connects to broker and starts consuming.

### Step 7: Smoke Validation (Must Pass)

Run these checks against API domain:

Preferred scripted validation (single pass/fail command):

```bash
python scripts/railway_smoke_check.py \
  --base-url https://<api-domain> \
  --provisioning-token <PROVISIONING_TOKEN>
```

If you need strict manual verification, use the endpoint-level checks below.

1. Liveness:

```bash
curl -i https://<api-domain>/health/live
```

Expected: `200` and status `ok`.

2. Readiness:

```bash
curl -i https://<api-domain>/health/ready
```

Expected: `200` and both DB/Redis checks `ok`.

3. Provisioning route without token:

```bash
curl -i -X POST https://<api-domain>/v1/projects \
  -H "Content-Type: application/json" \
  -d '{"name":"NoTokenProject"}'
```

Expected: `401`.

4. Provisioning route with admin token:

```bash
curl -i -X POST https://<api-domain>/v1/projects \
  -H "Content-Type: application/json" \
  -H "X-Zroky-Admin-Token: <PROVISIONING_TOKEN>" \
  -d '{"name":"ProdProject"}'
```

Expected: `201` and `project_id` in response.

5. Internal exchange-rate diagnostics (ops token required):

```bash
curl -i https://<api-domain>/internal/exchange-rate \
  -H "X-Zroky-Internal-Token: <INTERNAL_DEBUG_TOKEN>"
```

Expected: `200` and JSON includes `resolved_default.mode` and `cache.status`.

Script behavior notes:

- Validates `GET /health/live` and `GET /health/ready`.
- Validates provisioning guard by asserting unauthenticated `POST /v1/projects` returns `401`.
- Validates authenticated provisioning flow and confirms created project appears in `GET /v1/projects`.
- Exits non-zero on any failed check for CI/CD-friendly usage.

### Step 8: Rollback Drill (Required)

1. Redeploy previous successful revision from Railway history.
2. Run automated deploy verification:

```bash
python scripts/rollback_drill_verify.py \
  --base-url https://<api-domain> \
  --project-id <project_id> \
  --phase deploy \
  --deploy-revision <current-revision> \
  --access-token <admin-jwt>
```

Optional CI path: run GitHub Actions workflow `.github/workflows/zroky-staging-rollout-verify.yml` with:

- `phase=deploy` (or `both`)
- staging `base_url`
- target `project_id`
- `deploy_revision`
- secrets `ZROKY_STAGING_ADMIN_JWT` and `ZROKY_STAGING_PROVISIONING_TOKEN`

3. Re-run validation after rollback:

```bash
python scripts/rollback_drill_verify.py \
  --base-url https://<api-domain> \
  --project-id <project_id> \
  --phase rollback \
  --rollback-revision <previous-stable-revision> \
  --access-token <admin-jwt>
```

4. Confirm API and worker both stable after rollback.

## Production Exit Criteria

Go live only if all are true:

1. API deploy healthy for at least 15 minutes.
2. Worker deploy healthy for at least 15 minutes.
3. Health endpoints pass.
4. Provisioning token enforcement confirmed (`401` without token).
5. Rollback drill completed successfully.
6. Pricing validation launch gate is complete (`launch_gate_passed=true` with >=5 unique beta developer interviews and pricing decision locked).

## Where This Fits in Tracking

1. Execution plan: [EXECUTION_TRACKER.md](EXECUTION_TRACKER.md)
2. Build history: [BUILD_LOG.md](BUILD_LOG.md)
3. Secret naming/location: [DEPLOYMENT_SECRETS.md](DEPLOYMENT_SECRETS.md)
