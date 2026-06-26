# Zroky Product Operating Contract

This is the single product, implementation, and execution source of truth for
Zroky.

Old planning docs, broad dashboards, speculative roadmaps, and stale Markdown
files must not guide future implementation. Code should be changed only when it
serves the product loop defined here.

Do not create a second active roadmap, plan, strategy, or dashboard redesign
spec. If a future task needs planning, update this file or write the plan inside
the issue/PR for that task only. The repository should have one current plan:
this file.

## Product Thesis

Zroky is an Agent Reliability Control Plane: the control and proof layer for
autonomous AI agents.

Core promise:

> Companies can run autonomous agents unattended because Zroky stops risky
> actions before damage and proves the real-world outcome after execution.

The product is not a generic AI observability platform, eval tool, or agent IAM
console. The product is the gate that controls high-stakes agent actions,
verifies what actually happened, and turns important production failures into
replayable regression protection.

## Mandatory Core Loop

Every major feature must strengthen this loop:

```text
Autonomous agent intends a high-stakes action
-> SDK/Gateway preflight captures action, mandate, tool, args, risk, and context
-> Runtime Policy Gate returns allow, hold_for_approval, or block
-> approved/allowed action executes
-> Zroky verifies the real-world outcome against the system of record
-> Evidence Pack records decision, approval, outcome match, hash, and audit trail
-> important failures become replay/golden regression contracts
-> CI/runtime gates block repeat failures
-> owner sees proof
```

If a feature does not directly support this loop, it is not priority.

## Hard Problem

AI agents are not deterministic software. They fail because:

- prompt or model changes shift behavior
- wrong tool is selected
- tool arguments are malformed or unsafe
- RAG or memory is stale, missing, poisoned, or irrelevant
- handoffs go to the wrong agent
- loops, retries, or long-running autonomous plans drift
- output looks confident while the business task fails
- high-risk actions happen without policy or human approval
- production failures do not automatically become regression tests

Zroky exists to make these failures observable, understandable, replayable, and
blocked from repeating.

## Positioning

Preferred language:

- Production-derived regression firewall for AI agents
- Reliability control plane for autonomous AI agents
- Turn production AI failures into CI gates
- Stop AI agent regressions before they ship

Avoid:

- generic AI observability platform
- analytics dashboard
- AI monitoring
- fake AI insights
- chatbot-first product

## Product Architecture

```text
AI Agent / App
  -> SDK / Gateway / Trace Hook
  -> Agent Flight Recorder
  -> Trace Graph Store
  -> Failure Intelligence Engine
  -> Issue Inbox
  -> Replay Engine
  -> Golden Regression Registry
  -> CI Gate + Runtime Policy Gate
  -> Owner Evidence + Billing
```

## Current Dashboard Contract

The paid dashboard is an action-control surface, not a general analytics app.

Primary dashboard IA:

- Home
- Agents
- Approvals
- Outcomes
- Evidence
- Integrations
- Policies
- Settings

Temporary support routes may exist while the product is being rewired:

- Calls
- Trace
- Issues / Incidents
- Replay
- Goldens
- Contracts
- CI Gates
- Alerts
- Cost

Support routes must not be promoted back into the main IA unless they directly
serve pre-action control, post-action verification, evidence proof, or regression
gating. Delete or redirect support routes only after no primary page, SDK flow,
test, or backend contract still links to them.

## Product Objects

### Trace

A trace is the complete execution record of an agent run.

It should capture:

- user input
- system/developer prompt version
- model and provider
- tool calls
- tool arguments
- tool outputs
- RAG documents and retrieval metadata
- memory reads and writes
- agent handoffs
- guardrail and policy decisions
- final answer
- latency
- cost
- status and error
- business outcome
- code SHA, prompt version, model version, tool schema version, RAG index version

Flat logs are not enough. Complex agents need trace graphs.

### Failure

A failure is an actionable grouped problem, not a raw log.

Good failure:

```text
Refund agent called refund_tool without checking policy after prompt v14.
312 users affected. High risk. Introduced by prompt version v14.
```

Bad failure:

```text
500 traces failed.
```

### Replay

Replay is the proof layer.

Supported replay modes should be honest:

- recorded or stub replay: sanity check only
- mocked tool replay: freeze tool outputs and test prompt/model behavior
- frozen RAG replay: use the same retrieved context
- sandbox tool replay: exercise safe tool-like behavior
- real LLM replay: run against real provider/model
- live shadow replay: compare safely without production side effects

Never label a stub replay as a verified fix.

### Golden

A Golden is a production-derived regression contract.

It should verify more than final text:

- correct tool sequence
- correct tool arguments
- required policy checks
- required human approval
- grounded answer
- no unsafe action
- cost budget
- latency budget
- final task success

### Gate

The gate is the core product surface.

Verdicts:

- pass: release/runtime action is safe
- warn: risk exists but policy allows continuation
- fail: repeat failure or unsafe behavior detected
- not_verified: no real proof exists

CI and runtime gates are more important than dashboards.

### Verified Action

A verified action is a typed, idempotent, high-stakes action intent.

The public kernel is:

- `GET /v1/action-packs`
- `GET /v1/action-packs/{pack_id}`
- `POST /v1/action-packs/{pack_id}/install`
- `POST /v1/action-contracts`
- `POST /v1/action-intents`
- `GET /v1/action-intents/{action_id}`
- `POST /v1/action-intents/{action_id}/decide`
- `GET /v1/tools/registry`

Launch action packs are the default onboarding path. A customer should not have
to invent the first contract schema by hand. The first supported packs are:

- `support-ops-v1`: customer refunds and customer-record updates
- `devops-release-v1`: deploy/change control with CI and approval evidence

Each installed pack registers immutable action contract versions into the
tenant. Agents then create action intents against those contract versions,
receive a runtime policy decision, execute only when allowed or approved, and
produce source-of-record evidence.

## Build Priorities

### Phase 1: Agent Flight Recorder

Goal: if production agent behavior happened, Zroky has reliable evidence.

Build:

- SDK capture
- Gateway capture
- direct ingest API
- durable retry/spool
- PII and secret redaction
- idempotency
- tenant isolation
- trace graph schema

Do not accept best-effort capture as final production behavior.

### Phase 2: Failure Intelligence

Goal: users see a small number of actionable failures, not noisy logs.

Build first:

- wrong tool or tool error detection
- schema/output failure detection
- loop/retry detection
- unsafe action detection
- task outcome failure detection
- issue grouping
- severity
- blast radius
- introduced-by version attribution
- owner/team assignment
- Slack/GitHub notification

Avoid thirty weak detectors. Prefer five high-signal detectors.

### Phase 3: Real Replay

Goal: Zroky can prove whether a fix actually works.

Build:

- mocked tool replay
- frozen RAG replay
- sandbox replay
- real LLM replay
- replay budgets
- replay diff
- judge verdict
- before/after evidence
- durable result persistence

Stub mode must remain clearly labeled as sanity-only.

### Phase 4: Goldens

Goal: important production failures become permanent regression protection.

Build:

- one-click promote failure to Golden
- expected behavior editor
- tool sequence assertions
- tool argument assertions
- policy assertions
- grounding assertions
- cost and latency budgets
- flaky marker
- blocking/non-blocking setting

### Phase 5: CI Gate

Goal: bad agent releases are blocked before deploy.

Build:

- GitHub Action first
- durable backend queue
- PR comment with exact failed Golden
- required check support
- pass/warn/fail/not_verified result
- relevant Golden selection from changed files, prompt versions, model versions,
  RAG index versions, and tool schema versions

The API process must not be the durable execution engine.

### Phase 6: Runtime Policy Gate

Goal: dangerous autonomous behavior can be stopped before damage.

Build:

- max tool calls
- max cost
- max retries
- destructive action approval
- payment/refund/email/delete/code execution approval
- PII leak guard
- prompt injection guard
- tool permission checks
- kill switch
- policy-as-code

### Phase 7: Human Approval

Goal: high-risk agent actions pause for explicit approval.

Approval view must show:

- agent trace
- intended action
- reason
- policy hit
- risk level
- approve/reject controls
- audit trail

SDK contract:

- `guard()` runs immediately before the irreversible tool call
- `allowed=true` means the action may execute
- `ZrokyRuntimePolicyApprovalRequired` means the action is held and must not execute yet
- the exception exposes Python `approval_id` / TypeScript `approvalId`
- after a human approves, retry the same guarded action with that approval id
- rejected, expired, mismatched, or already-consumed approvals fail closed

Python:

```python
try:
    zroky.guard(
        action_type="refund",
        tool_name="refund_payment",
        tool_args={"order_id": "ord_123", "amount": 42.5},
        external_action=True,
    )
except zroky.ZrokyRuntimePolicyApprovalRequired as hold:
    approval_id = hold.approval_id
    # Store approval_id and stop. Do not call refund_payment until approved.
    raise

# After approval in Zroky:
zroky.guard(
    action_type="refund",
    tool_name="refund_payment",
    tool_args={"order_id": "ord_123", "amount": 42.5},
    external_action=True,
    approval_id=approval_id,
)
```

TypeScript:

```ts
import { guard, ZrokyRuntimePolicyApprovalRequired } from "@zroky-ai/sdk";

let approvalId: string | undefined;

try {
  await guard({
    actionType: "refund",
    toolName: "refund_payment",
    toolArgs: { order_id: "ord_123", amount: 42.5 },
    externalAction: true,
  });
} catch (error) {
  if (error instanceof ZrokyRuntimePolicyApprovalRequired) {
    approvalId = error.approvalId;
    // Store approvalId and stop. Do not call refund_payment until approved.
    throw error;
  }
  throw error;
}

// After approval in Zroky:
await guard({
  actionType: "refund",
  toolName: "refund_payment",
  toolArgs: { order_id: "ord_123", amount: 42.5 },
  externalAction: true,
  approvalId,
});
```

### Phase 8: Owner Evidence

Goal: owner can see agents becoming safer over time.

Show:

- bad deploys blocked
- production failures converted to Goldens
- verified fixes
- risky agents
- stale gates
- teams without gates
- money and incident cost avoided
- capture health
- replay health
- billing and quota health

## Current Codebase Reality

The repository already contains many real pieces:

- FastAPI backend control plane
- auth, projects, memberships, API keys
- ingest and calls
- diagnosis jobs and detectors
- issues/anomalies
- replay runs
- golden sets and traces
- regression CI routes
- provider key vault / BYOK
- billing and entitlements
- owner/admin APIs and dashboard
- customer dashboard
- Go gateway
- external replay worker
- GitHub CI action
- Slack/GitHub-style integration wiring

But the product is not yet mandatory infrastructure because several guarantees
need hardening:

- the deployed dashboard still has old-dashboard styling and support-route debt
- the new dashboard redesign must become the actual owner, not an override layer
- dashboard project selection is not end-to-end tenant selection
- gateway capture is best-effort and needs durable retry/spool
- regression CI execution must move from in-process background task to durable queue
- replay worker must fail closed when artifact signing is missing
- replay worker job claiming needs atomic locking
- quota metering must not silently fail for paid launch
- stale pricing/cost metadata must be visible and launch-blocking
- stub replay must never appear as verified proof

## Current Master Execution Plan

Work through these phases in order. Do not skip ahead unless the current task is
an urgent bug or security fix.

### Phase 0: Single Plan Lock

Goal: only this file guides product and implementation decisions.

- remove active stale specs, duplicate roadmaps, and obsolete assistant plans
- keep historical handoff docs only when they are clearly not the current plan
- do not create a separate master-plan document
- every future Codex task must reference this file's phase and non-goals

### Phase 1: Dashboard IA Freeze

Goal: the visible dashboard matches the paid product story.

- make shell, command palette, settings tabs, labels, and empty states match the
  primary dashboard IA
- keep support routes hidden unless they are still needed for deep links
- remove observability/analytics language from user-facing surfaces
- make every dashboard page answer one question: what action was controlled,
  verified, proved, or blocked?

### Phase 2: New Dashboard Attach

Goal: the new dashboard redesign becomes the real dashboard system.

- stop treating the redesign as a global CSS patch over old dashboard styles
- move dashboard styling toward one scoped dashboard system
- keep public/auth/landing styles separate from dashboard control styles
- verify desktop and mobile layouts before deleting old selectors

### Phase 3: Old Dashboard Removal

Goal: remove old dashboard code in dependency order.

- classify each route as primary, support, legacy redirect, or delete
- remove internal links before deleting routes
- remove tests only after the behavior is intentionally removed or replaced
- delete old CSS selectors only after no page depends on them

### Phase 4: Core Control Loop

Goal: pre-action control and post-action proof work end to end.

- agent declares intended action
- Zroky checks mandate, risk, policy, args, anomaly, and approval need
- Zroky returns allow, hold_for_approval, or block
- allowed action executes
- Zroky verifies the real outcome against a system of record
- evidence pack records the decision and verified outcome

### Phase 5: Evidence And Proof Polish

Goal: the customer can export and trust proof.

- evidence packs must include action, policy decision, approval state, outcome
  verification status, hash, timestamps, and audit trail
- every status must be honest: matched, mismatched, not_verified, pass, warn, or
  fail
- stubbed or simulated proof must be labeled clearly

### Phase 6: SDK Onboarding

Goal: JS and Python SDKs show the exact paid-product workflow.

- install, preflight, hold/block/allow, approval retry, outcome report, and
  evidence id must be easy to test
- examples must target refund, email, ticket, CRM, deploy, invoice, and spend
  approval style actions
- SDK docs must not describe Zroky as generic observability

### Phase 7: Backend Legacy Cleanup

Goal: backend APIs match the product loop without legacy aliases confusing new
work.

- remove deprecated aliases only after clients stop calling them
- keep tenant/project isolation strict
- fail closed for replay, CI, billing, quota, and policy enforcement
- every removed endpoint needs a reference check and targeted test update

### Phase 8: Paid Launch Hardening

Goal: launch only when the control/proof product can be sold honestly.

- production env validator passes
- billing and quota enforcement are enabled for paid workspaces
- real replay and owner proof are enabled for launch environments
- one design-partner flow proves a risky action was controlled and verified
- owner/admin launch-readiness has no fail or not_verified required gate

## Implementation Rules

Follow these rules strictly:

1. Code is source of truth after this file. Do not use deleted or stale docs.
2. Do not add broad features unless they strengthen the mandatory core loop.
3. Do not create vanity dashboard pages.
4. Do not add generic analytics unless tied to failure, replay, gate, or owner proof.
5. Do not overbuild admin before the core gate is reliable.
6. Do not call sanity/stub replay a verified fix.
7. Do not add detectors without clear failure grouping and action.
8. Do not accept best-effort capture, metering, or CI execution as final production guarantees.
9. Every implementation should include a focused test for the product guarantee it changes.
10. Every user-facing status should be honest: pass, warn, fail, or not_verified.
11. Do not add a new nav item without mapping it to the dashboard contract above.
12. Do not create a CSS patch on top of another CSS patch unless it is temporary
    and the cleanup target is documented in the same task.
13. Do not remove a route, API, or test until references are checked.
14. Do not mix unrelated product, UI, backend, and cleanup work in one slice.
15. Do not leave old dashboard code active when a replacement is complete.

Before a Codex implementation task starts, state:

- phase from the Current Master Execution Plan
- exact user/product outcome
- expected files or modules touched
- non-goals
- risk
- verification command or manual check
- cleanup target, if any

If a proposed change cannot fit this format, it is too broad and must be split.

## Near-Term Execution Order

Work in this order:

1. Keep this README as the only current plan and remove active stale specs.
2. Freeze the dashboard IA around Home, Agents, Approvals, Outcomes, Evidence,
   Connectors, Policies, and Settings.
3. Wire the new dashboard redesign as the actual dashboard system.
4. Remove old dashboard CSS/routes in dependency order.
5. Make pre-action control visible end to end in SDK, backend, and dashboard.
6. Make post-action outcome verification visible end to end.
7. Make evidence packs exportable and honest.
8. Align JS and Python SDK onboarding with control + proof.
9. Remove backend legacy aliases after reference checks.
10. Run paid-launch hardening: billing, quota, replay, tenant isolation, owner
    proof, and design-partner verification.

## What Not To Build First

Do not prioritize:

- decorative landing pages
- broad observability dashboards
- random charts
- generic AI assistant/chat inside the dashboard
- large admin features that do not improve gate reliability
- many low-signal detectors
- complex billing before replay and CI proof
- speculative roadmap docs

## Final Product Standard

Zroky should be judged by this question:

> Did we prevent an important AI agent failure from silently repeating?

If yes, the product is working.

If no, the work is probably not core.

## Final Paid Launch Gate

Paid launch is blocked unless every required gate is `pass`:

- durable capture
- tenant isolation
- failure intelligence
- honest replay proof
- behavioral Goldens
- durable CI gate
- runtime risk stop
- billing and quota reliability
- owner value proof
- single source of truth

Owner/admin exposes this as `/owner/launch-readiness`.

Run the local code-readiness verification:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_paid_launch_readiness.ps1 -Phase all
```

This can pass without a live customer artifact, but it is not enough to mark
paid launch complete. Final paid launch requires one hosted design-partner owner
proof artifact where `real_customer_proof=pass`.

The final owner proof validator fails closed unless the summary/evidence pair is
from a live run, uses a real HTTPS system-of-record URL instead of `example.com`,
includes the complete proof-flag set, has connector readiness `ready`, shows at
least one matched outcome and audit event, and has matching `sha256` evidence
hashes and decision IDs.

After `.github/workflows/zroky-design-partner-owner-proof.yml` uploads the
owner proof artifacts, validate the downloaded summary/evidence before launch:

```powershell
$env:ZROKY_REQUIRE_OWNER_PROOF = "true"
$env:ZROKY_OWNER_PROOF_SUMMARY = "artifacts/design-partner-owner-proof-summary.json"
$env:ZROKY_OWNER_PROOF_EVIDENCE = "artifacts/design-partner-owner-proof-evidence.json"
powershell -ExecutionPolicy Bypass -File scripts/verify_paid_launch_readiness.ps1 -Phase final
```

For artifact-only validation:

```bash
python scripts/verify_design_partner_owner_proof_artifact.py --summary artifacts/design-partner-owner-proof-summary.json --evidence artifacts/design-partner-owner-proof-evidence.json
```

Run the deterministic release-candidate evidence pack:

```bash
python scripts/run_money_path_demo.py --json
```

Run the design-partner install proof before handing a pilot to a real customer:

```bash
python scripts/run_design_partner_install_kit.py --json --write-summary artifacts/design-partner-summary.json --write-evidence artifacts/design-partner-evidence.json
```

Customer handoff guide:

```text
demos/design-partner-install-kit/HANDOFF.txt
```

Live partner smoke:

```bash
python scripts/run_design_partner_install_kit.py --api-base-url https://api.zroky.com --api-key <zroky_api_key> --ledger-base-url https://ledger.example.com/api --ledger-bearer-token <ledger_token> --refund-id <refund_id> --json --write-summary artifacts/design-partner-live-summary.json --write-evidence artifacts/design-partner-live-evidence.json
```

Final owner-gate proof for a hosted pilot is run by:

```text
.github/workflows/zroky-design-partner-owner-proof.yml
```

It requires a real captured `call_id` and `trace_id`, a project API key,
`ZROKY_STAGING_PROVISIONING_TOKEN`, and either a saved connector or the relevant
ledger/CRM connector secret. The workflow calls owner `/v1/owner/launch-readiness`
and fails unless `real_customer_proof=pass`.

Validate filled production environment files before real launch:

```bash
python scripts/validate_launch_env.py --roles backend,dashboard,admin,gateway,replay-worker --require backend,dashboard,admin,gateway,replay-worker
```

Run staging backend deployment smoke before a hosted pilot:

```bash
python scripts/run_deployment_smoke.py --api-base-url https://api-staging.zroky.com --provisioning-token <staging_provisioning_token> --backend-only
```

This must pass health, provisioning guard, API-key create/list/ingest/rotate/revoke,
provider-key vault redaction, and replay/CI plan gates. GitHub workflow
`.github/workflows/zroky-staging-rollout-verify.yml` runs the same backend smoke
after readiness checks. Required secrets: `ZROKY_STAGING_PROVISIONING_TOKEN` and
`ZROKY_STAGING_ADMIN_JWT`.

GitHub paid-launch readiness is checked by:

```text
.github/workflows/paid-launch-readiness.yml
```

Any `fail` or `not_verified` gate blocks paid launch.

## SDK Public Publish Runbook

Public SDK publishing requires registry credentials owned by the Zroky npm and
PyPI accounts. Never commit registry tokens.

Packages:

- JavaScript: `@zroky-ai/sdk`
- Python: `zroky`

npm publish:

1. Confirm the npm scope/organization `@zroky-ai`.
2. Add an npm automation token with publish access as GitHub secret `NPM_TOKEN`.
3. Run GitHub Actions workflow `Zroky JS SDK Publish`.
4. Use `target_registry=npm` and `expected_version` from
   `zroky-sdk-js/package.json`.
5. Wait for `publish-npm` and `verify-npm-registry` to pass.

PyPI publish:

1. Configure a Trusted Publisher, or a pending publisher for first publish,
   separately on TestPyPI and PyPI.
2. Use project name `zroky`, owner `Zrokyprod`, repository `Layers`, workflow
   filename `zroky-sdk-publish.yml`, and leave environment blank unless the
   workflow is intentionally changed to use one.
3. Run GitHub Actions workflow `Zroky SDK Publish` first with
   `target_repository=testpypi`, `auth_method=trusted-publisher`, and
   `expected_version` from `zroky-sdk/pyproject.toml`.
4. After `verify-testpypi-registry` passes, run the same workflow with
   `target_repository=pypi`.
5. Confirm `verify-pypi-registry` passes.

Token fallback:

- Use `TEST_PYPI_API_TOKEN` for TestPyPI.
- Use `PYPI_API_TOKEN` for PyPI.
- For a first-time PyPI project, prefer Trusted Publisher or an account-level
  token that can create the project. Rotate to project-scoped tokens after the
  first publish if token auth remains necessary.

Manual workflow dispatch is preferred for first release. Later releases can use
version tags:

- Python: `zroky-sdk-vX.Y.Z`
- JavaScript: `zroky-sdk-js-vX.Y.Z`

Registry versions are immutable. If publish partially succeeds and verification
fails, fix forward by bumping the package version before publishing again.

Real environment proof is still required before production launch:

- billing provider sandbox/live webhook verification
- replay worker signing key and private worker readiness
- gateway capture spool recovery with backend down/up
- production secrets and provisioning-token validation
