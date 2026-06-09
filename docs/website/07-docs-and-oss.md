# 07 — Docs Hub + OSS (`zroky-watch`) page

> Files: `src/pages/DocsPage.tsx`, `src/pages/docs/*`, `src/pages/ChangelogPage.tsx`. The OSS page is the distribution engine.

## A. Docs hub (`/docs`)
- **Layout:** left sidebar nav, center prose (720px), right "on this page" TOC. Search.
- **Sections:** Quickstart (5-min) · SDK (Python/JS) · Concepts (Discover/Prove/Guard, Anomaly≠Failure, fidelity) · Gateway · CI Action setup · Self-host · API reference (from frozen OpenAPI) · Security.
- **Quickstart is sacred** — the 5-minute path is the adoption moment. 3-line snippet, copy buttons, "what you'll see next."
- Code blocks: tabs (Python / JS / curl), copy, syntax highlight.

## B. OSS page (`/open-source` or prominent `/zroky-watch`)
> This is the bottom-up distribution surface (Langfuse-style). It must convert a curious dev into a GitHub star + install.
- **Hero:** "zroky-watch — open-source flight recorder + failure discovery for AI agents." ★ Star · Install.
- **Why OSS:** MIT, self-hostable, no usage limits on capture+discovery, your data stays yours.
- **What it does (free):** capture, structural detection, behavioral discovery (the differentiator, free).
- **Install:** `pip install zroky` / `npm i @zroky/sdk` + 3 lines.
- **Architecture diagram:** SDK → ingest → discovery (self-host or cloud).
- **Upgrade path (soft):** "Want to prove fixes and block regressions in CI? → Zroky Cloud (Pilot/Pro)."
- **GitHub embed:** live star count, contributors, recent commits.

## C. Changelog (`/changelog`)
- Clean reverse-chron, tagged (Discover/Prove/Guard/Platform). Builds "shipping velocity" trust. RSS.

## My POV
- The OSS page is **distribution, not marketing** — its only job is star + install. Keep it concrete, dev-to-dev, install-above-the-fold.
- Free **discovery** in OSS is the bold move that differentiates from eval tools (which gate everything). It's the funnel top; the money is Prove+Guard.
- Quickstart quality directly = activation rate. Over-invest in it.
