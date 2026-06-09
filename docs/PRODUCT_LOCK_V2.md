# Zroky Product Lock v2

## Positioning

Product name: AI Agent Regression Firewall

Zroky is an AI Agent Regression Firewall.

Hero promise:

> Stop shipping the same agent failure twice.

The product promise is not "AI fixes your code automatically." The promise is:

> A production agent failure can become replay proof, then a Golden, then a CI gate that prevents the same failure from shipping again.

Auto-fix is gated, reviewable, and optional. It is not the headline.

## Primary Buyer

Engineering teams running production AI agents that touch support, refunds, sales, operations, compliance workflows, or internal automations.

The first buyer has one or more of these problems:

- Silent agent failures reached users.
- Fixes are validated manually or with screenshots.
- The same prompt/tool/model regression has shipped more than once.
- Existing tracing/eval tooling does not connect production failures to CI release protection.

## Primary Workflow

```text
Capture -> Diagnose -> Issue -> Replay -> Golden -> CI Gate
```

Every primary surface must help answer one of these questions:

- What failed in production?
- How often did it happen?
- Which agent/workflow owns it?
- Can it be replayed?
- Has the fix been verified?
- Is a Golden protecting it?
- Will CI block it before deploy?

## Primary Product Surfaces

These are the primary dashboard nav items, in order:

1. Failure Inbox
   Ranked operational queue. It should show the next action, not generic charts.

2. Issues
   One owned failure pattern per row. The row must expose severity, impact, replay status, Golden status, and owner.

3. Replay Lab
   Original-vs-candidate verification with output, tool behavior, cost, latency, and verdict.

4. Goldens
   Release memory. Goldens should be created only from trusted evidence or explicit human criteria.

5. CI Gates
   Pull-request decisions. A failed protected Golden should produce a clear block reason and reviewer evidence.

6. Cost
   Impact and prioritization. Cost is useful only when tied back to issues, replays, and prevented repeats.

7. Settings
   API keys, provider keys, billing, team, and integrations. Provider-key setup must be clear because real replay depends on it.

## Secondary Surfaces

These are supporting surfaces, not the wedge:

- Traces
- Calls
- Provider drift
- Recommendations
- Ask Zroky
- Alerts
- Agents
- Admin console

They can stay in product if they serve the primary workflow, but they should not dominate nav or landing copy.

## Owner Dashboard Contract

The owner dashboard lives in `zroky-admin`, not in the customer dashboard.
It is the founder/operator control plane for the AI Agent Regression Firewall.

Source of truth:

- [OWNER_DASHBOARD_CONTRACT.md](OWNER_DASHBOARD_CONTRACT.md)

Owner dashboard purpose:

> Is the product loop working, which tenants are stuck, what revenue or quota
> risk exists, and where is the money path breaking?

Target owner navigation:

1. Overview
2. Money Path
3. Tenants
4. Issues & CI Risk
5. Revenue & Entitlements
6. Ops Health
7. Support
8. Audit
9. Settings

Owner dashboard rules:

- Do not add owner routes back into `zroky-dashboard`.
- Do not add dead owner navigation links before the page is real and API-backed.
- Customer production backends keep `FEATURE_LEGACY_OWNER=false`.
- Admin backend/service may enable `FEATURE_LEGACY_OWNER=true`.
- Owner metrics must be DB-backed or explicitly unavailable; no placeholder success.
- The owner money-path view must track Capture -> Diagnose -> Issue -> Replay -> Golden -> CI Gate across tenants.

## v1 Constraints

- Python SDK first; JS SDK second.
- GitHub integration first; Slack/Teams later.
- Postgres is the source of truth. ClickHouse is optional for high-volume analytics.
- Gateway is optional. SDK capture is the default adoption path.
- Auto-fix PRs are gated, reviewable, and not the headline.
- Framework coverage must be described honestly. Do not imply plug-and-play support where only manual wrappers exist.

## Dashboard UX Rules

- First screen starts with the Failure Inbox.
- Every issue row should show actionability: replay, promote Golden, run CI, assign, resolve.
- Empty states must explain the next setup step: install SDK, create API key, connect provider key, run replay, or add GitHub Action.
- Status labels must be plain: `not covered`, `replay pending`, `verified`, `Golden active`, `CI blocked`.
- Do not use decorative AI visuals in the dashboard.
- Prefer dense tables, timelines, diffs, status pills, and evidence panels.

## Landing Page Rules

- Hero promise: "Stop shipping the same agent failure twice."
- The phrase "AI Agent Regression Firewall" should appear as the product category.
- The primary loop is exactly: Capture -> Diagnose -> Issue -> Replay -> Golden -> CI Gate.
- Show the product loop above generic claims.
- Use concrete console/replay/CI evidence visuals.
- Avoid "AI magic", automatic repair, or autonomous merge language.
- CTA should route to project creation or docs for capture setup.

## Release-Readiness Checklist

Before calling the product enterprise-ready:

- SDK captures an event and backend accepts it.
- Failure is diagnosed and grouped into an issue.
- Issue has sample evidence and replay readiness.
- Provider key setup works without exposing plaintext.
- Replay run can execute in stub and real/provider-key mode.
- Verified replay can become a Golden.
- CI gate can dispatch against a Golden set.
- Dashboard surfaces the exact status of each step.
- Landing and README do not overpromise auto-fix.
- Tests pass for SDK, backend money path, dashboard, landing, and CI action.

## Launch Verification Bundle

The launch gate is the same across README, docs, and local release checks:

```powershell
python scripts/run_capture_e2e_local.py

cd zroky-dashboard
npm test
npm run build

cd ..\zroky-landing
npm run build

cd ..\zroky-sdk
..\.venv\Scripts\python.exe -m pytest -q

cd ..\zroky-sdk-js
npm test
npm run build
npm run size

cd ..\zroky-regression-ci-action
npm test -- --runInBand
```

The deployed Phase 8 smoke must pass against production URLs before launch:

```powershell
.\.venv\Scripts\python.exe scripts\run_deployment_smoke.py --grant-pro-via-railway-ssh
```

Current production proof:

- Railway backend health, readiness, ingest, issues, provider key vault, replay, Goldens, and CI gates passed.
- Vercel dashboard login, signup, proxy, session set, and session clear passed.
- Landing production home and auth CTA routes passed.
- Do not ship with generated `dist`, `.next`, coverage, cache, or TypeScript build-info artifacts in the worktree.
