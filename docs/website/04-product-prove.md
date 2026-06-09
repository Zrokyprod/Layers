# 04 — Product: Prove (Replay Lab pillar page)

> Route: `/product/prove`. Goal: "prove your fix works against the real failed scenario — honestly."

## Sections
1. **Hero** — H1: "Prove the fix before you ship it." Sub: replay the exact failed case. Visual: `product-replay-detail.png`.
2. **Before / after** — original failure vs candidate output, side by side. Tool-behavior diff, cost delta, latency delta.
3. **Replay modes** — explained honestly:
   - Stub (sanity only — never "verified")
   - Real-LLM (re-executes against candidate prompt/model)
   - Mocked-tool (frozen tool context)
   - Live-sandbox / Shadow (premium)
4. **Fidelity score (the differentiator)** — "How faithfully did we reproduce it? 92% — tool context matched; ⚠️ external state changed. Or: 'cannot replay — not marked verified.'" Most tools just print ✓; we show the truth.
5. **Verdict vocabulary** — verified_fix / fix_failed / inconclusive / tool_snapshot_missing / not_verified. Honest, explicit.
6. **From discovered → proved** — one click from a finding to a replay.
7. **CTA** — to Guard.

## Imagery
- `product-replay-detail.png` (real), fidelity-score panel, before/after diff, mode selector.

## My POV
- Fidelity score is the trust moat here — lead with it. It's the answer to "how do I know your 'verified' means anything?"
- Be explicit that stub ≠ verified; that honesty *sells* to senior engineers.
