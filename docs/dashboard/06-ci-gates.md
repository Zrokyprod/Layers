# 06 — CI Gates (Guard — list + detail)

| | |
|---|---|
| **Files** | `ci-gates/page.tsx` (463 LOC), `ci-gates/[runId]/page.tsx` (404 LOC), `ci-gates/ci-utils.ts` |
| **Pillar** | **Guard** — block regressions in PRs; the lock-in |
| **State** | Mature. KPI cards (failed/blocked, not_verified, running, pass), status filter, search/sort, auto-refresh, run-a-gate panel (git sha / threshold / changed files), `normalizeStatus`, trust-honest ("Not verified — never counted as pass"). |

## 1. Purpose
CI Gates show PR-level release decisions backed by replay evidence. This is the recurring-value surface: the gate that prevents the same failure shipping twice.

## 2. STAYS
- KPI cards + status filters, run detail, `summaryUrl`/PR linking, `normalizeStatus`, the honest "not_verified ≠ pass" framing (already correct and a key trust point).

## 3. CHANGES / ADD (from completion plan Phase 4)
- **Third verdict surfaced: `review`** — alongside pass / blocked / not_verified. Today statuses are fail/error/not_verified/pass; add a clearly-styled **Review suggested** state (borderline; not a block). This is the flake-resistance UX.
- **Flake transparency:** when a verdict came from re-runs, show "consistent across N re-runs" vs "flaky — downgraded to review." Builds trust that the gate won't false-block.
- **PR comment preview** (if not already) — show what the developer sees in GitHub.

## 4. CUT
- Nothing.

## 5. Data / API
- `ReplayRunItem` (trigger=github / `regression-ci:` set), `RegressionCIRunDetailResponse`, run-a-gate dispatch. Backend: extend `regression_ci` for the 3rd verdict + re-run/flake handling.

## 6. States
- Loading, empty ("no CI runs yet — connect the GitHub Action"), error, populated. Active/running auto-refresh.

## 7. Discovery integration
- Indirect: discovered → proven → golden → **guarded here**. Optionally tag a gate's protected flow with its discovery origin.

## 8. My POV
- The honesty here ("not verified never counts as pass") is a real asset — keep it loud.
- The **3rd verdict (review) + flake transparency is the most important add** — because one wrong BLOCK kills adoption. The UI must make "we only block when 99% sure" visible, or developers won't trust the gate in their critical path.
- Keep the run-a-gate panel; it's good for manual testing.

## 9. DoD
- [ ] `review` verdict surfaced + styled (not a block).
- [ ] Flake/re-run transparency shown.
- [ ] not_verified honesty intact; PR comment preview present.
