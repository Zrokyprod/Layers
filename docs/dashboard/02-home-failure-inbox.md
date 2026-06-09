# 02 — Home / Failure Inbox (Discover landing)

| | |
|---|---|
| **File** | `src/app/(dashboard)/home/page.tsx` (1234 LOC) + `components/kpi-strip.tsx`, `top-issues-queue.tsx`, `priority-queue.tsx` |
| **Pillar** | **Discover** — the default landing, the first impression |
| **State** | Mature, trust-aware. Hero + queue-focus tabs (`all/critical_high/replay_gap/impact/verified`) + sections (issues queue, pending replay runs, failed CI runs, goldens-needing-review) + first-run onboarding. 30s refresh. Plan-gated actions. |

## 1. Purpose
The home inbox is where a developer lands and asks "what's broken and what do I do next?" It must lead with **discovered unknown failures** (the wedge) while keeping the existing triage queue.

## 2. STAYS
- Hero + KPI strip; queue-focus tab pattern; section layout; 30s polling; plan-gating; first-run onboarding component; the `chooseIssueAction`/`nextActionTitle` next-action engine.
- Trust-aware sorting (severity → replay-gap → impact → recurrence).

## 3. CHANGES
- **Add queue focus `discovered`** to `InboxQueueFocus`: "failures Zroky found that you never wrote a test for." Filter = issues sourced from `BEHAVIORAL_DRIFT` / `is_discovered`.
- **Onboarding copy:** capture → **Zroky auto-discovers normal vs abnormal** → replay → prove. Keep "start with evidence, not replay."
- **Header subtitle:** when discoveries exist, lead with them ("N unknown failures discovered this week").

## 4. ADD
- **KPI tile:** "Unknown failures discovered" (count, window-scoped) with subtext "auto-surfaced, no eval written."
- Optional: a thin "Discovered" highlight strip above the queue when count > 0.

## 5. CUT
- Nothing structural. Ensure failed-CI / goldens-review sections don't visually outweigh the discovery story.

## 6. Data / API
- `listIssues`, `listReplayRuns`, `listGoldenSets`, `getBillingMe`, `getReplayQuota`, `getAnalyticsSummary` (already wired, `settleLoad` partial-failure pattern — keep).
- Needs issue payload to carry `is_discovered`, `reason`, `confidence` (file 03 §data; backend passthrough).

## 7. States
- **Loading:** existing skeleton per section.
- **Empty/first-run:** `FirstRunOnboarding` (already strong) — update copy for discovery.
- **Error:** per-source partial errors already handled (`loadErrors`) — keep.
- **Populated:** discovered focus shows reason-bearing cards.

## 8. Discovery integration (core)
This is the **primary discovery surface**. The `discovered` focus + KPI + onboarding copy are the visible wedge on the landing page. Gated by `DISCOVERY_ENABLED`.

## 9. My POV
- This page is the single most important UI for the wedge. If a first-time user lands and immediately sees "Zroky discovered 3 failures you weren't testing for — here's why," the product sells itself. If they see a generic issue list, it's a me-too.
- Don't over-engineer: one new focus tab + one KPI tile + copy. The infrastructure is already here.
- Resist adding more sections — the inbox is already dense; discovery should *reframe* it, not pile on.

## 10. DoD
- [ ] `discovered` focus + KPI tile live (gated).
- [ ] Onboarding tells the discovery story.
- [ ] 4 states intact; build passes.
