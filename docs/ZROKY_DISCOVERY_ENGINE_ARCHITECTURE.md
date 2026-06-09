# Zroky — Technical & Strategy Architecture Document
### Category: **AI Agent Failure Discovery & Regression Guard**
### Positioning: "Discover → Prove → Guard"

> **Category (locked):** **AI Agent Failure Discovery & Regression Guard.**
> Chosen over "AI AgentOps", "AI Observability", "AI Regression Firewall (only)", or "Zero-eval platform" — because it carries **both differentiation (Discovery) and monetization (Regression Guard)** in the name.
>
> **Public headline:** *"Find the AI agent failures you didn't know to test."*
> **Public subcopy:** *"Zroky learns normal production behavior, surfaces abnormal failures, replays fixes, and blocks repeat regressions in CI."*
>
> **Wording discipline (important):** "Zero-eval" is an **internal thesis only — never a public promise.** Public-safe phrasings: *"Production-discovered evals for AI agents"* / *"From unknown production failure to CI protection"* / *"Find failures before you write evals."* Never *"no evals needed."*

| | |
|---|---|
| **Status** | Draft v1.2 — direction-setting, pre-implementation (revised after critical review + positioning lock) |
| **Date** | June 2026 |
| **Owner** | Zroky Product + Engineering |
| **Purpose** | Capture the full reasoning, market evidence, the reframed product bet, and the technical architecture for the Discovery-first Zroky. This is the single source of truth before we write the formal spec (requirements → design → tasks). |
| **Supersedes (in spirit)** | The original `MVP_LOCK.md` "regression firewall" framing. The loop is kept; **Discovery becomes the hero, the Regression Firewall becomes the engine.** |

---

## 0. How to read this document

This is both a **strategy** doc and a **technical architecture** doc, because for Zroky the two cannot be separated — the differentiation *is* a technical capability (auto-discovery with near-zero false positives), and the architecture only matters if it serves the bet.

Sections 1–5 = the "why" (POV + market reality + the reframe).
Sections 6–11 = the "what/how" (product + engineering architecture).
Sections 12–18 = execution, risks, decisions.

Honesty note carried throughout: the market/competitor claims here are **research-backed hypotheses**, not customer-validated truths. Section 16 lists what still must be proven with real developers. Nothing in this document removes the need for that validation.

---

## 1. Executive Summary — The Bet

> **Discover → Prove → Guard.**
> Zroky learns your agent's "normal" from production traffic and **surfaces failures you never thought to test for** (Discover). It then **proves a candidate fix actually works** via faithful replay (Prove), and **guards against the repeat** in CI (Guard).

**One-line positioning:**
> *"Stop writing evals only for the failures you can imagine. Zroky finds the ones you can't — then proves the fix."*

**Three pillars, in order of how a user experiences value:**
1. **Discover** (the hook / differentiation) — find unknown production failures without pre-written evals.
2. **Prove** (the money) — replay + fidelity score: verify a fix is real, not guessed.
3. **Guard** (the lock-in) — goldens + flake-proof CI gate so the failure never ships again.

**Why this framing (vs. the old "Regression Firewall"):**
- We **do not discard** the Regression Firewall. Replay-proof + Goldens + CI Gates remain the **paid money value**. We *demote* them from hero to pillars 2–3, and *add* Discovery as pillar 1.
- The old framing **led** with the CI gate — which is **already sold by a funded competitor (Braintrust: $80M Series B at ~$800M valuation; sources: Axios, TechCrunch).** Leading there = me-too, late, crowded.
- Every incumbent (Braintrust, LangSmith, DeepEval, Langfuse, Phoenix) shares one model: **"you define what 'good' is, then we test it."** They have publicly admitted they **do not surface unknown failures** and that **day-one has zero labeled data.**
- Zroky's wedge: **"we learn what 'good' is, then we surface the abnormal"** — an un-occupied corner that attacks three competitor gaps at once: cold-start, unknown-failure discovery, and eval-vs-production drift.

**The make-or-break technical constraint:** the discovery engine must have a **near-zero false-positive rate**, AND it must distinguish **anomaly from failure** (see §1.1). A noisy or "everything-is-an-anomaly" tool is uninstalled in week one. This is not a feature — it is survival.

### 1.1 The single most important principle: **Anomaly ≠ Failure**

Detecting that a trace *deviates* from baseline is the easy 30%. **Proving the deviation is an actual business failure is the hard 70%** — and it is where most "anomaly detection" products quietly fail. A deviation is only promoted to a **failure** when it is corroborated by at least one of:

- **Outcome signal** — `zroky.outcome(...)`, thumbs-down, human override, ticket re-open (strongest, label-free).
- **Recurrence** — the same deviation repeats ≥ k times / crosses a population threshold.
- **Replay confirmation** — replaying the trace reproduces a bad result.
- **Human confirmation** — a developer marks the surfaced finding as real.

Until corroborated, a deviation is a **`watching`** signal (hidden), never a **`surfaced`** "failure." This principle governs the entire engine in §7.

### 1.2 Positioning: Discovery is the **hero**, Regression Firewall is the **engine**

The narrative changes; the money path underneath does **not**. We lead with Discovery (the differentiation) and keep the full Regression-Firewall pipeline as the engine that monetizes it.

```
OLD (internal/legacy):
  Capture → Diagnose → Issue → Replay → Golden → CI Gate

NEW (public narrative — 3 pillars):
  DISCOVER  →  PROVE  →  GUARD

SAME money path, under the hood:
  Discover unknown failure
    → Explain why it matters (impact / blast radius)
    → Replay candidate fix
    → Verify with fidelity score
    → Promote Golden
    → Block repeat regression in CI
```

**Website positioning (locked):**

- **Headline:** *Find the AI agent failures you did not know to test.*
- **Subcopy:** *Zroky learns normal production behavior, surfaces abnormal failures, replays fixes, and blocks repeat regressions in CI.*
- **Product pillars (the 3 words the site is built around):** **Discover · Prove · Guard**
- **Under the hood (shown on a "how it works" section, not the hero):** Capture SDK · Behavioral Baseline · Anomaly Scorer · False-Positive Suppressor · Replay Lab · Goldens · CI Gate

**Public-safe alternates** (rotate in copy/SEO): *"Production-discovered evals for AI agents"*, *"From unknown production failure to CI protection."* **Never** "zero-eval / no evals" in public — internal thesis only.

---

## 2. POV — Honest assessment of where Zroky stands today

This section is the unfiltered engineering + product opinion formed from reverse-engineering the existing codebase.

### 2.1 What is genuinely good (keep it)
- **SDK fail-closed guarantee is real and correctly implemented.** Telemetry is enqueued in `finally`; capture errors never break the customer's production call path. This is the single most important guardrail and it is honored.
- **Trust semantics are unusually mature.** Stub replay is never reported as `verified_fix`; the regression-CI path returns `not_verified` when no real comparison happened. This integrity is a genuine asset and rare in the space.
- **The ingest → diagnosis → issue pipeline is coherent and real**, with PII masking, idempotency (Redis fast-path + DB authority), cost enrichment, quota, monthly-partitioned tables, and a clean detector fan-out (`diagnosis_engine.py` → `detectors/*`).
- **The regression-CI orchestrator actually re-executes traces** through a candidate resolver and degrades gracefully — it is not a stub.

### 2.2 What is wrong / risky (must fix before scaling)
- **`sys.modules` hijacking shims everywhere** (`models.py`, `worker/tasks.py`, `replay_executor.py`, `fix_adoption.py`). Worst offender: `tasks_impl.py` reads sibling `.py` files, **string-strips** their import/`__all__` lines, and `exec(compile(...))` them into one namespace. This defeats static analysis and IDE navigation, and is fragile. **This is the worst architectural smell in the repo.**
- **Worker idempotency gap (a real data-correctness bug):** in `tasks_diagnosis.py`, `job.status='done'` is committed **before** the best-effort side-effect chain (issue upsert, fix events). A crash mid-chain + retry hits the "already done" short-circuit and the issue/fix-event writes are **never re-emitted**. Status commit and side-effects are not transactionally linked.
- **Public Issue is stored as a JSON blob inside `Anomaly.evidence_json`** instead of real columns → forces the `/v1/issues` list to filter/sort in Python.
- **`/v1/issues` is a severe N+1** (5–8 queries × N per page; `_latest_replay_for_issue` scans up to 200 `ReplayRun` rows and parses `summary_json` in Python). This is the dashboard home endpoint; it will not hold under real load.
- **Over-fetch + in-memory filter** on issues (`fetch_limit = (limit*4)+1`, capped 401) is a **correctness risk** — valid rows can fall outside the window and silently disappear.
- **`reproduce_test.py` is foreign code** (imports a medical `patient_name` model that doesn't exist in Zroky) — committed cruft.

### 2.3 What is unnecessary (scope drift — the trap `MVP_LOCK.md` predicted)
The codebase grew to **~155 service files, 67 route files, 69 migrations, Modules 1–12** — Provider Drift, Ablation, Judge Calibration, Outcome Attribution, Auto-PR, Digest, Billing lifecycle, etc. **The riskiest assumption (does a real developer complete the core loop and feel the magic?) is the least validated.** Engineering effort went wide where demand is thin, and stayed thin where the value is deepest (replay fidelity — flag-gated off; semantic failure detection — judge-heavy with hardcoded confidence).

**Verdict:** the engine is sound; the **product had the wrong hero and too much width**. The fix is *re-focus*, not rebuild.

---

## 3. Market Reality (research-backed, 2026 sources)

### 3.1 The problem is real and large
- **~88% of AI agent projects never reach production**; of those that ship, **<15% scale** beyond the initial team (multiple 2026 sources).
- **Gartner: 40% of agentic AI projects will be cancelled by 2027.**
- DigitalOcean (2026): **67% get pilot gains, only ~10% scale to production.** "The gap between working demo and production system is where most AI agent projects die."
- IDC/AWS: **97% of enterprises have not figured out how to scale agents** — gaps in observability, integration, training.

### 3.2 The hard pains (priority order, from practitioner posts + research)
1. **Silent failures** — "agent returns 200 OK but gave the user garbage at turn 6, and you have no idea why." This is developers' *own language*, and it is exactly Zroky's thesis.
2. **Evaluation is "the hardest problem of 2026"** — an agent can rate "good" on every turn and still fail the user's intent. Single-response eval misses goal-level failure. **Ground truth largely doesn't exist.**
3. **Reliability at scale / compounding errors** — 95% per-step reliability across ~8–10 steps ≈ 40–66% end-to-end. Failures compound silently.
4. **Failures are operational, not model-level** — routing, tool-call validation, degraded workspace state ("Memento problem"), offline/undeclared APIs. *"The model isn't the problem."*
5. **Non-determinism** — same input, different output → can't reproduce, can't write stable regression tests.
6. **Eval-to-production drift** — "the agent your eval measures and the agent your customer talks to are no longer the same system."

### 3.3 The competitive reality (uncomfortable but decisive)
- Market: **Agentic AI observability ≈ $0.55B (2025) → $2.05B (2030), ~30% CAGR.** Real and growing.
- **57% of orgs have agents in production, but observability/eval are the lowest-rated parts of the stack — only ~1/3 of teams are satisfied** with current solutions. (This dissatisfaction is the opening.)
- **Braintrust** ($800M valuation, $80M Series B) literally sells: *"evaluation-first architecture that turns production failures into permanent test cases with one click, with CI/CD quality gates that block regressions before they ship."* → **This is the old Zroky pitch, already funded.**
- **The admitted gaps (the opening):**
  - Braintrust *"requires you to define your evaluation surface upfront — it doesn't surface unknown failures."*
  - LangSmith's clustering has *"no issue lifecycle, no frequency tracking, no automatic eval generation."*
  - *"Teams skip eval infra because building evals requires labeled data, and on day one you have none."*

### 3.4 India lens (builder's home advantage, not the headline market)
- Cost is a **survival** issue, worsened by a weak rupee (+10–15% on dollar-priced LLM APIs). Western flat pricing ($249/mo) is heavy here.
- **Multilingual/Hinglish/Indic failure detection is a genuine blind spot** of English-biased eval/judge tools (Indic langs ≈ 1% of Common Crawl; 2–8× token tax). → A *hidden moat* feature, not the headline (we sell globally), but a differentiator competitors won't copy quickly.

**Net:** Problem = real, hard, growing. Solution-space = crowded. Therefore the decisive question is **not** "is the problem real?" (it is) but **"why would a developer already using Braintrust/LangSmith choose Zroky?"** → Answer: **unknown-failure discovery + faster time-to-first-value (find failures before writing evals)**, which they do not offer.

---

## 4. The Reframe — from "Regression Firewall (CI-gate-led)" to "Discover → Prove → Guard"

The technical engine is **largely the same**. What changes is the **lead pillar** and the **first-run experience**. We keep the Regression Firewall as the paid value (Prove + Guard) and put **Discover** in front of it.

```
Everyone else:   "You tell us what's good"  → write evals → test → CI gate
Zroky:           "We learn what's good"     → surface abnormal → PROVE → GUARD
                  └── Discover (hook) ──┘     └─ money + lock-in ─┘
```

| Dimension | Old (CI-gate-led) | New (Discover → Prove → Guard) |
|---|---|---|
| Lead pillar | CI gate / replay verification | **Discover (unknown-failure)** |
| First question answered | "Does my fix work?" | **"What don't I know is breaking?"** |
| User must pre-define failures? | Yes | **No for discovery — learned from traffic** |
| Competitor leads with this? | Yes (Braintrust) | **No (admitted gap)** |
| Time-to-first-value | ~7 days (inbox fills) | **~10 min via first-run path (see §5.1); full behavioral discovery after warmup** |
| Replay's role | Hero | **Pillar 2 — the money: prove the fix** |
| Regression Firewall (Goldens + CI) | The whole product | **Pillar 3 — retained as lock-in, not discarded** |

**Analogy:** competitors are smoke detectors you must place where you *think* fire might start. Zroky is an **immune system** that learns the body's normal and flags infection — including a virus it has never seen.

---

## 5. Product Shape — 3 pillars only (cut the rest)

```
┌─────────────────────────────────────────────────────────────┐
│ PILLAR 1 — DISCOVER          (FREE, OSS)  ← the hook         │
│   Auto-baseline + unknown-failure surfacing (anomaly→failure)│
├─────────────────────────────────────────────────────────────┤
│ PILLAR 2 — PROVE             (PAID, core revenue)           │
│   Replay a fix faithfully. Honest fidelity score.          │
├─────────────────────────────────────────────────────────────┤
│ PILLAR 3 — GUARD             (PREMIUM)  ← lock-in           │
│   Discovered+proven goldens → flake-proof CI gate.         │
└─────────────────────────────────────────────────────────────┘
```

- **Discover is the hook; Prove + Guard are the retained Regression-Firewall money value.** We are not throwing the old product away — we are leading with discovery and keeping the proof/gate as the paid pillars.
- **Multilingual/Indic failure detection** lives *inside* the discovery engine as a capability, not as a headline.
- Everything outside these three (Drift dashboard, Ablation, Judge-Calibration UI, Outcome-Attribution dashboard, Billing experiments, Auto-PR, Digest) moves to `/labs` or is deleted. See §12.

### 5.0 Mix discipline: core engine + Discovery hero, not old-everything + new-everything

The correct "mix" is narrow: keep the old core engine only where it directly powers **Discover -> Prove -> Guard**. That means SDK, Gateway, Capture, Diagnosis, Issues, Replay, Goldens, and CI Gate stay because they form the proof and revenue path behind Discovery.

The incorrect mix is broad: keeping every old module and adding Discovery on top. That recreates the exact width trap this document is trying to fix. Every customer-facing feature must pass one test: **does it directly help Discover, Prove, or Guard?** If yes, keep it in the product path. If no, move it to `/labs` or delete it.

### 5.1 Resolving the time-to-value vs. warmup tension (important — flagged in review)

There is a real tension: **behavioral discovery needs a warmed baseline (~200+ traces), but we promise value in ~10 minutes.** These are only compatible if the **first-run experience does not depend on the warmed baseline.** The first-run path uses what is available *immediately*:

1. **Structural findings (instant):** deterministic detectors (empty output, schema violation, tool error, timeout, loop) need no baseline and fire on the very first traces.
2. **"Replay my last failure" (instant):** the user pastes/points at one known-bad call → Prove pillar runs immediately. This is the 10-minute "wow," and it needs zero baseline.
3. **Behavioral / unknown-failure discovery (post-warmup):** activates only after the baseline matures. The UI is explicit: *"Learning your agent's normal — behavioral findings unlock after ~N traces."* No guessing before warmup.

So: **10-minute value = structural + replay-last-failure. Differentiated unknown-failure discovery = post-warmup.** We never pretend behavioral discovery is instant, and we never stay silent on day one either.

---

## 6. System Architecture (high level)

```
        ┌──────────────────┐
        │  Customer Agent  │   (any framework / direct provider SDKs)
        └────────┬─────────┘
                 │  zroky SDK (fail-closed capture)
                 ▼
        ┌──────────────────────────────┐
        │  Ingest API (FastAPI)        │  PII mask · idempotency · cost · quota
        └────────┬─────────────────────┘
                 │ Call row (Postgres, RLS, monthly partitions)
                 │ enqueue
                 ▼
        ┌──────────────────────────────┐
        │  Celery workers (Redis)      │
        │   ├─ Structural detectors    │  (deterministic, existing)
        │   ├─ Behavioral Baseline     │  ◄── NEW: learns "normal"
        │   ├─ Anomaly Scorer          │  ◄── NEW: surfaces "abnormal"
        │   └─ FP Suppressor           │  ◄── NEW: near-zero false positives
        └────────┬─────────────────────┘
                 │ Discovered Findings (clustered, ranked, confidence-scored)
                 ▼
        ┌──────────────────────────────┐
        │  Discovery Store + API       │  /v1/findings  (proper columns, no JSON-blob)
        └────────┬─────────────────────┘
                 │ one-click → replay
                 ▼
        ┌──────────────────────────────┐
        │  Replay & Verify Engine      │  real-LLM / mocked-tool + FIDELITY SCORE
        └────────┬─────────────────────┘
                 │ verified fix → golden
                 ▼
        ┌──────────────────────────────┐
        │  Guard / CI Gate             │  pass / block / review (flake-proof)
        └──────────────────────────────┘
```

**Reused from existing codebase:** SDK, Ingest, Postgres/RLS/partitions, Celery, structural detectors, issue clustering, replay executor, golden/CI plumbing.
**New (the differentiation):** Behavioral Baseline modeler, Anomaly Scorer, False-Positive Suppressor, the `findings` store/API, and the replay **fidelity score**.

---

## 7. The Discovery Engine — deep technical design (the core)

This is where Zroky wins or dies. Goal: surface **non-obvious, semantic, multi-step** failures the customer never wrote a test for — with a **near-zero false-positive rate**.

> **Difficulty honesty (flagged in review):** behavioral baseline + anomaly scorer + FP suppressor is **not a simple feature — it is the single hardest core of the product** and will consume the most engineering effort and iteration. Plan staffing, timeline, and risk around this being *the* hard thing. Everything else (capture, replay plumbing, CI) is comparatively well-trodden.

> **Governing principle (from §1.1): Anomaly ≠ Failure.** The engine produces *anomalies* (deviations). It must only **promote** an anomaly to a customer-visible *failure* after corroboration (outcome / recurrence / replay / human). The promotion logic in §7.4 is more important than the detection logic in §7.2–7.3.

### 7.1 Two classes of detection (keep them separate)
1. **Structural (deterministic, already built):** empty output, schema violation, timeout, tool error, loop, rate-limit. 100% confidence, no baseline needed → also powers the day-1 first-run path (§5.1). These are *table stakes*, NOT the differentiator.
2. **Behavioral / semantic (NEW, the differentiator):** "this trace deviates from how this workflow normally behaves." Probabilistic; requires baseline + corroboration + suppression. Only active **post-warmup**.

### 7.2 Behavioral Baseline modeler
For each `(project, agent, workflow_name)` key, learn a **behavioral fingerprint** from production traffic (no labels required):

- **Tool-sequence distribution** — the typical ordered set of tools called (e.g. `get_refund_status → issue_refund`), with frequency. A trace that *skips* a normally-present tool is suspicious.
- **Output shape distribution** — length bands, structure (JSON vs prose), language, presence/absence of key fields (via fingerprint, not raw PII).
- **Cost / latency / token distributions** — per-step and end-to-end, with rolling mean + variance.
- **Outcome distribution** — when `zroky.outcome(...)` or human/thumbs signals exist, the normal outcome mix (e.g. 92% `resolved`, 5% `escalated`).
- **Embedding centroid** (optional, Tier-2) — semantic centroid of "normal" responses per workflow; large cosine distance = candidate anomaly.

**Warmup discipline:** a baseline is not "active" until it has seen ≥ N traces (configurable, e.g. 200) across a minimum time window. Before warmup, the engine **stays silent** (no findings) rather than guess. This directly protects against day-1 noise.

**Storage:** baselines are versioned per key; recomputed incrementally (rolling windows) so provider/model drift naturally re-baselines instead of permanently flagging.

### 7.3 Anomaly Scorer
For each new trace, compute deviation signals against the active baseline:

- `tool_sequence_deviation` (edit distance vs typical sequence; missing critical tool weighted high)
- `output_shape_z` (z-score on length/structure)
- `cost_z`, `latency_z`
- `outcome_mismatch` (claimed success but outcome signal says otherwise — **strongest signal, label-free**)
- `semantic_distance` (embedding distance from centroid; Tier-2)

These combine into a single **anomaly score** with an attached, human-readable **reason** ("skipped `get_refund_status`, which is present in 96% of normal traces for this workflow").

**Hard rule:** a finding must carry a concrete, evidence-backed reason. No "quality issue detected." If we can't explain *why*, we don't surface it.

### 7.4 Anomaly → Failure promotion + False-Positive Suppressor (the survival layer)

This is the **most important component in the entire product** — it operationalizes §1.1 (Anomaly ≠ Failure). An anomaly score alone NEVER surfaces. It must pass these gates before being promoted from `anomaly` → `watching` → `surfaced failure`:

1. **Warmup gate** — baseline must be mature (§7.2). Before warmup, no behavioral findings at all.
2. **Corroboration gate (the anomaly→failure test):** an anomaly is only promoted toward "failure" when backed by at least one corroborating evidence type — **outcome signal**, **recurrence**, **replay confirmation**, or **human confirmation** (per §1.1). A bare statistical deviation with none of these stays an unsurfaced anomaly.
3. **Multi-signal rule** — require either one *strong* signal (outcome mismatch / missing critical tool) OR ≥2 corroborating *weak* signals. A single weak signal never fires.
4. **Frequency/recurrence gate** — a one-off deviation is *watched*, not surfaced, until it recurs ≥ k times or crosses a population threshold (matches how silent failures actually present: "it failed the same way dozens of times").
5. **Variance awareness** — high-variance workflows get wider bands; normal stochasticity is never flagged as failure.
6. **Feedback loop** — every finding has thumbs up/down + "not a failure." Dismissals raise that pattern's threshold (the baseline learns from the human).
7. **Severity tiering** — `watching` (low confidence, hidden) is the DEFAULT; `surfaced` (high confidence, shown prominently) is reached only conservatively. Promote slowly, demote fast.

**North-star metric for this layer:** *precision of surfaced findings* — of everything we call a "failure," what fraction the developer agrees is real. Target: **≥ 90% precision on `surfaced` tier before any OSS launch.** We optimize **precision over recall** — missing some failures is survivable; crying wolf is not. (This precision-over-recall stance is a deliberate, mature trade-off, not a limitation.)

### 7.5 Clustering & lifecycle
- Findings group by `(workflow, deviation-signature)` into **Issues** with frequency, first/last seen, blast radius, sample traces (reuse existing clustering, but key on behavioral signature, not just `failure_code`).
- Lifecycle: `watching → surfaced → acknowledged → replaying → resolved → (regressed)`. (Fixes the competitor gap: "no issue lifecycle.")

### 7.6 Multilingual capability (hidden moat)
- Language detection per trace; baselines are **per-language** where traffic warrants (Hinglish/Indic treated as first-class, not "noise").
- Judge/semantic-distance steps use language-aware handling so English-bias doesn't manufacture false anomalies on Indic outputs.

---

## 8. Replay & Verification layer (supporting hero)

Once a finding is confirmed, the developer proposes a fix (prompt/model/config). Replay proves it — **honestly**.

- **Modes:** `shadow` (real LLM, tool calls mocked from frozen recorded context — default paid mode) and `sandbox` (real tools in a customer-controlled safe environment — premium). Stub remains *sanity-only*, never `verified`.
- **Fidelity score (NEW, the trust differentiator):** every replay reports how faithfully it reproduced the original scenario:
  - `"92% faithful — tool context matched, prompt re-executed. ⚠️ depended on external DB state now changed (8% uncertainty)."`
  - or an honest refusal: `"Cannot replay — depended on real-time inventory now gone. We will not call this verified."`
- **Verdict vocabulary (unchanged trust contract):** `verified_fix | fix_failed | inconclusive | tool_snapshot_missing | sandbox_unavailable | not_verified`.
- **Production-on:** `REPLAY_REAL_LLM_ENABLED` must ship **on** (today it's off) with per-run budget caps.

This is where "verified" must always mean verified. The fidelity score is what makes Zroky trustworthy where every competitor will just print "verified ✅".

---

## 9. Guard / CI layer (flake-proof)

Discovered + verified failures become **Guards** (goldens) that run on PRs.

- **Three verdicts, not two:** `PASS` · `BLOCK` (only at ≥99% confidence, consistent across reruns) · `REVIEW SUGGESTED` (borderline → comment, never block).
- **Flake killer:** any `fail` is re-run k times; if the verdict flips, it's flake → downgrade to `REVIEW`, never `BLOCK`. (Defends against LLM non-determinism — the existential risk of any blocking gate.)
- **Built-in distribution:** the PR comment ("Zroky caught a regression you didn't write a test for") is itself a sharing/virality surface.

**Rule:** the gate's job is to *earn trust*, not to nitpick. One wrong block = gate disabled forever.

---

## 10. End-to-end dataflow (worked example: refund agent)

```
1. WATCH: SDK captures production calls. After warmup, baseline is active.
   Zroky learns: "normal refund-status workflow calls get_refund_status
   in 96% of traces; outcome is 'resolved' 92% of the time."

2. DISCOVER: New traffic. 47 traces skipped get_refund_status AND outcome
   data shows 12 customers re-opened tickets.
   → Multi-signal (missing critical tool + outcome mismatch) + recurrence(47)
   → SURFACED finding, confidence high, reason attached.
   (This is a failure the developer NEVER wrote a test for.)

3. REPLAY: Developer edits prompt ("always call get_refund_status first").
   Shadow replay re-executes with frozen tool context.
   → "Candidate now calls get_refund_status. Output correct. Fidelity 94%.
      Cost +$0.001. VERIFIED ✅"

4. GUARD: One click → Guard created from the discovered+verified case.

5. CI: A later prompt change reintroduces the skip.
   → "🛑 BLOCK: refund-status check regressed. Failed 8/10 reruns
      (consistent, not flake). Evidence attached." PR not merged.
```

---

## 11. Mapping to the existing codebase

| New capability | Reuse / build on | Action |
|---|---|---|
| Capture | `zroky-sdk` (fail-closed) | **Keep as-is** |
| Ingest/store | `ingest.py`, Postgres RLS, partitions, Celery | Keep; **fix worker idempotency** (transactional status+side-effects) |
| Structural detection | `services/detectors/*` | Keep |
| **Behavioral baseline** | new module `services/discovery/baseline.py` | **Build** |
| **Anomaly scorer** | new `services/discovery/scorer.py` | **Build** |
| **FP suppressor** | new `services/discovery/suppressor.py` | **Build** (most important) |
| Findings store/API | replace JSON-blob Issue with **proper columns**; fix `/v1/issues` N+1 | **Refactor** |
| Replay | `replay_executor` + `_internal/replay_executor_live` | **Turn real-LLM on**, add **fidelity score** |
| CI gate | `regression_ci/orchestrator` | Add **3rd verdict + flake reruns** |
| Multilingual | new language-aware path in scorer/judge | **Build** (moat) |

**Cleanups required regardless:** remove `sys.modules` shims, delete `reproduce_test.py` and committed dev-diary cruft, de-dupe the two PR-dispatch pipelines, extract the copy-pasted `_safe_json_object`.

---

## 12. What to cut / move to `/labs`

Provider Drift dashboard · Ablation · Judge-Calibration UI · Outcome-Attribution dashboard · Billing experiments/pricing · Auto-PR (Tier-2) · Weekly Digest. These dilute focus and contradict the 3-surface product. Feature-flag behind `/labs` or delete. The diagnosis/outcome *signals* may still feed discovery internally, but they are not customer surfaces.

---

## 13. Distribution Strategy — OSS-led (global, geography-agnostic)

**Why OSS:** Langfuse proved this exact path from the *same wedge* ("demo→production is hard"): 2,000+ GitHub stars, 26M+ SDK installs/mo, 6M+ Docker pulls, Fortune-500 adoption → **acquired by ClickHouse (Jan 2026)**. OSS distribution is geography-agnostic — solves the "selling globally from India" problem.

**What to open-source:** `zroky-watch` — a standalone, MIT-licensed flight recorder **+ auto-discovery**. Standalone-useful (Langfuse formula), with the differentiated hook baked into the README first line (note the disciplined wording — "before you write evals," not "no evals"):
> *"Your AI agent returns 200 OK but fails the task — and you find out when the customer complains. zroky-watch surfaces those silent production failures so you know what to fix — before you write a single eval for them."*

**Launch mechanics (week 1 = make-or-break; ~35% of 100-day stars land in first 30 days):**
1. Pre-seed 50–100 personal contacts for day-1 stars/upvotes (cold launch dies).
2. **Show HN** with a pain-led title ("finds AI agent failures you didn't write tests for").
3. Same day: **r/LLMDevs, r/MachineLearning, r/LocalLLaMA** — a genuine technical post, tool as byproduct.
4. **Product Hunt** same week.
5. Aim for **GitHub Trending** (≈12× visits when hit) → compounding.
6. Respond to issues/PRs within 24h (contributor momentum days 30–40).
7. Content moat: comparison + concept posts on the **unique angle** ("the cold-start problem in agent eval," "what your eval suite can't see").

**Critical pre-condition:** do **not** launch until `surfaced`-tier precision ≥ 90%. The week-1 first impression is permanent.

---

## 14. Pricing

| Tier | What | Price model |
|---|---|---|
| **Discover** | Capture + auto-discovery (anomaly→failure) | Free / OSS, no usage limits (trust → adoption) |
| **Prove** | Faithful fix verification + fidelity score | Usage-based, cheap entry (vs $249/mo flat) |
| **Guard** | Flake-proof CI gate + team workflow | Premium |

Usage-based + low entry serves both global mid-market and cost-sensitive markets (India).

**ICP (narrow on purpose):** money-path, customer-facing agents (support / refund / sales / ops), **50k–1M calls/month, WITHOUT a dedicated eval team** — the cold-start segment Braintrust underserves.

---

## 15. 90-Day Execution Plan

**Days 1–14 — VALIDATE (no new product code):**
10 conversations with the exact ICP. One question: *"Would you want production failures surfaced without writing tests? How do you do it today?"* Proceed only if ≥6/10 are excited. (This gap — real-developer validation — is still open and no amount of analysis closes it.)

**Days 15–45 — STRIP + CORE:**
Cut to 3 surfaces (move 9 modules to `/labs`). Build the discovery engine MVP: behavioral baseline + anomaly scorer + FP suppressor. Fix worker idempotency + `/v1/issues` N+1. Turn real-LLM replay **on**.

**Days 46–75 — WOW + OSS:**
"Replay my last failure in 10 minutes" onboarding. Add replay fidelity score. Release `zroky-watch` OSS **only if** precision ≥ 90%. Run 3 design partners end-to-end.

**Days 76–90 — ONE KILLER PROOF:**
One real agent → one **discovered unknown failure** → verified fix → blocked regression. Public case study = the launch story. This one proof sells more than 12 modules.

---

## 16. Risks & Open Questions (honest)

1. **False-positive rate is existential.** If discovery is noisy, the product dies in week one. This is the hardest engineering problem here — not building the feature, making it *trustworthy*. Everything depends on §7.4.
2. **Anomaly ≠ failure is the deepest technical risk.** Detecting deviation is feasible; *proving the deviation is a real business failure* is the hard 70%. If corroboration (outcome/recurrence/replay/human) is weak, every "finding" is a guess. §1.1 + §7.4 are the answer and must be built first.
3. **Overpromise risk in messaging.** "Zero-eval / magic" language invites distrust and backlash when the tool inevitably misses something. We commit to "find failures before you write evals," never "no evals." (Wording discipline in the header.)
4. **Time-to-value vs. warmup tension is resolved by design, not by hand-waving** (§5.1): 10-min value = structural findings + replay-last-failure (no baseline); behavioral discovery = post-warmup, with an explicit "learning" state. If we ever blur these, we overpromise.
5. **Difficulty / staffing:** the discovery core (§7) is the hardest part of the product and the most likely to slip. Timeline and team must be built around *this*, not the easy plumbing.
6. **This entire plan is a research-backed hypothesis, not customer-validated.** Days 1–14 exist for this reason. No spec or code removes the need.
7. **A funded competitor can close the "discovery" gap in ~6 months.** The durable moat is therefore **speed + narrow-niche obsession + OSS community**, not the feature itself.
8. **Stars ≠ revenue.** OSS distribution is top-of-funnel only; validation comes from paying users. Langfuse had 2,000 stars *and* 2,000 paying customers; it was acquired by ClickHouse (Jan 2026).
9. **Not all failures are replayable** (external/time-sensitive state). Be honest about coverage — the fidelity score is how we stay honest.
10. **Operational vs model failures:** developers say failures are operational (tools, state, integrations). The discovery engine must catch tool/sequence/state anomalies, not just prompt/model regressions.
11. **Maintaining a viral OSS project is near-full-time** (issues, PRs, Discord, docs) and can pull focus from the core.

---

## 17. Success Metrics

- **Discovery precision (`surfaced` tier): ≥ 90%** — the gating metric for launch.
- **Anomaly→failure promotion accuracy** — of promoted findings, % corroborated by an independent signal (target high; this is the §1.1 metric).
- **Time-to-first-finding: ≤ 10 minutes** via the first-run path (structural + replay-last-failure) — explicitly **not** dependent on baseline warmup.
- **% of findings the developer calls "I didn't know about this"** — measures the actual differentiation (not just re-detecting obvious errors).
- **Design-partner conversion:** ≥ 2 of 3 say "I want this."
- **OSS:** week-1 star spike + GitHub Trending; but track **active SDK installs**, not vanity stars.
- **Replay fidelity honesty:** 0 cases where `verified` was reported on an unfaithful replay.

---

## 18. Decision Log (captured from the working discussion + critical review)

| # | Decision | Rationale |
|---|---|---|
| D1 | Keep the engine; **Discovery = hero, Regression Firewall = engine** | Lead with differentiation; retain the full money path underneath (Discover→Prove→Verify→Golden→CI) |
| D1b | **Category = "AI Agent Failure Discovery & Regression Guard"** | Carries both differentiation + monetization; beats "AgentOps / Observability / Firewall-only / Zero-eval" |
| D1c | **Website locked:** headline "Find the AI agent failures you did not know to test"; pillars Discover·Prove·Guard | Hero = discovery; under-the-hood components shown lower, not in hero |
| D2 | Lead pillar = **unknown-failure discovery** | Competitors' admitted gap; un-occupied corner |
| D3 | **"Find failures before you write evals"** — "zero-eval" is internal thesis ONLY, never public | Magical phrasing overpromises and invites distrust (review) |
| D4 | **Anomaly ≠ Failure**; promote only on corroboration | Deviation is easy; proving real failure is the hard 70% (review) |
| D5 | **Near-zero false positives = survival**, not a feature; precision over recall | Noisy discovery is uninstalled in week 1 |
| D6 | Replay = **Pillar 2 (the money)**, with **fidelity score** | Trust differentiator; don't fight Braintrust on "verify" alone |
| D7 | CI gate (Guard) = **3 verdicts + flake-proof** | One wrong block kills adoption |
| D8 | 10-min value via **structural + replay-last-failure**; behavioral discovery **post-warmup** | Resolves the warmup-vs-speed contradiction honestly (review) |
| D9 | Cut to 3 pillars; rest → `/labs` | Width was the `MVP_LOCK` trap |
| D10 | **OSS-led distribution** (`zroky-watch`) | Langfuse-proven (ClickHouse acq. Jan 2026), geography-agnostic |
| D11 | Multilingual/Indic = hidden moat, not headline | Competitor blind spot; sell globally |
| D12 | ICP = money-path agents, no eval team, 50k–1M calls/mo | Highest pain, underserved by enterprise tools |
| D13 | **Validate with 10 real devs before heavy build** | Only real "yes" closes the loop; AI validation can't |
| D14 | Discovery core (§7) is **the hardest part** — staff/timeline around it | Behavioral baseline + scorer + suppressor is not a simple feature (review) |

---

## 19. Next Step

Convert the **Discovery Engine** (behavioral baseline + anomaly scorer + anomaly→failure promotion / FP suppressor) into a formal spec — Requirements (what discovery must do, the **anomaly→failure corroboration rules**, and the hard false-positive bound) and Design (baseline-modeling architecture), then tasks. This is the component on which the entire product, differentiation, and OSS launch depend.

> **The one sentence that decides everything:**
> *Can we make auto-discovery trustworthy enough that a developer says "yes, it caught a real failure I was missing" — without the noise, and without calling a harmless deviation a failure?*
> Yes → a genuinely differentiated global product. No → another noise machine.
