# Zroky Dashboard — Master Plan (Overview & Index)

| | |
|---|---|
| **Status** | Dashboard end-to-end plan — master index. Module files follow one-by-one. |
| **Scope** | The entire authenticated dashboard (`src/app/(dashboard)/*`) + cross-cutting shell. Public/marketing pages noted but not the focus. |
| **Framing** | The product is **Discover → Prove → Guard**. Every dashboard surface must serve one of these, support them, or be moved out. |
| **Grounding** | Based on the actual code: 27 pages, 42 components, `api.ts` 166 fns, `hooks.ts` 81 hooks, App Router + TanStack Query + Zustand, same-origin `/api/zroky` proxy. |

---

## 0. How this plan is organized

This is the **index**. Each module gets its own detailed file (purpose, what stays/changes/goes, data, states, discovery integration, my POV). Files:

```
docs/dashboard/
  00-OVERVIEW.md            ← you are here (master plan + nav + classification)
  01-shell-nav-layout.md    ← DashboardShell, nav, layout, global state
  02-home-failure-inbox.md  ← Discover landing
  03-issues.md              ← Discover surface (list + detail)
  04-replay-lab.md          ← Prove (list + detail)
  05-goldens.md             ← Guard (list + detail)
  06-ci-gates.md            ← Guard (list + detail)
  07-calls.md               ← Capture evidence (list + detail)
  08-trace.md               ← Evidence (list + detail)
  09-cost.md                ← Supporting (cost of failure)
  10-alerts.md              ← Supporting (triage routing)
  11-settings.md            ← Settings hub (billing/keys/team/providers/integrations/evaluation/profile)
  12-account.md             ← Account/security
  13-labs-and-cuts.md       ← agents, drift, recommendations, root-cause → /labs or delete
  14-cross-cutting.md       ← auth, entitlements/plan-gates, empty/loading/error, realtime, design system, a11y
```

> Build/priority order is NOT the file order. Priority lives in `ZROKY_DISCOVERY_COMPLETION_PLAN.md` (precision first). This set defines the *target clean dashboard*, module by module.

---

## 1. Dashboard principles (apply to every module)

1. **3-pillar clarity.** Primary nav and home tell one story: Discover → Prove → Guard. No module competes with that story.
2. **Discovered ≠ Detected is visible.** The differentiator must show in the UI (badge + reason), or the wedge is invisible.
3. **Trust-honest UI.** Never show "verified" unless verified; never surface low-confidence (`watching`) findings in primary lists. Mirror the backend's honesty.
4. **Reuse, don't restyle.** Existing `fi-*` inbox classes, issue cards, badges, KPI strip stay. Discovery plugs into them.
5. **Every list is an indexed read.** No N+1, no client-side over-fetch+filter (fix `/v1/issues`). Pages must scale.
6. **Plan-gated.** Entitlements decide what's visible/actionable; show upgrade states, never broken actions.
7. **Every surface handles 4 states:** loading, empty (first-run), error, populated. First-run is a product moment, not an afterthought.

---

## 2. Full module inventory + classification

### 🟢 CORE — the product (keep, harden, wire discovery)
| Page | LOC | Pillar | Plan file |
|---|---|---|---|
| `home` (Failure Inbox) | 1234 | Discover (landing) | 02 |
| `issues` + `[id]` | 506 + 1026 | Discover (surface) | 03 |
| `replay` + `[id]` | 769 + 1108 | Prove | 04 |
| `goldens` + `[id]` | 389 + 627 | Guard | 05 |
| `ci-gates` + `[runId]` | 463 + 404 | Guard | 06 |
| `calls` + `[id]` | 552 + 932 | Capture evidence | 07 |
| `trace` + `[id]` | 503 + 508 | Evidence | 08 |

### 🟡 SUPPORTING — keep, but secondary (not the hero)
| Page | LOC | Role | Plan file |
|---|---|---|---|
| `cost` | 970 | Cost of failure / spend | 09 |
| `alerts` | 440 | Triage routing | 10 |
| `settings/*` | ~3000 | Keys/billing/team/providers/integrations/evaluation | 11 |
| `account` | 2 (stub) | Identity/security | 12 |

### 🔴 SCOPE-DRIFT — move to `/labs` or feature-flag (out of primary nav)
| Page | LOC | Why | Plan file |
|---|---|---|---|
| `agents` (Release Safety Console) | 1029 | Advanced analytics; MVP_LOCK said hide | 13 |
| `drift` (Provider/Judge/Outcome) | 377 | Scope drift; not core loop | 13 |

### ⚫ DEAD — delete
| Page | State | Action | Plan file |
|---|---|---|---|
| `recommendations` | empty dir | delete | 13 |
| `root-cause` | empty dir | delete | 13 |
| `settings/profile` | 4 LOC stub | resolve/redirect | 11/12 |
| `account` | 2 LOC stub | resolve/redirect | 12 |
| duplicate auth routes (`/login` vs `/auth/login`, etc.) | parallel | consolidate | 14 |
| `coming-soon-poll.tsx` | unrendered | remove | 13 |

---

## 3. Target primary navigation (locked)

```
PRIMARY NAV (DashboardShell visibleInNav:true)
  ● Failure Inbox   /home      ← Discover (default landing)
  ● Issues          /issues    ← Discover
  ● Replay Lab      /replay     ← Prove
  ● Goldens         /goldens    ← Guard
  ● CI Gates        /ci-gates   ← Guard
  ● Cost            /cost       ← Supporting (keep visible)
  ● Settings        /settings

SECONDARY / REACHABLE (not primary nav)
  Calls /calls · Traces /trace · Alerts /alerts · Account /account

/labs (feature-flagged, out of primary nav)
  Agents (Release Safety Console) · Drift (Provider/Judge/Outcome)

DELETE
  recommendations · root-cause · coming-soon-poll · duplicate auth aliases
```

> Discover is the **quality of the inbox**, not a separate nav item (v1). Optional later: a "Discovered" saved-filter shortcut.

---

## 4. Cross-cutting (detailed in file 14)
- **Auth/session:** `/api/auth/*` cookie set/clear, `/api/zroky` proxy, middleware (currently no-op), refresh-on-401.
- **State:** Zustand (`store.ts`) for UI; TanStack Query for server state (`hooks.ts`).
- **Entitlements:** plan-gating via `feature-gate` / `hasPlanEntitlement`; `DISCOVERY_ENABLED` per project.
- **Design system:** existing CSS classes (`fi-*`, badges, `kpi-strip`); reuse, no restyle.
- **States:** loading / empty(first-run) / error / populated for every surface.
- **Realtime:** 30s polling on inbox; SSE for SDK connection status.
- **A11y:** keyboard nav, command palette, ARIA already present — preserve.

---

## 5. Discovery integration (summary — detail in 02/03/04)
- Engine writes `BEHAVIORAL_DRIFT` anomalies → already power `/v1/issues` (Option A). **No new page.**
- 02 home: new `discovered` queue focus + KPI + onboarding copy.
- 03 issues: Discovered/Detected badge + source filter + reason/corroboration + feedback + `watching` secondary view.
- 04 replay: discovered→replay handoff + fidelity score.
- All behind `DISCOVERY_ENABLED`.

---

## 6. Definition of done (dashboard)
- [ ] Primary nav = 3-pillar (§3).
- [ ] Discovery visible + differentiated in inbox/issues.
- [ ] Scope-drift moved to `/labs`; dead routes deleted; auth consolidated.
- [ ] Every surface: 4 states handled; lists indexed; plan-gated.
- [ ] Build passes; tests green.

---

## 7. Next
Proceed module-by-module: **01 (shell/nav/layout) → 02 (home) → 03 (issues) → …**. Each file is self-contained with my POV on what to keep, change, add, and cut.
