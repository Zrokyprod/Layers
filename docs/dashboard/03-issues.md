# 03 — Issues (Discover surface — list + detail)

| | |
|---|---|
| **Files** | `issues/page.tsx` (506 LOC), `issues/[id]/page.tsx` (1026 LOC), `lib/issue-format.ts`, `lib/detector-meta.ts` |
| **Pillar** | **Discover** — where surfaced findings live (Option A: `BEHAVIORAL_DRIFT` anomalies project here) |
| **State** | Mature. Filters (status/severity/failure-code/agent/replay-proof/search), next-action engine (run_replay → promote_golden → run_ci_gate → assign_resolve), trust-aware sort, proof snapshot (replay/golden/ci). |

## 1. Purpose
The Issues surface is the clustered "problem" list. Discovery findings appear here automatically. This is where **Discovered vs Detected** must become visible — the differentiator.

## 2. STAYS
- Filter bar, search, sort, `issueNextAction` engine, proof snapshot (`proof.replay/golden/ci_gate`), `ProviderKeyReplayGate`, trust statuses (`UNTRUSTED_REPLAY_STATUSES`, `hasVerifiedFix`).

## 3. CHANGES
- **Sort/group:** surface discovered findings prominently (already sorts untrusted-replay first; add discovered weighting).
- **Replay-proof filter** stays; add a **Source filter** (Discovered / Detected / All).

## 4. ADD (the differentiator)
- **Badge per issue:** `Discovered` (accent) vs `Detected` (neutral). Helper `isDiscovered(issue)` from detector code `BEHAVIORAL_DRIFT` / `is_discovered`.
- **Detail page (`[id]`): reason + corroboration block at top** for discovered issues:
  - Reason sentence ("missing critical tool get_refund_status present in 96% of normal traces; outcome success→failure").
  - Corroboration chips: `missing critical tool` · `outcome mismatch` · `recurrence ×47`.
  - Baseline context line.
- **Feedback control** (detail): Real failure / Not a failure / Unsure → writes feedback; "not a failure" demotes + raises signature bar (precision loop).
- **`watching` secondary view:** opt-in sub-tab "Watching (low confidence)", default hidden. Honors Anomaly ≠ Failure.

## 5. CUT
- Nothing. (Do NOT build a `/findings` page — Option A.)

## 6. Data the UI needs (backend passthrough from sink evidence)
- [ ] `is_discovered` (or detector == `BEHAVIORAL_DRIFT`)
- [ ] `reason` (string), `corroboration` (string[]), `confidence` (number), `tier` (surfaced/watching)
- These come straight from the sink's `evidence` payload — issue projection passes them through. **Depends on the `/v1/issues` N+1 fix** (completion plan Phase 3) so this read stays clean.

## 7. States
- Loading skeleton; empty ("no open issues — discovery is learning your normal" when `DISCOVERY_ENABLED` and baseline learning); error retry; populated.

## 8. Discovery integration (core)
This + home are THE discovery surfaces. The badge + reason is where the buyer sees "you found something I wasn't testing for." Without it, discovery is invisible.

## 9. My POV
- The **Discovered badge is the single highest-signal UI element in the whole product.** Build it first (smallest change, biggest differentiation payoff).
- The reason/corroboration block must be honest and specific — generic text kills trust. It's already produced by the engine; just render it well.
- The `watching` view is important for trust: it lets power users audit "what's Zroky considering but not surfacing?" — proof the engine isn't crying wolf.

## 10. DoD
- [ ] Discovered/Detected badge + Source filter.
- [ ] Detail reason/corroboration block + feedback buttons.
- [ ] Watching secondary view (gated).
- [ ] Backend passthrough fields present; list is indexed (no N+1).
