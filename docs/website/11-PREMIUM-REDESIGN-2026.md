# Zroky Website — Premium Redesign 2026 (10/10 developer-grade)

Reference bar: Maxim, Braintrust, Linear, Vercel, Resend. Monochrome (white/grey/black),
semantic accent only (violet=discovered, green=verified, red=blocked). Dark canvas #0A0A0A.

## Why the current site feels "simple" (problems being fixed)
1. Full-length stretched dashboard screenshots → amateur. Premium sites CROP UI into a
   floating, tilted device-frame with glow + bottom fade. Show a corner, not the whole app.
2. Three separate long pillar sections (Discover/Prove/Guard) eat 3 full screens →
   replace with ONE interactive tabbed product showcase (one frame, tabs swap the UI).
3. Flat. No depth. Add: gradient mesh glow, film grain, glass layering, floating chips,
   bento grid, animated logo marquee, oversized stat numbers.
4. Weak hero. New hero = big framed product visual + overlapping live "DISCOVERED" chip
   + mesh glow + tight headline. Premium, not a card stack.

## Design system additions (already in index.css)
- `.device-frame` + `.device-shot` + `.device-fade` — cropped, depth-shadowed product frame
- `.mesh-glow` — monochrome ambient radial glow
- `.grain` — film-grain texture overlay (premiumness)
- `.bento` — asymmetric grid cell with hover lift
- `.marquee-track` + `.marquee-mask` — infinite logo scroll

## Home page section order (tight rhythm, ~9 sections)
1. HERO — left: eyebrow + shimmer headline + subcopy + 2 CTAs + trust line.
   right: floating `device-frame` (cropped replay screenshot, slight tilt) with an
   overlapping glass "DISCOVERED" chip card + mesh glow behind. Grain on section.
2. LOGO MARQUEE — infinite scroll: OpenAI, Anthropic, Google, LangChain, LangGraph,
   CrewAI, OpenTelemetry, Vercel AI SDK. Masked edges.
3. STATS BAND — 4 oversized mono numbers (e.g. <10 min first finding, 90%+ precision
   target, 3 verdicts, 0 false blocks). Hairline dividers between.
4. PROBLEM — 3 tight cards (silent failures / can't test the unknown / ships twice),
   compact, icons in bordered tiles.
5. PRODUCT SHOWCASE (the centerpiece) — ONE device-frame + 3 tabs (Discover/Prove/Guard).
   Click a tab → headline+bullets on left swap, screenshot/mock on right swaps with a
   crossfade. Replaces the 3 long pillars. This is the "wow".
6. BENTO CAPABILITIES — asymmetric grid (2-3-2 layout): behavioral baseline, fidelity
   replay, goldens, CI verdict, multilingual, evidence trail. Some cells have cropped UI
   fragments, some are pure text+icon.
7. COMPARISON — eval-first vs Zroky table (keep, restyle tighter).
8. TRUST STRIP — 3 honesty chips (stub≠verified, review never false-block, fidelity shown).
9. QUICKSTART + FINAL CTA — code block with copy + big closing CTA card with mesh glow.

## Motion
- framer-motion reveal (already), tab crossfade (AnimatePresence), marquee CSS,
  subtle parallax tilt on hero frame, count-up optional on stats. Respect reduced-motion.

## Screenshot strategy
- Only 2 real shots exist (product-replay-detail.png, product-ci-gate.png).
- Crop them inside device-frame (object-position top, device-fade bottom). Never stretch.
- For Discover tab (no real shot) → use the existing hand-built DISCOVERED mock card
  enlarged inside the frame. Honest: it's a mock, looks like product.

## Build order
1. index.css utilities (DONE)
2. Rebuild HomePage.tsx with new sections + ProductShowcase tabs + bento + marquee + stats
3. Tighten Nav (already glass) — add scroll-shrink
4. Rebuild verify with `npm run build`
