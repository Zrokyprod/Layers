# Zroky — Discovery Engine: Dashboard UI Plan

| | |
|---|---|
| **Status** | UI build plan — grounded in the existing dashboard code |
| **Scope** | How the **Discover** pillar appears in the dashboard. Prove (Replay) + Guard (CI) UIs already exist; this plan only adds discovery surfaces + wiring. |
| **Core rule** | **No new top-level page.** Discovery surfaces through the existing Failure Inbox + Issues, because the engine writes `BEHAVIORAL_DRIFT` rows into `anomalies` (Option A) which already power `/v1/issues`. |
| **Design rule** | Reuse existing components/CSS (`fi-*` inbox classes, issue cards, badges). Match current trust-aware tone. No restyle. |

---

## 0. Guiding principles (UX)

1. **Discovered ≠ Detected must be visible.** The whole differentiation vs Braintrust/Judgment is "we found a failure you never wrote a test for." If the user can't *see* which findings were auto-discovered, the wedge is invisible. This badge is the single most important UI element.
2. **Always show the "why".** Every discovered finding renders its evidence-backed reason + corroboration. No "quality issue detected" — always "missing critical tool present in 96% of normal traces + outcome mismatch."
3. **Anomaly ≠ Failure in the UI too.** Only `surfaced` findings appear in the inbox. `watching` lives in a secondary, opt-in view. Never dump low-confidence noise on the primary surface.
4. **Feedback is one click.** real / not-a-failure / unsure — and "not a failure" visibly removes it (and quietly raises that signature's bar).
5. **No new nav item for v1.** Discover is the *quality* of the inbox, not a separate destination. (Optional later: a "Discovered" saved-filter shortcut.)

---

## 1. Where discovery shows up (existing screens)

```
home (Failure Inbox 1234 LOC)  ── new "Discovered" queue focus + KPI + onboarding copy
issues (506 LOC) + [id] (1026) ── Discovered/Detected badge, reason+corroboration, feedback, watching tab
replay (769) + [id] (1108)     ── one-click handoff from a discovered finding + fidelity score
goldens / ci-gates             ── unchanged (Guard); reached from a proven discovered finding
```

Nothing else changes. No `/findings` page (deliberately removed — Option A).

---

## 2. Component-level plan

### 2.1 Failure Inbox — `home/page.tsx` (1234 LOC)

**A. New queue focus `discovered`**
- Extend `InboxQueueFocus` type: `"all" | "critical_high" | "replay_gap" | "impact" | "verified" | "discovered"`.
- `filterIssuesForFocus(items, "discovered")` → items whose source is behavioral discovery (detector `BEHAVIORAL_DRIFT`, or an `is_discovered` flag on the issue payload).
- `queueFocusDescription("discovered")` → "Failures Zroky found from production behavior — that you never wrote a test for."
- Add the focus chip in the queue tab row (same styling as existing chips).

**B. KPI tile (in the existing metric strip / `kpi-strip.tsx`)**
- "Unknown failures discovered" → count of surfaced discovered issues in window.
- Subtext: "auto-surfaced, no eval written."

**C. First-run onboarding copy (`FirstRunOnboarding`)**
- Current: capture → (implies) replay.
- New: "Capture your first agent call. Zroky learns its normal behavior and **surfaces failures you didn't write tests for** — then you replay and prove the fix."
- Keep the "don't start with replay, start with evidence" ordering.

**Exit:** a discovered failure appears in the inbox under the Discovered focus with a count tile; onboarding tells the discovery story.

### 2.2 Issues list — `issues/page.tsx` (506 LOC)

**A. Discovered vs Detected badge (THE differentiator)**
- On each issue card, a small badge:
  - **Discovered** (accent color) — behavioral, no rubric (detector `BEHAVIORAL_DRIFT`).
  - **Detected** (neutral) — structural detector (everything else).
- Source: issue `failure_code`/detector already on `IssueItem`. Add a helper `isDiscovered(issue)`.

**B. Filter option**
- Add to the existing `Filters` (`replayProof` row style): a "Source: Discovered / Detected / All" select.

**C. Watching (secondary) view**
- A toggle / sub-tab "Watching (low confidence)" — lists `watching`-tier findings, clearly labeled "not yet confirmed." Default hidden. Honors Anomaly ≠ Failure.

**Exit:** user can see and filter which issues were auto-discovered; low-confidence stays out of the primary list.

### 2.3 Issue detail — `issues/[id]/page.tsx` (1026 LOC)

**A. Reason + corroboration block (top, prominent)**
- For discovered issues, render the evidence panel first:
  - The reason sentence ("On refund_status_check, this trace deviated: missing critical tool get_refund_status (96%); outcome changed success→failure.")
  - Corroboration chips: `missing critical tool` · `outcome mismatch` · `recurrence ×47`.
  - Baseline context: "Normal: get_refund_status called in 96% of N traces."

**B. Feedback control**
- Buttons: **Real failure** / **Not a failure** / **Unsure** (writes feedback; "not a failure" demotes + raises signature bar). Small, inline, non-intrusive.

**C. Next-action CTA (reuse existing engine)**
- Keep the existing `issueNextAction` flow (run_replay → promote_golden → run_ci_gate). For discovered issues the first CTA is **Run replay** (Prove).

**Exit:** the "why" is the hero of the detail page; one click moves to Prove; feedback closes the precision loop.

### 2.4 Replay (Prove) — `replay/[id]/page.tsx` (1108 LOC)

- One-click handoff already exists (`createReplayRunFromIssue`); ensure a discovered issue routes here cleanly with its sample call.
- **Add fidelity score** display in the verification panel (plan): "92% faithful — tool context matched; ⚠️ external state changed (8%)."
- No restyle; add to the existing verification block.

**Exit:** discovered → replay is one click; replay honesty (fidelity) is visible.

### 2.5 Nav — `components/dashboard-shell.tsx` (812 LOC)

- **v1: no new nav item.** Discover lives inside the inbox/issues.
- Optional later: a sidebar shortcut "Discovered" that deep-links to `/home?focus=discovered` or `/issues?source=discovered`.
- Scope-drift cleanup (separate, Phase 5d): move `agents` + `drift` out of primary nav → `/labs`.

---

## 3. Data contract the UI needs (backend)

For the UI to render the above, the issue payload (`IssueItem` / `/v1/issues`) must expose (from the `BEHAVIORAL_DRIFT` anomaly evidence the sink already writes):
- [ ] `is_discovered` (bool) or rely on detector code = `BEHAVIORAL_DRIFT`.
- [ ] `reason` (string) — already produced by the engine; surface it.
- [ ] `corroboration` (string[]) — already in evidence_json; surface it.
- [ ] `confidence` (number) — for sort/marking.
- [ ] tier (`surfaced` only in main list; `watching` for the secondary view).

> These come straight from the sink's `evidence` payload (`source=discovery`, `primary_dimension`, `summary`, `corroboration`, `confidence`). The issue projection just needs to pass them through (and the `/v1/issues` N+1 fix in Phase 3 makes this read clean).

---

## 4. Build order (small — UI mostly reuses existing)

1. **Backend passthrough** — issue projection exposes `is_discovered` + `reason` + `corroboration` + `confidence` (depends on sink, done).
2. **Issues badge + filter** (2.2) — smallest, highest-signal (the differentiator becomes visible).
3. **Issue detail reason/corroboration + feedback** (2.3).
4. **Inbox discovered focus + KPI + onboarding copy** (2.1).
5. **Replay fidelity display** (2.4).
6. **Watching secondary view** (2.2C).
7. **Nav cleanup / optional shortcut** (2.5).

> All of this is gated behind `DISCOVERY_ENABLED` per project — UI shows discovery surfaces only when the engine is enabled and has surfaced findings.

---

## 5. Out of scope (deliberately)

- New `/findings` page — removed (Option A).
- New nav destination for v1.
- Restyling existing screens.
- Slack investigation / similar-case triage UI — tracked separately (Phase 5.5), lower priority.

---

## 6. Dependency note

This UI is only worth building **after Phase 1 (precision ≥90%)** proves discovery surfaces real failures without noise. A beautiful "Discovered" badge on noisy findings actively hurts trust. Build the engine's precision first; this UI plan is ready to execute the moment precision holds.
