# Design Document: Zroky Discover Offline Spike

## Overview

Discover will be proven as an offline harness before any product code exists. The harness answers one question: can Zroky surface likely unknown failures from captured traces with high precision?

The implementation is a standalone Python script, `zroky-backend/scripts/discovery_harness.py`. It imports only the Python standard library, reads JSONL and read-only SQLite call stores, normalizes traces, builds in-memory baselines, scores post-warmup traces, promotes only corroborated recurring failures, and emits the exact precision report required by `docs/ZROKY_DISCOVERY_ENGINE_PLAN.md`.

DB persistence, API routes, UI, worker tasks, and feature flag wiring are explicitly deferred until after:

1. Phase B mechanics pass on existing/seed plus injected-failure data.
2. Phase C precision holds on real/pilot traces.

## Harness Architecture

Pipeline:

```text
TraceReader
  -> TraceNormalizer
  -> FeatureExtractor
  -> InMemoryBaselineBuilder
  -> AnomalyScorer
  -> CorroboratingPromoter
  -> ReportWriter
```

### TraceReader

Supported inputs:

- `--traces path.jsonl`: generic normalized or raw trace rows.
- `--inject path.jsonl`: deliberately broken traces tagged with `injected_failure_type`.
- `--sqlite path.db`: read-only SQLite database with a `calls` table.
- `--scan-data`: optional read-only scan of local `.data/*.db` stores.
- `--demo`: deterministic in-memory sample set for harness smoke validation only.

The reader must never write to the input database and must not import `app.*`.

### TraceNormalizer

The normalizer produces one internal trace shape:

```text
call_id, project_id, agent_name, workflow_name, created_at,
status, error_code, latency_ms, cost_usd, output, output_fingerprint,
finish_reason, tool_names[], output_shape, outcome_category,
injected_failure_type, source
```

Top-level persisted `Call` fields override `payload_json`; payload fields fill gaps such as `workflow_name`, `tool_calls`, `normalized_output`, `output_content`, `outcome`, and `finish_reason`.

### FeatureExtractor

Phase B uses deterministic local signals only:

- critical tool missing from a workflow
- unseen tool sequence
- output shape/schema shift
- output length z-score
- latency and cost z-scores
- unusual status/error
- finish reason shift
- outcome mismatch when outcome exists

Embeddings are deliberately excluded from Phase B so the harness is cheap, reproducible, and usable on local seed data.

## Baseline Design

Baselines are grouped by specificity:

- exact: `(project_id, agent_name, workflow_name)`
- low specificity agent fallback: `(project_id, agent_name)`
- low specificity project fallback: `(project_id)`

Warmup rules default to the plan values:

- `DISCOVERY_WARMUP_MIN_TRACES = 200`
- `DISCOVERY_WARMUP_MIN_DAYS = 3`
- `DISCOVERY_CRITICAL_TOOL_PCT = 0.90`

A key that does not satisfy warmup remains `learning` and emits no findings. A key learned from high-error or outcome-failure-heavy traffic is marked `suspect`; suspect baselines can produce dismissed diagnostics in the report but never `surfaced` findings.

The baseline stores in-memory counters and sufficient statistics:

- critical tool frequency and known tool sequences
- output shape frequency and output length stats
- status, finish reason, and outcome category frequency
- latency and cost stats
- sample count, distinct days, specificity, and error rate

## Scoring and Promotion

Scoring creates trace-level candidates with:

- normalized anomaly score in `[0, 1]`
- confidence in `[0, 1]`
- ranked corroboration reasons
- deterministic signature for de-duplication

Promotion happens after all candidates are clustered by signature:

- `dismissed`: suspect baseline or confidence below the watching threshold
- `watching`: anomaly exists but promotion evidence is insufficient
- `surfaced`: warm non-suspect baseline, confidence above threshold, and either outcome corroboration or recurring structural corroboration

No-outcome traces require stronger evidence: recurrence plus structural signals such as missing critical tool or schema shift. This preserves the rule that anomaly is not the same thing as failure.

## Report Design

The harness prints the exact report shape from the plan and can write:

- `discovery_harness_report.json`
- `discovery_harness_findings.csv`

Manual labels are read from CSV by `finding_id` or `signature`. Precision is computed only from labels where `manual_label` is `real` or `not_a_failure`. Without labels, the report explicitly says manual labels are required and does not mark the gate as passed.

Injected failure recall is computed separately from known injected call IDs. Synthetic recall proves mechanics only; it does not replace real-trace validation.

## Edge Cases

- Missing workflow falls back to agent-level baseline and raises thresholds.
- Missing agent falls back to project-level baseline and raises thresholds further.
- Low volume stays `learning` forever and emits no behavioral findings.
- Missing outcome is supported but requires recurrence and stronger structural corroboration.
- Baseline poisoning is reduced by marking high-error baselines `suspect`.
- High variance widens numeric z-score bands naturally through standard deviation.
- Legitimate schema/deploy changes should tend to `watching` unless recurring structural evidence and confidence are strong enough.

## Deferred Productization

After real-trace precision passes, a later plan may promote the harness logic into runtime services. That later work may include package skeleton, config, persistence, scorer/promoter modules, findings storage, API, and UI. None of those are part of Phase B.
