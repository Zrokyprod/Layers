# Zroky MVP Execution Goal

## Objective

Bring Zroky to a paid private-beta MVP as the Zroky Verified Action Control Plane.

Core promise:

AI agents can perform high-risk actions only through controlled, approved, verified, and receipted workflows.

Launch loop:

1. Agent proposes an action.
2. Zroky validates the Action Contract.
3. Policy decides allow, deny, or approval required.
4. Approval is collected when required.
5. A protected runner executes with isolated credentials.
6. A verifier checks the source of record.
7. Zroky generates a signed Action Receipt and Evidence Pack.
8. Dashboard shows coverage, mismatch, bypass risk, and pending approvals.

## Non-Negotiable Launch Scope

- Action Kernel with tenant, project, environment, agent registry, action contracts, canonical intent digest, deterministic policy decisions, lifecycle states, risk classes, assurance levels, verification levels, and immutable timeline.
- Four first action verbs only: TRANSFER, UPDATE, SEND, EXECUTE.
- Policy Engine with deterministic rules, approval requirements, quota rules, connector minimum rules, kill switches, versioning, and audit trail.
- Approval System in Zroky dashboard and Slack only.
- Protected Action Runner with runner identity, heartbeat, plan-before-execute, idempotency, credential references, and execution attempt logs.
- Verification Engine that checks source-of-record state, not just HTTP status.
- Signed Action Receipt plus human-readable Evidence Pack.
- Reconciliation Lite for unreceipted mutation and bypass detection.
- Tight connector scope: Generic REST/OpenAPI, webhook/audit ingestion, PostgreSQL read verifier, Slack approvals, and one payment/support action pack.
- Premium light-theme dashboard focused on Overview, Actions, Approvals, Verification/Reconciliation, Policies, Connectors, Evidence, and Settings/Billing. Standalone Incidents is cut from first launch.
- ActionKit OSS as developer adoption layer, with explicit cooperative-mode limits.
- Billing and quota enforcement around protected action usage.
- Production ops with observability, auditability, health checks, kill switches, and tenant isolation tests.

## Current CTO Status

| Track | Status | Verdict |
| --- | --- | --- |
| Repo hygiene and launch scope | Complete | Launch scope, blockers, and execution order are fixed in this document. Current tree is still dirty and must be consolidated before commit/release. |
| Legacy dashboard sunset | Mostly complete | Old analytics/dashboard routes are deleted or retired. New route contract exists. |
| Light theme | Complete | Dashboard provider enforces light theme. |
| zroky.com domain guard | Complete | Static launch guard checks domain policy. |
| Action Kernel | Partial | Contracts/intents/digest/policy wiring exist. Immutable timeline, runner execution attempts, dispatch/claim/start/finish lifecycle, and receipt binding now exist. Still missing explicit A0-A5 assurance fields, V0-V5 verification fields, and adapter-specific executor implementations. |
| Agent registry | Mostly complete | Agent profile and route foundation exists. |
| Tool registry | Partial | Typed P0/P1 connector catalog exists in `/v1/tools/registry`, including runtime paths, verification connectors, native tool families, launch tiers, and honest availability notes. Only connector marketplace remains visible as a P2 placeholder; other P2 ideas are hidden. Several P0 entries are still template/planned until live adapter work is complete. |
| Policy Engine | Mostly complete | Approval, kill switch, amount thresholds, production deploy approval, changed-recipient deny, high-value refund dual approval, and digest-safe PII policy handling exist. Remaining work is production policy ops hardening, not core MVP decision logic. |
| Approval System | Mostly complete | Dashboard approval exists. Slack approvals now use signed exact-approval callbacks, Slack request signature verification, Slack user allowlisting, stale-context rejection, and audit-visible Slack actors. Exact action-intent approval binding is covered for wrong-digest approval attempts and consumed approval reuse. High-value actions require two distinct approvals before authorization. Self-serve Slack approver allowlist UI remains pending; design-partner launch can operate this through install/Ops configuration. |
| Protected Runner | Partial | Runner registry, heartbeat, credential-reference enforcement, plan-before-execute, dispatch, runner claim/start, finish/fail/ambiguous/cancel lifecycle, result summaries, adapter contract validation, Python customer-hosted runner package, daemon mode, graceful shutdown, heartbeat/backoff loop, Docker/Compose deployment package, generic REST executor, Stripe refund executor, deterministic Stripe money-path proof, CLI, and timeline events exist. Catalog marks this honestly. Razorpay/Zendesk/message adapters and live partner deployment validation are still pending. |
| Verification Engine | Partial | Outcome checks now expose launch statuses: verified, mismatched, pending, unverifiable, and cancelled. Direct and encrypted saved PostgreSQL read-only verification, plus saved Generic REST verification, now exist with sanitized evidence metadata. Deeper payment/support/message verifiers are still pending. |
| Evidence Pack | Partial | Evidence hash/pack and signed Action Receipt now exist, including verification status and execution attempt context. Generic REST/Stripe runner result summaries can now flow into attempts; deeper adapter-specific evidence normalization remains pending. |
| Reconciliation Lite | Partial | Source mutation records, receipt matching, unreceipted mutation list, bypass taxonomy, summary/list APIs, and Outcomes-page bypass visibility now exist. Production webhook adapters are still pending. |
| Dashboard MVP IA | Complete | First-class Actions wires protected-action quota, runtime decisions, runner/receipt meters, verification, and bypass risk. Billing shows protected-action meters. Outcomes covers verification/reconciliation/bypass. System-of-record connectors now expose ledger refund, CRM customer record, and encrypted PostgreSQL read setup/test/saved-proof visibility. Desktop/mobile Playwright coverage now verifies the launch route contract, paid money path, reliability UX, accountability cockpit, and PostgreSQL proof controls. Standalone Incidents is cut from first launch and retired from the route contract. |
| ActionKit OSS | Partial | SDK guard/verify helpers and Python customer-hosted runner example now exist. Missing ActionKit polish, digest utility, local policy test, receipt verify CLI, JS runner parity, and broader examples. |
| Billing/Quota | Mostly complete | Protected-action billing now has named monthly meters for protected actions, policy checks, runner executions, receipts/evidence, verification checks, source mutations, plus active source-of-record connector limits. `/v1/billing/usage` exposes these meters and strict quota mode returns 402/503 on protected-action paths. Hosted payment provider checkout is still Razorpay-first; Stripe/Lemon Squeezy provider parity and final pricing ops remain pending. |
| Production ops | Partial | Health/OTel/audit pieces exist. Sentry, PostHog, backup/restore, and connector monitoring need final verification. |
| Paid launch readiness | Blocked | Deterministic Verified Action Stripe refund proof now runs in the evidence phase. Final gate must stay blocked until real owner-proof artifacts and live design-partner evidence exist. |

## Execution Order

1. Stabilize repo hygiene and launch gates.
2. Implement Protected Action Runner foundation. Done for registry, heartbeat, credential references, execution planning, adapter contract validation, Python customer-hosted runner package, daemon mode, graceful shutdown, heartbeat/backoff loop, Docker/Compose deployment package, generic REST/Stripe executors, CLI, and attempt logs.
3. Add immutable Action Timeline and signed Action Receipt. Done for lifecycle events and HMAC-signed receipt artifact.
4. Harden first-launch Policy Engine rules. Done for deterministic MVP rules, exact action-intent approval binding validation, true dual approval for high-value refund/transfer actions, and signed Slack approval callbacks.
5. Upgrade Verification Engine and Reconciliation Lite. Done for launch statuses, direct and encrypted saved PostgreSQL read-only verification, saved Generic REST verification, source mutation records, unreceipted mutation list, bypass taxonomy, and Outcomes-page bypass watch. Production webhook adapters and deeper payment/support/message verifiers remain pending.
6. Finalize dashboard IA and wiring. Done for first-class Actions, Billing quota visibility, Evidence links, Outcomes/Reconciliation visibility, bypass watch, PostgreSQL read connector setup/test/saved-proof visibility, and desktop/mobile e2e route-contract coverage. Standalone Incidents is cut from launch scope; action exceptions live in Actions, Outcomes, and Evidence.
7. Complete live runner adapter coverage. Started with Python customer-hosted runner, daemon deployment package, generic REST, Stripe refund, and deterministic Verified Action Stripe money-path proof. Razorpay, Zendesk, customer-message, live Docker build validation, and design-partner deployment proof remain pending.
8. Formalize connector catalog. Done for visible P0/P1 launch tiers, connector marketplace placeholder, availability statuses, and API contract fields. Keep non-marketplace P2 ideas hidden and keep marketing claims aligned to available/template/planned status.
9. Move billing/quota to protected-action usage. Done for backend enforcement, plan entitlements, usage API, strict quota responses, and tests. Stripe/Lemon Squeezy provider parity remains a commercial/payment-ops decision.
10. Package ActionKit OSS.
11. Run full readiness gates and produce owner-ready completion report.

## CTO Rule

## Latest Verification

- `npm run test:e2e -- e2e/dashboard-modules.spec.ts --project=chromium --project=mobile-chromium` passed: 5 tests.
- `npm run test:e2e -- e2e/money-path.spec.ts e2e/reliability-ux.spec.ts e2e/action-accountability-cockpit.spec.ts --project=chromium --project=mobile-chromium` passed: 8 tests, 1 intended mobile money-path skip.
- `npm run lint -- e2e/dashboard-modules.spec.ts e2e/helpers.ts e2e/money-path.spec.ts e2e/reliability-ux.spec.ts e2e/action-accountability-cockpit.spec.ts e2e/settings-account.spec.ts` passed.

The green e2e scope covers the paid-MVP dashboard route contract, protected-action money path, route retirement redirects, responsive shell behavior, accountability/evidence/outcome proof, reliability UX, and PostgreSQL read connector setup/test/saved-proof controls on desktop and mobile.

Do not claim full production-grade managed execution until protected runner adapter coverage is complete, live runner deployment is verified, and protected credentials are never returned to agents.

Current honest claim after the backend control-plane upgrade is:

"Zroky controls the protected action lifecycle, binds dashboard and Slack approvals to exact action intent scope, requires two distinct approvals for high-value protected money movement, validates runner adapter contracts, ships a daemon-capable customer-hosted runner path for generic REST/Stripe execution, proves the deterministic Stripe refund money path, requires credential-isolated runner execution, verifies outcomes through Generic REST and direct PostgreSQL read-only source checks, detects bypass risk, and issues signed receipts."

After production adapters, live deployment evidence, and dashboard wiring are complete, the launch claim becomes:

"Zroky controls, executes, verifies, and receipts high-risk AI agent actions."
