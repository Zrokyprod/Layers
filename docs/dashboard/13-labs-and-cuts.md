# 13 — /labs & Cuts (scope-drift + dead modules)

| | |
|---|---|
| **Scope** | Everything that should leave the primary product: scope-drift modules (→ `/labs`) and dead code (→ delete). |
| **Why** | The product is Discover → Prove → Guard. These dilute the story (the exact `MVP_LOCK` trap) — but we don't necessarily delete value, we *hide* it. |

## 1. Move to `/labs` (feature-flagged, out of primary nav)

### `agents` — Release Safety Console (1029 LOC)
- Largest non-core module. Advanced agent reliability/cost/determinism analytics.
- **Action:** route → `/labs/agents`, feature-flag, remove from primary nav + command palette (or label `/labs`).
- **Why not delete:** it has real analytics value for advanced users; just not the hero. Revisit post-PMF.

### `drift` — Provider/Judge/Outcome (377 LOC)
- Provider drift + judge drift + outcome drift tabs.
- **Action:** route → `/labs/drift`, feature-flag, out of primary nav.
- **Why not delete:** drift is a legit signal (and competitors surface it), but it's not the core loop. Some drift signals already feed discovery internally — keep the *engine*, hide the *dashboard*.

## 2. Delete (dead code)

| Item | State | Action |
|---|---|---|
| `recommendations/` | empty route dir (no page.tsx) | **delete** |
| `root-cause/` | empty route dir (no page.tsx) | **delete** |
| `components/coming-soon-poll.tsx` (239 LOC) | rendered nowhere (feature voting) | **delete** (or `/labs` if voting is wanted) |
| Duplicate auth aliases | `/login,/signup,/forgot-password,/reset-password,/verify-email` vs `/auth/*` | consolidate → file 14 |

## 3. Backend modules that pair with these (hide customer surface, keep engine)
- Provider Drift service, Ablation, Outcome-Attribution dashboard, Auto-PR (Tier-2), Weekly Digest, Judge-Calibration UI → keep code (feature-flagged / `/labs` / internal), remove from primary customer nav. (Tracked in completion plan Phase 5/6.)

## 4. My POV
- **Don't delete the analytics modules — hide them.** They represent real engineering effort and may matter post-PMF or for enterprise. But every one of them in primary nav makes Zroky look like "AI observability platform #7" instead of "the tool that discovers, proves, and guards." The nav is the product's thesis statement.
- **Do delete the genuinely dead stuff** (empty route dirs, unrendered components, duplicate auth) — that's just cleanliness, no downside.
- `/labs` is the honest home for "built, valuable, but not the wedge." It also signals to users "we're focused" while preserving optionality.

## 5. DoD
- [ ] `agents`, `drift` → `/labs`, flagged, out of primary nav + palette.
- [ ] `recommendations`, `root-cause`, `coming-soon-poll` deleted.
- [ ] Duplicate auth consolidated (file 14).
- [ ] Non-core backend surfaces hidden from customer nav (engines preserved).
