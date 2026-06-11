"""Golden contract helpers.

Goldens keep their public storage in ``GoldenTrace.criteria_json`` for
backwards compatibility. Phase 7 adds a structured ``golden_contract_v1``
object inside that JSON rather than adding many nullable columns.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

GOLDEN_CONTRACT_KEY = "golden_contract_v1"
REPLAY_MODE_STUB = "stub"
_REPLAY_MODE_ALIASES = {
    "mocked-tool": "mocked_tool",
    "live-sandbox": "sandbox",
}


def safe_json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        decoded = json.loads(raw)
        return decoded if isinstance(decoded, dict) else {}
    except Exception:
        return {}


def validate_criteria_json(raw: str | None) -> str | None:
    if raw is None or not str(raw).strip():
        return None
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("criteria_json must be valid JSON") from exc
    if not isinstance(decoded, dict):
        raise ValueError("criteria_json must be a JSON object")
    contract = decoded.get(GOLDEN_CONTRACT_KEY)
    if contract is not None and not isinstance(contract, dict):
        raise ValueError("golden_contract_v1 must be a JSON object")
    return json.dumps(decoded, separators=(",", ":"), default=str)


def build_golden_contract(
    *,
    final_output: str | None = None,
    tool_sequence: list[str] | None = None,
    tool_args: Mapping[str, Any] | None = None,
    policy_checks: list[str] | None = None,
    required_approval: str | None = None,
    rag_grounding: Mapping[str, Any] | None = None,
    max_cost_usd: float | None = None,
    max_latency_ms: int | None = None,
    max_tool_calls: int | None = None,
    business_outcome: str | None = None,
    linked_issue_id: str | None = None,
    linked_trace_id: str | None = None,
    linked_replay_run_id: str | None = None,
    proof_status: str | None = None,
) -> dict[str, Any]:
    contract: dict[str, Any] = {"schema": GOLDEN_CONTRACT_KEY}
    if final_output:
        contract["final_output"] = {"kind": "text", "expected": final_output}
    if tool_sequence:
        contract["tool_sequence"] = list(tool_sequence)
    if tool_args:
        contract["tool_args"] = dict(tool_args)
    if policy_checks:
        contract["policy_checks"] = list(policy_checks)
    if required_approval:
        contract["required_approval"] = required_approval
    if rag_grounding:
        contract["rag_grounding"] = dict(rag_grounding)
    budgets: dict[str, Any] = {}
    if max_cost_usd is not None:
        budgets["max_cost_usd"] = float(max_cost_usd)
    if max_latency_ms is not None:
        budgets["max_latency_ms"] = int(max_latency_ms)
    if max_tool_calls is not None:
        budgets["max_tool_calls"] = int(max_tool_calls)
    if budgets:
        contract["budgets"] = budgets
    if business_outcome:
        contract["business_outcome"] = business_outcome
    linked: dict[str, Any] = {}
    if linked_issue_id:
        linked["issue_id"] = linked_issue_id
    if linked_trace_id:
        linked["trace_id"] = linked_trace_id
    if linked_replay_run_id:
        linked["replay_run_id"] = linked_replay_run_id
    if proof_status:
        linked["proof_status"] = proof_status
    if linked:
        contract["linked_proof"] = linked
    return contract


def criteria_with_contract(
    criteria_json: str | None,
    contract: Mapping[str, Any],
) -> str:
    criteria = safe_json_object(criteria_json)
    criteria[GOLDEN_CONTRACT_KEY] = dict(contract)
    return validate_criteria_json(json.dumps(criteria, separators=(",", ":"), default=str)) or "{}"


def trusted_replay_summary(summary: Mapping[str, Any], *, replay_mode: str | None = None) -> bool:
    raw_mode = str(
        replay_mode
        or summary.get("requested_replay_mode")
        or summary.get("executor_replay_mode")
        or summary.get("replay_mode")
        or ""
    ).strip().lower()
    mode = _REPLAY_MODE_ALIASES.get(raw_mode, raw_mode)
    return (
        mode != REPLAY_MODE_STUB
        and summary.get("verified_fix") is True
        and str(summary.get("verification_status") or "") == "verified_fix"
    )
