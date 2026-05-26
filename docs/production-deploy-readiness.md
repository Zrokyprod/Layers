# Production Deploy Readiness

Status: code-level deploy readiness is verified. A fresh production environment
still must run the external smoke drill with real managed Postgres, Redis,
domains, and secret-manager values.

## Required Services

Deploy these as separate production services:

1. Backend API
   - Source: `zroky-backend`
   - Start command: `sh scripts/start-api.sh`
   - Healthcheck: `GET /health/live`
   - Readiness: `GET /health/ready`

2. Backend Worker
   - Source: `zroky-backend`
   - Start command: `sh scripts/start-worker.sh`
   - Uses the same `DATABASE_URL`, `REDIS_URL`, and secrets as the API.

3. Beat/Scheduler
   - Source: `zroky-backend`
   - Start command: `sh scripts/start-beat.sh`
   - Responsible for retention, digests, billing sweeps, judge calibration,
     provider drift, gateway stream ingestion, and optional ClickHouse sync.

4. Gateway
   - Source: `zroky-gateway`
   - Dockerfile builds a static Linux binary from `./cmd/gateway`.
   - Healthcheck: `GET /health`
   - Production mode should use either Redis stream emit or backend batch ingest.

5. Replay Worker
   - Source: `zroky-replay-worker`
   - Start command: Dockerfile default `uvicorn app.main:app --host 0.0.0.0 --port 8080`
   - Healthcheck: `GET /health`
   - Readiness: `GET /ready`
   - Must set `WORKER_TOKEN` matching backend `REPLAY_WORKER_TOKEN`.

6. Customer Dashboard
   - Source: `zroky-dashboard`
   - Start command: `npm start`
   - Production backend must set `FEATURE_LEGACY_OWNER=false`.

7. Admin Dashboard
   - Source: `zroky-admin`
   - Start command: `npm start`
   - Backend service serving admin APIs may set `FEATURE_LEGACY_OWNER=true`.

## Required Managed Infrastructure

Set these before first production boot:

```text
DATABASE_URL=postgresql+psycopg://...
REDIS_URL=redis://...
ALLOWED_ORIGINS=https://dashboard.example.com
TRUSTED_HOSTS=api.example.com
FRONTEND_URL=https://dashboard.example.com
AUTH_JWT_SECRET=<secret-manager>
PII_ENCRYPTION_KEY=<secret-manager>
PROVISIONING_TOKEN=<secret-manager>
METRICS_TOKEN=<secret-manager>
REPLAY_WORKER_TOKEN=<secret-manager>
```

Production startup fails closed when critical settings are unsafe:

- SQLite database in production
- localhost Redis in production
- missing CORS origins or trusted hosts
- localhost frontend URL
- trusted project-header context enabled
- provisioning token disabled or missing
- readiness DB/Redis checks disabled
- metrics endpoint enabled without a token
- missing dashboard session JWT secret
- missing PII encryption key

## Optional ClickHouse

Keep ClickHouse disabled until the Postgres-backed path is green:

```text
CLICKHOUSE_ENABLED=false
```

Only enable it after:

1. `sync_clickhouse` beat task runs successfully.
2. `/cost` and issue analytics match Postgres totals.
3. ClickHouse-down fallback has been tested.

## Health, Metrics, Logs, Alerts

Required checks:

```text
GET https://api.example.com/health/live
GET https://api.example.com/health/ready
GET https://api.example.com/metrics
GET https://gateway.example.com/health
GET https://replay-worker.example.com/health
GET https://replay-worker.example.com/ready
```

Metrics endpoint requires:

```text
x-zroky-metrics-token: <METRICS_TOKEN>
```

Prometheus rules already exist under:

```text
prometheus/slo-rules.yml
prometheus/rules/slo_burn.yml
```

Minimum alert policy:

- Backend readiness degraded
- Redis unavailable
- Worker task failure spike
- Gateway capture stream lag
- Replay worker not ready
- High 5xx rate
- ClickHouse sync failure, only if ClickHouse is enabled

## Rollback Drill

Rollback drill is tracked in the customer dashboard under Settings.

Backend APIs:

```text
GET  /v1/settings/rollback-drill
POST /v1/settings/rollback-drill/verify
PUT  /v1/settings/rollback-drill
```

The drill is not considered passed until:

1. Deploy verification passes.
2. Rollback verification passes.
3. Failure simulation is documented.
4. Deploy and rollback revisions are both recorded.
5. Pricing launch gate is complete.

## Final Production Smoke

A fresh production project is ready only when this sequence passes end to end:

1. Sign up from the customer dashboard.
2. Create or select a project.
3. Generate an API key.
4. Send one SDK or gateway capture event.
5. Confirm `/v1/capture/health` reports `connected`.
6. Confirm the captured call appears in Calls.
7. Trigger or seed a failing trace that groups into an Issue.
8. Create a replay from the Issue.
9. Run replay in a non-stub verification mode when validating a fix.
10. Promote a passing replay/call into a Golden.
11. Run regression CI against the Golden set.
12. Confirm dashboard shows issue, replay, golden, and CI proof.

Resolve output:

```text
Fresh production project can signup -> capture -> issue -> replay -> golden -> CI.
```

## Verified Locally

These local verification commands passed after this readiness pass:

```text
go test ./...                         # zroky-gateway
python -m compileall app              # zroky-replay-worker
pytest tests/test_production_config.py tests/test_health.py -q
npm run lint                          # zroky-dashboard
npm run build                         # zroky-dashboard
npm run lint                          # zroky-admin
npm run build                         # zroky-admin
```

