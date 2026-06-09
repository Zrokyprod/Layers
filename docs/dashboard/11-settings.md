# 11 — Settings (hub + sub-pages)

| | |
|---|---|
| **Files** | `settings/page.tsx` (694), `settings/layout.tsx`, `billing/` (386), `keys/` (489), `team/` (423), `providers/` (527), `integrations/` (151) + `slack/` (178) + `teams/` (203), `evaluation/` (412), `profile/` (4 — stub) |
| **Pillar** | Cross-cutting config (enables capture, replay keys, billing, team) |
| **State** | Mature hub with tabbed sub-pages. Profile is a 4-LOC stub. |

## 1. Purpose
Settings is the control plane: API keys (capture), provider keys (replay), billing/plan, team, integrations (Slack/Teams/GitHub), evaluation (judge/calibration). All necessary plumbing for the loop to function.

## 2. STAYS
- **keys** — API key create/revoke (capture onboarding; critical for first-run).
- **providers** — provider key vault (required for real-LLM replay / Prove).
- **billing** — plan, Stripe portal, sla_tier (paid loop).
- **team** — invites/members.
- **integrations** — Slack/Teams/GitHub connect (alerts + CI Action + future Slack investigation).
- **evaluation** — judge/calibration controls (this is where judge-calibration lives, correctly in settings, NOT a primary nav module).

## 3. CHANGES / ADD
- **Discovery settings (small):** a per-project toggle surface for `DISCOVERY_ENABLED` + tunables (warmup, recurrence, surface-confidence) under settings (advanced). Default off until precision proven. This is the only discovery-specific settings add.
- **First-run priority:** keys page is part of the 10-minute path — ensure it's frictionless from onboarding.

## 4. CUT / FIX
- **`settings/profile` (4 LOC stub)** → either implement minimally (identity/password live in `/account`) or redirect/remove. Don't ship a dead stub.
- Ensure `evaluation` stays in settings (it's correctly demoted from primary nav — judge-calibration is supporting, not a hero module).

## 5. Data / API
- Keys, provider verifications, billing me/checkout/portal, team/invites, integration install/status/test, evaluation settings. All wired (`api.ts`).

## 6. States
- Each sub-page: loading, empty, error, populated. Plan-gating on billing-dependent features.

## 7. Discovery integration
- Discovery enable/tune toggle (advanced). Provider keys (Prove) and API keys (capture) are prerequisites for the discovery→prove loop.

## 8. My POV
- Settings is appropriately comprehensive — keep it. The discipline point: **evaluation/judge-calibration belongs HERE, not in primary nav** (it's a control, not a destination). This is already the case — preserve it.
- Fix the profile stub (small but it's a visible dead-end).
- The discovery toggle should be **advanced/hidden** — most users never touch it; it flips on per-project after precision is proven.

## 9. DoD
- [ ] Discovery enable/tune under settings (advanced, default off).
- [ ] Profile stub resolved.
- [ ] Evaluation/judge stays in settings; keys/providers frictionless for first-run.
