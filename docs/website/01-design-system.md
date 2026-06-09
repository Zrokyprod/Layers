# 01 — Website Design System

> Reference tier: Linear / Vercel / Stripe / Resend. Dark-first, calm, one accent, product-led. Built on the existing Tailwind setup.

## 1. Color (dark-first)
```
Base / surfaces (dark)
  --bg            #0A0B0D   (near-black, slight warm)
  --surface       #121419
  --surface-2     #1A1D24
  --border        #262A33
  --text          #E7E9EE
  --text-muted    #9AA1AD

Accent (one, confident — electric indigo/violet)
  --accent        #6D5EF8
  --accent-hover  #8174FF
  --accent-soft   rgba(109,94,248,0.12)

Semantic (map to product meaning — reused on site + app)
  --discovered    #8B5CF6   (violet) — "Zroky found this"
  --verified      #22C55E   (green)  — proven fix
  --blocked       #EF4444   (red)    — CI blocked / failure
  --review        #F59E0B   (amber)  — review suggested / watching
  --neutral       #64748B
```
Light theme: optional v2. Launch dark-first (matches dev-tool norm + product screenshots).

## 2. Typography
- **Display/Headings:** a modern grotesk — `Geist` / `Inter Tight` / `Satoshi`. Tight tracking on big sizes.
- **Body:** `Inter`. **Mono (code/metrics):** `Geist Mono` / `JetBrains Mono`.
- Scale (clamp, fluid):
```
display  clamp(2.75rem, 6vw, 4.5rem)  / 1.05 / -0.02em
h1       clamp(2rem, 4vw, 3rem)
h2       clamp(1.5rem, 3vw, 2.25rem)
h3       1.25rem
body     1.0625rem / 1.6
small    0.875rem
mono     0.9rem
```

## 3. Spacing / layout
- 8pt grid. Max content width 1200px; prose 720px.
- Section vertical rhythm: 96–160px desktop, 64px mobile.
- Generous whitespace > density. One idea per section.

## 4. Radius / shadow / glass
```
--radius-sm 8px  --radius 12px  --radius-lg 20px  --radius-pill 999px
--shadow-card  0 1px 0 rgba(255,255,255,0.04) inset, 0 20px 40px -24px rgba(0,0,0,0.6)
--glass        backdrop-blur(12px) + surface @ 70% (nav, cards on hero)
```
Subtle accent glow behind hero visual only (radial, low opacity). No neon everywhere.

## 5. Components
- **Buttons:** primary (accent, solid), secondary (border + glass), ghost. Pill option for "★ star" + "Start free". 44px min touch target.
- **Cards:** surface-2 + border + subtle inset highlight; hover lift 2px + border-accent.
- **Badges (semantic):** Discovered (violet), Verified (green), Blocked (red), Review (amber) — same vocabulary as the dashboard (consistency = trust).
- **Code block:** mono, surface, copy button, accent line-highlight. Used for the 3-line SDK snippet.
- **Stat/metric:** big mono number + muted label.
- **Comparison table:** "eval-first tools" vs "Zroky discovery" (honest, no names).

## 6. Motion (framer-motion, already installed)
- Scroll-reveal: fade + 12px rise, stagger children 40ms. Once only.
- Hero loop: the Discover→Prove→Guard cards animate in sequence (3s), loop subtly.
- Hover: card lift, button sheen. 150–200ms ease-out.
- **Respect `prefers-reduced-motion`** — disable transforms, keep opacity.

## 7. Imagery rules
- Real product screenshots in a minimal browser/device frame, soft shadow, ≤4° tilt only on hero.
- No stock photos, no "AI brain/robot" art, no generic gradients-as-content.
- Diagrams = clean SVG line art, animated on scroll.

## 8. Accessibility
- Contrast AA min (AAA for body where possible). Focus rings visible (accent). Keyboard nav everywhere. Semantic landmarks. Alt text on every product image describing the *insight* ("CI gate blocking a regressing PR").

## 9. DoD
- [ ] Tokens in Tailwind config + CSS vars; one accent; semantic colors match app.
- [ ] Fonts loaded with `font-display: swap`, preloaded.
- [ ] Motion respects reduced-motion.
- [ ] Components: button/card/badge/code/stat/comparison built + documented.
