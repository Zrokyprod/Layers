from __future__ import annotations

from app.services._runtime_policy_core import *  # noqa: F403


def evaluate_runtime_policy(
    db: Session,
    *,
    project_id: str,
    payload: dict[str, Any],
    persist: bool = True,
) -> RuntimePolicyResult:
    policy = resolve_runtime_policy(db, project_id=project_id, payload=payload).policy

    def make_result(
        *,
        decision: str,
        status: str,
        reasons: list[str],
        allowed: bool,
        requires_approval: bool,
        expires_at: datetime | None = None,
        required_approval_count: int = 0,
    ) -> RuntimePolicyResult:
        maker = _create_decision if persist else _preview_decision
        row = maker(
            db,
            project_id=project_id,
            payload=payload,
            policy=policy,
            decision=decision,
            status=status,
            reasons=reasons,
            expires_at=expires_at,
            required_approval_count=required_approval_count,
        )
        if persist:
            db.commit()
            db.refresh(row)
        return RuntimePolicyResult(row, allowed=allowed, requires_approval=requires_approval, reasons=reasons)

    reasons: list[str] = []
    if policy.get("runtime_enabled") is False:
        return make_result(
            decision="allow",
            status="allowed",
            reasons=["runtime policy gate disabled for this project"],
            allowed=True,
            requires_approval=False,
        )

    if policy.get("kill_switch") is True:
        reasons.append("project kill switch is enabled")

    tool_name = _bounded(payload.get("tool_name"), max_length=255)
    allowed_tools = policy.get("runtime_allowed_tools")
    if isinstance(allowed_tools, list) and allowed_tools and tool_name:
        normalized_allowed = {_normalize_tool(str(item)) for item in allowed_tools}
        if _normalize_tool(tool_name) not in normalized_allowed:
            reasons.append(f"tool {tool_name!r} is not allowlisted for this project")

    tool_call_count = _as_int(payload.get("tool_call_count"))
    max_tool_calls = _as_int(policy.get("runtime_max_tool_calls"))
    if tool_call_count is not None and max_tool_calls is not None and max_tool_calls >= 0 and tool_call_count > max_tool_calls:
        reasons.append(f"tool call count {tool_call_count} exceeds runtime limit {max_tool_calls}")

    retry_count = _as_int(payload.get("retry_count"))
    max_retries = _as_int(policy.get("runtime_max_retries"))
    if retry_count is not None and max_retries is not None and max_retries >= 0 and retry_count > max_retries:
        reasons.append(f"retry count {retry_count} exceeds runtime limit {max_retries}")

    estimated_cost = _as_float(payload.get("estimated_cost_usd"))
    max_cost = _as_float(policy.get("runtime_max_cost_usd"))
    if estimated_cost is not None and max_cost is not None and max_cost >= 0 and estimated_cost > max_cost:
        reasons.append(f"estimated action cost ${estimated_cost:.6f} exceeds runtime limit ${max_cost:.6f}")

    external_action = _is_external_action(payload)
    if policy.get("runtime_block_pii_leak") is True and external_action and _payload_has_pii(payload):
        reasons.append("external action payload contains PII or secret-shaped data")

    if (
        policy.get("runtime_block_prompt_injected_external_action") is True
        and external_action
        and _contains_prompt_injection(payload)
    ):
        reasons.append("prompt-injection-shaped instruction attempted an external action")

    reasons.extend(_first_launch_block_reasons(payload, policy))

    if reasons:
        return make_result(
            decision="block",
            status="blocked",
            reasons=reasons,
            allowed=False,
            requires_approval=False,
        )

    approval_reasons = _first_launch_approval_reasons(payload, policy)
    if _is_sensitive_action(payload, policy) and policy.get("runtime_sensitive_actions_require_approval") is True:
        approval_reasons.insert(0, "sensitive action requires human approval before execution")
    required_approval_count = _required_approval_count(payload, policy, approval_reasons)

    if approval_reasons:
        if not persist:
            return make_result(
                decision="requires_approval",
                status="pending_approval",
                reasons=approval_reasons,
                allowed=False,
                requires_approval=True,
                expires_at=_approval_expiry(policy),
                required_approval_count=required_approval_count,
            )
        approval = _valid_approval(
            db,
            project_id=project_id,
            approval_id=_bounded(payload.get("approval_id"), max_length=36),
            payload=payload,
        )
        if approval is not None:
            before_approval = _decision_snapshot(approval)
            approved_reason = f"human approval {approval.id} accepted"
            row = _create_decision(
                db,
                project_id=project_id,
                payload=payload,
                policy=policy,
                decision="allow",
                status="allowed",
                reasons=[approved_reason],
            )
            approval.consumed_at = _now()
            approval.consumed_by_decision_id = row.id
            db.add(approval)
            db.flush()
            _log_audit_event(
                db,
                decision=approval,
                event_type="approval_consumed",
                actor=_bounded(payload.get("actor") or payload.get("agent_name"), max_length=128),
                reason=approved_reason,
                before=before_approval,
                after=_decision_snapshot(approval),
            )
            _update_trace_policy_span(db, project_id=project_id, decision=approval)
            db.commit()
            db.refresh(row)
            return RuntimePolicyResult(row, allowed=True, requires_approval=False, reasons=[approved_reason])

        pending = _find_reusable_pending_approval(db, project_id=project_id, payload=payload)
        if pending is not None:
            reasons = _json_loads(pending.reasons_json, approval_reasons)
            return RuntimePolicyResult(pending, allowed=False, requires_approval=True, reasons=reasons)

        return make_result(
            decision="requires_approval",
            status="pending_approval",
            reasons=approval_reasons,
            allowed=False,
            requires_approval=True,
            expires_at=_approval_expiry(policy),
            required_approval_count=required_approval_count,
        )

    return make_result(
        decision="allow",
        status="allowed",
        reasons=["runtime policy checks passed"],
        allowed=True,
        requires_approval=False,
    )
