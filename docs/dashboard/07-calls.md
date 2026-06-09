# 07 — Calls (Capture evidence — list + detail)

| | |
|---|---|
| **Files** | `calls/page.tsx` (552 LOC), `calls/[id]/page.tsx` (932 LOC) |
| **Pillar** | Capture / evidence (feeds Discover + Prove) |
| **State** | Mature. Call list with rich filters (status/model/user/agent/call_type/cost/time), CSV/JSON export, call detail with trace tree, adjacent calls, diagnosis, evidence. |

## 1. Purpose
Calls is the raw evidence layer — every captured production call. It's where a finding's "sample calls" resolve to concrete traces. Not a hero surface, but essential proof substrate.

## 2. STAYS
- Filter set, pagination, export (CSV/JSON with bounded fetch), call detail (trace tree, adjacent calls, diagnosis panel, evidence).

## 3. CHANGES / ADD
- **From-discovery linking:** a discovered finding's `sample_call_ids` deep-link here; ensure the call detail shows "part of discovered finding X" back-link.
- Keep filters; optionally add a "is_production / synthetic" filter chip (discovery only baselines on production).

## 4. CUT
- Nothing. Secondary nav (not primary) — correct.

## 5. Data / API
- `listCalls`, `getCallDetail`, `getCallTraceTree`, `getAdjacentCalls`, export helpers — all wired.

## 6. States
- Loading, empty ("no calls captured yet — install the SDK"), error, populated.

## 7. Discovery integration
- Evidence sink: discovered findings point at calls here. Bi-directional link (finding ↔ call) is the only add.

## 8. My POV
- Calls is correctly a **supporting/secondary** surface — keep it out of primary nav. It's where you go to inspect, not where you start.
- The 932-LOC detail page is heavy but justified (trace tree + evidence). Don't trim; just add the finding back-link.
- Export is a quiet but valuable feature for enterprise/debugging — keep.

## 9. DoD
- [ ] Finding ↔ call back-link.
- [ ] Filters/export intact; secondary nav placement.
