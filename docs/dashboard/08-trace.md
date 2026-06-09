# 08 — Traces (Evidence — list + detail)

| | |
|---|---|
| **Files** | `trace/page.tsx` (503 LOC), `trace/[id]/page.tsx` (508 LOC) |
| **Pillar** | Evidence (multi-step/agent execution paths) |
| **State** | Mature. Recent traces list, trace detail with span hierarchy / execution path / multi-agent context. |

## 1. Purpose
Traces show the multi-step execution path of an agent run — the span-level evidence behind a failure. Critical for the "operational failure" reality (tool/sequence/state issues), which is exactly what discovery's tool-sequence signals key on.

## 2. STAYS
- Recent traces list, trace detail (spans, path, multi-agent context).

## 3. CHANGES / ADD
- **Tool-sequence highlight:** when a trace is the sample for a discovered finding (e.g. "missing critical tool"), highlight the *missing/abnormal* step in the span view. This visually proves the discovery reason.
- Back-link to the originating finding.

## 4. CUT
- Nothing. Secondary nav.

## 5. Data / API
- `getRecentTraces`, `getTraceById`, `getCallTraceTree`.

## 6. States
- Loading, empty, error, populated. Multi-agent traces render hierarchy.

## 7. Discovery integration
- **High value:** discovery's strongest signal is tool-sequence deviation; the trace view is where "agent skipped get_refund_status" is *seen*. Highlighting the deviant span turns the discovery reason into visual proof.

## 8. My POV
- Traces is currently set `visibleInNav:false` though it's in the locked MVP nav — decide: keep it reachable from findings/calls (my preference) rather than a primary nav item. Evidence is reached *from* a problem, not browsed standalone.
- The tool-sequence highlight is a small, high-impact add that directly reinforces the discovery wedge ("here's the exact step that was skipped").

## 9. DoD
- [ ] Deviant-step highlight for discovered findings.
- [ ] Finding back-link; reachable from calls/issues (not primary nav).
