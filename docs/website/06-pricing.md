# 06 — Pricing Page

> File: `src/pages/PricingPage.tsx` + `src/data/pricing-plans.json` (exists). Route `/pricing`.

## Structure
1. **Header** — "Start free. Pay when you prevent regressions." Toggle: monthly/annual.
2. **Tiers** (4 cards) — aligned to the locked plan model:

| Tier | Tagline | For | Key includes |
|---|---|---|---|
| **Watch / Free** (OSS) | "Capture what happened." | Individual devs, OSS | OSS SDK, local capture, basic traces, PII masking, limited cloud ingest |
| **Pilot** | "Diagnose & discover, replay fixes." | Small AI teams | Failure Inbox, discovery, root-cause, one-click replay (stub + limited real/mocked), basic Goldens, Slack/GitHub alerts |
| **Pro** | "Prevent regressions before deploy." | Production AI teams | All replay modes, blocking CI gate, Golden sets, fidelity, outcome attribution, 90-day retention |
| **Enterprise** | "Govern reliability at scale." | Large orgs | Private replay worker, SSO/SAML, audit logs, custom retention, provider key vault, SLA |

3. **Feature comparison table** — grouped by pillar (Discover / Prove / Guard / Platform). Honest checkmarks; usage-based notes (cheap entry vs flat $249).
4. **Cost framing** — "Usage-based replay. You pay for proof, not seats." (contrast with per-seat competitors).
5. **FAQ** — data privacy, self-host, does capture slow my agent (no — fail-closed), what's free forever, how discovery differs from evals.
6. **CTA** — Start free / Talk to sales.

## My POV
- Lead with **free OSS** — it's the adoption engine. Make "free forever for capture+discovery" unmissable.
- **Usage-based, cheap entry** is a real wedge vs $249/mo flat + per-seat competitors — say it plainly. Good for global + cost-sensitive (India) markets.
- Don't over-gate discovery — it's the hook; gate the *money* (real replay, blocking CI, enterprise).
- Keep pricing honest and simple; 4 tiers max.
