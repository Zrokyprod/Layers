# Zroky MVP Lock Document

File: docs/MVP_LOCK.md
Status: Locked for MVP Execution
Owner: Zroky Product + Engineering
Purpose: Prevent feature drift, protect product clarity, and force all engineering work around the core
monetizable loop.

## 0. Why This Document Exists

Zroky has been built fast through AI-assisted / vibe-coding execution. That helped us explore many product
directions quickly, but it also created a risk:

The product can become a collection of many impressive modules instead of one sharp
developer workflow.

This document locks the MVP scope.

From this point, Zroky should not be developed as a broad AI observability platform, analytics dashboard,
or general agent monitoring suite.

Zroky must be developed as:

An AI Agent Failure Replay + Fix Verification Platform.

The product must help developers and AI teams answer five questions:

1. Did the agent fail?
2. Why did it fail?
3. Can we reproduce the failure?
4. Did the fix actually work?
5. Will this failure happen again after deployment?

If a feature does not directly support one of these five questions, it is outside the MVP.

## 1. Locked Product Positioning

### 1.1 What Zroky Is

Zroky is a reliability layer for production AI agents.

It captures real production agent calls, detects silent failures, diagnoses root causes, replays failed
scenarios, verifies whether fixes work, converts important cases into Goldens, and blocks regressions in CI.

### 1.2 Locked One-Line Positioning

Zroky turns failed production AI agent calls into verified fixes and regression tests.

### 1.3 Locked Developer Pitch

When your AI agent returns 200 OK but fails the actual task, Zroky captures the trace,
diagnoses the root cause, replays the same scenario after your fix, verifies pass/fail,
and turns the case into a Golden regression test.

### 1.4 Locked Enterprise Pitch

Zroky reduces production risk in AI agents by continuously capturing failures, verifying
fixes, and blocking regressions before deployment.

### 1.5 What Zroky Is Not

Zroky is not:

- a generic AI observability dashboard
- a cost analytics dashboard
- a LangSmith clone
- a generic logs viewer
- a prompt playground
- a generic evaluation platform
- a BI dashboard for LLM usage
- a general customer support tool
- a general DevOps alerting system
- an autonomous coding agent first

Zroky may have analytics, traces, alerts, recommendations, PR generation, and dashboards, but these are
supporting features. They are not the product center.

## 2. Locked Product Spine

Every MVP engineering task must map to this product spine:

SDK captures production AI agent call
-> Backend ingests and stores call/trace
-> Diagnosis detects failure

-> Issue groups repeated failures
-> Replay reruns the failed case
-> Verification proves fix pass/fail
-> Golden stores the fixed behavior as regression test
-> CI Gate blocks future regressions

This is the only MVP spine.

Any work outside this spine must be explicitly marked as:

non_mvp
hidden
future
enterprise_later

## 3. MVP Success Definition

The MVP is successful only when a developer can complete this workflow:

### 3.1 Required Demo Flow

1. Developer installs SDK.
2. AI agent call is captured.
3. Agent silently fails in production.
4. Zroky detects failure.
5. Zroky groups similar failures into an Issue.
6. Developer opens Issue Detail.

7. Developer sees:

8. what failed

9. why it failed
10. evidence
11. affected calls
12. suggested fix
13. Developer clicks Replay.
14. Developer changes prompt/model/config or provides candidate fix.
15. Zroky replays the same failed case.

16. Zroky shows:

17. original failed output

18. candidate output
19. output diff
20. tool behavior diff
21. cost delta
22. latency delta
23. verification status
24. Developer confirms fix.
25. Developer converts verified case into Golden.
26. GitHub CI later runs Goldens.
27. CI blocks a PR when the same flow regresses.

If this workflow is not smooth, the MVP is not ready.

## 4. MVP Included Modules

The following modules are included in MVP and must be hardened.

### 4.1 SDK Capture

Purpose

Capture production AI agent behavior safely and non-blockingly.

Included SDK Capabilities

- LLM call capture
- prompt/message capture
- response capture
- tool call capture
- retrieval/RAG capture
- memory operation capture
- trace ID
- parent call ID
- workflow ID
- workflow name
- agent name
- prompt version
- environment
- model/provider
- status
- latency
- token usage
- cost estimation
- output fingerprint

- prompt fingerprint
- PII masking
- async queue
- local fallback behavior
- outcome capture

MVP Requirement

SDK integration must take less than 5 minutes.

Developer Experience Target

Python:

import zroky

zroky.init(
api_key="...",
project="refund-agent-prod",
environment="production"
)

response = zroky.call(
provider="openai",
model="gpt-4o-mini",
messages=[
{"role":    "user",    "content":    "Where is my refund?"}
]
)

JavaScript:

import OpenAI from "openai";
import { init, wrap } from "@zroky/sdk";

init({
projectId: process.env.ZROKY_PROJECT_ID,
apiKey: process.env.ZROKY_API_KEY,
});

const openai = wrap(new OpenAI(), {
agentName: "refund-agent",
environment: "production",
});

Non-Negotiable Rule

SDK must never break the customer's production call path.

If Zroky ingest fails, the customer's AI call must still work.

### 4.2 Ingest API

Purpose

Accept SDK/gateway events, normalize them, persist calls, and enqueue diagnosis.

Included

- /v1/ingest
- schema validation
- event normalization
- idempotency
- rate limiting
- PII masking
- cost enrichment
- call creation
- diagnosis job creation
- async diagnosis enqueue
- usage metering
- tenant/project isolation

MVP Requirement

Every valid captured call must create:

1. Call
2. optional DiagnosisJob
3. usage metering record

Failure Handling

If duplicate event:

status = duplicate

If quota exceeded:

status = rejected
reason = quota_exceeded
upgrade_required = true

If diagnosis queue fails:

call should still be stored
diagnosis should be retryable

### 4.3 Diagnosis Engine

Purpose

Convert raw calls into actionable failure detection.

Included Failure Categories

MVP must support at least:

TOOL_NOT_CALLED
WRONG_TOOL_SELECTED
TOOL_ARGUMENT_INVALID
TOOL_CALL_FAILURE
SCHEMA_VALIDATION_FAILED
LOOP_DETECTED
CONTEXT_OVERFLOW
RAG_CONTEXT_MISSING
EMPTY_OUTPUT
OUTPUT_TRUNCATED
HALLUCINATION_RISK
BUSINESS_OUTCOME_MISSING
RATE_LIMIT
AUTH_FAILURE
PROVIDER_ERROR
COST_SPIKE
LATENCY_DRIFT

Diagnosis Output Must Include

{
"failure_code": "TOOL_NOT_CALLED",

"severity": "high",
"confidence": 0.91,
"summary": "Refund agent did not call get_refund_status and returned generic
refund policy.",
"evidence": [],
"suggested_fix":
"Add explicit instruction to call get_refund_status when user asks for refund
status.",
"replay_recommended": true,
"replay_mode_recommendation": "mocked_tool"
}

Non-Negotiable Rule

Diagnosis must be developer-actionable.

Bad:

Agent quality issue detected.

Good:

The agent failed because it selected search_docs instead of get_refund_status.

### 4.4 Issue Grouping

Purpose

Group repeated failures into customer-facing issues.

Public Object

The public customer-facing object is:

Issue

Internal Object

The internal detector/anomaly object may be:

Anomaly

But dashboard must show:

Issue

Not:

Anomaly

Issue Grouping Key

Default grouping key:

project_id
failure_code
prompt_fingerprint
agent_name
workflow_name
tool_name if available

Issue Must Include

{
"issue_id": "...",
"title": "Refund agent did not call refund status API",
"failure_code": "TOOL_NOT_CALLED",
"severity": "high",
"status": "open",
"agent_name": "refund-agent",
"occurrence_count": 38,
"first_seen_at": "...",
"last_seen_at": "...",
"sample_call_id": "...",
"sample_evidence": {},
"blast_radius_usd": 1240.00,
"recommended_action": "Replay this issue with mocked tool outputs"
}

Issue Statuses

open
acknowledged
resolved
ignored
muted

MVP UI Requirement

Issue Detail page must answer:

1. What failed?
2. Why?
3. How many users/calls affected?
4. What evidence proves it?
5. What should developer do next?
6. Can it be replayed?

### 4.5 Replay Runs

Purpose

Reproduce failed scenarios and verify whether candidate fixes work.

Included Replay Modes

stub
real_llm
mocked_tool
live_sandbox
shadow

Replay Mode Definitions

Stub Replay

Re-grades recorded output.

Allowed for:

- sanity check
- judge calibration

- historical scoring

Not allowed for:

- verified fix
- CI pass
- proving prompt/model/RAG changes

Real LLM Replay

Reruns the source call against a live model with optional candidate prompt/model override.

Allowed for:

- prompt comparison
- model comparison
- output-level verification

Mocked Tool Replay

Reruns model with frozen captured tool outputs.

Allowed for:

- deterministic replay
- safe tool behavior comparison
- prompt/model verification without side effects

Live Sandbox Replay

Runs replay through a customer-controlled sandbox worker.

Allowed for:

- strongest workflow verification
- real tool execution in safe environment
- enterprise/pro verification

Shadow Replay

Runs baseline and candidate side-by-side.

Allowed for:

- PR comparison
- production-safe evaluation
- enterprise rollout testing

### 4.6 Replay Trust Rules

Rule 1: Stub Replay Cannot Verify Fix

If:

replay_mode = stub

Then:

{
"verified_fix": false,
"verification_status": "stub_only",
"replay_confidence_level": "low",
"warning": "Stub replay re-graded recorded output. It did not rerun the
agent."
}

Never return:

{
"verified_fix": true
}

for stub replay.

Rule 2: Real Verification Requires Actual Candidate Output

A fix can be verified only if:

candidate_output exists
AND replay_mode is real_llm OR mocked_tool OR live_sandbox OR shadow
AND judge/deterministic criteria pass

Rule 3: Tool Replay Must Show Evidence

If a failure involves tools, replay result should show:

{
"tool_behavior_diff": {
"expected_tool": "get_refund_status",
"original_tool": "search_docs",
"candidate_tool": "get_refund_status",
"changed": true,
"fixed": true
}
}

Rule 4: Replay Result Must Be Explicit

Allowed verification statuses:

verified_fix
fix_failed
stub_only
not_verified
inconclusive
sandbox_unavailable
tool_snapshot_missing
judge_uncertain
budget_exceeded
provider_error

### 4.7 Golden Creation

Purpose

Turn important fixed production failures into regression tests.

Golden Definition

A Golden is:

A production-derived test case representing expected agent behavior for a critical flow.

Golden Must Store

{
"source_call_id": "...",

"baseline_failed_output": "...",
"expected_output_text": "...",
"criteria_json": {},
"expected_tool_behavior": {},
"expected_cost_usd": 0.01,
"expected_latency_ms": 3000,
"weight": 1.0,
"blocks_ci": true
}

Non-Negotiable Rule

Never automatically treat a failed output as expected behavior.

If original call failed, store original response as:

baseline_failed_output

Not:

expected_output_text

Golden Creation Flow

Allowed:

Replay passed
-> Developer confirms behavior
-> Golden created

Not allowed:

Failed call captured
-> Original failed output automatically becomes Golden expected output

Golden Statuses

draft
active
needs_review

drift_suspected
deprecated

Golden Drift

Golden drift means expected behavior may be outdated.

If a Golden fails but new behavior may be correct, status should become:

drift_suspected

Not automatically:

agent_failed

### 4.8 Regression CI Gate

Purpose

Block bad AI agent changes before merge/deployment.

Included

- GitHub Action client
- backend regression CI route
- replay sampling
- PR comment
- pass/fail/not_verified statuses
- blocking mode by plan

CI Statuses

pass
fail
error
not_verified
skipped

Non-Negotiable Rule

CI cannot pass if no real comparison happened.

If candidate resolver used baseline/default/stub output, return:

{
"status": "not_verified",
"reason": "real_comparison_not_enabled"
}

Not:

{
"status": "pass"
}

PR Comment Must Show

Zroky Regression CI

Status: failed / passed / not verified

Protected flows checked:
- refund_status_check
- billing_support_json_schema
- onboarding_agent_tool_selection

Failures:
- Refund status check regressed: refund tool not called

Replay evidence:
- Replay mode: mocked_tool
- Confidence: high
- Output diff: available
- Tool diff: available

Action:
Do not merge until replay passes.

## 5. MVP Excluded Modules

These modules may remain in code but must be hidden from primary MVP UX.

### 5.1 Hidden Until Later

advanced_provider_drift
ablation_engine
advanced_recommendations
autonomous_pr_generation
complex_judge_calibration_dashboard
advanced_outcome_attribution_dashboard
enterprise_governance_dashboard
billing_polish_beyond_plan_enforcement
advanced_analytics_dashboard

### 5.2 Why Hidden

They may be valuable, but they distract from the paid core loop.

The MVP cannot feel like:

a giant AI operations dashboard

It must feel like:

a failure-fix-prevention workflow

## 6. Dashboard Lock

### 6.1 Primary Navigation

MVP dashboard primary nav is locked as:

Failure Inbox
Issues
Replay Lab
Goldens
CI Gates
Traces
Settings

### 6.2 Hidden / Secondary Navigation

These should not appear as primary MVP nav items:

Provider Drift
Ablation
Recommendations
Advanced Analytics
Judge Calibration
Outcome Attribution
Billing Experiments
Rollback Drill
Feature Voting

They can exist as:

/settings/advanced
/internal
/enterprise
/labs

or be feature-flagged.

### 6.3 Dashboard Home

Dashboard home must be:

Failure Inbox

Not:

Analytics Overview

Failure Inbox Sections

Critical open issues
Silent failures detected
Pending replay runs
Failed CI gates

Goldens needing review
Usage / plan limit status

Failure Inbox Table

Columns:

Severity
Issue
Failure Code
Affected Calls
Agent
Last Seen
Replay Status
Primary Action

Primary action should be one of:

View Issue
Replay
Create Golden
Resolve
Upgrade

### 6.4 Issue Detail Page

Must include:

Issue summary
Root cause
Evidence timeline
Sample trace
Affected calls
Suggested fix
Replay CTA
Golden CTA
Triage controls
Plan lock/upgrade state

Required CTA Priority

1. Replay this issue
2. Create Golden
3. Resolve / Ignore
4. Create GitHub issue/PR

### 6.5 Replay Lab Page

Replay Lab is the core "wow" screen.

Required Layout

Left: Original Failure
Right: Candidate Replay
Bottom: Verification Result

Original Failure Panel

Show:

input
original output
failure reason
tool behavior
retrieval context
cost
latency
model/provider

Candidate Replay Panel

Show:

candidate prompt/model/config
candidate output
candidate tool behavior
cost
latency
errors

Verification Panel

Show:

verification_status
replay_mode
replay_confidence_level
output_diff
tool_behavior_diff
cost_delta
latency_delta
judge_confidence
warning if any

CTA Logic

If verified_fix:
enable Create Golden

If stub_only:
disable Create Golden unless expected criteria manually entered

If fix_failed:
suggest modify prompt/model/config and rerun

If inconclusive:
show reason and recommended next replay mode

### 6.6 Goldens Page

Must show:

Golden Sets
Golden Traces
Last run status
Blocks CI
Drift suspected
Owner
Last updated
Replay history

Golden Detail

Must show:

source trace
expected behavior
required tool behavior
criteria JSON UI builder
cost/latency bounds
CI usage
last failures
drift state

### 6.7 CI Gates Page

Must show:

Recent PR runs
Status
Git SHA
PR link
Regression rate
Failed Goldens
Not verified warnings
PR comment preview
Replay links

CI Status Meaning

pass = real/mocked/sandbox comparison completed and under threshold
fail = regressions exceeded threshold
error = infrastructure/provider/system problem
not_verified = no real comparison happened
skipped = plan/config disabled

## 7. Plan Lock

Zroky uses four plans:

Free / Watch
Pilot
Pro
Enterprise

### 7.1 Free / Watch

Purpose

Build trust and adoption.

User

Individual developer, OSS user, early tester.

Promise

"Capture what happened."

Included

OSS SDK
local capture
local JSON export
cloud trace ingestion limited
basic trace view
prompt fingerprint
tool/retrieval/memory capture
PII masking
basic warnings

Not Included

root-cause diagnosis
issue grouping
real replay
mocked-tool replay
live sandbox replay
Goldens
CI gate
team workflow

Slack/GitHub alerts
outcome attribution

Suggested Limits

projects = 1
members = 1
cloud_calls_per_month = 3,000
retention_days = 7
diagnosis_jobs_per_month = 0 or basic hints only
real_replay_runs_per_month = 0
golden_traces = 0
ci_gates = 0

Free Upgrade Hooks

Show:

317 likely failures detected.
Upgrade to Pilot to group issues, diagnose root cause, and replay fixes.

### 7.2 Pilot

Purpose

First paid team plan.

User

Small AI startup or agent team.

Promise

"Diagnose failures and replay fixes."

Included

hosted traces
Failure Inbox
issue grouping
root-cause diagnosis
one-click replay

stub replay clearly labeled
limited real LLM replay
limited mocked-tool replay
basic Goldens
Slack/GitHub alerts
30-day retention

Suggested Limits

projects = 2
members = 5
cloud_calls_per_month = 50,000
diagnosis_jobs_per_month = 10,000
real_replay_runs_per_month = 100
mocked_tool_replay_runs_per_month = 100
golden_traces = 100
ci_gate_mode = non_blocking
retention_days = 30

Not Included

blocking CI
live sandbox replay
shadow replay
private replay worker
SSO
audit logs
custom retention

### 7.3 Pro

Purpose

Serious production reliability.

User

AI product teams shipping agents to real users.

Promise

"Prevent regressions before deployment."

Included

everything in Pilot
higher trace volume
real LLM replay
mocked-tool replay
live sandbox replay
shadow replay
Golden sets
blocking GitHub CI gate
PR comments
team assignment
advanced issue triage
outcome attribution
replay budget controls
90-day retention

Suggested Limits

projects = 10
members = 25
cloud_calls_per_month = 1,000,000
diagnosis_jobs_per_month = 250,000
real_replay_runs_per_month = 2,000
mocked_tool_replay_runs_per_month = 5,000
live_sandbox_replay_runs_per_month = 1,000
golden_traces = 5,000
ci_gates = unlimited fair use
retention_days = 90

### 7.4 Enterprise

Purpose

Governance, security, private infra.

User

Large companies.

Promise

"Run agent reliability verification at enterprise scale."

Included

everything in Pro
private replay worker
VPC/self-host option
SSO/SAML
audit logs
custom retention
provider key vault
custom detectors
custom judge policy
dedicated support
security review package
SLA

Limits

custom
annual contract
custom deployment

## 8. Entitlement Lock

All features must be gated by entitlement keys.

### 8.1 Entitlement Keys

watch.cloud_capture
watch.basic_trace_view

pilot.failure_inbox
pilot.issue_grouping
pilot.root_cause_diagnosis
pilot.replay_stub
pilot.replay_real_llm
pilot.replay_mocked_tool
pilot.goldens_basic
pilot.alerts_basic

pro.replay_live_sandbox
pro.replay_shadow
pro.ci_gate_nonblocking

pro.ci_gate_blocking
pro.outcome_attribution
pro.team_workflow
pro.advanced_goldens

enterprise.private_replay_worker
enterprise.sso
enterprise.audit_logs
enterprise.custom_retention
enterprise.provider_key_vault
enterprise.custom_detectors

### 8.2 Numeric Limits

Each plan should define:

{
"max_projects": 1,
"max_members": 1,
"max_calls_per_month": 3000,
"max_diagnosis_jobs_per_month": 0,
"max_real_replay_runs_per_month": 0,
"max_mocked_tool_replay_runs_per_month": 0,
"max_live_sandbox_replay_runs_per_month": 0,
"max_golden_traces": 0,
"retention_days": 7
}

### 8.3 Entitlement Enforcement Points

Must enforce at:

ingest
diagnosis
issues
replay run creation
replay mode selection
golden creation
CI gate dispatch
team invite
retention/export

provider key vault
private replay worker

## 9. API Trust Contract

### 9.1 Replay API Must Return

Every replay run detail must include:

{
"run_id": "...",
"status": "pass",
"replay_mode": "mocked_tool",
"verification_status": "verified_fix",
"verified_fix": true,
"replay_confidence_level": "high",
"warning": null,
"output_diff": {},
"tool_behavior_diff": {},
"cost_delta_usd": -0.001,
"latency_delta_ms": 420
}

### 9.2 Stub Replay Response Example

{
"run_id": "...",
"status": "pass",
"replay_mode": "stub",
"verification_status": "stub_only",
"verified_fix": false,
"replay_confidence_level": "low",
"warning": "Stub replay re-graded the recorded output. It did not rerun the
agent or verify a fix."
}

### 9.3 CI Not Verified Response Example

{
"run_id": "...",

"status": "not_verified",
"reason": "real_comparison_not_enabled",
"message": "This CI run did not execute real comparison replay, so it cannot
prove this PR is safe."
}

## 10. Coding Rules for Codex / AI Agents

All AI coding agents must follow these rules.

### 10.1 Do Not Add New Product Modules

Unless explicitly approved, do not add:

new analytics pages
new AI recommendation systems
new autonomous PR systems
new drift pages
new ablation pages
new billing experiments
new generic dashboards

### 10.2 Prefer Hardening Existing Core

Prioritize:

SDK capture reliability
ingest correctness
diagnosis correctness
issue grouping
replay trust semantics
Golden criteria
CI gate correctness
dashboard core flow
plan enforcement

### 10.3 Every PR Must State Product Spine Mapping

Every PR description must include:

Product spine area:
- Capture
- Diagnose
- Issue
- Replay
- Verify
- Golden
- CI

If no area applies, the PR is probably non-MVP.

### 10.4 Tests Required for Trust-Sensitive Work

Any changes to replay, Golden, CI, diagnosis, or entitlements must include tests.

## 11. P0 Engineering Tasks

These must be completed before serious launch.

### P0.1 Stub Replay Trust Fix

Problem

Stub replay can be misunderstood as verified fix.

Required Change

Stub replay must always return:

verification_status = stub_only
verified_fix = false

Acceptance Criteria

- Unit test proves stub replay never returns verified fix.
- UI displays warning.
- API response includes replay confidence.

### P0.2 Regression CI Not Verified Fix

Problem

Regression CI may pass if baseline/default resolver is used.

Required Change

If no real candidate comparison happened, CI returns:

status = not_verified

Acceptance Criteria

- No real comparison cannot produce pass.
- GitHub Action handles not_verified.
- PR comment explains why.

### P0.3 Golden Expected Behavior Fix

Problem

Failed output may become expected output.

Required Change

Separate:

baseline_failed_output
expected_output_text
criteria_json

Acceptance Criteria

- Failed call cannot create active Golden without expected behavior.
- Draft Golden allowed.
- UI prompts developer to define expected behavior.

### P0.4 GitHub Action Changed Files Fix

Problem

GitHub Action may not collect changed files automatically.

Required Change

Action should use GitHub API to list PR files and include paths/hunks.

Acceptance Criteria

- Works without ZROKY_CHANGED_FILES_JSON .
- Sends changed files to backend.
- README updated.

### P0.5 Issue vs Anomaly Clarification

Problem

Customer-facing and internal grouping concepts overlap.

Required Change

Lock:

Issue = customer-facing
Anomaly = internal detector group

Acceptance Criteria

- Dashboard uses Issue language.
- API docs clarify relationship.
- No customer-facing page says Anomaly.

## 12. P1 Engineering Tasks

### P1.1 Entitlement Catalog

Centralize plan capabilities.

### P1.2 Plan-Based Usage Limits

Enforce limits for:

calls
diagnosis jobs
replay runs
real replay
Goldens
CI gates
retention
members
projects

### P1.3 Dashboard Feature Gates

Add plan-aware UI gates.

### P1.4 Failure Inbox

Make it default dashboard home.

### P1.5 Replay Lab

Build before/after replay comparison UI.

### P1.6 Goldens Page

Show protected flows and criteria.

### P1.7 CI Gates Page

Show PR safety status.

## 13. P2 Engineering Tasks

These come after MVP is stable.

provider drift
ablation intelligence
advanced recommendations

outcome attribution dashboard
autonomous PR generation
enterprise governance dashboard
judge calibration UI

## 14. Launch Readiness Checklist

Zroky is not launch-ready until all are true:

Capture

SDK integration works in <5 minutes
ingest stores calls reliably
PII masking works
calls are grouped by trace/workflow

Diagnose

diagnosis job created after ingest
failure codes are actionable
issues are created/grouped
issue detail is clear

Replay

stub is labeled correctly
real replay works
mocked-tool replay works
replay result shows before/after diff
verified_fix only possible with real comparison

Golden

verified replay can become Golden
failed output is not expected output
Golden criteria can be edited
Golden can block CI

CI

GitHub Action collects changed files
CI cannot pass without real comparison
PR comment is clear
blocking mode works for Pro

Plans

Free limits enforced
Pilot unlocks diagnosis/replay
Pro unlocks CI blocking/live replay
Enterprise unlocks private/security features

Dashboard

Failure Inbox is home
Issue Detail is actionable
Replay Lab is clear
Goldens visible
CI Gates visible
non-MVP modules hidden

## 15. Product Copy Lock

Use these lines consistently.

Homepage Headline

Replay failed AI agent calls. Verify fixes before they hit production again.

Subheadline

Zroky captures silent production failures, diagnoses root causes, replays the exact
scenario against new prompts/models/code, and turns verified fixes into CI regression
gates.

Free Plan Copy

Capture what happened.

Pilot Plan Copy

Diagnose failures and replay fixes.

Pro Plan Copy

Block AI agent regressions before deploy.

Enterprise Plan Copy

Govern AI agent reliability at scale.

OSS Copy

Zroky Watch is the open-source flight recorder for production AI agents.

Paid Cloud Copy

Zroky Pilot/Pro turns captured failures into verified fixes, Goldens, and CI gates.

## 16. What We Will Not Do During MVP

We will not:

- build more generic analytics
- create new dashboards unrelated to failure/fix/prevention
- market as generic observability
- call stub replay a verified fix
- let CI pass without real comparison
- create Goldens from failed outputs without expected criteria
- expose every internal module in dashboard nav
- build autonomous PR generation before replay is trustworthy
- over-optimize billing before product loop works

## 17. Final MVP Principle

The MVP is not a set of features.

The MVP is one reliable loop:

Failed production agent call
-> root cause
-> replay
-> verified fix
-> Golden
-> CI prevention

If this loop is magical, Zroky can become world-class.

If this loop is weak, no amount of dashboards, analytics, recommendations, or AI-generated PRs will matter.

## 18. Final Lock Statement

From this point forward:

Zroky MVP development is locked around failure replay, fix verification, Goldens, and CI
prevention.

Every task, PR, route, page, and model change must support that mission.

The product mission is:

Make AI agent failures reproducible, fixable, and preventable.
