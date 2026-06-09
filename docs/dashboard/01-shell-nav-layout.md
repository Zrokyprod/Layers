# 01 — Shell, Navigation & Layout

| | |
|---|---|
| **Files** | `src/components/dashboard-shell.tsx` (812 LOC), `src/app/(dashboard)/layout.tsx`, `src/lib/store.ts` (Zustand), `src/components/command-palette.tsx` (160 LOC), `src/lib/keyboard-shortcuts.ts` |
| **Pillar** | Cross-cutting frame for all Discover/Prove/Guard pages |
| **Current state** | Mature. App Router group `(dashboard)` wraps every page in `DashboardShell`. Nav config (`NAV_ITEMS` + `DASHBOARD_ROUTES`), top bar (project switch, date range, env, account menus), command palette, keyboard shortcuts, KPI/"saved-you" badge. |

---

## 1. Purpose
The shell is the persistent frame: sidebar nav, top bar, global filters (project, date range, env), command palette, account menu. It decides **what the product looks like it is** — so it must tell the Discover → Prove → Guard story and nothing else.

## 2. What STAYS (good, keep)
- The `(dashboard)/layout.tsx` route-group wrapper pattern.
- Top bar: project switcher, date-range presets (24h/7d/14d/30d), env selector, account menu.
- Command palette (`Ctrl+K`-style) + keyboard shortcuts — strong power-user UX, preserve.
- Zustand `store.ts` for UI state (sidebar, filters, real-time toggle, unread, last-visited).
- TanStack Query provider wrapping.
- Responsive sidebar collapse.

## 3. What CHANGES
**A. Nav config = 3-pillar (the key change).** Today `NAV_ITEMS` (visibleInNav) ≈ Failure Inbox, Issues, Replay Lab, Goldens, CI Gates, Cost, Settings, with Traces hidden. Target primary nav (lock to `00-OVERVIEW §3`):
```
Failure Inbox · Issues · Replay Lab · Goldens · CI Gates · Cost · Settings
```
- Group nav visually by pillar (optional dividers): **Discover** (Inbox, Issues) · **Prove** (Replay) · **Guard** (Goldens, CI Gates) · then Cost · Settings.
- `Traces` stays reachable but not primary (it's evidence, not a destination).
- Remove scope-drift items from `DASHBOARD_ROUTES`/breadcrumb that imply primary status for `agents`/`drift` (they move to `/labs`, file 13).

**B. Command palette** (`command-palette.tsx`) currently lists `agents`, `drift`, `recommendations` etc. Prune to match the target nav: keep core + settings deep-links; drop dead/`/labs` routes (or clearly label `/labs`).

**C. Top-bar "discovered" signal (small).** Optional: a compact count "N discovered this week" linking to `/home?focus=discovered`. Reinforces the hero without a new nav item.

## 4. What is CUT / moved
- Breadcrumb/route metadata for `recommendations`, `root-cause` (dead) — remove.
- `agents`, `drift` — keep route working but **out of primary nav** (move under `/labs`, file 13).
- Any nav entry pointing at duplicate auth aliases — n/a here (auth is pre-shell), see file 14.

## 5. Data / dependencies
- Reads: billing/plan (for plan label + gating), unread notifications, savings/"saved-you" badge (`getSavingsSummary`), SDK-connection status (SSE, from store).
- Entitlements: nav items carry `requiredEntitlement` (e.g. `pilot.replay_stub`, `pilot.goldens_basic`) — gate visibility/lock state.
- `DISCOVERY_ENABLED` (per project): controls whether the "discovered" focus/badge appears at all.

## 6. States to handle
- **Loading:** skeleton nav + top bar (don't block on billing/savings).
- **Plan-locked item:** show with lock icon + upgrade affordance, never hide silently for entitlements the plan can upgrade into.
- **No project / first run:** nav present, content area shows first-run (file 02).
- **Error (billing/savings fetch fail):** degrade gracefully — nav still works, badge hidden.

## 7. Discovery integration
- Add nav-level affordance only if `DISCOVERY_ENABLED`: the optional "Discovered" top-bar count (3C). No new nav destination in v1.
- Everything else discovery-related lives inside Inbox/Issues (files 02/03).

## 8. My POV
- The shell is **over-built for the current story** — it carries nav for 12 modules. The single highest-leverage change here is **pruning nav + command palette to the 3-pillar set**. That one change makes the product *feel* focused even before any backend change.
- Do **not** add a "Discover" nav item. Discover is the quality of the inbox; a separate nav item would fragment the story and imply discovery is a side-feature rather than the hero lens on issues.
- Keep the command palette — it's a genuine differentiator for power users and cheap to maintain.
- Grouping nav by pillar (with subtle dividers) is worth doing: it visually teaches the buyer "this tool discovers, proves, and guards" without copy.

## 9. Definition of done
- [ ] Primary nav = exactly the 3-pillar set (+ Cost, Settings).
- [ ] Command palette pruned to match; no dead/scope-drift destinations (or `/labs`-labeled).
- [ ] Scope-drift (`agents`,`drift`) removed from primary nav (routes still work via `/labs`).
- [ ] Optional discovered count gated by `DISCOVERY_ENABLED`.
- [ ] Loading/locked/error states intact; build passes.
