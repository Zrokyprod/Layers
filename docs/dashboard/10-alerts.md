# 10 — Alerts (Supporting — triage routing)

| | |
|---|---|
| **File** | `alerts/page.tsx` (440 LOC) |
| **Pillar** | Supporting — alert triage (ack/resolve/reopen) |
| **State** | Mature. Alert list with status/severity/category filters, acknowledge/resolve/reopen, channel test. |

## 1. Purpose
Alerts is the triage queue for fired alerts (drift, auth, rate-limit, cost-spike, judge-drift, etc.) routed to Slack/Teams. It overlaps conceptually with Issues — needs clear boundary.

## 2. STAYS
- Triage actions (ack/resolve/reopen), filters, channel test.

## 3. CHANGES
- **Clarify Alerts vs Issues boundary.** Issues = clustered *problems* (incl. discovered). Alerts = *notifications* of events. Avoid duplicating the same failure in both as separate concepts. Consider: alerts link to their issue rather than standing alone.
- Discovery does NOT create a separate alert stream — a surfaced finding can *notify* via the existing alert/Slack path, but the canonical object stays the Issue.

## 4. CUT / consider
- If Alerts and Issues drift into duplication, demote Alerts to a notifications log under settings/integrations rather than a primary surface. (Decide during Phase 5.)

## 5. Data / API
- `listAlerts`, `getAlertDetail`, `acknowledge/resolve/reopenAlert`, `testAlertChannel`.

## 6. States
- Loading, empty, error, populated.

## 7. Discovery integration
- A surfaced discovered finding may emit a notification through existing channels (Slack/Teams) — but it appears as an Issue, not a parallel alert object. Keep one source of truth.

## 8. My POV
- Alerts risks being a **second "problem" concept** competing with Issues — the same trap we avoided with the findings table. Be disciplined: **Issue is the object; alert is a delivery mechanism.**
- Keep Alerts as a supporting triage/notifications surface, not primary nav. If it starts duplicating Issues, fold it into integrations.

## 9. DoD
- [ ] Alerts clearly = notifications, not a parallel problem model.
- [ ] No duplicate failure concept vs Issues.
- [ ] Triage actions intact; secondary placement.
