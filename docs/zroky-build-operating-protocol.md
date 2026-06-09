# Zroky Build Operating Protocol

## Purpose

This document defines how Zroky should be built without drifting, overclaiming, or shipping incomplete product loops.

The goal is simple:

> Build the exact product, prove every change, and never confuse product vision with current code reality.

This protocol applies to every meaningful code change in Zroky.

## Core Rule

Every change must directly support at least one part of the Zroky reliability loop:

```text
Capture
-> Diagnose
-> Issue
-> Replay
-> Golden
-> CI Gate
```

If a change does not help one of these, it is secondary and should not distract from the core product.

## Non-Negotiable Build Principles

### 1. Current Code Is The Source Of Truth

Before implementation:

- search the repo
- read the existing files
- understand local patterns
- confirm data models and API contracts
- verify route names, field names, hooks, and schemas

Never assume a function, endpoint, model field, route, or component exists.

Required first step for most tasks:

```bash
rg "<feature-or-field-name>"
```

### 2. Product Vision Is Not Current Reality

The product blueprint describes what Zroky should become.

The codebase describes what Zroky currently is.

When building, always separate:

- already implemented
- partially implemented
- missing
- broken
- stub/dry-run only

Never describe a feature as complete unless the implementation and tests prove it.

### 3. Build Vertical Slices

Do not build vague systems.

Build complete user-visible slices.

Correct slice shape:

```text
User action
-> frontend state
-> API call
-> backend behavior
-> persistence or computed result
-> test
-> user-visible confirmation
```

Bad scope:

> Make replay perfect.

Good scope:

> Add "Create Replay" action from Issue Detail, call backend endpoint, create replay case, show result, and test the flow.

### 4. Acceptance Criteria Before Code

Before editing files, define:

- what the user can do
- what data is required
- what API is called
- what result is shown
- what failure state is shown
- what tests prove it

No acceptance criteria means no implementation.

### 5. Contract-First Development

Zroky depends on clean contracts.

For every cross-system feature, verify all involved contracts:

- backend schema
- database model
- Python SDK payload
- JS SDK payload
- gateway event shape
- dashboard API client type
- dashboard hook/component type
- tests

Do not allow mismatches like:

```text
backend expects completion_tokens
SDK sends output_tokens
```

Contract drift is a product reliability bug.

### 6. No Unsupported Product Claims

Do not use these words unless proven:

- complete
- perfect
- verified
- production-ready
- end-to-end working
- real replay
- safe to merge
- fixed

Use honest labels:

- stub mode
- dry-run
- partial
- not wired
- unverified
- local-only
- needs real integration test

### 7. Small Edits, Tight Scope

Do not refactor unrelated code.

Do not touch unrelated pages, styles, APIs, or models.

Do not mix:

- SDK contract fix
- dashboard redesign
- replay engine changes
- billing changes
- auth changes

One task should have one clear product outcome.

### 8. Follow Existing Patterns

Use the repo's existing style:

- FastAPI route structure
- service-layer pattern
- SQLAlchemy model conventions
- dashboard API client pattern
- TanStack Query hook pattern
- existing CSS/design language
- existing test style
- existing auth and tenant dependency pattern

Add new abstraction only when it removes real complexity or matches a repeated pattern.

### 9. Tests Are Proof

Every meaningful change needs verification.

Backend:

```bash
python -m pytest <relevant-tests>
```

Dashboard:

```bash
npm run lint
npm run build
```

Python SDK:

```bash
python -m pytest
```

JS SDK:

```bash
npm test
```

Gateway:

```bash
go test ./...
go vet ./...
```

If a command cannot run because the environment is missing a dependency, report that clearly.

### 10. User Changes Are Protected

The worktree may contain user changes.

Rules:

- never revert files without explicit request
- inspect changed files before editing them
- work with existing changes
- ignore unrelated dirty files
- report conflicts if they block the task

### 11. Friendly Product, Strict Code

The dashboard should be simple for users.

The implementation should not be vague.

For every UI action, define:

- exact API endpoint
- typed request
- typed response
- loading state
- empty state
- error state
- success state
- permission behavior
- test coverage

No fake success states.

### 12. Evidence In Final Report

Every completed coding task must report:

- files changed
- behavior added or fixed
- tests run
- test results
- known limitations
- remaining risks

Do not say "done" without proof.

## Required Workflow For Every Feature

### Step 1: Scope Lock

Write the exact task in one sentence.

Example:

> Add one-click replay creation from Issue Detail.

### Step 2: Product Mapping

Map the task to the reliability loop:

```text
Capture / Diagnose / Issue / Replay / Golden / CI Gate
```

If it maps to none, reconsider the task.

### Step 3: Repo Discovery

Search and read:

- existing routes
- existing models
- existing services
- existing dashboard pages
- existing hooks/API client
- existing tests

Output:

- what exists
- what is missing
- what must be changed

### Step 4: Acceptance Criteria

Define clear criteria:

- user action
- expected behavior
- error behavior
- test proof

### Step 5: Implementation Plan

List files to edit.

Keep the list tight.

If more than 8-10 files are needed, split the task unless the slice genuinely requires it.

### Step 6: Code

Implement using existing patterns.

Avoid unrelated cleanup.

### Step 7: Verify

Run the smallest relevant tests first.

Then run broader checks when risk is higher.

### Step 8: Report Honestly

Final report must say:

- what works
- what was verified
- what was not verified
- what remains

## Zroky Product-Specific Guardrails

## Capture Guardrails

Do not build diagnosis or replay features on incomplete capture.

Before using captured data, confirm:

- `call_id` exists
- `trace_id` exists when needed
- agent/workflow fields exist
- model/provider captured
- prompt version captured if comparing prompts
- tool spans captured if diagnosing tool behavior
- retrieval spans captured if diagnosing RAG behavior
- outcome captured if claiming task success/failure

If missing, UI should say what instrumentation is missing.

## Diagnosis Guardrails

Every diagnosis must include:

- failure code
- confidence
- evidence
- affected scope
- next action

Never show an unsupported root cause as fact.

Use language like:

- "Likely cause"
- "Evidence suggests"
- "Not enough data"

when confidence is not high.

## Issue Guardrails

Issues are actionable failure groups.

An issue should not be created from one weak signal unless:

- severity is high
- user manually creates it
- detector confidence is high

Issue pages must avoid raw-noise-first design.

Every issue should answer:

> What broke, who is affected, why likely, and what next?

## Replay Guardrails

Never call stub replay a verified fix.

Replay modes must be clearly labeled:

- stub
- mocked-tool
- live-sandbox
- shadow

Replay result must show:

- what was replayed
- what changed
- pass/fail
- evidence
- limitations

## Golden Guardrails

Goldens are regression memory.

A golden should include:

- source issue or trace
- expected behavior
- evaluator
- priority
- owner
- last result

Do not let the UI show "healthy" when critical workflows have no goldens.

## Fix Verification Guardrails

A fix is verified only when:

- original replay passes
- relevant goldens pass
- major cost/latency regression is absent or accepted
- evidence is linked

Dry-run PRs must be labeled dry-run.

Auto-generated patches must be treated as candidates, not truth.

## CI Guardrails

CI must be part of the product.

For reliability-critical code:

- avoid `|| true` soft gates
- avoid ignored type failures
- avoid ignored security failures
- keep schema drift checks strict
- keep file-size lint meaningful

Zroky should hold itself to the reliability standard it sells.

## Dashboard Guardrails

Default mode should be simple.

Every page must have:

- one primary question
- one primary action
- plain-English status
- progressive disclosure for advanced details

Avoid:

- raw JSON first
- database-browser UI
- charts without next action
- expert-only language
- scattered workflows

Use the primary dashboard nav:

- Failure Inbox
- Issues
- Replay Lab
- Goldens
- CI Gates
- Cost
- Settings

Keep Traces, Calls, Drift, Alerts, Ask Zroky, and admin views as secondary surfaces unless they directly support the primary loop.

## Ask Zroky Guardrails

Ask Zroky must be evidence-grounded.

Every answer must include:

- conclusion
- confidence
- evidence links
- affected scope
- recommended next action

If evidence is missing, Ask Zroky should say:

> Not enough data.

It should not invent root causes.

## Stop Conditions

Stop and clarify before coding if:

- product requirement conflicts with current architecture
- data model needed for the feature does not exist
- feature requires real credentials or external service setup
- "verified" cannot be proven locally
- user changes conflict with the required edit
- implementation would require broad refactor outside the task

## Completion Checklist

Before saying a task is complete:

- [ ] Codebase was searched/read first.
- [ ] Scope was kept tight.
- [ ] Product loop mapping is clear.
- [ ] API/schema contracts match.
- [ ] UI has loading, error, empty, and success states where relevant.
- [ ] Tests were added or existing tests cover the change.
- [ ] Relevant verification commands were run.
- [ ] Stub/dry-run/partial behavior is labeled honestly.
- [ ] No unrelated files were changed.
- [ ] Final report includes proof and limitations.

## Final Rule

Build only what can be proven.

If it cannot be proven, label it honestly.

If it does not help users diagnose, replay, verify, or prevent production agent failures, it is not core Zroky.
