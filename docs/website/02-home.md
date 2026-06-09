# 02 — Home Page (the hero page — most important)

> File: `src/pages/HomePage.tsx`. This is the page that must be world-class. Section-by-section: copy, layout, cards, imagery, motion.

---

## Section 1 — Announcement bar (`AnnouncementBar.tsx`, exists)
- Slim, dismissible. Copy: **"zroky-watch is now open source — capture & discover agent failures free. ★ Star on GitHub →"**
- Left dot accent; right close. Links to OSS repo.

## Section 2 — HERO
**Layout:** left copy (60%), right animated product loop (40%) on desktop; stacked on mobile.

**Copy:**
- Eyebrow: `AI AGENT FAILURE DISCOVERY & REGRESSION GUARD`
- H1 (display): **"Find the AI agent failures you didn't know to test."**
- Sub: *"Zroky learns your agent's normal behavior in production, surfaces the abnormal — including failures you never wrote a test for — proves your fix with replay, and blocks the repeat in CI."*
- CTAs: **[Start free →]** (accent) · **[★ zroky-watch — open source]** (ghost/pill) · tiny: "5-min install · works with any framework"
- Trust line under CTA: *"We never call a stub replay a verified fix."*

**Hero visual (the centerpiece):** animated 3-card loop
```
[ Discovered ]            [ Proved ]                 [ Guarded ]
 refund_agent              candidate fix              PR #482 blocked
 skipped get_refund_status replay: now calls tool     "refund-status regressed"
 ·96% normal ·outcome✗     fidelity 94% ✓ verified    do not merge
   (violet badge)            (green badge)              (red badge)
```
Cards animate in sequence, arrows draw between them, subtle loop. This single visual *is* the pitch.

## Section 3 — Credibility strip
- Muted line: **"Works with OpenAI · Anthropic · Google · LangChain · LangGraph · any framework (OpenTelemetry)."**
- Framework wordmarks (not fake customer logos). Replace with real customers when they exist.

## Section 4 — The problem (3 cards)
Heading: **"Your agent returns 200 OK — and still fails the task."**
Sub: *"The worst failures are silent. You find out when the customer complains."*
Cards:
1. **Silent failures** — "Valid-looking output, wrong result. No error fired." (icon: eye-off)
2. **You can't test what you can't imagine** — "Eval-first tools only catch failures you already wrote a rubric for." (icon: help-circle)
3. **The same bug ships twice** — "Fixed last sprint, regressed this one. Nobody caught it." (icon: rotate)

## Section 5 — The loop (the spine)
Heading: **"Discover → Prove → Guard"**
Animated SVG line diagram, 3 nodes, scroll-revealed. One line each:
- **Discover** — find unknown failures from real behavior.
- **Prove** — replay the exact case; verify the fix (with fidelity).
- **Guard** — turn it into a CI gate; block the repeat.

## Section 6 — Pillar 1: DISCOVER (the differentiator)
**Layout:** copy left, "discovered finding" card right.
- H2: **"Catch the failures your tests miss."**
- Body: *"Zroky learns each workflow's normal behavior — tool sequences, outputs, outcomes — and surfaces deviations that matter. No rubric required. Every finding comes with the evidence: 'present in 96% of normal traces, missing here, outcome flipped to failure.'"*
- Visual: the Discovered card with reason + corroboration chips (violet badge). Small note: "Anomaly ≠ failure — we only surface when corroborated."
- Micro-CTA: "See how discovery works →" (→ /product/discover)

## Section 7 — Pillar 2: PROVE
- H2: **"Prove the fix works — honestly."**
- Body: *"Replay the exact failed scenario against your candidate fix. See before/after, tool-behavior diff, cost & latency delta — and a fidelity score that tells you how faithfully we reproduced it. 'Verified' only ever means verified."*
- Visual: `product-replay-detail.png` (real) + fidelity score callout.
- Micro-CTA: "Explore Replay Lab →" (→ /product/prove)

## Section 8 — Pillar 3: GUARD
- H2: **"Stop the same failure from shipping twice."**
- Body: *"Promote a verified fix into a Golden. Zroky runs it on every PR and blocks regressions — and it only blocks when it's sure. Borderline? It says 'review', never a false block."*
- Visual: `product-ci-gate.png` (real PR comment). Note: "not_verified is never counted as a pass."
- Micro-CTA: "See CI Gates →" (→ /product/guard)

## Section 9 — Why different (honest comparison)
Heading: **"Eval-first tools test what you imagine. Zroky finds what you didn't."**
Two-column comparison (no competitor names):
| Eval-first tooling | Zroky |
|---|---|
| You write rubrics/evals upfront | Learns normal from production |
| Catches known failure modes | Surfaces unknown failures |
| Day 1 = blank (no labels) | Value as traffic arrives |
| "Verified" = ran a judge | Fidelity-scored, honest verdicts |

## Section 10 — Trust / honesty (a differentiator, not fine print)
Heading: **"Built to earn trust, not inflate it."**
3 chips: "Stub replay is never 'verified'." · "CI blocks only at high confidence." · "We show replay fidelity, including when we can't reproduce."

## Section 11 — Quickstart
Heading: **"Live in 5 minutes."**
Code block (copyable):
```python
import zroky
zroky.init(api_key=..., project="refund-agent-prod")

@zroky.trace(agent="refund_agent", workflow="status_lookup")
async def handle(q): ...
```
Sub: *"Capture starts immediately. Structural failures surface now; behavioral discovery unlocks as Zroky learns your normal."* (honest — no "instant magic").

## Section 12 — Social proof / metrics
- Until real customers: OSS stat ("★ N on GitHub"), "built for production agents at 10k–1M calls/mo".
- Later: customer quotes, "$ wasted-spend prevented", logos.

## Section 13 — Final CTA
- Big: **"Stop shipping the same agent failure twice."**
- [Start free →] · [Talk to us] · [★ zroky-watch]

## Section 14 — Footer (file 09)

---

## Imagery checklist (home)
- [ ] Animated Discover→Prove→Guard hero loop (build as React+framer, not a static png).
- [ ] Discovered-finding card (capture from real dashboard once discovery UI ships).
- [ ] `product-replay-detail.png` + fidelity callout.
- [ ] `product-ci-gate.png`.
- [ ] Loop SVG diagram.

## My POV
- The **hero loop visual is 50% of this page's value** — invest there. It literally animates the product thesis in 3 seconds.
- Lead with Discover (section 6) — it's the only thing competitors don't have. Prove/Guard are credibility, not the hook.
- The honesty section (10) is unusual and memorable — keep it. It signals confidence.
- Resist feature-listing. One idea per section, lots of air.
