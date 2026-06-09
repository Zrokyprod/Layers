# Backend Production Env Checklist

Use this checklist to fill `zroky-backend/.env.production` or the deployment
platform secret store. Do not paste real values into chat, docs, commits, or
tracked `.env.example` files.

Run the no-leak validator while filling values:

```powershell
python scripts/validate_launch_env.py --root . --roles backend --require backend
```

Optional fingerprint mode prints short hashes for comparison without printing
raw secret values:

```powershell
python scripts/validate_launch_env.py --root . --roles backend --require backend --fingerprints
```

## Required Runtime Values

| Key | Real value source | Validation rule |
|---|---|---|
| `APP_ENV` | Literal deployment mode | Must be `production` |
| `DATABASE_URL` | Managed PostgreSQL connection string | Must be non-SQLite and non-localhost |
| `REDIS_URL` | Managed Redis connection string | Must be non-localhost |
| `ALLOWED_ORIGINS` | Customer dashboard origin | Must include `https://app.zroky.com` and no wildcard |
| `TRUSTED_HOSTS` | Backend API hostnames | Must include `api.zroky.com` and no wildcard/localhost |
| `FRONTEND_URL` | Customer dashboard URL | Must be `https://app.zroky.com` for launch |
| `ALLOW_PROJECT_HEADER_CONTEXT` | Security policy | Must be `false` |
| `REQUIRE_PROVISIONING_TOKEN` | Provisioning gate policy | Must be `true` |
| `ENABLE_READY_DB_CHECK` | Readiness policy | Must be `true` |
| `ENABLE_READY_REDIS_CHECK` | Readiness policy | Must be `true` |
| `BILLING_ENFORCE_QUOTA` | Paid launch quota policy | Must be `true` |
| `REPLAY_REAL_LLM_ENABLED` | Replay launch policy | Must be `true` |

## Required Secrets

Generate/store these in the real secret manager for the production deployment.
The validator rejects placeholders such as `__SET_IN_SECRET_MANAGER__`,
`replace-with`, `fake`, `dummy`, and test keys.

| Key | Real value source | Validation rule |
|---|---|---|
| `AUTH_JWT_SECRET` | Random production session-signing secret | Present, not placeholder |
| `OAUTH_STATE_SECRET` | Separate random OAuth state HMAC secret | Present, not placeholder |
| `PII_ENCRYPTION_KEY` | Random production encryption key | Present unless `GITHUB_TOKEN_ENCRYPTION_KEY` is used |
| `PROVIDER_KEY_VAULT_KEK` | KMS-resolved KEK or secret-manager KEK | At least 32 characters |
| `PROVISIONING_TOKEN` | Owner/provisioning admin token | Present, not placeholder |
| `METRICS_TOKEN` | Metrics scrape token | Required when `ENABLE_METRICS_ENDPOINT=true` |
| `GITHUB_WEBHOOK_SECRET` | GitHub webhook secret configured in GitHub | Present, not placeholder |
| `REPLAY_WORKER_TOKEN` | Shared with replay worker `WORKER_TOKEN` | At least 16 characters |
| `OPENROUTER_API_KEY` or `OPENAI_API_KEY` | Real platform LLM provider key | Required for production diagnosis/judgment |

## Billing Secrets

For current hosted launch:

| Key | Real value source | Validation rule |
|---|---|---|
| `BILLING_ENABLED` | Literal launch policy | `true` for paid launch |
| `BILLING_PROVIDER` | Billing integration | `skydo` |
| `SKYDO_WEBHOOK_SECRET` | Skydo/manual billing webhook signing secret | Required when Skydo billing is enabled |

If switching to Stripe later, set `BILLING_PROVIDER=stripe` and use real
`STRIPE_API_KEY` plus `STRIPE_WEBHOOK_SECRET` instead.

## Optional Integrations

Leave optional integrations unset until real provider credentials exist. If any
Slack production key is set, all of these must be set together:

```text
SLACK_CLIENT_ID
SLACK_CLIENT_SECRET
SLACK_TOKEN_ENCRYPTION_KEY
SLACK_SIGNING_SECRET
```

Teams webhook encryption is optional, but if Teams is enabled, set a real
`MS_TEAMS_WEBHOOK_ENCRYPTION_KEY`.

## Fill Order

1. Copy non-secret launch policy values from `zroky-backend/.env.production.example`.
2. Add real managed `DATABASE_URL` and `REDIS_URL`.
3. Add real auth, OAuth, PII, provider-vault, provisioning, metrics, GitHub,
   replay worker, and platform LLM secrets from the secret manager.
4. Add real Skydo webhook secret before enabling billing.
5. Run the backend-only validator until it passes.
6. Run the full launch validator:

```powershell
python scripts/validate_launch_env.py --root .
```
