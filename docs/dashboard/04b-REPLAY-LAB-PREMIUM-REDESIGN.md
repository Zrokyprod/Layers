# Replay Lab — Premium 10/10 Redesign Plan

Grounded in: real code (`replay/page.tsx` 769 LOC, `replay/[id]/page.tsx` 1108 LOC,
`lib/replay-mode.ts`), spec `04-replay-lab.md`, and actual CSS in `globals.css`.

## Critical finding — 3 conflicting design languages
1. Dashboard root tokens = **LIGHT** SaaS (canvas `#f6f7f9`, accent Stripe-purple `#635bff`).
2. Replay Lab overrides to a **DARK + ORANGE island** (`#0b0c0f`, `#f97316`) — inconsistent
   with the rest of the dashboard.
3. New landing = **black monochrome** (violet/green/red semantic).

This inconsistency is the #1 reason it doesn't feel "worldclass". A premium product has ONE
language. **Decision needed (see bottom).**

## What the spec 04 mandates (must respect)
- DO NOT change functional logic. Module is functionally the strongest.
- KEEP: mode selection + gating, original-vs-candidate panels, verification vocabulary
  (`verified_fix / fix_failed / inconclusive / tool_snapshot_missing / sandbox_unavailable / not_verified`),
  trust semantics (stub = sanity only, never "verified").
- ADD: discovered→replay handoff with source-finding reason; **fidelity score** in the
  verification panel (the trust differentiator — top priority).
- 4 states everywhere: loading / empty(first-run) / error / populated.

So: **elevate the visual + interaction layer, preserve the logic + vocabulary.**

## Honest current rating: 7/10
Strong IA + trust semantics + proof density. Loses points on:
- Native `<select>` / `<textarea>` form controls (2018 admin vibe).
- Flat density, no visual hierarchy — every block same weight.
- Plain-text empty/loading states (no skeletons / illustrated first-run).
- Dark+orange island clashes with the rest of the app.
- The "wow" (original vs candidate diff + fidelity) lives only on `[id]`; list page reads
  like a spreadsheet.

## Premium target — what 10/10 looks like
### List page (`/replay`)
- **One clear hero CTA** (Start replay). Metrics strip becomes secondary (smaller, muted).
- **Launcher upgrade:** native selects → custom comboboxes with search + inline source
  preview card (shows the finding reason / call error / golden trace count live).
- **Mode selector:** segmented "proof strength" ladder with a confidence meter, not 5 equal
  boxes; clearly mark stub as "sanity only".
- **Run queue:** premium cards with a mini before→after sparkline, verdict pill, fidelity
  badge, cost/latency delta. Skeleton shimmer while loading. Illustrated empty state
  ("Replay a discovered failure" → deep-links to inbox).
### Detail page (`/replay/[id]`) — the money shot
- **Split original-vs-candidate diff** as the centerpiece: side-by-side panels with a
  synced diff, tool-behavior diff, output diff.
- **Verification panel = the star:** big verdict, **fidelity score with a ring/meter** and a
  plain-language explanation ("92% faithful — tool context matched… ⚠️ 8% external state"),
  honest refusal state.
- Cost/latency/outcome deltas as a compact stat band.
- Sticky action bar: Promote to Golden (gated on verified), Re-run, Open source.

## Motion / polish
- Framer-motion reveal + verdict count-up + fidelity ring draw. Respect reduced-motion.
- Skeletons for loading; illustrated empty/warmup states.

## Build approach (scoped, low-risk)
The pages are large (1877 LOC). I will NOT rewrite logic. Plan:
1. Add a dedicated premium CSS layer for replay (new classes, scoped) OR refactor in-place.
2. Phase 1 — list page visual layer (hero hierarchy, launcher controls, run cards, states).
3. Phase 2 — detail page diff + fidelity panel (the "wow").
4. Fidelity score: UI ships now reading `summary.verification_status` + a new
   `summary.fidelity` field (backend addition tracked separately); UI degrades gracefully
   when absent.
5. `npm run build` + lint after each phase.

## OPEN DECISION (need user pick before building)
**Which theme is the One?**
- (A) Keep Replay dark+orange, but make it premium-dark (Linear-grade). Fastest; but the rest
  of the dashboard stays light — island remains.
- (B) Re-theme Replay to the LIGHT Stripe-purple system to match the rest of the dashboard.
  Most consistent *within the app*.
- (C) Move the WHOLE dashboard to the black monochrome landing system (biggest job, but one
  language across site + app — true worldclass consistency).
