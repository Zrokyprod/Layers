"""MCP JSON-RPC proxy surface.

Speaks just enough of the Model Context Protocol to sit transparently
between an agent's MCP client and its upstream tool servers:

  * ``initialize`` / ``ping`` - handshake, advertise proxy identity
  * ``tools/list``            - passthrough, annotate protected tools
  * ``tools/call``            - classify, gate, audit, then maybe forward

``handle_message`` is intentionally pure over the kernel, upstream transport,
and event sink ports so the decision and response mapping is unit-testable
without a live DB or network.

Safety posture:
  * protected action + gate/kernel error -> fail closed
  * protected action + missing audit     -> fail closed
  * unprotected action + gate/audit error -> fail open
  * a durable binding may override gate-error posture via ``fail_posture``

Every protected ``tools/call`` decision must be durably recorded before the
proxy returns a final policy result or forwards an allowed action. Forward
outcome is then applied as a best-effort update to the same audit row.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from app.mcp.gate import (
    GateDecision,
    IdempotencyConflict,
    KernelPort,
    McpSession,
    evaluate,
)
from app.mcp.remediation import (
    Remediation,
    for_execution_unknown,
    for_hold,
    for_idempotency_conflict,
    for_policy_deny,
    for_service_unavailable,
)
from app.mcp.tool_binding import ActionClassification, ToolBinding, classify_tool

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "2025-06-18"
_SERVER_INFO = {"name": "zroky-mcp-proxy", "version": "0.1.0"}

_METHOD_NOT_FOUND = -32601


@dataclass(frozen=True)
class InterceptionEvent:
    """The decision record for one intercepted tools/call.

    Recorded before any upstream forward. The forward outcome is applied later
    via ``EventSink.update_outcome`` so the durable audit reflects the decision
    even if the forward, or the process, dies mid-call.
    """

    tool_name: str
    action_type: str | None
    protected: bool
    binding_source: str | None
    decision: str
    intent_id: str | None
    fail_posture: str | None


class EventSink(Protocol):
    def record(self, event: InterceptionEvent) -> str | None:
        """Durably persist the decision and return a row id for outcome updates.

        Implementations must raise on failure so protected actions can fail
        closed before a side effect happens or a policy decision is returned.
        """
        ...

    def update_outcome(
        self,
        event_id: str | None,
        *,
        forward_attempted: bool,
        forward_succeeded: bool,
        execution_state: str,
        upstream_error: str | None,
        action_receipt_id: str | None = None,
        receipt_digest: str | None = None,
        proof_status: str | None = None,
    ) -> None:
        """Best-effort: apply the forward result to a recorded decision."""
        ...


class UpstreamTransport(Protocol):
    """The real MCP server(s) this proxy forwards allowed calls to."""

    def list_tools(self) -> list[dict[str, Any]]: ...

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


class PostExecutionProcessor(Protocol):
    """Optional Slice-2 bridge that queues async verification and receipts."""

    def process(
        self,
        *,
        project_id: str,
        intent_id: str,
        event_id: str | None,
        tool_name: str,
        arguments: dict[str, Any],
        execution_state: str,
        upstream_result: dict[str, Any] | None,
        upstream_error: str | None,
    ) -> Any: ...


def _ok(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _tool_result(text: str, *, is_error: bool, meta: dict | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "content": [{"type": "text", "text": text}],
        "isError": is_error,
    }
    if meta is not None:
        result["_meta"] = {"zroky": meta}
    return result


def handle_message(
    message: dict[str, Any],
    *,
    session: McpSession,
    kernel: KernelPort,
    upstream: UpstreamTransport,
    bindings: list[ToolBinding] | None = None,
    event_sink: EventSink | None = None,
    post_execution: PostExecutionProcessor | None = None,
) -> dict[str, Any]:
    """Handle one JSON-RPC request and return the JSON-RPC response."""
    request_id = message.get("id")
    method = message.get("method")
    params = message.get("params") or {}

    if method == "initialize":
        return _ok(
            request_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "serverInfo": _SERVER_INFO,
                "capabilities": {"tools": {}},
            },
        )

    if method == "ping":
        return _ok(request_id, {})

    if method == "tools/list":
        tools = upstream.list_tools()
        for tool in tools:
            cls = classify_tool(tool.get("name", ""), None, bindings)
            tool.setdefault("_meta", {})["zroky"] = {
                "protected": cls.protected,
                "action_type": cls.action_type,
            }
        return _ok(request_id, {"tools": tools})

    if method == "tools/call":
        result = _handle_tool_call(
            params, session, kernel, upstream, bindings, event_sink, post_execution
        )
        return _ok(request_id, result)

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": _METHOD_NOT_FOUND, "message": f"method not found: {method}"},
    }


def _effective_posture(classification: ActionClassification) -> str:
    if classification.fail_posture in ("fail_open", "fail_closed"):
        return classification.fail_posture
    return "fail_closed" if classification.protected else "fail_open"


def _handle_tool_call(
    params: dict[str, Any],
    session: McpSession,
    kernel: KernelPort,
    upstream: UpstreamTransport,
    bindings: list[ToolBinding] | None,
    event_sink: EventSink | None,
    post_execution: PostExecutionProcessor | None,
) -> dict[str, Any]:
    name = params.get("name", "")
    arguments = params.get("arguments") or {}
    classification = classify_tool(name, arguments, bindings)
    posture = _effective_posture(classification)

    try:
        outcome = evaluate(
            session=session,
            tool_name=name,
            arguments=arguments,
            kernel=kernel,
            bindings=bindings,
        )
    except IdempotencyConflict:
        logger.info("mcp.idempotency_conflict tool=%s protected=%s", name, classification.protected)
        return _deny_with_audit(
            event_sink,
            classification,
            name,
            intent_id=None,
            required_audit=classification.protected,
            text="Idempotency key already belongs to a different action intent.",
            meta_reason="idempotency_conflict",
            remediation=for_idempotency_conflict(),
            fail="closed",
        )
    except Exception:
        logger.exception("mcp.gate_error tool=%s protected=%s", name, classification.protected)
        if posture == "fail_closed":
            return _deny_with_audit(
                event_sink,
                classification,
                name,
                intent_id=None,
                required_audit=classification.protected,
                text="Zroky policy engine unavailable - protected action blocked.",
                meta_reason="gate_unavailable",
                remediation=for_service_unavailable("gate_unavailable"),
                fail="closed",
            )
        return _forward(
            name,
            arguments,
            upstream,
            event_sink,
            post_execution,
            session,
            classification,
            decision="observe",
            intent_id=None,
            required_audit=False,
            degraded=True,
        )

    if outcome.decision is GateDecision.DENY:
        return _deny_with_audit(
            event_sink,
            outcome.classification,
            name,
            intent_id=outcome.intent_id,
            required_audit=outcome.classification.protected,
            text="Zroky policy blocked this action. Review the remediation metadata before retrying.",
            meta_reason=None,
            remediation=for_policy_deny(outcome.reasons),
            fail=None,
        )

    if outcome.decision is GateDecision.HOLD:
        audit_error = _record_decision(
            event_sink,
            _event(outcome.classification, name, "hold", outcome.intent_id),
            required=outcome.classification.protected,
            tool_name=name,
        )
        if audit_error is not None:
            return audit_error
        return _tool_result(
            "Awaiting human approval before this action can run.",
            is_error=False,
            meta={
                "decision": "hold",
                "action_type": outcome.classification.action_type,
                "approval_ref": outcome.approval_ref,
                "intent_id": outcome.intent_id,
                "remediation": for_hold(approval_ref=outcome.approval_ref).to_meta(),
            },
        )

    return _forward(
        name,
        arguments,
        upstream,
        event_sink,
        post_execution,
        session,
        outcome.classification,
        decision=outcome.decision.value,
        intent_id=outcome.intent_id,
        required_audit=outcome.classification.protected,
    )


def _deny_with_audit(
    event_sink: EventSink | None,
    classification: ActionClassification,
    tool_name: str,
    *,
    intent_id: str | None,
    required_audit: bool,
    text: str,
    meta_reason: str | None,
    remediation: Remediation,
    fail: str | None = None,
) -> dict[str, Any]:
    audit_error = _record_decision(
        event_sink,
        _event(classification, tool_name, "deny", intent_id, fail=fail),
        required=required_audit,
        tool_name=tool_name,
    )
    if audit_error is not None:
        return audit_error

    meta: dict[str, Any] = {
        "decision": "deny",
        "action_type": classification.action_type,
        "intent_id": intent_id,
    }
    if meta_reason:
        meta["reason"] = meta_reason
    if fail:
        meta["fail"] = fail
    meta["remediation"] = remediation.to_meta()
    return _tool_result(text, is_error=True, meta=meta)


def _forward(
    name: str,
    arguments: dict[str, Any],
    upstream: UpstreamTransport,
    event_sink: EventSink | None,
    post_execution: PostExecutionProcessor | None,
    session: McpSession,
    classification: ActionClassification,
    *,
    decision: str,
    intent_id: str | None,
    required_audit: bool,
    degraded: bool = False,
) -> dict[str, Any]:
    event_id, audit_error = _record_decision_with_id(
        event_sink,
        _event(classification, name, decision, intent_id),
        required=required_audit,
        tool_name=name,
    )
    if audit_error is not None:
        return audit_error

    try:
        result = upstream.call_tool(name, arguments)
    except Exception as exc:
        logger.exception("mcp.upstream_error tool=%s decision=%s", name, decision)
        receipt_meta = _post_execute_best_effort(
            post_execution,
            session=session,
            event_id=event_id,
            tool_name=name,
            arguments=arguments,
            decision=decision,
            intent_id=intent_id,
            execution_state="unknown",
            upstream_result=None,
            upstream_error=str(exc),
        )
        _update_outcome_best_effort(
            event_sink,
            event_id,
            forward_attempted=True,
            forward_succeeded=False,
            execution_state="unknown",
            upstream_error=str(exc)[:512],
            receipt_meta=receipt_meta,
        )
        meta = {
            "decision": decision,
            "intent_id": intent_id,
            "execution_state": "unknown",
            "remediation": for_execution_unknown(intent_id=intent_id).to_meta(),
        }
        meta.update(receipt_meta)
        return _tool_result(
            "Upstream execution outcome is unknown. Check execution status before retrying.",
            is_error=True,
            meta=meta,
        )

    receipt_meta = _post_execute_best_effort(
        post_execution,
        session=session,
        event_id=event_id,
        tool_name=name,
        arguments=arguments,
        decision=decision,
        intent_id=intent_id,
        execution_state="succeeded",
        upstream_result=result,
        upstream_error=None,
    )
    _update_outcome_best_effort(
        event_sink,
        event_id,
        forward_attempted=True,
        forward_succeeded=True,
        execution_state="succeeded",
        upstream_error=None,
        receipt_meta=receipt_meta,
    )
    meta = result.setdefault("_meta", {}).setdefault("zroky", {})
    meta["decision"] = decision
    meta["execution_state"] = "succeeded"
    if intent_id:
        meta["intent_id"] = intent_id
    if degraded:
        meta["degraded"] = True
    meta.update(receipt_meta)
    return result


def _post_execute_best_effort(
    post_execution: PostExecutionProcessor | None,
    *,
    session: McpSession,
    event_id: str | None,
    tool_name: str,
    arguments: dict[str, Any],
    decision: str,
    intent_id: str | None,
    execution_state: str,
    upstream_result: dict[str, Any] | None,
    upstream_error: str | None,
) -> dict[str, Any]:
    """Queue post-execution proof work without keeping it on the inline path."""
    if post_execution is None or decision != "allow" or not intent_id:
        return {}
    try:
        result = post_execution.process(
            project_id=session.project_id,
            intent_id=intent_id,
            event_id=event_id,
            tool_name=tool_name,
            arguments=arguments,
            execution_state=execution_state,
            upstream_result=upstream_result,
            upstream_error=upstream_error,
        )
    except Exception as exc:
        logger.exception("mcp.post_execution_failed tool=%s intent=%s", tool_name, intent_id)
        return {"receipt_status": "failed", "post_execution_error": exc.__class__.__name__}
    if result is None:
        return {}
    if hasattr(result, "to_meta"):
        meta = result.to_meta()
        return dict(meta) if isinstance(meta, dict) else {}
    if isinstance(result, dict):
        return dict(result)
    return {}


def _record_decision(
    event_sink: EventSink | None,
    event: InterceptionEvent,
    *,
    required: bool,
    tool_name: str,
) -> dict[str, Any] | None:
    _, response = _record_decision_with_id(
        event_sink,
        event,
        required=required,
        tool_name=tool_name,
    )
    return response


def _record_decision_with_id(
    event_sink: EventSink | None,
    event: InterceptionEvent,
    *,
    required: bool,
    tool_name: str,
) -> tuple[str | None, dict[str, Any] | None]:
    if event_sink is None:
        if required:
            return None, _audit_unavailable_response()
        return None, None
    try:
        return event_sink.record(event), None
    except Exception:
        logger.exception(
            "mcp.audit_write_failed tool=%s decision=%s required=%s",
            tool_name,
            event.decision,
            required,
        )
        if required:
            return None, _audit_unavailable_response()
        return None, None


def _audit_unavailable_response() -> dict[str, Any]:
    return _tool_result(
        "Zroky audit log unavailable - protected action blocked.",
        is_error=True,
        meta={
            "decision": "deny",
            "reason": "audit_unavailable",
            "fail": "closed",
            "remediation": for_service_unavailable("audit_unavailable").to_meta(),
        },
    )


def _update_outcome_best_effort(
    event_sink: EventSink | None,
    event_id: str | None,
    *,
    forward_attempted: bool,
    forward_succeeded: bool,
    execution_state: str,
    upstream_error: str | None,
    receipt_meta: dict[str, Any] | None = None,
) -> None:
    if event_sink is None or event_id is None:
        return
    receipt_meta = receipt_meta or {}
    try:
        event_sink.update_outcome(
            event_id,
            forward_attempted=forward_attempted,
            forward_succeeded=forward_succeeded,
            execution_state=execution_state,
            upstream_error=upstream_error,
            action_receipt_id=receipt_meta.get("receipt_id"),
            receipt_digest=receipt_meta.get("receipt_digest"),
            proof_status=receipt_meta.get("proof_status"),
        )
    except Exception:
        logger.exception("mcp.audit_outcome_update_failed event_id=%s", event_id)


def _event(
    classification: ActionClassification,
    tool_name: str,
    decision: str,
    intent_id: str | None,
    *,
    fail: str | None = None,
) -> InterceptionEvent:
    return InterceptionEvent(
        tool_name=tool_name,
        action_type=classification.action_type,
        protected=classification.protected,
        binding_source=classification.binding_source,
        decision=decision,
        intent_id=intent_id,
        fail_posture=fail or classification.fail_posture,
    )
