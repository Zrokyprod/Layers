# 14 — Cross-Cutting (auth, entitlements, states, realtime, design system, a11y)

| | |
|---|---|
| **Scope** | Concerns that span every module. Get these right once; every page benefits. |

## 1. Auth & session
**Files:** `src/app/api/auth/{set-session,clear-session}/`, `src/app/api/zroky/[...path]/route.ts`, `middleware.ts`, `src/lib/auth.ts`, `auth/redirect-alias.ts`.
- **Server proxy** (`/api/zroky/[...path]`) forwards to `ZROKY_API_BASE_URL`, injects bearer/project/api-key/provisioning headers, SSE pass-through. **Keep — solid.**
- **Cookie session** via `/api/auth/set-session` + `clear-session`; tokens also in localStorage; refresh-on-401 in `api.ts`. **Keep.**
- **FIX — `middleware.ts` is a no-op.** It matches all non-api/static routes but just `NextResponse.next()`. Dashboard pages have **no edge auth guard** — protection is client-side only. Decide: add real edge auth (redirect unauthenticated → `/auth/login`) OR document that protection is intentionally client+proxy side. My POV: add a minimal edge guard for `(dashboard)/*` — defense in depth.
- **FIX — duplicate auth routes:** top-level `/login,/signup,/forgot-password,/reset-password,/verify-email` AND `/auth/*`. Consolidate to `/auth/*` (canonical); make top-level ones redirect (the `redirect-alias.ts` already hints at this pattern). One surface.

## 2. Entitlements / plan-gating
**Files:** `components/feature-gate`, `hasPlanEntitlement`, nav `requiredEntitlement`.
- Every actionable surface checks entitlement → show locked/upgrade state, never a broken action.
- **`DISCOVERY_ENABLED`** (per project) is a separate gate from plan entitlements — discovery UI only renders when enabled AND surfaced findings exist.
- **Keep consistent:** locked features visible-with-lock (upgradeable) vs hidden (not in plan path).

## 3. The 4 states (every surface)
- **Loading** — skeletons, never blank/janky; don't block page on secondary fetches (inbox already does partial `settleLoad`).
- **Empty / first-run** — a *product moment*, not an afterthought. "Install SDK → Zroky learns normal → discovers failures." First-run copy unified across home/issues/calls.
- **Error** — retry affordance; partial-failure tolerance (one source down ≠ whole page down).
- **Populated** — the real UI.
> Audit every module against these 4. Inconsistent empty/first-run states are the most common polish gap.

## 4. Realtime
- Inbox 30s polling; SSE for SDK-connection status (store `sdkConnected`). CI gates auto-refresh on active runs.
- **Keep.** Don't add websockets complexity; polling + SSE is adequate at current scale.

## 5. Design system
- Existing CSS classes (`fi-*` inbox, `alert-cat-badge`, `kpi-*`, `ci-kpi-*`, badges), `globals.css` + `premium-overrides.css`.
- **Rule: reuse, do not restyle.** Discovery badges/blocks use existing badge/card classes. New "Discovered" accent = one new badge variant, not a new system.

## 6. Accessibility & power-user UX
- Command palette, keyboard shortcuts, ARIA roles already present (dialogs, listbox, status/alert regions). **Preserve.**
- New controls (feedback buttons, discovered filter) must be keyboard-reachable + labeled.

## 7. Data layer
- TanStack Query (`hooks.ts`, 81 hooks) for server state; Zustand (`store.ts`) for UI state; `api.ts` (166 fns) single client over the proxy. **Keep architecture.**
- **Discovery needs:** issue payload passthrough (`is_discovered`, `reason`, `corroboration`, `confidence`, `tier`) + the `/v1/issues` N+1 fix so the list read stays indexed.

## 8. My POV
- The **two real cross-cutting risks** are: (1) the no-op `middleware.ts` (no edge auth) and (2) duplicate auth surfaces. Both are cheap to fix and both are credibility/security issues a sharp reviewer (or customer security team) will flag. Fix in Phase 6.
- Everything else cross-cutting is in good shape — the data layer, proxy, entitlements, and realtime are mature. Don't rebuild; just enforce the 4-states audit and reuse the design system.
- **First-run is the highest-ROI cross-cutting polish** — it's the 10-minute-value moment that decides adoption. Make it consistent and discovery-aware everywhere.

## 9. DoD
- [ ] Edge auth guard for `(dashboard)/*` (or documented decision).
- [ ] Auth routes consolidated to `/auth/*`.
- [ ] 4-states audited across all modules; first-run unified + discovery-aware.
- [ ] Entitlement + `DISCOVERY_ENABLED` gating consistent.
- [ ] Design-system reuse (no restyle); a11y preserved.
- [ ] Issue payload passthrough + `/v1/issues` indexed read.
