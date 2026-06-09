# 09 — Cost (Supporting — cost of failure)

| | |
|---|---|
| **File** | `cost/page.tsx` (970 LOC) |
| **Pillar** | Supporting — spend, waste, cost-of-failure |
| **State** | Large, mature. Daily trend, by-model/user/agent breakdown, reasoning share, cache savings, top calls, budget config + status, hourly. |

## 1. Purpose
Cost shows spend, wasted spend on failures, and budget risk. MVP_LOCK called this non-core, but **cost-of-failure ($ blast radius) is a real selling point** — it quantifies why a discovered failure matters.

## 2. STAYS
- Cost analytics surfaces (trend/breakdowns/budget). Keep in primary nav (per locked nav) — it's the one analytics surface that ties to the wedge ($ impact of failures).

## 3. CHANGES / ADD
- **Tie cost to failures:** surface "wasted spend on failed/abnormal calls" prominently and link to the discovered findings driving it. Cost becomes "cost of *failure*," not generic spend analytics.
- De-emphasize generic LLM-usage analytics (that's the LangSmith/observability framing we don't compete on).

## 4. CUT / trim
- Trim or `/labs` the parts that are pure usage analytics with no failure tie-in (e.g. reasoning-share, cache-savings deep dives) if they dilute the cost-of-failure story. Keep them reachable, not front-and-center.

## 5. Data / API
- `getCostDailyTrend/ByModel/ByUser/ByAgent`, `getReasoningShare`, `getCacheSavings`, `getCostTopCalls`, `getBudget/Status`, `getCostHourly`.

## 6. States
- Loading, empty, error, populated.

## 7. Discovery integration
- Blast-radius USD on discovered findings should roll up here ("$X wasted on the failure Zroky discovered"). Strong ROI narrative.

## 8. My POV
- Cost is **bigger than it needs to be** (970 LOC). The valuable 30% is "cost of failure / wasted spend"; the rest is generic spend analytics that competes in the crowded observability lane.
- Reframe, don't delete: make this the **"what failures cost you"** page, not the "LLM spend dashboard." That reframe aligns it with Discover (impact) and Prove (cost delta of a fix).
- Keep budget controls — practical and sticky.

## 9. DoD
- [ ] Cost-of-failure framing front; generic analytics secondary.
- [ ] Wasted-spend links to discovered findings.
- [ ] Budget controls intact.
