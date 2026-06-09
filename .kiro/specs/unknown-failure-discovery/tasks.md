# Tasks: Zroky Discover Offline Spike

## Phase A: Formal Spec

- [x] Create `requirements.md` with phase discipline, input, baseline, scoring, report, and validation requirements.
- [x] Rewrite `design.md` around the offline harness and real-trace gate.
- [x] Create this task checklist with DB/API/UI work deferred until after Phase C.

## Phase B: Offline Harness

- [x] Implement standalone `zroky-backend/scripts/discovery_harness.py`.
- [x] Support JSONL traces, injected-failure JSONL, read-only SQLite `calls` tables, local `.data` scanning, manual label CSV, and demo data.
- [x] Normalize persisted `Call` fields plus `payload_json` into the harness trace shape.
- [x] Build in-memory baselines with warmup, low-specificity fallback, critical tools, output shapes, numeric stats, and suspect-baseline detection.
- [x] Score deterministic local anomalies and cluster them into deduplicated findings.
- [x] Promote only warm, non-suspect, corroborated, high-confidence findings to `surfaced`; default everything else to `watching` or `dismissed`.
- [x] Print the required report and optionally write JSON/CSV artifacts.

## Phase B Validation

- [x] Create deterministic mixed synthetic dataset generator for mechanics validation.
- [x] Run the harness on generated mixed synthetic traces plus injected failures.
- [x] Fill synthetic labels for every surfaced finding.
- [x] Verify surfaced precision is at least 90% on synthetic mechanics data (`3/3 = 1.000`; recall `36/44 = 0.818`; latency-only injected failures remained `watching`).
- [ ] If precision is below 90%, adjust only harness gates and rerun.

## Phase C: Real-Trace Gate

- [x] Add hard gate CLI controls: `--precision-threshold`, `--min-scored-traces`, `--min-labelled-surfaced`, and `--fail-on-gate`.
- [x] Make SQLite `.data` probes immutable/read-only so validation does not touch captured stores.
- [x] Add `scripts/export_discovery_traces.py` to export production `calls` rows into harness JSONL with default shape-only privacy.
- [x] Verify exporter -> harness flow fails closed on low-volume local e2e data (`1` exported row, `0` scored traces).
- [x] Add `scripts/seed_discovery_dogfood_calls.py` for local DB-backed mechanics testing when no real database exists.
- [x] Verify dogfood DB -> exporter -> harness path (`454` rows exported, `404` traces scored, `3` surfaced, gate fail-closed because manual labels are absent).
- [x] Add hidden Discovery read model and provisioning-token internal status endpoint for dogfood/admin inspection.
- [x] Verify dogfood runtime -> read model path (`2` baselines, `3` surfaced anomalies, scan watermark advanced, customer surface still blocked).
- [x] Add surfaced-finding label template output so pilot reviewers can fill `manual_label` and rerun the same precision gate.
- [x] Add one-command precision gate runner for scoped DB export or existing JSONL traces, with manifest/report/template artifacts.
- [x] Add trace-readiness preflight for pilot/exported JSONL volume, time-span, workflow, output, status, tool, and outcome signal coverage.
- [x] Run local `.data` probe; result is fail-closed because local stores only produced `1` learning baseline, `0` scored traces, and no manual labels.
- [ ] Collect traces from 2-3 real or pilot agents.
- [ ] Run the same harness and label surfaced findings.
- [ ] Verify precision still holds at about 90% or better.
- [ ] Record false-positive examples and threshold changes.

## Runtime Staging: Still Hidden Behind `DISCOVERY_ENABLED=false`

- [x] Product package skeleton and `DISCOVERY_ENABLED=false` runtime config.
- [x] Baseline persistence and worker refresh task.
- [x] Production scorer/promoter/findings modules shared with the harness.
- [x] Scan watermark/idempotency so repeated scans do not inflate anomaly occurrence counts.
- [x] Disabled-by-default Celery task wrappers for baseline refresh and anomaly scan.
- [x] Add `DISCOVERY_CUSTOMER_SURFACE_ENABLED=false` so `BEHAVIORAL_DRIFT` rows stay hidden from customer `/v1/issues` list/detail/mutations until real-trace precision passes.
- [ ] Customer dashboard UI, feedback loop, and OSS packaging remain blocked until Phase C passes.
