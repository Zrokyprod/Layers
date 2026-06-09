# Zroky — Discovery Pillar: End-to-End Completion Plan

| | |
|---|---|
| **Status** | Build tracking doc — single source of truth for "what's left to a clean product" |
| **Scope** | The **Discover** pillar end-to-end, plus the wiring into the existing Prove (Replay) + Guard (CI) engine. |
| **Parent docs** | `ZROKY_DISCOVERY_ENGINE_ARCHITECTURE.md` (strategy), `ZROKY_DISCOVERY_ENGINE_PLAN.md` (engineering plan) |
| **Decisions locked** | Discover = hero, Regression Firewall = engine · Option A (discovery writes to existing `anomalies`/`/v1/issues`, no parallel table) · one shared engine for harness + production · "Anomaly ≠ Failure" · precision over recall |

---

## 0. Definition of "clean product"

A clean product means ALL of these are true:
1. One coherent loop: **Discover → Prove → Guard**, no duplicate concepts.
2. Discovery runs live (capture → baseline → score → surface) behind `DISCOVERY_ENABLED` (default off).
3. Surfaced findings appear in the existing Issues surface, can be replayed (Prove), promoted to Golden, and guarded in CI (Guard) — end to end.
4. Precision gate proven (≥90% surfaced) on realistic data before it's enabled for anyone.
5. Dashboard reflects the 3-pillar story; non-core modules moved to `/labs`.
6. Known debt fixed (worker idempotency, `/v1/issues` N+1, committed cruft).
7. Tests green; migrations apply; build passes.
8. OSS `zroky-watch` packaged (final step, gated on precision).

---

## 1. Where we are now (done)

- [x] Strategy + positioning locked (architecture doc).
- [x] Engineering plan + spec (requirements/design/tasks) for the Discover spike.
- [x] **Shared discovery engine** (pure, DB-free) — single source of truth:
  - `features.py` (trace → features), `baseline_core.py` (baseline math),
    `scorer.py` (anomaly scoring), `promote.py` (anomaly→failure gates).
- [x] **DB layer** — `behavioral_baselines` table + migration `0077`; `baseline.py` (persistence); `BEHAVIORAL_DRIFT` detector added to anomalies.
- [x] **Option A sink** — `sink.py` writes surfaced clusters into the existing `anomalies` table (single problem surface).
- [x] **Offline harness** refactored to a thin wrapper over the shared engine (no duplicate logic). Demo: 1 baseline, 3 surfaced clusters, 11/11 injected recall, precision 0/0 (labels required).

**Current completion: ~25%** — engine core + offline proof tooling exist; not yet live, not yet proven on real data, no UI, debt not fixed.

---

## 2. The end-to-end plan (phases to a clean product)

Each phase has a clear exit. Phases are ordered so the riskiest/cheapest validation comes before expensive build, and the product stays shippable-clean at every step.

### PHASE 1 — Prove precision on realistic data (GATE — do first)
*Why first: everything downstream is wasted if discovery cries wolf.*
- [ ] Build a realistic mixed dataset generator (~300–500 traces: ~90% normal + ~10% realistic failures — tool skip, schema break, outcome mismatch, latency/cost spikes) with proper `agent_name`/`workflow_name`/`outcome`.
- [ ] Run harness → manually label surfaced findings → produce precision report.
- [ ] Iterate **only on the shared gates** (`scorer.py`/`promote.py`) until `surfaced` precision ≥ ~90%.
- **Exit:** documented precision number ≥ ~90% on the mixed dataset. If unreachable → revisit thresholds/signals before building further.

### PHASE 2 — Runtime orchestration (make discovery live)
*The engine exists but nothing runs it on real traffic yet.*
- [ ] `discovery/runtime.py` — `refresh_baselines(project)` and `scan_and_surface(project)` that read recent `Call` rows (read-replica aware), build/persist baselines, score new traces, and call the sink.
- [ ] Celery beat task(s): periodic baseline refresh + scan, gated by `DISCOVERY_ENABLED` (default off) and per-project flag.
- [ ] Config keys (`DISCOVERY_ENABLED`, warmup/recurrence/confidence tunables) in `core/config.py`, default safe.
- **Exit:** with `DISCOVERY_ENABLED=true` on a test project, a captured failure becomes a surfaced anomaly automatically; off by default for everyone else.

### PHASE 3 — Fix the engine debt it touches
*Clean product can't ship on top of known bugs in the same path.*
- [ ] **Worker idempotency** — make `job.status='done'` commit + side-effects (issue upsert, fix events) one transactional unit (or re-emit on retry). (Pre-existing data-correctness bug.)
- [ ] **`/v1/issues` N+1 + in-memory filter** — fix the dashboard-home read path. (`findings`-style indexed reads / precomputed columns; discovery surfaces here so it must scale.)
- **Exit:** issues list is an indexed query; worker retry can't drop side-effects; tests cover both.

### PHASE 4 — Discover → Prove → Guard end-to-end wiring
*Make the loop real in the product, reusing existing Replay/Golden/CI.*
- [ ] Surfaced finding (anomaly) → **one-click Replay** (reuse `create_replay_from_issue` / `replay_runs`; the issues page already has `createReplayRunFromIssue`).
- [ ] Replay verified (fidelity score) → **promote to Golden** (existing goldens).
- [ ] Golden → **CI Gate** with 3 verdicts (pass / block / review) + flake re-runs (extend `regression_ci`).
- [ ] First-run "replay my last failure" path (10-min value, no warmup dependency).
- **Exit:** a discovered unknown failure can be replayed, verified, goldened, and block a regressing PR — one continuous flow.

### PHASE 5 — Dashboard alignment (the 3-pillar product)

The core UI is already deep and trust-aware (home Failure Inbox 1234 LOC, issues 506 + detail 1026, replay 769 + detail 1108, goldens/ci-gates/calls/trace all substantial). Discovery needs **no new page** — it surfaces through the existing issues/inbox because the sink writes `BEHAVIORAL_DRIFT` rows into `anomalies` (Option A). Concrete UI work:

**5a — Surface discovery in the Failure Inbox (`home/page.tsx`)**
- [ ] Add a queue focus **`discovered`** to `InboxQueueFocus` (next to all/critical_high/replay_gap/impact/verified): "failures Zroky found that you didn't write a test for."
- [ ] Update the first-run onboarding copy: capture → **Zroky auto-discovers** → replay (today it implies capture → replay).
- [ ] A KPI/section: "N unknown failures discovered this week."

**5b — Differentiate Discovered vs Detected on Issues (`issues/page.tsx` + `[id]`)**
- [ ] Badge on each issue: **"Discovered"** (behavioral, no rubric) vs **"Detected"** (structural). Drives from the anomaly detector code (`BEHAVIORAL_DRIFT` vs others). This badge is where the differentiation vs Braintrust/Judgment becomes *visible*.
- [ ] On issue detail, prominently render discovery **reason + corroboration** ("present in 96% of normal traces; missing here + outcome mismatch"). The "why" is the wow.
- [ ] Feedback control (real / not-a-failure / unsure) → feeds the suppressor's adaptive threshold (precision loop).

**5c — Discovery → Replay handoff (Prove)**
- [ ] One-click from a discovered issue → Replay Lab (reuse existing handoff). Add the fidelity score display in `replay/[id]`.

**5d — Scope-drift cleanup (move out of primary nav)**
- [ ] `agents` (Release Safety Console, 1029 LOC) → `/labs` or feature flag.
- [ ] `drift` (Provider/Judge/Outcome, 377 LOC) → `/labs` or feature flag.
- [ ] Nav (`dashboard-shell.tsx`) reflects Discover · Prove · Guard; non-core out of primary nav.
- **Exit:** dashboard tells the 3-pillar story; discovery is visible and differentiated; no scope-drift modules in primary nav.

### PHASE 5.5 — Judgment-inspired enhancements (adopt the idea, not the heavy impl)
*Borrowed from competitor analysis (Judgment Labs). Adopt selectively; do NOT copy their funded-team heavy features.*
- [ ] **Slack investigation** — extend existing `slack_integration` so a developer can investigate a surfaced failure conversationally from Slack ("show similar cases", "root cause"), not just receive an alert. (Adoption booster — devs live in Slack.)
- [ ] **Similar-case triage surface** — reuse the existing signature clustering to show "similar failure cases + which use cases are impacted" on an issue. (Use our cheap statistical clustering; do NOT build LLM "agent swarms".)
- [ ] Borrow framing: "don't push into the dark" for the Prove/Replay CTA copy.
- **Exit:** Slack investigation + similar-case triage live; framing aligned. (Lower priority than precision + core loop.)

### PHASE 6 — Cleanup + hardening
- [ ] Delete committed cruft: `reproduce_test.py` (foreign project), throwaway scripts, dev-diary files as appropriate.
- [ ] **Dashboard dead routes:** delete empty `recommendations/` + `root-cause/` route dirs; resolve stub `account` (2 LOC) + `settings/profile` (4 LOC); consolidate duplicate auth routes (top-level `/login,/signup,/forgot-password,/reset-password,/verify-email` vs `/auth/*`); remove unrendered `coming-soon-poll.tsx`.
- [ ] De-dupe leftover patterns (`_safe_json_object` copies; redundant PR-dispatch paths) where they intersect the discovery path.
- [ ] Tests: unit (features/scorer/promote/baseline), integration (runtime→sink→issues), migration apply, route tests for any new surface.
- [ ] Run backend test suite + dashboard build; fix breakages.
- **Exit:** green tests, clean tree, migrations apply, build passes.

### PHASE 7 — Real-trace validation (mandatory before launch)
- [ ] Run the harness/engine on **2–3 real or pilot agents' traces**; label; confirm precision holds (synthetic-pass ≠ product-proven).
- **Exit:** precision holds on real traces → safe to enable discovery for real projects.

### PHASE 8 — OSS packaging + launch (`zroky-watch`)
- [ ] MIT standalone capture + discovery; README per positioning doc; demo GIF; < 5-min install.
- [ ] Launch sequence (Show HN + Reddit + PH), only after Phase 7 precision holds.
- **Exit:** public OSS release.

---

## 3. Dependency order (at a glance)

```
PHASE 1 (precision gate) ──► PHASE 2 (runtime) ──► PHASE 4 (loop wiring) ──► PHASE 5 (dashboard)
        │                          │                                              │
        └─ blocks everything       └─ PHASE 3 (debt fix, parallel-ok)             │
                                                                                  ▼
                                          PHASE 6 (cleanup) ──► PHASE 7 (real traces) ──► PHASE 8 (OSS launch)
```

- **Phase 1 is the gate** — do not invest in 4/5/8 until precision is proven.
- **Phase 3 (debt)** can run in parallel with 2, since it's independent code.
- **Phase 7** is the hard launch gate (real data).

---

## 4. Definition of done per pillar

- **Discover:** baselines learn live; deviations corroborated → surfaced anomalies; feedback loop active; precision ≥90% (synthetic) then real-trace confirmed.
- **Prove:** surfaced finding → real-LLM/mocked replay with honest fidelity score; "verified" only when truly verified.
- **Guard:** verified golden → CI gate with pass/block/review + flake resistance; PR comment.

---

## 5. Open risks carried forward (from architecture doc)
- False-positive rate is existential (Phase 1 + 7 address it).
- Synthetic-pass ≠ product-proven (Phase 7 mandatory).
- A funded competitor can copy "discovery" → moat = speed + niche + OSS community.
- Real-developer validation still required; this plan builds the thing worth validating, it does not replace validation.

---

## 6. Immediate next action

**Phase 1, step 1:** build the realistic mixed-failure dataset generator + run the harness to get the first precision number. This is the gate that unlocks (or redirects) everything else.
