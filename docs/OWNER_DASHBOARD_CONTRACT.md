# Zroky Owner Dashboard Contract

Status: Phase 10.0 locked
Date: 2026-06-04

## Product Role

The owner dashboard is the founder/operator control plane for the AI Agent
Regression Firewall. It is not the customer dashboard and it is not a generic
admin CRUD app.

The owner dashboard must answer this in five minutes:

> Is the product loop working, which tenants are stuck, what revenue or quota
> risk exists, and where is the money path breaking?

Primary product loop:

```text
Capture -> Diagnose -> Issue -> Replay -> Golden -> CI Gate
```

## App Boundary

- Source app: `zroky-admin`
- Customer app: `zroky-dashboard`
- Owner API prefix: `/v1/owner/*`
- Admin feature gate: `FEATURE_LEGACY_OWNER=true`
- Customer production backend: `FEATURE_LEGACY_OWNER=false`

Owner routes must not be added back into the customer dashboard. If a future
owner page shares UI components with the customer dashboard, the component can
be shared, but the route and data access must stay inside `zroky-admin`.

The owner app proxy must not inject server-side owner credentials, project API
keys, or project IDs. It forwards only the operator-provided
`x-zroky-admin-token` header from the browser session.

## Primary Owner Questions

Every owner surface should answer one or more of these:

- Are tenants capturing production agent events?
- Are captured failures becoming Issues?
- Are Issues replayable?
- Are verified replays becoming Goldens?
- Are Goldens running in CI and blocking regressions?
- Which tenants are missing provider keys, replay credits, Goldens, or CI gates?
- Which tenants are near quota or plan-limit risk?
- Which failures are creating support, cost, or revenue risk?
- Is the deployed product healthy enough to sell today?

## Target Navigation

The target owner navigation is:

1. Overview
2. Money Path
3. Tenants
4. Issues & CI Risk
5. Revenue & Entitlements
6. Ops Health
7. Support
8. Audit
9. Settings

Current implementation may keep existing route labels until the route is real.
Do not add a navigation link to a planned page until the page is backed by real
API state and has a non-placeholder empty state.

## Route Contract

| Target surface | Route | Status | Purpose |
| --- | --- | --- | --- |
| Overview | `/owner` | Phase 10.3 done | Snapshot of money-path health, owner risk, tenant actions, and deployed smoke proof. |
| Money Path | `/owner/money-path` | Phase 10.4 done | Tenant drill-down for Capture -> Issue -> Replay -> Golden -> CI Gate risk and proof. |
| Tenants | `/owner/projects` and `/owner/projects/[id]` | Phase 10.5 done | Tenant list plus tenant-specific usage, provider-key, replay, Golden, CI, quota, and last-capture evidence. |
| Issues & CI Risk | `/owner/issues-ci-risk` | Planned | Cross-tenant open Issues, failed Goldens, blocked PRs, and missing proof. |
| Revenue & Entitlements | `/owner/pricing` | Phase 10.6 done | Plan contract drift, billing status, quota burn, replay credits, Goldens, blocking CI eligibility, and provider-key vault limits. |
| Ops Health | `/owner/ops` and `/owner/infrastructure` | Phase 10.7 done | Backend health, workers, queues, maintenance, deployed smoke proof, and daily operating queue. |
| Support | `/owner/support` | Phase 10.8 done | Tickets linked to tenant, issue, replay, CI, quota, and provider-key evidence. |
| Audit | `/owner/audit` | Phase 10.8 done | Immutable owner action trail linked to current tenant product evidence when available. |
| Settings | `/owner/settings` | Existing | Session, environment, retention, and dangerous-operation guardrails. |

## Money-Path Health API

Phase 10.2 adds:

```http
GET /v1/owner/money-path-health
```

The response is DB-backed and must not synthesize success. `null`,
`unavailable`, or explicit empty arrays are better than fake zeros when the
backend cannot compute a field.

Required platform summary:

- captures_24h
- issues_open
- replay_runs_7d
- verified_replay_runs_7d
- golden_traces_active
- ci_runs_7d
- ci_blocks_7d
- tenants_missing_provider_key
- tenants_near_replay_quota
- tenants_without_recent_capture
- last_deployed_smoke

Required tenant rows:

- project_id
- project_name
- plan_code
- last_capture_at
- captures_24h
- open_issue_count
- replay_run_count_7d
- verified_replay_count_7d
- golden_trace_count
- ci_run_count_7d
- blocking_ci_failures_7d
- provider_key_status
- replay_quota_status
- next_owner_action

## Data Rules

- No placeholder metrics in authenticated owner pages.
- No plaintext provider keys, API keys, tokens, or customer secrets.
- No owner provisioning token in `zroky-admin` client or server environment.
- Missing provider keys must be shown as missing, not as replay-ready.
- Disabled or unconfigured billing must be shown as disabled or unavailable.
- Failed health checks must stay visible until the backend reports recovery.
- Empty states should say what is missing and which setup step fixes it.
- Owner pages should prefer tables, funnels, evidence panels, and operational
  status over marketing cards.

## Mutation Rules

Every risky owner mutation must write an audit event:

- project pause or activation
- user suspend, delete, or anonymize
- rate-limit override
- replay-credit or entitlement grant
- pricing or plan change
- maintenance mode toggle
- queue purge or task revoke
- support reply
- provider-key administrative action, if added

The UI must show destructive actions as guarded operations and must not hide
backend failure behind optimistic success.

## Phase Order

1. Phase 10.0: lock this contract and align docs/admin shell language.
2. Phase 10.1: harden owner access and deployment gate.
3. Phase 10.2: build `/v1/owner/money-path-health`. Done.
4. Phase 10.3: upgrade `/owner` overview to product health. Done.
5. Phase 10.4: build `/owner/money-path`. Done.
6. Phase 10.5: upgrade tenant detail with product intelligence. Done.
7. Phase 10.6: align revenue, pricing, and entitlements. Done.
8. Phase 10.7: add deployed smoke and ops-health proof. Done.
9. Phase 10.8: link support and audit to product evidence. Done.
10. Phase 10.9: add owner regression tests. Done.
11. Phase 10.10: deploy admin separately and smoke it. Done.

## Phase 10.10 Deployment Smoke Status

Current admin frontend deployment:

- Production alias: `https://ops.zroky.com`
- Vercel project: `zroky-admin`
- Vercel `ZROKY_API_BASE_URL`: owner-enabled backend URL, currently `https://zroky-api-admin.up.railway.app`

Current owner API deployment:

- Railway project: `zroky-prod`
- Railway environment: `admin`
- Railway service: `zroky-api`
- Public URL: `https://zroky-api-admin.up.railway.app`
- Owner gate: `FEATURE_LEGACY_OWNER=true`
- Customer production API remains `https://api.zroky.com` with
  `FEATURE_LEGACY_OWNER=false`.

- Smoke command:

```powershell
.\.venv\Scripts\python.exe scripts\run_admin_deployment_smoke.py --admin-url https://ops.zroky.com
```

Verified:

- `zroky-admin` production build deploys separately from the customer dashboard.
- `/`, `/owner`, `/owner/money-path`, `/owner/projects`, `/owner/pricing`,
  `/owner/ops`, `/owner/infrastructure`, `/owner/support`, `/owner/audit`,
  and `/owner/settings` return HTTP 200.
- Security headers include clickjacking protection and CSP frame-ancestor guard.
- Admin proxy no-token guard returns 401, not 404.
- Authenticated proxy checks pass for owner stats, health, money-path health,
  and pricing plans when run with an owner token.

## Acceptance For Phase 10.0

- This document is the source of truth for owner-dashboard phases.
- Product lock points to this document.
- `zroky-admin` README explains the owner control-plane purpose and gate.
- No dead owner navigation links are introduced.
- Existing owner tests, lint, and build still pass.
