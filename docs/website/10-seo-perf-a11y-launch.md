# 10 — SEO, Performance, Accessibility, Launch

> The non-negotiable quality bar that makes the site feel "world-class" beyond visuals.

## A. SEO
- **Per-page metadata:** unique title + meta description (react-helmet or Vite SSG/prerender). Title pattern: `{Page} — Zroky | AI Agent Failure Discovery & Regression Guard`.
- **OG/Twitter cards:** custom OG image per key page (Home, Product×3, Pricing, OSS). Dark, product-led, headline baked in.
- **Structured data:** Organization, SoftwareApplication, FAQPage (pricing/faq), BreadcrumbList.
- **Sitemap.xml + robots.txt.** Canonical URLs.
- **Content SEO (the moat):** target the unique angle — "unknown failure discovery", "agent eval-to-production gap", "what your eval suite can't see". Blog/docs feed this. (Vite SPA → add prerender/SSG for crawlability; consider migrating marketing to Next or vite-ssg.)

## B. Performance (budget)
- **LCP < 1.2s, CLS ~0, INP < 200ms, TBT minimal.** Lighthouse ≥ 95 all categories on Home.
- Hero visual is React/SVG (not a heavy gif/video); lazy-load below-fold images; `srcset` + AVIF/WebP for screenshots.
- Fonts: preload, `font-display: swap`, subset.
- Code-split routes; framer-motion only where needed; no unused JS.
- Self-host fonts + images (no third-party render-blocking).

## C. Accessibility
- WCAG AA min. Visible focus (accent ring), full keyboard nav, semantic landmarks, skip-link.
- Alt text describes the *insight* ("CI gate blocking a regressing PR"), not "screenshot".
- `prefers-reduced-motion` disables transforms.
- Color not the only signal (badges carry text/icon too).
- Test with keyboard + screen reader before launch.

## D. Analytics / instrumentation
- Privacy-friendly analytics (Plausible/PostHog). Track: hero CTA, OSS star click, quickstart copy, pricing→signup, docs entry. (Dogfood: capture the marketing site's own funnel.)

## E. Launch checklist
- [ ] All pages: metadata + OG + canonical.
- [ ] Lighthouse ≥95 (Home, Product, Pricing).
- [ ] Mobile-perfect at 360px; CTA reachable.
- [ ] Wording discipline pass (no "zero-eval" public).
- [ ] Every product claim ↔ real artifact/screenshot.
- [ ] 404/error/legal/security.txt present.
- [ ] Reduced-motion + keyboard + contrast verified.
- [ ] Sitemap/robots submitted; OG previews validated (X, LinkedIn, Slack).

## My POV
- A Vite SPA is fine for the app but **marketing needs crawlable HTML** — add prerendering/SSG (vite-ssg) or move the marketing site to Next. SEO is half the distribution; don't ship a JS-only marketing site.
- Perf is part of the "world-class" feeling — a 3s hero kills the Linear/Vercel impression instantly. Treat the budget as a hard gate.
- **Launch gate:** like the rest, ship the world-class site only once the product's Discover precision is proven. A beautiful site over a noisy product converts then churns — worse than waiting.
