# 09 — Global Nav, Footer, Legal, 404

> Files: `src/components/Nav.tsx`, `src/components/Footer.tsx`, `src/App.tsx` (routing).

## A. Top Nav (`Nav.tsx`)
- **Sticky, glass/blur, compact.** Logo left.
- **Product ▾** mega-menu: Discover · Prove · Guard · How it works (with mini-icons + one-line each).
- **Solutions ▾**: AI Engineers · Eng Leaders · Platform/SRE.
- **Pricing · Docs · Changelog** (flat links).
- Right: **★ zroky-watch** star pill · **Sign in** (ghost) · **Start free** (accent).
- Mobile: hamburger → full-screen sheet, same items, CTA pinned bottom.
- Active route indicator; scroll-shrink (taller at top, compact on scroll).

## B. Footer (`Footer.tsx`)
4–5 columns + bottom bar:
```
Product            Developers         Company            Resources
  Discover           Docs               About              Changelog
  Prove              Quickstart         Careers            Blog
  Guard              OSS (zroky-watch)  Contact            Security/Trust
  Pricing            API reference      Brand/Press        Status
  Dashboard ↗        GitHub ↗           Privacy            System health

Bottom bar:
  © Zroky · Privacy · Terms · Security · security.txt
  [GitHub] [X/Twitter] [LinkedIn]   ·  Made for production AI agents
```
- Newsletter / "get launch updates" inline (optional).
- Theme toggle (if light theme ships).

## C. Legal pages
- `/privacy`, `/terms`, `/security` (links to Trust page), `/subprocessors`, `/dpa` (enterprise). Clean prose template, last-updated date.

## D. 404 / error
- On-brand 404: "This page didn't pass the gate." (playful nod to CI) + search + back-home + popular links.
- Error boundary: graceful, "something broke — we'd want to know" + status link.

## My POV
- Keep nav **shallow + honest** — two dropdowns max (Product, Solutions). Don't bury the OSS star pill; it's a credibility + distribution signal.
- Footer is where SEO + trust links live — complete it properly (security.txt, status, legal). A thin footer reads "early/unserious" to enterprise.
- The 404 nod to "the gate" is a small brand-personality moment — cheap, memorable.
