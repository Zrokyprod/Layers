# 05 — Goldens (Guard — list + detail)

| | |
|---|---|
| **Files** | `goldens/page.tsx` (389 LOC), `goldens/[id]/page.tsx` (627 LOC), `goldens/golden-utils.ts` |
| **Pillar** | **Guard** — promoted, proven failures become regression guards |
| **State** | Mature. Create set panel, set list with filters/search, run status, CI-blocking visibility, golden detail with criteria/traces. React Query mutations. |

## 1. Purpose
A Golden is a production-derived test case representing expected behavior for a critical flow. Goldens are how a proven fix becomes durable protection. Guard pillar entry.

## 2. STAYS
- Golden set CRUD, trace list, `blocks_ci` toggle, flaky flag, CI badge classes, plan-gating (`pilot.goldens_basic`), needs-review logic (`trace_count===0 || is_flaky || !blocks_ci`).
- The non-negotiable rule (already enforced): a failed output is never auto-treated as expected behavior; active goldens require expected behavior/criteria.

## 3. CHANGES / ADD
- **Promote-from-verified flow:** from a verified replay (Prove) of a discovered finding → "Promote to Golden" pre-filled with source call + expected behavior. (Issues page already deep-links `/goldens?call_id=...`; ensure discovery source context carries through.)
- **Drift/needs-review surfacing:** keep — but label clearly ("expected behavior may be outdated" vs "agent regressed").

## 4. CUT
- Nothing.

## 5. Data / API
- `listGoldenSets`, `createGoldenSet`, set/trace CRUD, `ReplayRunItem` for run status. CI-block flags.

## 6. States
- Loading, empty ("no goldens yet — promote a verified fix"), error, populated. Draft vs active trace distinction visible.

## 7. Discovery integration
- Indirect: discovered → proven → **golden**. The handoff must preserve "this golden came from a discovered failure" provenance (nice for trust/audit, optional v1).

## 8. My POV
- Goldens are solid and the trust rules are mature (draft vs active, expected-behavior requirement). Minimal change needed.
- The one thing worth adding: **provenance** — showing a golden was born from a discovered+proven failure closes the Discover→Prove→Guard story visually. Low effort, high narrative value.
- Don't expand criteria-builder complexity now; it's adequate.

## 9. DoD
- [ ] Promote-from-verified carries source/discovery context.
- [ ] Draft/active + drift labeling clear.
- [ ] Plan-gating + CI-block visibility intact.
