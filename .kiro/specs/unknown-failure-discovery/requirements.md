# Requirements Document: Zroky Discover Offline Spike

## Introduction

Discover is the zero-eval engine for surfacing previously unknown agent failures from captured traces. The immediate objective is not productization. The immediate objective is to prove, offline, whether a deterministic baseline/scoring/promoter loop can surface high-confidence failures without creating noisy customer-facing findings.

The required sequence is:

1. Formal spec for Discover.
2. Standalone `discovery_harness.py`.
3. Run existing/seed traces plus injected failures.
4. Manually label surfaced findings and verify the precision gate.
5. Repeat on 2-3 real or pilot agents' traces.
6. Only after the real-trace gate passes, consider migrations, APIs, UI, worker tasks, or OSS packaging.

## Requirements

### R0. Phase Discipline

0.1 WHEN implementing Phase A or Phase B THEN the system SHALL NOT add or modify migrations, database models, API routes, UI components, Celery tasks, feature flags, or customer-facing runtime behavior.

0.2 WHEN the harness runs THEN it SHALL operate offline and in memory, reading traces from files or read-only SQLite databases and writing only explicit harness report artifacts.

0.3 WHEN `DISCOVERY_ENABLED` is discussed for product code THEN its default SHALL remain `false`; Phase B SHALL NOT introduce runtime config wiring.

### R1. Trace Inputs

1.1 WHEN a JSONL trace file is provided THEN the harness SHALL read one trace object per line.

1.2 WHEN an injected-failure JSONL file is provided THEN the harness SHALL treat every row as a known synthetic failure and preserve `injected_failure_type` for recall measurement.

1.3 WHEN a SQLite database containing a `calls` table is provided THEN the harness SHALL read the existing `Call` fields in read-only mode and normalize them without importing backend application code.

1.4 WHEN trace fields exist both top-level and inside `payload_json` THEN top-level persisted `Call` fields SHALL win, with `payload_json` used as fallback.

1.5 WHEN optional fields are missing or malformed THEN the harness SHALL continue and mark the trace with the coarsest usable behavior key instead of crashing.

### R2. Baseline Formation

2.1 WHEN traces include `(project_id, agent_name, workflow_name)` THEN the harness SHALL build baselines at that exact behavior key.

2.2 WHEN `workflow_name` is missing but `agent_name` exists THEN the harness SHALL fall back to an agent-level key and mark the baseline `low_specificity`.

2.3 WHEN `agent_name` is missing THEN the harness SHALL fall back to a project-level key and mark the baseline `low_specificity`.

2.4 WHEN a behavior key does not meet `DISCOVERY_WARMUP_MIN_TRACES` and `DISCOVERY_WARMUP_MIN_DAYS` THEN it SHALL remain `learning` and emit no behavioral findings.

2.5 WHEN a baseline is learned from high-error or failure-heavy traffic THEN it SHALL be marked `suspect`; suspect baselines SHALL NOT produce surfaced findings.

### R3. Feature Extraction

3.1 The harness SHALL extract tool sequence, critical tool frequency, output length, output shape, status, error code, finish reason, latency, cost, and outcome category.

3.2 The Phase B harness SHALL use deterministic local features only; embeddings and semantic distance may be designed later but SHALL NOT be required for the offline spike.

3.3 WHEN outcome is unavailable THEN scoring SHALL still run, but surfacing SHALL require stronger structural corroboration and recurrence.

### R4. Anomaly Scoring and Promotion

4.1 The harness SHALL treat anomaly as distinct from failure. Statistical deviation alone SHALL NOT be enough to surface.

4.2 Every candidate finding SHALL include a human-readable reason, anomaly score, confidence, corroboration list, signature, and sample call IDs.

4.3 The default tier SHALL be `watching`; promotion to `surfaced` SHALL require a warm non-suspect baseline, sufficient confidence, and either outcome corroboration or recurring structural corroboration.

4.4 WHEN a candidate has low confidence or comes from a suspect baseline THEN it SHALL be counted as `dismissed` in the harness report rather than surfaced.

4.5 WHEN a signature recurs THEN the harness SHALL de-duplicate it into one finding and raise `occurrence_count` rather than emit duplicate findings.

### R5. Harness Report

5.1 The harness SHALL print and optionally write a report with:

- Baseline keys found, including active, learning, suspect, and low-specificity counts.
- Traces scored.
- Findings by `watching`, `surfaced`, and `dismissed`.
- One row per surfaced finding with `finding_id`, `signature`, `anomaly_score`, `confidence`, `reason`, `corroboration[]`, `sample_call_ids`, and `manual_label`.
- Surfaced precision from manual labels.
- Recall on injected failures.
- False-positive examples labeled `not_a_failure`.
- Watching-to-surfaced rate.

5.2 WHEN manual labels are absent THEN the report SHALL not claim the precision gate has passed.

5.3 WHEN report files are written THEN the harness SHALL produce machine-readable JSON and CSV suitable for manual labeling.

### R6. Validation Gates

6.1 Synthetic and seed data SHALL be treated as mechanics-only validation.

6.2 The surfaced precision gate SHALL be at least 90% on manually labeled surfaced findings.

6.3 Real-trace validation on 2-3 real or pilot agents SHALL be mandatory before any DB/API/UI/product implementation.

6.4 IF the Phase B or Phase C precision gate fails THEN iteration SHALL happen inside the harness logic only, not in product code.

## Non-Goals

- No database migrations.
- No `/v1/findings` API.
- No findings table.
- No dashboard or customer UI.
- No Celery/worker product integration.
- No OSS packaging.
