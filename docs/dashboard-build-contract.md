# Zroky Dashboard Build Contract

Last updated: 2026-06-04

## 1. Purpose

This document translates the product blueprint into an implementation-ready dashboard contract.

Primary objective:

1. Convert production agent failures into the contract loop: Capture -> Diagnose -> Issue -> Replay -> Golden -> CI Gate.
2. Keep V1 scope disciplined while delivering premium UX quality.
3. Bind every important UI block to explicit backend data contracts.

Reference source:

1. [zroky-blueprint.md](../zroky-blueprint.md)

## 2. Scope Lock (Non-negotiable)

Phase 1 dashboard scope:

1. Primary nav, in order: Failure Inbox, Issues, Replay Lab, Goldens, CI Gates, Cost, Settings.
2. Calls, Traces, Drift, Alerts, Agents, and admin views are secondary/deep-linked support surfaces.
3. Auth and onboarding are required supporting flows, not product wedges.
4. Auto-fix is gated, reviewable, and optional; it is not the dashboard headline.

## 2.1 Implementation Snapshot (2026-04-23)

Implemented now in `zroky-dashboard`:

1. App shell with responsive sidebar/topbar and mobile navigation.
2. Primary route coverage: `/home`, `/issues`, `/replay`, `/goldens`, `/ci-gates`, `/cost`, `/settings`.
3. Server-side proxy route (`/api/zroky/*`) that injects project/API key/provisioning headers from environment.
4. Typed frontend API client mapped to phase-0 backend endpoints.
5. UX modules wired for failure inbox, issue triage, replay proof, Goldens, CI gates, cost/budget widgets, settings controls, and provider-key setup.

Still pending for parity with full blueprint depth:

1. Auth backend integration for login/register/GitHub flows.
2. SSE live-feed transport (currently polling-based refresh).
3. Advanced charting polish and richer action feedback/undo patterns.

## 3. UX and Visual Language Contract

Mandatory design direction:

1. Smooth, minimalist, monochrome-first.
2. High information density with low noise.
3. Clarity over decoration.

Design tokens and typography:

1. Use monochrome palette defined in blueprint section 11.9.
2. Font pairing: Manrope for UI text, JetBrains Mono for numeric and code surfaces.
3. Spacing rhythm: 8px base grid.

Interaction and motion:

1. Page transitions: 180-220ms ease-out.
2. Subtle card hover only.
3. Tooltip follow target: < 50ms.
4. Skeleton states for widgets loading > 200ms.

Performance targets:

1. 60 FPS interaction target on standard developer laptop.
2. Dashboard first meaningful paint <= 2.0s on warm path.
3. Dashboard render p95 tracked and reported.

Accessibility semantics:

1. Never rely on color alone for status.
2. Use icon + label + pattern for warning/error states.
3. Keyboard navigation across sidebar and core actions is mandatory.

## 4. Information Architecture and Routes

Desktop V1 structure:

1. Sidebar always visible (desktop only, >= 1024px target).
2. Topbar includes project selector, environment badge, and profile menu.

Primary route map:

1. /home
2. /issues
3. /replay
4. /goldens
5. /ci-gates
6. /cost
7. /settings

Secondary/deep-link route map:

1. /calls
2. /calls/:id
3. /trace
4. /trace/:id
5. /drift
6. /alerts
7. /account
8. /auth/login
9. /auth/register

## 5. Page-by-Page Component Map

### 5.1 Failure Inbox

Required modules:

1. Ranked production failure queue with severity, impact, owner, replay readiness, Golden status, and CI gate status.
2. Open issues KPI.
3. Cost impact KPI.
4. Replay coverage KPI.
5. CI gate coverage KPI.
6. Next-action panel for diagnose, replay, promote Golden, or run CI gate.
7. Capture health warning when no usable production evidence exists.

Health score formula must be fixed and transparent:

1. success_rate: 40%
2. latency_score: 25%
3. cost_anomaly_score: 20%
4. open_issues_score: 15%

### 5.2 Calls List

Required modules:

1. Filter bar: status, model, date range, user, call_type.
2. Virtualized table with fixed columns:
   Time, Provider, Model, Agent, User, Tokens, Cost, Latency, Status.
3. Row click navigation to Call Detail route.
4. Required empty state with SDK quickstart snippet and docs links.

### 5.3 Call Detail (Inside Calls)

Required modules:

1. Failure summary.
2. Evidence block.
3. Primary fix code block.
4. Alternative fix block.
5. Fix status actions: Resolved and Dismissed.
6. Tool timeline block (if available).
7. Reasoning/cache cost split block.
8. Blast radius block (if trace linked impact exists).
9. Comparison context block (for example 4.2x average).
10. Wasted cost block.
11. Active fix watch status block.
12. Diagnosis helpfulness actions (Yes or No + optional note).
13. Share diagnosis action (24h read-only link).

### 5.4 Cost Dashboard

Required modules:

1. Daily trend chart.
2. Spend by model chart.
3. Spend by user chart.
4. Reasoning cost share.
5. Cache savings trend.
6. Budget alert status.
7. Budget setup and update controls.
8. Pricing freshness block:
   pricing_last_updated_at, pricing_age_days, cost_confidence badge.
9. Stale pricing warning when pricing_age_days > 14.

### 5.5 Alerts

Required modules:

1. Alert list with severity, category, status, source, created time.
2. Filter bar: status, severity, category, project, date range.
3. Actions: Acknowledge, Resolve, Re-open.
4. Alert detail drawer with evidence and linked diagnosis/call.
5. Channel test action: email, slack, browser, terminal.

### 5.6 Settings + API Keys

Required modules:

1. Project settings.
2. API key create/revoke management.
3. PII policy controls.
4. Retention policy controls.
5. Notification channel settings.
6. Provider verification panel with per-provider Test connection.

### 5.7 Supporting Flows (Required)

Auth pages:

1. Login with email/password and GitHub option.
2. Register with email/password confirm and GitHub option.
3. Inline error handling.

Onboarding wizard (3-step):

1. Project and environment setup.
2. SDK install command + code snippet copy actions.
3. Verify connection + synthetic failure trigger.

## 6. API-to-Widget Binding Matrix (Current Reality)

### 6.1 Endpoints already available in backend

Health and platform:

1. GET /health/live
2. GET /health/ready
3. GET /metrics

Diagnosis:

1. POST /v1/diagnosis/submit
2. GET /v1/diagnosis/{diagnosis_id}
3. POST /v1/diagnosis/{diagnosis_id}/feedback
4. POST /v1/diagnosis/{diagnosis_id}/share
5. GET /v1/diagnosis/share/{token}

Projects and API keys:

1. POST /v1/projects
2. GET /v1/projects
3. POST /v1/projects/{project_id}/api-keys
4. GET /v1/projects/{project_id}/api-keys
5. POST /v1/projects/{project_id}/api-keys/{key_id}/revoke
6. POST /v1/projects/{project_id}/memberships
7. GET /v1/projects/{project_id}/memberships
8. GET /v1/projects/{project_id}/diagnosis-shares
9. POST /v1/projects/{project_id}/diagnosis-shares/{share_id}/revoke

### 6.2 Backend gaps vs blueprint dashboard requirements

Missing read APIs required for full dashboard experience:

1. Calls list API with filters and pagination.
2. Call detail API normalized for UI rendering.
3. Diagnoses list API (project timeline view).
4. Analytics summary API for Home KPIs.
5. Health score API with full sub-score transparency payload.
6. Cost analytics APIs (daily trend, by model, by user, cache savings, reasoning share).
7. Budget config and budget status APIs.
8. Alerts CRUD and alert actions APIs.
9. Alerts channel-test APIs.
10. Auth APIs for login/register/GitHub start.
11. Onboarding synthetic failure trigger endpoint.
12. Settings APIs for PII, retention, notification channels, provider verification.
13. SSE endpoint for live feed.

### 6.3 Immediate leverage from existing diagnosis payload

Current diagnosis result_json already supports several Call Detail blocks after parsing:

1. category, confidence, root_cause.
2. fix.primary, fix.code, fix.alternative.
3. evidence object per rule.
4. blast_radius block when available.
5. informational cost warnings.

## 7. Frontend Architecture Contract (Recommended)

Framework baseline:

1. Next.js App Router.
2. React Query for server state.
3. Zod-based runtime validation for API responses.
4. Recharts or Visx with strict monochrome chart styling rules.
5. Virtualized table for Calls page.

State model:

1. Global scope: active project, environment, auth identity.
2. Page scope: filter/query params encoded in URL.
3. Widget scope: loading, error, empty, and stale states mandatory.

Data freshness policy:

1. Home KPIs and live feed: poll every 5-10s until SSE is live.
2. Calls list: cache for 15-30s with manual refresh affordance.
3. Cost widgets: cache for 30-60s with visible timestamp.

## 8. World-class UX Execution Rules (Within Scope)

These rules keep V1 premium without scope creep:

1. Every page must answer: what happened, why, what to do now.
2. Every critical card must have one primary action.
3. Empty states must be action-first, never dead-end.
4. Copy must be developer-direct and measurable.
5. Diagnostics must show evidence before recommendation.
6. Cost numbers must carry freshness and confidence metadata.
7. Three-click issue-to-fix flow must be testable in QA scripts.

## 9. Delivery Phases

Phase 0: Contract completion (backend-first)

1. Add missing read APIs for calls, analytics, cost, alerts.
2. Add health-score endpoint with sub-score payload and timestamp.
3. Add onboarding trigger and settings policy endpoints.

Phase 1: Frontend foundation

1. App shell, sidebar, topbar, project selector.
2. Tokenized design system and core components.
3. Query client, auth/session scaffolding, error boundaries.

Phase 2: Core pages

1. Home with KPI cards and unusual activity.
2. Calls list and Call Detail with diagnosis actions.
3. Cost dashboard with trust indicators.
4. Alerts list and detail actions.
5. Settings and API key management.

Phase 3: Live and polish

1. SSE live feed and notification channels.
2. Motion and interaction polish under performance guardrails.
3. Accessibility and keyboard nav pass.

## 10. Exit Gates for Dashboard Completion

Dashboard work is complete only if all pass:

1. All 5 top-level pages and required supporting flows are live.
2. Call Detail includes all mandatory evidence and action blocks.
3. Health score is transparent with sub-score breakdown and timestamp.
4. Cost page exposes pricing freshness and confidence signals.
5. Alerts workflows (ack/resolve/reopen) are fully functional.
6. issue-to-fix flow validated at <= 3 clicks.
7. dashboard render p95 and interaction targets are within blueprint budgets.
