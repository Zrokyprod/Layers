# 05 — Product: Guard (CI Gates + Goldens pillar page)

> Route: `/product/guard`. Goal: "stop the same failure shipping twice — without false-blocking."

## Sections
1. **Hero** — H1: "The same failure should never ship twice." Sub: verified fix → Golden → CI gate. Visual: `product-ci-gate.png` (real PR comment).
2. **Goldens** — promote a verified fix into a production-derived regression test. "A failed output is never auto-treated as expected behavior."
3. **CI Gate** — runs Goldens on every PR. PR comment preview.
4. **Three verdicts (flake-proof)** — Pass / **Block (only at high confidence)** / **Review suggested (borderline, never blocks)**. "One wrong block and you'd turn us off — so we don't."
5. **Honesty: not_verified ≠ pass** — "If no real comparison happened, we say not_verified. We never fake a green check."
6. **GitHub Action** — drop-in, lists changed files, posts the comment. Setup snippet.
7. **CTA** — Start free / book demo.

## Imagery
- `product-ci-gate.png` (real), PR-comment mock, 3-verdict diagram, GitHub Action yaml snippet.

## My POV
- The **3rd verdict (review) + "we only block when sure"** is the single most important trust message for a blocking gate — it's what keeps the gate from being disabled. Make it loud.
- "not_verified ≠ pass" is a genuine differentiator vs tools that print green too easily.
