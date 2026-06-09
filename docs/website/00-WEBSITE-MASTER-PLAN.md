# Zroky Marketing Website — World-Class Plan (Master)

| | |
|---|---|
| **Status** | Complete website plan — content, sections, cards, images, nav, footer, design system, motion, SEO. |
| **Stack (existing)** | Vite + React + TypeScript + Tailwind + framer-motion + react-router + lucide-react. Pages already scaffolded: Home, Features, Pricing, Docs, Changelog, Auth. Assets: `product-ci-gate.png`, `product-replay-detail.png`, logo. |
| **Positioning (locked)** | Category: **AI Agent Failure Discovery & Regression Guard**. Pillars: **Discover · Prove · Guard**. Headline: *"Find the AI agent failures you didn't know to test."* |
| **Wording discipline** | Never "zero-eval / no evals / magic" in public. Use "find failures before you write evals", "production-discovered evals", "from unknown failure to CI protection". |

---

## 0. Design north star (what "world-class" means here)

Reference tier: **Linear, Vercel, Stripe, Resend, Braintrust**. The site must feel:
- **Calm + confident**, not loud. Dark-first, generous whitespace, one accent.
- **Product-led** — real product screenshots/loops, not stock illustration.
- **Honest** — the trust angle (fidelity, "not_verified ≠ pass") is a *feature we show off*, not hide.
- **Fast** — sub-1s LCP, no layout shift, motion that respects `prefers-reduced-motion`.

> One sentence the whole site must earn: *"This tool finds the production failures my tests miss, proves the fix, and stops the repeat."*

---

## 1. Design system (file 01)
Colors, type scale, spacing, radius, shadows, components (buttons, cards, badges, code block), motion tokens, dark/light. Single accent + semantic colors (discovered/verified/blocked). Detailed in `01-design-system.md`.

---

## 2. Sitemap & navigation

```
TOP NAV (sticky, blurred, compact)
  Logo
  Product ▾   (mega-menu: Discover · Prove · Guard · How it works)
  Solutions ▾ (By role: Eng leaders · AI engineers · Platform/SRE)
  Pricing
  Docs
  Changelog
  ─────────────
  [Sign in]   [Start free →]  (GitHub-star pill: ★ zroky-watch)

FOOTER (see file 09)
```

Pages (each its own plan file):
```
docs/website/
  00-WEBSITE-MASTER-PLAN.md   ← this file
  01-design-system.md
  02-home.md                  ← the hero page (most important)
  03-product-discover.md
  04-product-prove.md
  05-product-guard.md
  06-pricing.md
  07-docs-and-oss.md          ← docs hub + zroky-watch OSS page
  08-solutions-and-trust.md   ← role pages, security/trust, customers
  09-footer-nav-legal.md      ← global nav, footer, legal, 404
  10-seo-perf-a11y-launch.md  ← metadata, OG, sitemap, perf budget, a11y, launch
```

---

## 3. Home page — section order (detail in 02)
1. **Announcement bar** — "zroky-watch is open source ★" / launch note.
2. **Hero** — headline + subcopy + dual CTA + live "discovered failure" visual.
3. **Logo/credibility strip** — "works with OpenAI, Anthropic, LangChain, LangGraph, any framework" (frameworks, not fake logos until real ones exist).
4. **The problem** — "Your agent returns 200 OK and still fails. You find out when the customer complains." (3 pain cards).
5. **The loop** — Discover → Prove → Guard animated 3-step (the spine).
6. **Pillar 1: Discover** — unknown-failure card + reason example (the differentiator).
7. **Pillar 2: Prove** — replay before/after + fidelity score (real screenshot).
8. **Pillar 3: Guard** — CI gate PR comment (real screenshot, `product-ci-gate.png`).
9. **Why different** — comparison vs "eval-first" tools (honest, no competitor names).
10. **Trust/honesty** — "We never call stub a verified fix. We show fidelity." (trust as a feature).
11. **Quickstart** — 3-line SDK snippet + "first finding in minutes".
12. **Social proof / metrics** — when real; until then, OSS stars + "built for production agents".
13. **Final CTA** — "Stop shipping the same failure twice."
14. **Footer.**

---

## 4. Imagery / visual asset plan (detail per page)
- **Hero visual:** an animated "Discovered failure" card (reason + corroboration chips) → arrow → Replay before/after → arrow → CI gate blocked. This single loop *is* the product.
- **Real product shots:** `product-replay-detail.png`, `product-ci-gate.png` (exist). Add: discovered-finding card, failure inbox, fidelity score panel (capture from the real dashboard once discovery UI ships).
- **Style:** dark UI screenshots in a subtle device/browser frame, soft shadow, slight tilt only on hero. No stock photos. No generic AI brain art.
- **Diagrams:** the Discover→Prove→Guard loop as a clean line diagram (SVG, animated on scroll).
- **Icons:** lucide (already in stack) — consistent stroke weight.

---

## 5. Content pillars / voice
- **Voice:** senior engineer to senior engineer. Direct, specific, no hype. Show, don't tell.
- **Proof over adjectives:** every claim pairs with a concrete artifact (a reason string, a diff, a PR comment).
- **Honesty as brand:** the trust section is a differentiator — most competitors won't say "we won't call this verified."

---

## 6. Build order (website)
1. Design system tokens (file 01) — foundation.
2. Home (file 02) — the one page that must be world-class.
3. Product pillar pages (03/04/05).
4. Pricing (06).
5. Docs hub + OSS page (07).
6. Solutions/trust (08).
7. Footer/legal/404 (09).
8. SEO/perf/a11y/launch pass (10).

> Like the dashboard plan: this defines the target. Actual build happens after the product's Discover precision is proven (a world-class site selling a noisy product is worse than no site).

---

## 7. Definition of done (website)
- [ ] Lighthouse ≥95 perf/a11y/SEO/best-practices on Home.
- [ ] LCP <1.2s, CLS ~0, motion respects reduced-motion.
- [ ] Every page: clear single CTA, consistent nav/footer, OG image, metadata.
- [ ] Copy follows wording discipline (no "zero-eval" public).
- [ ] Mobile-perfect (hero → CTA legible/usable on 360px).
- [ ] All product claims backed by a real artifact/screenshot.
