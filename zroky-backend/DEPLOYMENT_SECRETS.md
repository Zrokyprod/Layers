# Deployment Secrets

This is the launch-current reference for production secrets and environment
variables. Store real values in Railway, Vercel, GitHub Actions secrets, or a
secret manager. Do not commit real tokens, provider keys, PATs, webhook secrets,
database URLs, or Vercel tokens.

Generate random shared secrets with:

```sh
python -c "import secrets; print(secrets.token_hex(32))"
```

## Backend Required

| Variable | Notes |
|---|---|
| `DATABASE_URL` | Managed Postgres connection string. |
| `REDIS_URL` | Redis for queues, stream ingest, cache, and rate limits. |
| `AUTH_JWT_SECRET` | Dashboard session signing. |
| `OAUTH_STATE_SECRET` | OAuth CSRF state. |
| `PII_ENCRYPTION_KEY` | Encrypts sensitive identity data. |
| `PROVIDER_KEY_VAULT_KEK` | Key-encryption-key for customer BYOK provider keys. |
| `PROVIDER_KEY_VAULT_KEY_ID` | Active KEK label, for example `prod-kek-v1`. |
| `PROVISIONING_TOKEN` | Guards provisioning routes such as `POST /v1/projects`. |
| `REPLAY_WORKER_TOKEN` | Shared backend-to-replay-worker control-plane secret. |
| `METRICS_TOKEN` | Guards `/metrics` when enabled. |
| `ALLOWED_ORIGINS` | Comma-separated dashboard origins, for example `https://app.zroky.com`. |
| `TRUSTED_HOSTS` | Comma-separated API hosts, for example `api.zroky.com`. |
| `FRONTEND_URL` | Dashboard root URL for redirects. |

Production policy:

```env
REQUIRE_PROVISIONING_TOKEN=true
ALLOW_PROJECT_HEADER_CONTEXT=false
ACCEPT_LEGACY_TENANT_HEADER=false
API_KEY_HEADER_NAME=x-api-key
PROVISIONING_TOKEN_HEADER_NAME=x-zroky-admin-token
```

## Backend Optional

| Variable | Notes |
|---|---|
| `BILLING_PROVIDER` | Set to `skydo` for hosted billing. |
| `SKYDO_PAYMENT_INSTRUCTIONS_URL` | Default Skydo payment/instructions URL shown after plan selection. |
| `SKYDO_PAYMENT_LINK_TEMPLATE` | Optional payment-link template with `{payment_request_id}`, `{org_id}`, `{plan_code}`, `{amount_usd}`, `{customer_email}` tokens. |
| `SKYDO_PORTAL_URL` | Skydo dashboard URL opened from billing pages. |
| `SKYDO_WEBHOOK_SECRET` | HMAC secret for signed Skydo/manual billing webhooks. |
| `STRIPE_API_KEY` / `STRIPE_WEBHOOK_SECRET` / `STRIPE_PRICE_IDS_JSON` | Deprecated Stripe compatibility only. |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | GitHub OAuth login and connect flow. |
| `GITHUB_TOKEN_ENCRYPTION_KEY` | Encrypts stored GitHub tokens. |
| `GITHUB_PR_BOT_TOKEN` | PAT or GitHub App token for PR creation. |
| `GITHUB_WEBHOOK_SECRET` | GitHub webhook verification. |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google OAuth. |
| `SMTP_HOST` / `SMTP_USER` / `SMTP_PASSWORD` | Email delivery. |
| `SLACK_CLIENT_ID` / `SLACK_CLIENT_SECRET` | Slack OAuth. |
| `SLACK_WEBHOOK_URL` | Slack alert webhook. |
| `SLACK_TOKEN_ENCRYPTION_KEY` | Encrypts stored Slack tokens. |
| `SLACK_SIGNING_SECRET` | Verifies Slack slash-command and button requests. |
| `CLICKHOUSE_URL` / `CLICKHOUSE_PASSWORD` | Optional analytics acceleration. |

## Provider Keys

Signup, capture, traces, issues, and stub replay do not require provider keys.
Verified replay, Golden replay, CI replay, judge, and provider drift can require
a provider key depending on plan and replay mode.

Customer BYOK keys are created through the dashboard provider-key vault and are
stored encrypted with `PROVIDER_KEY_VAULT_KEK`. Platform-side provider keys are
optional and should only be set for managed replay or managed judge operation:

```env
OPENAI_API_KEY=__SET_IN_SECRET_MANAGER__
ANTHROPIC_API_KEY=__SET_IN_SECRET_MANAGER__
GOOGLE_API_KEY=__SET_IN_SECRET_MANAGER__
OPENROUTER_API_KEY=__SET_IN_SECRET_MANAGER__
AZURE_OPENAI_API_KEY=__SET_IN_SECRET_MANAGER__
```

## Customer Project Keys

| Variable | Where used | Notes |
|---|---|---|
| `ZROKY_API_KEY` | Python SDK, JS SDK, CI action | Project-scoped capture key. |
| `ZROKY_PROJECT_ID` | SDKs and CI action | Project identifier. |
| `ZROKY_GATEWAY_API_KEY` | Gateway | Same project key under gateway naming. |

## Dashboard and Landing

Vercel dashboard needs the backend API URL configured for proxy routes:

```env
ZROKY_API_BASE_URL=https://api.zroky.com
NEXT_PUBLIC_API_BASE_URL=https://api.zroky.com
```

Landing is a Vite SPA. Production must include SPA rewrites for `/auth/*`,
`/docs/*`, `/features`, `/pricing`, and `/changelog`.

## Replay Worker

```env
CONTROL_PLANE_URL=https://api.zroky.com
WORKER_TOKEN=__SET_IN_SECRET_MANAGER__
ARTIFACT_SIGNING_KEY=__SET_IN_SECRET_MANAGER__
```

Provider keys are normally delivered per job by the backend control plane after
vault decryption. Configure platform-side fallback keys only for managed replay.

## Verification

Required production checks:

1. `GET /health/live` returns `200`.
2. `GET /health/ready` returns `200` with database and Redis healthy.
3. `POST /v1/projects` without provisioning token returns `401`.
4. `POST /v1/projects` with provisioning token returns `201`.
5. A project API key can ingest one capture event through `/v1/ingest`.
6. `/v1/issues`, provider-key routes, replay dispatch, Golden promotion, and CI gate dispatch work for a Pro-entitled smoke project.
7. Dashboard `/login`, `/signup`, `/api/zroky/health/live`, session set, and session clear work on Vercel.
8. Landing `/`, `/auth/register`, and `/auth/login` work on Vercel.

Run the deployed smoke from the repository root:

```powershell
Push-Location zroky-backend
$vars = railway variable list --json | ConvertFrom-Json
Pop-Location
$env:ZROKY_PROVISIONING_TOKEN = [string]$vars.PROVISIONING_TOKEN
.\.venv\Scripts\python.exe scripts\run_deployment_smoke.py --grant-pro-via-railway-ssh
```

If a Vercel token is used manually for deployment, revoke or rotate it after
the deploy completes.
