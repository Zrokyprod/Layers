# Zroky Product Operating Contract

This is the single product and implementation source of truth for Zroky.

Old planning docs, broad dashboards, speculative roadmaps, and stale Markdown
files must not guide future implementation. Code should be changed only when it
serves the product loop defined here.

## Product Thesis

Zroky is an Agent Reliability Control Plane.

Core promise:

> Your AI agents may fail once in production, but the same important failure
> should never silently ship again.

The product is not a generic AI observability platform. The product is the gate
that turns real production agent failures into replayable regression protection.

## Mandatory Core Loop

Every major feature must strengthen this loop:

```text
Production agent behavior
-> captured trace
-> detected and grouped failure
-> replay against current fix
-> verified fix evidence
-> promoted Golden regression contract
-> CI/runtime gate blocks repeat failure
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

- dashboard project selection is not end-to-end tenant selection
- gateway capture is best-effort and needs durable retry/spool
- regression CI execution must move from in-process background task to durable queue
- replay worker must fail closed when artifact signing is missing
- replay worker job claiming needs atomic locking
- quota metering must not silently fail for paid launch
- stale pricing/cost metadata must be visible and launch-blocking
- stub replay must never appear as verified proof

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

## Near-Term Execution Order

Work in this order:

1. Fix tenant/project selection end-to-end.
2. Make replay worker artifact signing fail closed.
3. Move regression CI execution to durable queue.
4. Add atomic claim/locking to replay worker polling.
5. Add gateway durable capture retry/spool.
6. Make billing metering failures visible and policy-controlled.
7. Fix API-key prefix drift in UI/docs/tests.
8. Make stale pricing evidence visible in owner health.
9. Upgrade Goldens from output checks to behavior contracts.
10. Add runtime policy and human approval gates.

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
