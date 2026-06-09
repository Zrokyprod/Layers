# 12 — Account (identity & security)

| | |
|---|---|
| **Files** | `account/page.tsx` (2 LOC — stub), `components/account-page.tsx` (344 LOC — real impl) |
| **Pillar** | Cross-cutting (identity/security/session) |
| **State** | The route page is a 2-LOC stub that renders the real `account-page.tsx` component (344 LOC: profile, password, sessions, account deletion). |

## 1. Purpose
Personal account: identity, password change, active sessions, account deletion. Standard but necessary for a real product (security/compliance).

## 2. STAYS
- `account-page.tsx` (the real implementation) — profile, password, sessions, deletion. Solid.

## 3. CHANGES / FIX
- **Resolve the stub confusion:** `account/page.tsx` (2 LOC) just mounts `account-page.tsx`. That's fine as a thin route wrapper — but verify it's intentional, not an accident. Document the pattern so it's not flagged as "dead."
- **Profile overlap:** `settings/profile` (4 LOC stub) overlaps with account identity. Pick ONE home for identity (recommend: `/account`), redirect the other.

## 4. CUT
- `settings/profile` stub → redirect to `/account` (file 11).

## 5. Data / API
- `getMe`, change-password, sessions, security status, account deletion, `clearAuthSession`.

## 6. States
- Loading, error, populated. Destructive (delete account) needs confirmation.

## 7. Discovery integration
- None. Pure account management.

## 8. My POV
- This is fine — the "2 LOC" is a thin route wrapper around a real 344-LOC component, not actually a stub. Just **document it** so future audits don't flag it.
- The only real action is **de-duplicating identity** between `/account` and `settings/profile`. One canonical home, redirect the other.
- Secondary nav placement (not primary) — correct.

## 9. DoD
- [ ] Identity consolidated to `/account`; `settings/profile` redirects.
- [ ] Route-wrapper pattern documented (not flagged as dead).
- [ ] Destructive actions confirmed; secondary placement.
