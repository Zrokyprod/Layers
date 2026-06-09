# Zroky Exact Product Blueprint

## One-Line Product

Zroky is the AI Agent Regression Firewall for complex production agents.

Hero promise: Stop shipping the same agent failure twice.

It captures every important agent failure, explains the real root cause, groups it into an issue, turns it into replay proof, promotes trusted proof into a Golden, and prevents the same failure from shipping again through a CI gate.

This is not a generic LLM dashboard.
This is not only tracing.
This is not only evals.
This is not only prompt management.

The product exists for one user problem:

> "My AI agent failed in production. I need to know why, reproduce it, fix it safely, and make sure it never comes back."

Everything in Zroky should serve this loop.

```text
Production agent run
-> capture full execution evidence
-> detect failure or risk
-> diagnose root cause
-> group into issue
-> create replay proof
-> promote a Golden
-> block regression in CI
```

## Product Positioning

### What Zroky Is

Zroky is an AI Agent Regression Firewall.

It is built for teams running real agents in production:

- customer support agents
- coding agents
- sales/research agents
- data analysis agents
- workflow automation agents
- internal ops agents
- multi-agent systems
- RAG-heavy agents
- tool-using agents that take real actions

The user is not looking for another analytics page.
The user is trying to run agents at scale without losing trust, money, or engineering time.

### What Zroky Must Own

Zroky should own four words:

1. Diagnose
2. Replay
3. Verify
4. Prevent

If a feature does not strengthen one of these four words, it is secondary.

### What Zroky Should Not Become

Zroky should not become:

- a generic APM replacement
- a prompt playground first
- a token dashboard first
- a LangSmith clone
- a logging warehouse
- a model leaderboard
- a vague "AI observability" product
- an auto-fix gimmick that opens PRs without proof

Zroky can have observability, traces, costs, dashboards, and evals.
But those are ingredients.
The product is the closed reliability loop.

## The Core User Pain

### Pain 1: Silent Agent Failure

Agents often fail without throwing an exception.

Examples:

- answer is fluent but wrong
- tool call succeeds but business task fails
- retrieved context is irrelevant
- model uses the wrong tool
- agent loops and wastes money
- output violates policy
- response is incomplete after token truncation
- workflow finishes but user outcome is bad

Traditional monitoring sees a successful HTTP 200.
The user sees a broken product.

Zroky must detect both hard failures and silent failures.

### Pain 2: Root Cause Is Hidden

When a complex agent fails, the cause may be:

- prompt version changed
- model behavior drifted
- provider latency increased
- retrieval returned bad chunks
- tool schema changed
- tool output was malformed
- memory carried bad state
- context overflow removed important instruction
- fallback model behaved differently
- judge/eval criteria changed
- user segment shifted

Teams waste hours reading logs manually.

Zroky must answer:

> "What caused this failure, and what evidence proves it?"

### Pain 3: Reproduction Is Hard

Agent failures are not normal deterministic bugs.

To reproduce a real agent failure, the team needs:

- original prompt
- system/developer prompt versions
- user input
- model/provider/config
- tool calls
- tool outputs
- RAG queries
- retrieved chunks
- memory/state
- retry/fallback path
- final output
- outcome/feedback
- timestamps and environment

Without this, every fix is guesswork.

Zroky must convert production incidents into replay cases.

### Pain 4: Fixes Cannot Be Trusted

Prompt fixes and model changes are risky.

A change may fix one failure and break ten other workflows.

Zroky must verify:

- did the fix solve the original incident?
- did it regress golden cases?
- did cost increase?
- did latency increase?
- did tool behavior change?
- did safety/quality degrade?

The product must replace hope with evidence.

### Pain 5: Teams Repeat the Same Failures

Most AI teams manually debug the same classes of failures repeatedly.

Zroky must turn every serious production failure into institutional memory:

- issue cluster
- root cause
- replay test
- golden case
- regression check
- release verification

The strongest product promise:

> "Never ship the same agent failure twice."

## Exact Product Architecture

### 1. Agent Flight Recorder

This is the capture layer.

It must record the full execution story, not only prompt and response.

#### Captured Objects

Agent run:

- run_id
- project_id
- environment
- agent_name
- workflow_name
- session_id
- user_segment
- release_version
- prompt_version
- model/provider versions
- start/end time
- total latency
- total cost
- final status
- outcome signal

Model call span:

- call_id
- parent_run_id
- provider
- model
- model parameters
- input messages
- output
- token usage
- latency
- error
- retry/fallback metadata

Tool call span:

- tool_call_id
- tool_name
- input args
- output
- schema version
- status
- latency
- error
- side-effect marker

Retrieval span:

- retrieval_id
- query
- index name
- retriever version
- document ids
- chunk ids
- scores
- chunk text snapshot or reference
- grounding relevance

Memory/state span:

- memory keys read
- memory keys written
- summarized state
- redacted sensitive values

Outcome:

- user feedback
- task success/failure
- business event
- judge score
- support escalation
- refund/chargeback/action reversal
- manual label

#### How It Solves User Pain

The user no longer asks engineers to reconstruct a failure from logs.
Zroky already has the full black-box recording.

#### Important Product Rule

Capture must be privacy-aware by default:

- PII redaction
- prompt/output sampling controls
- field-level masking
- retention policies
- tenant/project isolation
- opt-out for sensitive tools

No enterprise team will trust Zroky if capture feels unsafe.

### 2. Failure Detection Engine

This engine converts raw traces into meaningful failure signals.

#### Failure Classes Zroky Should Detect

Hard failures:

- provider_error
- rate_limit
- auth_error
- timeout
- tool_exception
- schema_validation_failed
- output_parse_failed
- replay_execution_failed

Silent failures:

- wrong_tool_selected
- hallucinated_tool_args
- tool_output_ignored
- retrieval_miss
- weak_grounding
- context_overflow
- instruction_lost
- agent_loop
- repeated_output
- incomplete_task
- unsafe_action_risk
- prompt_regression
- model_regression
- cost_regression
- latency_regression
- quality_score_drop
- user_outcome_failed

#### Output Of The Engine

Every detected issue should have:

- failure_code
- severity
- confidence
- evidence
- affected agent/workflow
- first_seen
- last_seen
- occurrence count
- example runs
- suspected root cause
- suggested next action

#### How It Solves User Pain

The user does not need to stare at raw traces.
Zroky tells them which failures matter and why.

### 3. Root Cause Diagnosis

Diagnosis is the heart of Zroky.

Detection says:

> "This looks broken."

Diagnosis says:

> "This broke because the retrieval layer returned irrelevant policy chunks after index version 2026-05-20, causing the model to guess refund policy."

#### Diagnosis Types

Prompt diagnosis:

- prompt version introduced regression
- instruction conflicts with tool behavior
- output format instruction is weak
- system prompt lost due context overflow

Model/provider diagnosis:

- provider latency degraded
- model changed behavior
- fallback model produced lower-quality output
- specific model has high schema failure rate

Tool diagnosis:

- tool schema changed
- model hallucinated args
- tool returned malformed output
- agent ignored tool result
- tool side effect succeeded but final answer was wrong

Retrieval diagnosis:

- query rewrite failed
- top chunks irrelevant
- required doc missing
- stale document used
- chunking/indexing created bad context

Memory/state diagnosis:

- stale memory influenced answer
- previous session state leaked
- summarization removed key fact

Outcome diagnosis:

- output passed format checks but failed business outcome
- customer feedback dropped
- judge score dropped for a segment

#### Diagnosis Output

Each diagnosis page must include:

- plain-English root cause
- confidence level
- evidence timeline
- changed variable
- affected scope
- exact examples
- recommended fix path
- replay/golden generation option

#### How It Solves User Pain

The user can move from "something is wrong" to "this is the variable to fix."

### 4. Issue Clustering

Zroky should group related failures into issues.

Raw calls are too noisy.
Issue clusters are actionable.

#### Grouping Keys

Use a combination of:

- failure_code
- agent_name
- workflow_name
- prompt_version
- model/provider
- tool_name
- retriever/index version
- error signature
- output pattern
- user segment
- embedding similarity of failure context

#### Issue Object

An issue should contain:

- issue_id
- title
- severity
- status
- affected workflows
- affected customers/users
- occurrence count
- cost impact
- quality impact
- first seen / last seen
- root cause summary
- representative traces
- replay coverage status
- linked fix attempts
- linked PRs
- owner

#### How It Solves User Pain

The team sees 12 important issues instead of 50,000 traces.

### 5. Replay Case Builder

This is the product wedge.

Every serious issue should become replayable.

#### Replay Case Contains

- original user input
- system/developer prompt version
- model/provider config
- tool mocks or real tool mode
- frozen retrieval context
- memory snapshot
- expected behavior
- pass/fail evaluator
- judge rubric
- deterministic settings where possible
- allowed variance

#### Replay Modes

Stub mode:

- no external model call
- checks stored output against evaluator
- useful for cheap validation and UI demos

Mocked-tool mode:

- real model call
- tool calls replayed with frozen outputs
- best for prompt/model verification

Live-tool sandbox mode:

- real model call
- tools run against sandbox environment
- best for integration validation

Production shadow mode:

- candidate prompt/model runs alongside production
- no side effects
- compares output and behavior

#### How It Solves User Pain

The user can reproduce a production failure without recreating production manually.

### 6. Golden Regression Suite

Goldens are the memory of production failures.

#### Sources Of Goldens

- manually selected critical workflows
- high-severity production failures
- customer-reported failures
- high-cost failures
- policy/safety failures
- flaky nondeterministic cases
- model upgrade comparison cases
- top recurring issue examples

#### Golden Test Object

- golden_id
- source_run_id
- workflow
- scenario title
- input
- frozen context
- evaluator
- expected behavior
- owner
- priority
- last_passed
- last_failed
- linked releases

#### How It Solves User Pain

Every production incident improves the future test suite.
The agent gets safer over time instead of only more complex.

### 7. Fix Verification

Zroky should not be judged by how many fixes it suggests.
It should be judged by how many fixes it proves.

#### Fix Attempt Object

- fix_id
- linked_issue_id
- change type
- changed prompt/tool/retriever/code/model
- author
- before metrics
- after metrics
- replay result
- golden suite result
- cost delta
- latency delta
- quality delta
- safety delta
- PR link
- deployment status

#### Supported Fix Types

- prompt patch
- output schema tightening
- tool schema description improvement
- retry/fallback rule change
- retrieval query rewrite
- retriever/index config change
- model/provider switch
- threshold update
- guardrail update
- code patch

#### Verification Output

The UI should say:

- fixed original issue: yes/no
- regressed goldens: yes/no
- cost impact
- latency impact
- confidence
- evidence traces
- recommendation: merge / hold / needs review

#### How It Solves User Pain

The team can change agents without fear.

### 8. Regression CI

Zroky must plug into engineering workflow.

#### CI Behavior

On PR:

- detect prompt/model/tool/retrieval changes
- run relevant replay cases
- run golden suite subset
- compare against baseline
- comment result on PR
- block merge when critical regressions appear

#### PR Comment Should Show

- pass/fail summary
- changed workflows
- failed goldens
- cost/latency deltas
- top evidence links
- recommended action

#### How It Solves User Pain

Agent reliability becomes part of shipping discipline.
Not a manual dashboard check after users complain.

### 9. Ask Zroky

Ask Zroky should be the fastest path to an answer.

#### It Should Answer

- Why did failures increase yesterday?
- Which prompt version caused this regression?
- Which model is safest for this workflow?
- What broke after the last deploy?
- Which failures are costing us the most?
- Which issues need replay coverage?
- Can we safely upgrade this agent model?
- What should we fix first this week?

#### Answer Format

Every answer should include:

- short conclusion
- evidence
- affected scope
- confidence
- links to traces/issues/replays
- recommended next action

#### It Should Not Do

- answer without evidence
- produce vague summaries
- hallucinate root cause
- hide uncertainty
- act like a chatbot detached from product data

#### How It Solves User Pain

The user gets from question to action without learning every dashboard page.

## Dashboard Product Specification

The dashboard is a reliability control plane.

It should not feel like a marketing analytics page.
It should feel like a production command center for agent reliability.

## Dashboard Experience For Fast-Moving Agent Builders

Zroky should be simple enough for "vibe coding" developers and powerful enough for serious production teams.

Many agent builders are not full-time reliability engineers.
They are moving fast, shipping agent workflows quickly, changing prompts often, testing tools, switching models, and debugging by instinct.

The dashboard must help them run agents smoothly without forcing them to learn observability vocabulary first.

### Product Principle

The dashboard should always answer:

> "What is wrong, why is it wrong, and what should I do next?"

Not:

> "Here are 30 charts. Interpret them yourself."

### Default Mode: Simple

The default dashboard experience should be Simple Mode.

Simple Mode shows:

- agent health
- top problems
- plain-English root cause
- suggested next action
- replay/fix buttons
- cost and latency warnings only when actionable
- setup guidance when instrumentation is missing

Simple Mode hides:

- raw JSON
- complex filters
- statistical tuning
- internal detector confidence math
- advanced infrastructure metrics
- noisy span details unless the user opens a trace

### Advanced Mode: Expert

Advanced Mode should exist, but it should not be the default.

Advanced Mode shows:

- full trace details
- raw spans
- evaluator configuration
- detector thresholds
- replay environment details
- model/provider comparison tables
- redaction and sampling controls
- export/debug tools

This allows advanced teams to go deep without making the first experience heavy.

### First-Run Experience

The first dashboard screen should not be an empty analytics page.

It should guide the developer through:

1. Create project.
2. Copy SDK snippet.
3. Send first agent run.
4. Confirm captured data.
5. Show what is missing:
   - tool calls not captured
   - retrieval spans not captured
   - outcome signals missing
   - prompt version missing
6. Offer one-click fixes or code snippets.
7. Show first useful trace.
8. Suggest first replay/golden only after enough data exists.

### Everyday Experience

For a fast-moving developer, the dashboard should feel like this:

```text
Open Zroky
-> see whether my agent is healthy
-> see the top 3 things hurting users or cost
-> click one issue
-> read the plain-English root cause
-> create replay
-> test fix
-> ship with confidence
```

The user should not need to know where logs live, how traces are structured, or which metric to query.

### Friendly Language

The dashboard should use product language, not infrastructure language.

Use:

- "Your refund agent is looping"
- "This prompt version increased schema failures"
- "This issue has no replay coverage"
- "This fix passed 18/20 goldens"
- "Tool output was ignored by the model"

Avoid as primary UI language:

- "span cardinality"
- "p95 histogram bucket"
- "embedding cluster anomaly"
- "detector threshold exceeded"
- "statistical drift coefficient"

Advanced users can still access those details.
They should not be the first layer.

### Guided Actions

Every important screen should have one obvious next action.

Examples:

- Issue without replay: "Create replay"
- Replay passed: "Promote to golden"
- Golden failed in PR: "Open failed case"
- Cost spike: "Find wasted failed runs"
- Drift detected: "Run affected replay suite"
- Missing instrumentation: "Add tool-call capture"
- Fix attempt passed: "Open verified PR"

The dashboard should never leave the user thinking:

> "Okay, now what?"

### Secondary Agent View

Zroky can have an agent-level support view for non-expert users, but the default product surface is the Failure Inbox.

It should show each agent as a simple row/card:

- agent name
- health status
- latest issue
- success rate
- cost per successful task
- replay coverage
- last deploy impact
- recommended action

Clicking an agent opens:

- workflows
- issues
- traces
- replays
- goldens
- model/prompt versions
- setup quality

This makes Zroky feel like an agent operations product, not a generic telemetry explorer.

### Smooth Agent Running Experience

The dashboard should help users run agents smoothly by making the operational loop obvious:

1. Build agent.
2. Connect SDK.
3. Watch first runs.
4. Detect failures.
5. Create replay.
6. Add golden.
7. Change prompt/model/tool.
8. Verify fix.
9. Ship.
10. Monitor after deploy.

This should be visible in the UI as a progress path, especially for new projects.

### Empty States

Empty states should be useful, not decorative.

Examples:

No traces:

> "No agent runs captured yet. Install the SDK or gateway to send your first run."

No issues:

> "No active issues found. Add outcome tracking to detect silent failures."

No replays:

> "No replay cases yet. Create one from a failed trace or issue."

No goldens:

> "No regression goldens yet. Promote important replays to prevent repeat failures."

No outcomes:

> "Zroky can see technical success, but not task success yet. Add outcome signals."

### UI Complexity Rule

Each screen should have:

- one primary question
- one primary action
- one clear status
- progressive disclosure for details

If a module needs many controls, hide them behind:

- filters drawer
- advanced tab
- compare mode
- settings panel

Do not make the default dashboard feel like a database browser.

### Best User Feeling

The ideal user reaction should be:

> "I do not fully understand reliability engineering, but I know what is wrong with my agent and what to do next."

That is the friendly dashboard standard.

Primary navigation should be organized around the Phase 1 contract:

1. Failure Inbox
2. Issues
3. Replay Lab
4. Goldens
5. CI Gates
6. Cost
7. Settings

Secondary diagnostic surfaces such as Traces, Calls, Drift, Alerts, Ask Zroky, and admin views can exist when they support the primary loop, but they should not dominate the nav.

## Module 1: Failure Inbox

### User Problem

"Which production agent failures need attention first?"

### Shows

- reliability score by project
- top failing agents/workflows
- open critical issues
- new regressions in last 24h
- silent failure rate
- cost per successful task
- replay coverage percentage
- recent deployments and reliability impact
- drift warnings
- golden suite health
- alerts needing owner

### Primary Actions

- open top issue
- ask "why did this spike happen?"
- create replay coverage for uncovered issue
- assign issue owner
- open latest regression report

### Does Not Show

- raw trace table as the first experience
- vanity token charts
- generic "number of requests" as the main metric
- marketing-style summary cards with no action

### Success Criteria

An engineering lead should know within 60 seconds:

- what is broken
- how serious it is
- who/what is affected
- what action to take next

## Module 2: Issues

### User Problem

"I do not want 50,000 traces. Show me the actual failure groups I need to fix."

### Shows

- issue list grouped by root failure pattern
- severity
- status
- owner
- affected agent/workflow
- occurrence trend
- first seen / last seen
- customer/user impact
- cost impact
- confidence
- replay coverage status
- linked fix status

### Issue Detail Shows

- issue title
- root cause summary
- evidence timeline
- representative traces
- affected versions
- affected segment
- suspected changed variable
- related issues
- suggested fix paths
- "Create replay case" action
- "Add to goldens" action
- "Open fix attempt" action

### Primary Actions

- assign owner
- create replay
- mark as known/accepted risk
- link to deploy
- create fix attempt
- close only when verified by replay or monitoring

### Does Not Show

- every raw call by default
- low-confidence guesses as facts
- generic stack traces without product interpretation

### Success Criteria

The user should not ask "where do I start?"
The issue page should prioritize work automatically.

## Module 3: Traces

### User Problem

"I need to inspect exactly what happened during this agent run."

### Shows

- full agent execution timeline
- model calls
- prompts and outputs
- tool calls and outputs
- retrieval queries and chunks
- memory reads/writes
- retries/fallbacks
- token usage
- latency
- cost
- errors
- outcome/feedback
- redaction status

### Trace Detail Should Highlight

- where failure likely started
- span that caused downstream failure
- lost instruction/context
- wrong tool choice
- malformed tool args
- irrelevant retrieval chunk
- output format break
- cost/latency anomaly

### Primary Actions

- copy sanitized evidence
- create issue from trace
- add trace to existing issue
- create replay from trace
- add to golden suite
- compare with successful trace

### Does Not Show

- unredacted sensitive content unless permission allows
- trace data without relation to issue/outcome
- confusing nested JSON as the main view

### Success Criteria

An engineer can understand one failed run without opening logs, database, and provider dashboard separately.

## Module 4: Replay Lab

### User Problem

"Can I reproduce this production failure and test a fix safely?"

### Shows

- replay cases
- source issue/run
- replay mode
- evaluator/rubric
- expected behavior
- latest result
- pass/fail trend
- baseline vs candidate comparison
- diff of output/tool behavior
- cost/latency deltas

### Replay Detail Shows

- frozen input/context
- tool mocks
- retrieval snapshot
- model/provider config
- evaluator config
- previous runs
- candidate runs
- failure explanation

### Primary Actions

- run replay
- compare prompt versions
- compare model versions
- switch replay mode
- promote to golden
- attach replay to PR

### Does Not Show

- generic playground for random prompts
- live production side-effect tools without sandbox warning
- pass/fail without evidence

### Success Criteria

The user can reproduce the incident and know whether a candidate change fixes it.

## Module 5: Goldens

### User Problem

"How do I make sure old failures do not come back?"

### Shows

- golden regression suite
- scenario title
- source production incident
- workflow/agent
- priority
- owner
- evaluator
- last result
- failure history
- linked releases
- coverage by workflow

### Primary Actions

- create golden from issue
- edit evaluator
- run suite
- run selected subset
- attach suite to CI
- mark flaky
- require for release

### Does Not Show

- synthetic evals with no production relevance as the main asset
- giant unreadable test outputs
- green status when high-priority workflows have no coverage

### Success Criteria

Every important production failure becomes a permanent regression guard.

## Secondary Module: Gated Fix Review

### User Problem

"Which proposed fixes are reviewed, verified, and safe to consider?"

### Shows

- open fix attempts
- linked issue
- change type
- owner
- PR status
- replay result
- golden result
- cost delta
- latency delta
- quality delta
- confidence
- reviewable recommended action

### Fix Detail Shows

- before/after behavior
- exact changed prompt/tool/code/model
- replay evidence
- failed goldens if any
- risk summary
- PR link
- deployment status
- post-deploy monitoring

### Primary Actions

- run verification
- request review
- open PR only when enabled by policy
- mark as unsafe
- re-run after changes
- monitor after deploy

### Does Not Show

- "auto-fixed" claims without verification
- merge recommendations when evidence is incomplete
- AI-generated patches as magic

### Success Criteria

The user trusts the decision because Zroky proves it. Auto-fix remains gated, reviewable, and optional.

## Module 7: Drift

### User Problem

"Did model, provider, prompt, retrieval, or user behavior change enough to break my agent?"

### Shows

- model drift by workflow
- provider latency/error drift
- prompt version impact
- retrieval quality drift
- tool failure drift
- cost drift
- outcome drift
- segment-specific drift
- deploy correlation

### Drift Detail Shows

- baseline period
- comparison period
- changed metric
- affected segment
- suspected cause
- example traces
- recommended replays/goldens to run

### Primary Actions

- compare model versions
- run affected replay suite
- create issue
- freeze model/provider
- add alert

### Does Not Show

- abstract statistical charts without operational meaning
- drift warnings without affected workflow
- model leaderboard detached from production data

### Success Criteria

The user knows whether the agent is becoming less reliable before customers report it.

## Module 8: Outcomes

### User Problem

"Did the agent actually complete the task successfully?"

### Shows

- task success rate
- silent failure rate
- user feedback
- judge score
- business outcome metrics
- escalation rate
- manual override rate
- outcome by workflow/model/prompt version
- top failure reasons

### Primary Actions

- inspect failed outcomes
- create issue from outcome drop
- attach evaluator
- calibrate judge
- compare versions

### Does Not Show

- only model-level quality scores
- success rate without definition
- judge results without calibration metadata

### Success Criteria

The user can measure agent reliability by real outcomes, not only technical success.

## Module 9: Cost and Latency

### User Problem

"Where are agents wasting money or becoming too slow?"

### Shows

- cost per successful task
- cost per workflow
- cost by model/provider
- wasted cost from failed runs
- retry/fallback cost
- loop cost
- latency by span type
- p50/p95/p99 latency
- cost/latency regression after deploy

### Primary Actions

- open high-cost issue
- detect runaway agent loop
- compare model cost vs outcome
- create cost regression alert
- run cheaper model replay comparison

### Does Not Show

- token count as the only cost story
- cheap model recommendation without quality evidence
- infra metrics unrelated to agent behavior

### Success Criteria

The user can reduce waste without lowering reliability blindly.

## Module 10: Alerts

### User Problem

"Tell me when production reliability is at risk, but do not spam me."

### Shows

- active alerts
- severity
- affected workflow
- trigger rule
- evidence
- owner
- status
- linked issue
- linked replay
- notification history

### Alert Types

- critical issue spike
- silent failure spike
- outcome drop
- cost runaway
- latency degradation
- provider failure
- replay suite failure
- golden regression
- drift threshold exceeded
- replay coverage missing for critical issue

### Primary Actions

- acknowledge
- assign
- create issue
- create replay
- mute with reason
- send to Slack/PagerDuty/GitHub

### Does Not Show

- noisy low-value alerts
- duplicate alerts for the same issue cluster
- alerts with no next action

### Success Criteria

Alerts should start the right workflow, not just create anxiety.

## Module 11: Ask Zroky

### User Problem

"I want answers, not navigation."

### Shows

Ask Zroky is a drawer or full-page assistant that can inspect product data.

It should answer:

- What broke after deploy 782?
- Why did refund agent cost increase?
- Which issue should we fix first?
- Which failures have no replay coverage?
- Can we safely move support agent to a cheaper model?
- What caused yesterday's schema failures?
- Which prompt version is safest?

### Answer Must Include

- conclusion
- confidence
- evidence links
- affected workflows
- metrics
- recommended action

### Primary Actions

- create issue
- create replay
- run comparison
- open trace
- summarize incident
- draft PR comment

### Does Not Show

- unsupported guesses
- generic AI advice
- answers without trace/replay/metric evidence

### Success Criteria

Ask Zroky should reduce time-to-root-cause from hours to minutes.

## Module 12: Settings and Integrations

### User Problem

"How do I connect Zroky safely to my production agent stack?"

### Shows

- SDK install
- API keys
- projects/environments
- provider integrations
- GitHub integration
- Slack/PagerDuty integration
- CI integration
- data retention
- redaction rules
- sampling rules
- team permissions
- audit log
- billing/usage

### Primary Actions

- create project
- rotate API key
- configure redaction
- connect GitHub
- connect Slack
- set retention
- configure replay sandbox
- configure CI gate

### Does Not Show

- unsafe defaults
- unclear data capture behavior
- broad admin powers without audit trail

### Success Criteria

An enterprise team can adopt Zroky without fearing data leakage or workflow disruption.

## End-To-End User Workflows

## Workflow 1: First-Time Setup

### User Goal

"I want Zroky connected to my production agent today."

### Flow

1. Create project.
2. Select framework: Python SDK, JS SDK, gateway, or custom API.
3. Install SDK.
4. Add API key and project id.
5. Send first test run.
6. Zroky validates captured fields.
7. Zroky recommends missing instrumentation:
   - tool calls missing
   - retrieval spans missing
   - outcomes missing
   - prompt version missing
8. User fixes instrumentation.
9. Failure Inbox shows first reliability baseline.

### Product Must Solve

The user should not need to understand Zroky internals.
They should get from install to useful trace quickly.

## Workflow 2: Production Incident

### User Goal

"Something broke. Tell me why."

### Flow

1. Alert fires or user opens Failure Inbox.
2. User opens top issue.
3. Zroky shows root cause summary and evidence.
4. User opens representative trace.
5. User creates replay case.
6. User runs replay against current production config.
7. Failure reproduces.
8. User creates fix attempt.
9. Zroky verifies fix against replay and goldens.
10. User merges only if verification passes.
11. Zroky monitors issue after deploy.
12. Issue auto-resolves only when failure disappears.

### Product Must Solve

No manual log archaeology.
No guess-based fix.

## Workflow 3: Prompt Change

### User Goal

"Can I safely change this prompt?"

### Flow

1. PR changes prompt.
2. Zroky CI detects affected workflow.
3. Relevant replays/goldens run.
4. PR comment shows:
   - fixed cases
   - regressed cases
   - cost delta
   - latency delta
   - quality delta
5. Merge blocked if critical regression exists.

### Product Must Solve

Prompt engineering becomes testable engineering.

## Workflow 4: Model Upgrade

### User Goal

"Can I move this agent to a newer or cheaper model?"

### Flow

1. User selects workflow and candidate model.
2. Zroky runs replay suite against baseline and candidate.
3. Zroky compares:
   - task success
   - tool behavior
   - schema adherence
   - cost
   - latency
   - safety
4. Zroky recommends:
   - safe to upgrade
   - unsafe
   - safe for selected segments
   - needs more coverage

### Product Must Solve

Model selection becomes production-evidence-based.

## Workflow 5: Weekly Reliability Review

### User Goal

"What should the team fix this week?"

### Flow

1. Engineering lead opens Failure Inbox.
2. Sees top issues by customer impact and wasted cost.
3. Opens Ask Zroky:
   - "What should we fix first?"
4. Zroky returns ranked list with evidence.
5. Lead assigns owners.
6. Team converts top issues to replay/goldens.
7. Gated fix review tracks progress when enabled.

### Product Must Solve

Reliability work becomes prioritized and measurable.

## Key Data Model

### Core Entities

Project:

- owns agents, traces, issues, replays, goldens

Environment:

- production, staging, development

Agent:

- name, framework, owner, workflows

Workflow:

- business process the agent performs

Run:

- one end-to-end agent execution

Span:

- model/tool/retrieval/memory step inside a run

Outcome:

- task success/failure signal

Issue:

- cluster of related failures

Diagnosis:

- root cause explanation and evidence

ReplayCase:

- reproducible test from production evidence

Golden:

- long-term regression test

FixAttempt:

- candidate change plus verification result

Release:

- deployment/prompt/model/index version

Alert:

- operational trigger linked to issue or metric

## Build Sequence

The product should be built in this exact order.

### Phase 1: Trustworthy Capture

Must have:

- Python SDK stable
- JS SDK stable
- gateway stable
- backend ingest contract aligned
- trace timeline
- tool and retrieval spans
- prompt/model version capture
- redaction and retention controls

Why first:

No diagnosis or replay is trustworthy without complete evidence.

### Phase 2: Actionable Issues

Must have:

- failure taxonomy
- detection engine
- issue clustering
- severity and confidence
- representative traces
- root cause summary v1
- issue page

Why second:

Raw traces do not create product value at scale.

### Phase 3: Replay From Production

Must have:

- create replay from trace
- create replay from issue
- stub mode
- mocked-tool mode
- evaluator/rubric
- before/after comparison
- replay page

Why third:

Replay is the wedge that separates Zroky from normal observability.

### Phase 4: Goldens and CI

Must have:

- promote replay to golden
- golden suite management
- GitHub Action / CI integration
- PR comments
- merge-blocking status
- failed golden evidence

Why fourth:

This turns incident learning into regression prevention.

### Phase 5: Fix Verification

Must have:

- fix attempts
- prompt/model/tool/retrieval change comparison
- verified PR status
- post-deploy monitoring
- automatic issue resolution based on evidence

Why fifth:

Verified fix is the strongest product claim.

### Phase 6: Ask Zroky

Must have:

- evidence-grounded answers
- issue/trace/replay aware
- action creation
- confidence/uncertainty
- no unsupported claims

Why sixth:

Ask Zroky becomes powerful only when the underlying reliability graph is strong.

## MVP Definition

The first strong sellable MVP should include:

1. SDK/gateway captures full model calls, tool calls, retrieval spans, and outcomes.
2. Dashboard shows Failure Inbox, Issues, Replay Lab, Goldens, CI Gates, Cost, Settings.
3. Zroky detects at least 10 high-value failure classes:
   - provider error
   - timeout
   - schema failure
   - context overflow
   - tool exception
   - wrong tool selected
   - retrieval miss
   - agent loop
   - cost spike
   - outcome drop
4. User can create replay from failed trace.
5. User can promote replay to golden.
6. CI can run selected goldens and comment on PR.
7. Gated fix review can show before/after verification when enabled.
8. Ask Zroky can answer evidence-based questions for issues and traces.

This is enough to make serious AI teams care.

## What "Perfectly Solved" Means

Zroky perfectly solves a production agent failure when:

1. The failure is captured with enough evidence.
2. The failure is classified correctly.
3. Related failures are grouped into one issue.
4. The root cause is explained with evidence.
5. A replay case reproduces the failure.
6. A fix can be tested against that replay.
7. Existing goldens confirm no major regression.
8. CI prevents the same failure from shipping again.
9. Post-deploy monitoring confirms the issue is gone.

If any step is missing, the loop is incomplete.

## Product Quality Bar

### Every Page Must Answer One Question

Failure Inbox:

> What needs attention now?

Issues:

> What failure groups should we fix?

Traces:

> What exactly happened in this run?

Replay:

> Can we reproduce and compare?

Goldens:

> Are old failures protected?

Gated fix review:

> Which fixes are proven safe?

Drift:

> What changed in production behavior?

Outcomes:

> Did the agent actually succeed?

Cost:

> Where are failures wasting money?

Alerts:

> What needs action now?

Ask Zroky:

> What is the answer and evidence?

Settings:

> Is Zroky connected safely?

### Every Insight Must Have Evidence

No vague AI summaries.
No root cause without trace links.
No fix recommendation without replay result.
No regression claim without baseline.

### Every Workflow Must End In Action

Every page should push the user toward:

- inspect
- assign
- create replay
- add golden
- verify fix
- open PR
- configure alert
- monitor release

## Pricing And Packaging Direction

Pricing should align with reliability value, not only token volume.

Possible packaging:

Developer:

- traces
- basic issues
- manual replay

Team:

- issue clustering
- replay lab
- goldens
- CI integration
- alerts

Business:

- fix verification
- drift
- Ask Zroky
- GitHub/Slack/PagerDuty
- retention controls
- team permissions

Enterprise:

- enterprise VPC
- SSO/SAML
- audit logs
- advanced redaction
- custom retention
- dedicated replay sandbox
- compliance controls

The main value metric should be production agent reliability, not only event count.

## The Website Promise

The website should lead with this:

> Stop shipping the same agent failure twice.

Subline:

> Zroky captures production agent failures, diagnoses root cause, turns them into replay tests, and verifies fixes before they reach users again.

Proof points:

- full agent flight recorder
- root cause issue clustering
- replay from production failure
- golden regression suite
- verified fix queue
- CI gate for agent changes

Avoid leading with:

- "LLM observability"
- "monitor tokens"
- "debug prompts"
- "AI dashboard"

Those are weaker and more crowded.

## Current Codebase Alignment Notes

The current codebase already has useful foundations:

- FastAPI backend and tenant/project structure
- ingest pipeline
- diagnosis engine
- Celery workers
- replay run services
- regression CI action
- dashboard shell
- calls, alerts, cost, replay, outcomes, reliability, recommendations surfaces
- Ask Zroky direction

But the product should not claim the full loop is perfect until these are hardened:

- SDK contracts aligned across Python, JS, gateway, backend
- gateway ingestion connected end to end
- replay supports real production-like comparison, not only stub mode
- fix PR flow produces evidence-first verification
- ClickHouse/analytics paths match backend models
- dashboard modules reflect the reliability loop, not scattered feature pages
- Ask Zroky always answers from evidence

## Final Product Rule

Zroky wins if the user can say:

> "Before Zroky, production agent failures were random, slow to debug, and risky to fix. After Zroky, every important failure becomes an issue, every issue becomes a replay, every replay becomes a regression guard, and every fix is verified before release."

That is the exact product.
