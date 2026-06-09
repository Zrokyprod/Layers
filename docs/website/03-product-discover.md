# 03 — Product: Discover (pillar page)

> Route: `/product/discover`. The differentiator page. Goal: make "we find failures you didn't write tests for" concrete and believable.

## Sections
1. **Hero** — H1: "Discover the failures you never tested for." Sub: how baseline-learned discovery works without rubrics. Visual: discovered card.
2. **How it works (3 steps, diagram)**
   - Learn normal — per (agent, workflow): tool sequences, output shape, outcomes, cost/latency.
   - Score deviation — every new trace vs baseline.
   - Surface only corroborated — outcome / recurrence / replay / human. (Anomaly ≠ Failure.)
3. **What it catches** (card grid): missing critical tool, wrong tool sequence, schema/output drift, outcome mismatch, silent cost/latency drift, recurrence of a known-bad pattern.
4. **The evidence** — show a real reason string + corroboration chips. "No black box. Every finding explains itself."
5. **Precision promise** — "Precision over recall. We'd rather miss than cry wolf. Low-confidence stays in Watching, hidden from your inbox." (the trust/FP story)
6. **Cold-start honesty** — "Structural failures surface day one. Behavioral discovery unlocks as we learn your normal (~N traces)." (no overpromise)
7. **CTA** — Start free / see Prove.

## Imagery
- Discovered-finding card (real), baseline-learning state, Watching vs Surfaced tiers diagram.

## My POV
- This page must over-deliver on **specificity** — vague = me-too. Show the actual reason text the engine produces.
- The precision/FP section is what makes a skeptical engineer trust it. Don't bury it.
