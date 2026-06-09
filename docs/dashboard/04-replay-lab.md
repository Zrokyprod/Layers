# 04 — Replay Lab (Prove — list + detail)

| | |
|---|---|
| **Files** | `replay/page.tsx` (769 LOC), `replay/[id]/page.tsx` (1108 LOC), `lib/replay-mode.ts` |
| **Pillar** | **Prove** — the money pillar; the "wow" screen |
| **State** | Most polished module. Replay modes (stub/real_llm/mocked_tool/live_sandbox/shadow), `DEFAULT_VERIFICATION_REPLAY_MODE`, before/after, verification status. Trust-honest (stub never "verified"). |

## 1. Purpose
Replay proves a candidate fix works against the real failed scenario — honestly. It's where "verified_fix" is earned. This is the screen that justifies paying.

## 2. STAYS
- Mode selection + gating (overrides require real comparison), original-vs-candidate panels, verification status vocabulary, cost/latency deltas, trust semantics (stub = sanity only).

## 3. CHANGES / ADD
- **Discovery → Replay handoff:** a discovered issue routes here in one click with its sample call (reuse `createReplayRunFromIssue`). Ensure the source-finding context (reason) is shown so the developer knows *what* they're proving.
- **Fidelity score (NEW, the trust differentiator):** in the verification panel, show how faithfully the replay reproduced the scenario:
  - "92% faithful — tool context matched, prompt re-executed. ⚠️ external state changed (8% uncertainty)."
  - or honest refusal: "Cannot replay — depended on real-time state now gone. Not marked verified."
- Verdict vocabulary unchanged: `verified_fix / fix_failed / inconclusive / tool_snapshot_missing / sandbox_unavailable / not_verified`.

## 4. CUT
- Nothing. This module is the strongest as-is.

## 5. Data / API
- `replay_runs` create/get/list; provider-key vault gate; `REPLAY_REAL_LLM_ENABLED` (must ship ON in prod per completion plan). Fidelity score from the replay executor (backend addition).

## 6. States
- Loading (run pending/running with progress), empty ("no replays yet — replay a discovered failure"), error, populated (before/after + verdict + fidelity).

## 7. Discovery integration
- Entry point from a discovered finding; the rest is the existing Prove flow. The fidelity score is the cross-pillar honesty signal.

## 8. My POV
- This is your strongest screen and a genuine differentiator — most competitors print "verified ✅"; Zroky shows *how faithful* the proof was. The **fidelity score is worth prioritizing** because it's the trust moat that pairs with discovery.
- Don't restyle. Add fidelity + handoff context only.
- Make sure real-LLM replay is actually ON in production — a Prove pillar that's flag-off is a hollow center.

## 9. DoD
- [ ] One-click discovered→replay with source context.
- [ ] Fidelity score in verification panel.
- [ ] Real-LLM replay enabled in prod; trust vocabulary intact.
