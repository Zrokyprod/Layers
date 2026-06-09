# Zroky Owner Dashboard

Founder/operator control plane for the Zroky AI Agent Regression Firewall.

This app is separate from the customer dashboard. Its job is to show whether
the product loop is working, which tenants are stuck, where revenue or quota
risk exists, and where the money path is breaking.

Primary product loop:

```text
Capture -> Diagnose -> Issue -> Replay -> Golden -> CI Gate
```

Source of truth:

- `docs/OWNER_DASHBOARD_CONTRACT.md`

## Runtime Configuration

Required:

- `ZROKY_API_BASE_URL`: production backend URL. In production this must not be localhost.
- `FEATURE_LEGACY_OWNER=true`: set only on the backend service serving this owner app.
- Provisioning/admin token: entered in the owner gate UI, verified by `/api/owner/session`, and stored only in an HttpOnly cookie.

The customer dashboard must deploy against a backend with `FEATURE_LEGACY_OWNER=false`.

Do not set these in the owner app environment:

- `ZROKY_PROVISIONING_TOKEN`
- `ZROKY_API_KEY`
- `ZROKY_PROJECT_ID`

The owner proxy must not mint credentials from environment variables or trust
browser-supplied owner headers. It converts the HttpOnly owner cookie into the
backend `x-zroky-admin-token` header server-side.

## Current Routes

- `/owner`: product-health snapshot for the regression firewall.
- `/owner/money-path`: tenant drill-down for Capture -> Issue -> Replay -> Golden -> CI Gate.
- `/owner/ops`: founder operating queue with deployed smoke proof.
- `/owner/infrastructure`: services, workers, queues, maintenance, and ops-health proof.
- `/owner/projects`: tenants/projects.
- `/owner/projects/[id]`: tenant detail, product intelligence, and rate limits.
- `/owner/pricing`: revenue, entitlement contract, billing accounts, quota risk, and model pricing.
- `/owner/support`: support tickets, replies, and tenant product evidence.
- `/owner/audit`: owner action trail with tenant product evidence.
- `/owner/rate-limits`: global and tenant rate-limit overrides.
- `/owner/platform-llm`: internal model usage.
- `/owner/feature-flags`: owner-only feature rollouts.
- `/owner/feature-votes`: feature-interest demand signals.
- `/owner/settings`: session, environment, retention, and guardrails.

Do not add navigation links to planned pages until the route is backed by real
API state and has a truthful empty state.

## Owner Product Health API

The first product-specific backend surface is implemented at:

```http
GET /v1/owner/money-path-health
```

Next UI surface:

- Launch verification: keep `https://ops.zroky.com` pointed at the owner-enabled Railway admin API and run deployment smoke before release.

## Verification

```powershell
npm test
npm run lint
npm run build
npx playwright test e2e/owner.spec.ts --project=chromium
cd ..
.\.venv\Scripts\python.exe scripts\run_admin_deployment_smoke.py --admin-url https://ops.zroky.com
```

Backend owner checks:

```powershell
cd ..\zroky-backend
..\.venv\Scripts\python.exe -m pytest -q tests\test_owner_money_path_health.py tests\test_owner_route_gate.py tests\test_owner_support_billing.py tests\test_feature_flags.py tests\test_feature_interest.py
```
