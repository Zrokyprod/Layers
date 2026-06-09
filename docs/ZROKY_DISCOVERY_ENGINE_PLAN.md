# Zroky Discovery Engine — End-to-End Engineering Plan

| | |
|---|---|
| **Status** | Plan v1.1 — revised after review. **Next step = formal spec + offline harness spike, NOT full product build.** |
| **Parent doc** | `ZROKY_DISCOVERY_ENGINE_ARCHITECTURE.md` (strategy + positioning) |
| **Scope of THIS doc** | Only the **Discover** pillar (Behavioral Baseline + Anomaly Scorer + Anomaly→Failure promotion). Prove (Replay) and Guard (CI) are existing engine — referenced, not rebuilt here. |
| **Governing principle** | **Anomaly ≠ Failure.** Precision over recall. Near-zero false positives = survival. |
| **North-star** | ≥ 90% precision on the `surfaced` tier before any OSS launch. |

---

## 0. What "done" means (acceptance, up front)

The Discovery Engine is successful when, run against real/captured production traces, it can:

1. Learn a per-workflow behavioral baseline **without any labels**.
2. Score new traces for deviation and attach a **human-readable reason**.
3. Promote a deviation to a `surfaced` finding **only** when corroborated (outcome / recurrence / replay / human).
4. Achieve **≥ 90% precision** on `surfaced` findings (of what we call a failure, ≥9/10 a developer agrees is real).
5. Stay **silent before warmup** (no guessing on day 1) while structural findings + "replay last failure" still deliver 10-minute value.
6. Hand a `surfaced` finding cleanly to the existing **Replay → Golden → CI** path.

If #4 fails, nothing else matters. The entire plan is organized to test #4 as early and as cheaply as possible (Phase 2, on existing data).

---

## 1. Scope

### In scope
- Behavioral baseline modeling per `(project_id, agent_name, workflow_name)`.
- Anomaly scoring of incoming traces against the active baseline.
- Anomaly→Failure promotion logic (corroboration gates).
- A `findings` store with proper columns (not a JSON blob) + a read API.
- Feedback capture (thumbs up/down / "not a failure") feeding threshold adaptation.
- An **offline harness** to replay captured traces through the engine and measure precision.

### Out of scope (this plan)
- Replay/fidelity score (Prove) — existing `replay_executor`, only the handoff is defined here.
- CI gate verdicts (Guard) — existing `regression_ci`.
- Multilingual specifics — designed as a pluggable scorer input, built later.
- Embedding/Tier-2 semantic distance — interface defined; can ship after the statistical core proves out.

---

## 2. Component architecture

```
                 incoming Call (post-ingest, post-structural-detectors)
                                   │
                                   ▼
   ┌──────────────────────────────────────────────────────────────┐
   │  DISCOVERY PIPELINE  (Celery, async — never blocks ingest)     │
   │                                                                │
   │  1. FeatureExtractor   → BehavioralFeatures (per trace)        │
   │  2. BaselineStore      → load active baseline for the key      │
   │       └─ BaselineBuilder (incremental/rolling, separate task)  │
   │  3. AnomalyScorer      → AnomalySignals + composite score      │
   │  4. Corroborator       → attach outcome/recurrence/replay/human│
   │  5. Promoter/Suppressor→ tier: ignored | watching | surfaced   │
   │  6. FindingWriter      → upsert into `findings` (+ clustering) │
   └──────────────────────────────────────────────────────────────┘
                                   │ surfaced
                                   ▼
                  Findings API  →  one-click → existing Replay → Golden → CI
```

**New modules (proposed):**
```
app/services/discovery/
  __init__.py
  features.py        # FeatureExtractor: Call → BehavioralFeatures
  baseline.py        # BaselineBuilder + BaselineStore (versioned, rolling)
  scorer.py          # AnomalyScorer: features + baseline → signals + score
  corroborate.py     # Corroborator: gather outcome/recurrence/replay/human
  promote.py         # Promoter/Suppressor: the anomaly→failure gates (CORE)
  findings.py        # FindingWriter + clustering + lifecycle
  harness.py         # OFFLINE: replay captured traces, measure precision
```

**Reused (do not rebuild):** SDK, ingest, `Call` model, structural `detectors/*`, `replay_executor`, `goldens`, `regression_ci`, clustering helpers.

---

## 3. Data model (new tables)

### 3.1 `behavioral_baselines`
One active row per `(project_id, agent_name, workflow_name)`, versioned.
```
id                      uuid pk
project_id              fk (RLS tenant boundary)
agent_name              text
workflow_name           text
version                 int
status                  text  -- 'learning' | 'active' | 'superseded'
sample_count            int            -- traces seen
window_start_at         timestamptz
window_end_at           timestamptz
features_json           jsonb          -- the learned distributions (see §4.2)
created_at, updated_at  timestamptz
UNIQUE (project_id, agent_name, workflow_name, version)
INDEX (project_id, agent_name, workflow_name, status)
```

### 3.2 `findings`  (replaces the JSON-blob-in-Anomaly pattern — proper columns)
```
id                      uuid pk
project_id              fk
agent_name              text
workflow_name           text
signature               text   -- (workflow, deviation-signature) cluster key
tier                    text   -- 'watching' | 'surfaced' | 'dismissed'
status                  text   -- 'open' | 'replaying' | 'resolved' | 'regressed'
title                   text   -- human-readable
reason                  text   -- evidence-backed "why" (REQUIRED, never null)
anomaly_score           float
confidence              float
occurrence_count        int
first_seen_at           timestamptz
last_seen_at            timestamptz
sample_call_ids         text[]         -- bounded (e.g. last 5)
corroboration_json      jsonb          -- which signals fired (outcome/recurrence/replay/human)
blast_radius_usd        float
created_at, updated_at  timestamptz
INDEX (project_id, tier, status, last_seen_at desc)
INDEX (project_id, signature)
```
> **Note:** proper columns here directly fix the existing `/v1/issues` N+1 + in-memory-filter problem. Findings list becomes a real indexed query.

### 3.3 `finding_feedback`
```
id, finding_id fk, project_id fk, user_id,
verdict text -- 'real' | 'not_a_failure' | 'unsure',
note text, created_at
```

---

## 4. The pipeline, stage by stage

### 4.1 FeatureExtractor (`features.py`)
Pure function: `Call → BehavioralFeatures`. No DB, no side effects (testable in isolation).
Extracts, per trace:
- `tool_sequence`: ordered list of tool names called.
- `output_shape`: length band, JSON-vs-prose flag, presence of key fields (fingerprint, not raw PII), detected language.
- `cost_usd`, `latency_ms`, `total_tokens`.
- `outcome` (if `zroky.outcome(...)` / metadata present).
- `status`, `error_code` (from structural layer).

### 4.2 BaselineBuilder + BaselineStore (`baseline.py`)
- **BaselineBuilder** runs as a scheduled/rolling Celery task per key. It aggregates the last N traces / last T days into distributions stored in `features_json`:
  - tool-sequence frequency map + "critical tools" (present in ≥X% of normal traces).
  - output-shape distributions (length mean/variance, structure mix, language mix).
  - cost/latency/token rolling mean + variance.
  - outcome distribution (e.g. resolved 92% / escalated 5% / …).
- **Warmup rule:** `status='learning'` until `sample_count ≥ WARMUP_MIN` (configurable, e.g. 200) over `≥ WARMUP_DAYS`. While learning → **scorer is skipped entirely** (no behavioral findings).
- **Rolling re-baseline:** baselines recompute on a window so provider/model drift naturally re-baselines instead of flagging forever. New version supersedes old.
- **BaselineStore** = read/write accessor with simple in-process + Redis cache.

### 4.3 AnomalyScorer (`scorer.py`)
Pure function: `(BehavioralFeatures, Baseline) → AnomalySignals`. Per trace computes:
| Signal | How | Strength |
|---|---|---|
| `tool_sequence_deviation` | edit distance vs typical; **missing critical tool weighted high** | strong if critical tool missing |
| `outcome_mismatch` | claimed success but outcome says otherwise | **strongest (label-free)** |
| `output_shape_z` | z-score on length/structure | weak |
| `cost_z`, `latency_z` | z-score vs rolling mean/var | weak |
| `semantic_distance` | embedding vs centroid (Tier-2, optional) | medium |

Output: individual signals + a composite `anomaly_score` + a **human-readable reason string** ("skipped `get_refund_status`, present in 96% of normal traces"). **Hard rule: no reason → no finding.**

### 4.4 Corroborator (`corroborate.py`)
Gathers independent evidence that a deviation is a *real* failure (the §1.1 test):
- **outcome**: outcome signal contradicts success.
- **recurrence**: same `signature` seen ≥ k times / crosses population threshold.
- **replay**: (optional, on-demand) replay reproduces a bad result.
- **human**: a developer marked a matching finding `real`.
Returns a `corroboration` record (which signals fired, strength).

### 4.5 Promoter / Suppressor (`promote.py`) — **the core, build most carefully**
Decision logic (the survival layer). Order:
1. **Warmup gate** — baseline `active`? else stop.
2. **Reason gate** — concrete reason exists? else stop.
3. **Corroboration gate** — ≥1 strong corroboration OR ≥2 weak corroborating signals? else → `watching` (hidden).
4. **Variance gate** — high-variance workflows get wider bands; normal stochasticity never fires.
5. **Recurrence gate** — one-off → `watching`; recurring → eligible for `surfaced`.
6. **Feedback gate** — if this signature was dismissed before, raise its threshold.
7. **Tiering** — default `watching`; promote to `surfaced` only when all gates pass. Promote slow, demote fast.

Every decision is logged with its reason (for the offline harness to audit precision).

### 4.6 FindingWriter (`findings.py`)
- Upserts into `findings` keyed by `signature`; maintains occurrence_count, first/last seen, sample call ids, blast radius.
- Lifecycle: `watching → surfaced → (replaying → resolved) → regressed`.
- Surfaced findings expose a one-click handoff to existing Replay (`create_replay_from_*`).

### 4.7 Edge cases & failure modes the engine MUST handle (added after review)

These are not optional — each one silently breaks precision or coverage if ignored.

| Edge case | Behavior |
|---|---|
| **`agent_name` / `workflow_name` missing** | Fall back to a coarser key (`agent_name` only, or `project_id` only) and tag the baseline `low_specificity`. Never crash, never silently drop the trace. Low-specificity baselines are held to a *higher* surface threshold (more prone to noise). |
| **Low-volume workflows never warm up** | Accept it — they stay `learning` forever and produce **no behavioral findings**. Structural findings still fire. UI is explicit ("not enough traffic to learn normal yet"). We do NOT fake a baseline from 5 traces. |
| **Outcome signal unavailable** (common) | Engine must work without it — outcome is the *strongest* corroborator but not the *only* one. With no outcome, surfacing requires stronger structural corroboration (missing critical tool + recurrence). Document that precision is higher when customers emit `zroky.outcome(...)`. |
| **Baseline poisoning** (bad behavior becomes "normal") | If a workflow was broken during the whole learning window, the bad pattern becomes baseline → real failures look normal. Mitigations: (a) keep prior baseline versions; (b) flag *large* baseline shifts between versions for human review instead of silently adopting; (c) cross-check baseline against structural error rate — a baseline learned from high-error traffic is marked `suspect`. |
| **Non-deterministic normal variance** | Variance-aware bands (§4.5 gate 4); widen automatically for high-variance workflows. |
| **Schema/format change (legit deploy)** | A legitimate intended change looks like drift. Rolling re-baseline absorbs it over the window; large abrupt shifts → `review`, not `surfaced failure`. |

---

## 5. Configuration (all tunable, no magic numbers in code)
```
DISCOVERY_ENABLED                 = false   # DEFAULT OFF until precision is proven (Phase 2 gate)
DISCOVERY_WARMUP_MIN_TRACES       = 200
DISCOVERY_WARMUP_MIN_DAYS         = 3
DISCOVERY_BASELINE_WINDOW_DAYS    = 14
DISCOVERY_RECURRENCE_K            = 3
DISCOVERY_CRITICAL_TOOL_PCT       = 0.90
DISCOVERY_SURFACE_MIN_CONFIDENCE  = 0.80
DISCOVERY_Z_WEAK                  = 3.0
```
> `DISCOVERY_ENABLED` ships **false by default** and is only flipped on per-project after the offline precision gate (Phase 2) is met. A discovery engine that hasn't proven precision must never surface findings to a customer.

---

## 6. Implementation phases (REVISED after review — spike before product)

> **Core correction:** do **not** start full DB/API/UI implementation. The first real build step is a **formal spec + an offline harness spike** that answers the only question that matters: *can Zroky surface useful failures without crying wolf?* DB migrations, `/v1/findings`, UI, and feedback come **only after** the precision gate passes.

### Phase A — Formal spec (no product code)
- Convert this plan into Requirements + Design + Tasks for the Discover pillar.
- Lock: detection scope, anomaly→failure corroboration rules, edge-case behavior (§4.7), precision bound, label format (§7.1), report format (§7.2).
- **Exit:** spec approved.

### Phase B — Offline harness spike (`discovery_harness.py`) — **the make-or-break, do this FIRST**
- Standalone script. **No DB migration, no API, no UI.** Reads captured traces from existing stores (`.data/*`, seed scripts) and/or a JSONL trace file.
- Implements the pure logic in-memory: FeatureExtractor → in-memory BaselineBuilder → AnomalyScorer → Corroborator → Promoter.
- **Build synthetic failures deliberately** (inject known-bad traces: dropped critical tool, broken schema, outcome mismatch) so we can measure recall on *known* injected failures AND precision on the mixed set.
- Emits the precision report (§7.2).
- **Exit (THE gate):** on the available data, `surfaced`-tier **precision ≥ 90%**. If not met → iterate on §4.5 gates here, cheaply, before writing any product code. Iterate in this script only.

### Phase C — Real-trace validation (caveat from review)
- Synthetic/seed data proves **mechanics**, not **real-world precision**. Before trusting the gate, run the harness on **2–3 real or pilot agents' traces** (even a small sample).
- **Exit:** precision holds (≥ ~90%) on real traces, not just synthetic. Only now do we productize.

### Phase 0 — Foundations & cleanup (prereq for productizing)
- Fix worker idempotency (status commit + side-effects in one transaction).
- Add `discovery/` package skeleton + config keys (`DISCOVERY_ENABLED=false`).
- **Exit:** package imports, config resolves, no behavior change.

### Phase 1 — Baseline persistence
- Promote the harness's in-memory baseline to `behavioral_baselines` table + `BaselineBuilder`/`BaselineStore` Celery task. Stays `learning`/silent.
- **Exit:** baselines persist with sane distributions; unit tests.

### Phase 2 — Scorer + Promoter productionized + `findings` table
- Move the proven harness logic into `scorer.py` / `promote.py` / `findings.py` + `findings` table.
- **Exit:** online pipeline reproduces the harness's offline verdicts on the same inputs.

### Phase 3 — API + minimal UI
- `/v1/findings` list/detail (proper columns, indexed — no N+1). Findings inbox + feedback buttons. One-click → existing Replay.
- **Exit:** a discovered finding flows end-to-end to a replay run in the UI.

### Phase 4 — First-run / 10-minute value
- Structural findings (instant) into the same inbox; "replay my last failure" path; "learning your normal" state.
- **Exit:** fresh project shows value in ≤10 min without warmup.

### Phase 5 — OSS packaging (`zroky-watch`)
- Only after precision holds on real traces. MIT standalone capture + discovery; README per positioning doc.
- **Exit:** clean self-host, < 5-min install, demo GIF.

---

## 7. Offline harness — exact spec (so it's unambiguous to build)

### 7.1 Input & label format
- **Trace input:** JSONL, one trace per line (or a reader over the existing `Call` store). Minimum fields: `call_id, project_id, agent_name, workflow_name, tool_calls[], output, status, error_code, cost_usd, latency_ms, outcome?`.
- **Injected synthetic failures:** a separate JSONL of deliberately-broken traces, each tagged `injected_failure_type` (e.g. `missing_critical_tool`, `schema_break`, `outcome_mismatch`) — these are the *known* failures for recall measurement.
- **Manual label file (CSV):** after a run, a human fills the `manual_label` column per surfaced finding:
  ```
  finding_id, signature, reason, anomaly_score, manual_label   # real | not_a_failure | unsure
  ```

### 7.2 Precision report — exact output
The harness MUST print (and write to CSV/JSON):
```
=== Discovery Harness Report ===
Baseline keys found:           <n>   (active: <a>, learning: <l>, suspect: <s>, low_specificity: <ls>)
Traces scored:                 <n>
Findings — watching:           <n>
Findings — surfaced:           <n>
Findings — dismissed:          <n>

For each SURFACED finding:
  finding_id | signature | anomaly_score | confidence | reason | corroboration[] | sample_call_ids | manual_label

Precision (surfaced):          <surfaced_real / surfaced_total>   ← GATE: ≥ 0.90
Recall on injected failures:   <injected_caught / injected_total>
False-positive examples:       <list of surfaced findings labeled not_a_failure, with their reason>
Watching→surfaced rate:        <ratio>   (runaway = noise warning)
```
> The **false-positive examples list with their reasons** is the most valuable output — it tells us exactly which gate to tighten.

---

## 7b. Validation strategy — what synthetic data can and cannot prove

1. **Existing/seed + injected-failure data (Phase B)** proves the **mechanics**: baselines form, scorer fires on injected failures, promoter suppresses noise. This is the cheap, fast first gate. It is necessary but **not sufficient**.
2. **Honest limitation (review):** synthetic/seed data does **not** prove real-world precision — real production noise is messier. A 90% precision on synthetic data is a green light to *productize the spike*, not proof the product works.
3. **Real-trace validation (Phase C)** is mandatory before OSS/customers: run the same harness on **2–3 real or pilot agents' traces**. Precision must hold there too.
4. Only after Phase C do we build DB/API/UI (Phases 0–3).

> This makes "build the spike" and "validate the hardest risk" the same activity — but we never confuse synthetic-pass with product-proven.

---

## 8. Metrics

- **Surfaced precision ≥ 90%** (gating).
- **Anomaly→failure promotion accuracy** — % of surfaced findings with ≥1 independent corroboration.
- **Time-to-first-finding ≤ 10 min** (via structural + replay-last-failure; not baseline-dependent).
- **"I didn't know about this" rate** — % of surfaced findings the developer says were unknown (measures real differentiation).
- **Watching→surfaced promotion rate** (watch for runaway promotion = noise).
- **Dismissal rate** (high dismissals = thresholds too loose).

---

## 9. Risks specific to the engine

1. **False positives kill it.** Mitigation: precision-over-recall, default-to-`watching`, Phase-2 hard gate before anything else.
2. **Anomaly ≠ failure.** Mitigation: corroboration gate is mandatory; statistical deviation alone never surfaces.
3. **Sparse / low-volume workflows** never reach warmup → no behavioral findings. Mitigation: structural findings still fire; be explicit in UI; don't fake a baseline.
4. **High-variance workflows** look anomalous normally. Mitigation: variance-aware bands; widen automatically.
5. **Re-baseline masking real regressions** (rolling window absorbs a genuine bad change as "new normal"). Mitigation: keep prior baseline version; flag large baseline shifts for review rather than silently adopting.
6. **Difficulty/timeline** — this is the hardest part of the product; Phase 2 may need several iterations. Plan for it.

---

## 10. Next step (revised)

**Do NOT build DB/API/UI yet.** The sequence is:

1. **Formal spec** for the Discover pillar (Requirements → Design → Tasks), with Phase B/C front-loaded.
2. **Build `discovery_harness.py`** (Phase B) — pure offline logic, no migrations, no API, no UI.
3. **Run on existing + injected-failure data**, manually label surfaced findings, produce the §7.2 report.
4. **Check the gate:** surfaced precision ≥ 90%? If not, iterate on §4.5 gates *in the harness only*.
5. **Phase C:** repeat on 2–3 real/pilot traces (synthetic-pass ≠ product-proven).
6. **Only then** start Phase 0–3 (idempotency fix → baseline table → scorer/findings → API/UI).

> The whole product rests on one provable question, and the harness answers it cheaply, before any product code:
> **Can the engine surface a real, unknown failure — without crying wolf?**
>
> Synthetic data answers "do the mechanics work?" Real traces answer "does it actually work?" We need both, in that order, before we productize.
