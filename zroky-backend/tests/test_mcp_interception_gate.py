"""Unit tests for the MCP interception layer (app.mcp).

These run with no DB, tenant, or network — the gate's KernelPort and the
proxy's UpstreamTransport are faked, which is the whole point of the
hexagonal shape: the decision logic is provable in isolation.
"""
from __future__ import annotations

from app.mcp.gate import (
    GateDecision,
    IdempotencyConflict,
    KernelDecision,
    McpSession,
    evaluate,
)
from app.mcp.proxy import handle_message
from app.mcp.tool_binding import ToolBinding, classify_tool


SESSION = McpSession(project_id="proj_1", environment="production", agent_id="agent_1")


class FakeKernel:
    def __init__(self, decision: KernelDecision):
        self._decision = decision
        self.calls: list[str] = []

    def open_and_decide(self, *, session, tool_name, classification, arguments):
        self.calls.append(tool_name)
        return self._decision


class ExplodingKernel:
    def open_and_decide(self, *, session, tool_name, classification, arguments):
        raise RuntimeError("kernel down")


class ConflictKernel:
    def open_and_decide(self, *, session, tool_name, classification, arguments):
        raise IdempotencyConflict("conflicting idempotency key")


class FakeUpstream:
    def __init__(self, raise_on: str | None = None):
        self.called: list[tuple[str, dict]] = []
        self._raise_on = raise_on

    def list_tools(self):
        return [{"name": "create_refund"}, {"name": "get_customer"}]

    def call_tool(self, name, arguments):
        if self._raise_on is not None and name == self._raise_on:
            raise RuntimeError("upstream boom")
        self.called.append((name, arguments))
        return {"content": [{"type": "text", "text": f"ran {name}"}], "isError": False}


class RecordingSink:
    def __init__(self):
        self.records: list = []
        self.outcomes: list = []

    def record(self, event):
        event_id = f"ev-{len(self.records)}"
        self.records.append(event)
        return event_id

    def update_outcome(self, event_id, **kw):
        self.outcomes.append((event_id, kw))


class FailingSink:
    def record(self, event):
        raise RuntimeError("audit down")

    def update_outcome(self, *a, **k):  # pragma: no cover - never reached
        pass


# ── classification ────────────────────────────────────────────────────────


def test_refund_tool_is_protected():
    cls = classify_tool("create_refund")
    assert cls.protected is True
    assert cls.action_type == "refund"
    assert cls.operation_kind == "create"


def test_read_tool_is_unprotected():
    cls = classify_tool("get_customer")
    assert cls.protected is False
    assert cls.operation_kind == "read"


def test_unknown_tool_is_never_protected():
    cls = classify_tool("do_something_weird")
    assert cls.protected is False
    assert cls.binding_source == "unclassified"


def test_exact_binding_wins():
    bindings = [ToolBinding(match="magic_tool", action_type="access_grant", operation_kind="create")]
    cls = classify_tool("magic_tool", None, bindings)
    assert cls.protected is True
    assert cls.action_type == "access_grant"
    assert cls.binding_source == "exact"


def test_regex_binding_matches():
    bindings = [ToolBinding(match=r"^acme\..*payout", action_type="vendor_payout", is_regex=True)]
    cls = classify_tool("acme.finance.payout_v2", None, bindings)
    assert cls.action_type == "vendor_payout"
    assert cls.binding_source == "pattern"


# ── gate ──────────────────────────────────────────────────────────────────


def test_gate_observes_unprotected_without_calling_kernel():
    kernel = FakeKernel(KernelDecision(allowed=True, requires_approval=False, reasons=[]))
    outcome = evaluate(session=SESSION, tool_name="get_customer", arguments={}, kernel=kernel)
    assert outcome.decision is GateDecision.OBSERVE
    assert kernel.calls == []  # unprotected must not touch the policy engine
    assert outcome.forwards_upstream is True


def test_gate_allows_protected():
    kernel = FakeKernel(KernelDecision(allowed=True, requires_approval=False, reasons=["policy ok"], intent_id="i1"))
    outcome = evaluate(session=SESSION, tool_name="create_refund", arguments={"amount": 600}, kernel=kernel)
    assert outcome.decision is GateDecision.ALLOW
    assert outcome.intent_id == "i1"
    assert kernel.calls == ["create_refund"]


def test_gate_denies_protected():
    kernel = FakeKernel(KernelDecision(allowed=False, requires_approval=False, reasons=["over limit"], intent_id="i2"))
    outcome = evaluate(session=SESSION, tool_name="create_refund", arguments={"amount": 999999}, kernel=kernel)
    assert outcome.decision is GateDecision.DENY
    assert outcome.forwards_upstream is False


def test_gate_holds_for_approval():
    kernel = FakeKernel(KernelDecision(allowed=False, requires_approval=True, reasons=["needs approval"], intent_id="i3"))
    outcome = evaluate(session=SESSION, tool_name="access_grant_admin", arguments={}, kernel=kernel)
    assert outcome.decision is GateDecision.HOLD
    assert outcome.approval_ref == "i3"


# ── proxy protocol ────────────────────────────────────────────────────────


def _call(name, args, kernel, upstream, bindings=None):
    msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}}
    return handle_message(msg, session=SESSION, kernel=kernel, upstream=upstream, bindings=bindings)


def test_initialize_advertises_proxy():
    resp = handle_message({"jsonrpc": "2.0", "id": 0, "method": "initialize"},
                          session=SESSION, kernel=FakeKernel(KernelDecision(True, False, [])), upstream=FakeUpstream())
    assert resp["result"]["serverInfo"]["name"] == "zroky-mcp-proxy"


def test_tools_list_annotates_protected():
    resp = handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                          session=SESSION, kernel=FakeKernel(KernelDecision(True, False, [])), upstream=FakeUpstream())
    tools = {t["name"]: t["_meta"]["zroky"]["protected"] for t in resp["result"]["tools"]}
    assert tools == {"create_refund": True, "get_customer": False}


def test_allow_forwards_to_upstream():
    up = FakeUpstream()
    kernel = FakeKernel(KernelDecision(allowed=True, requires_approval=False, reasons=[], intent_id="i1"))
    resp = _call_sink("create_refund", {"amount": 600}, kernel, up, RecordingSink())
    assert up.called == [("create_refund", {"amount": 600})]
    assert resp["result"]["isError"] is False
    assert resp["result"]["_meta"]["zroky"]["decision"] == "allow"


def test_deny_does_not_forward_and_is_error():
    up = FakeUpstream()
    kernel = FakeKernel(KernelDecision(allowed=False, requires_approval=False, reasons=["over limit"], intent_id="i2"))
    resp = _call_sink("create_refund", {"amount": 999999}, kernel, up, RecordingSink())
    assert up.called == []  # blocked before reaching the SOR
    assert resp["result"]["isError"] is True
    assert resp["result"]["_meta"]["zroky"]["decision"] == "deny"


def test_hold_does_not_forward():
    up = FakeUpstream()
    kernel = FakeKernel(KernelDecision(allowed=False, requires_approval=True, reasons=["approval"], intent_id="i3"))
    resp = _call_sink("access_grant_admin", {}, kernel, up, RecordingSink())
    assert up.called == []
    assert resp["result"]["_meta"]["zroky"]["approval_ref"] == "i3"


def test_observe_forwards_unprotected():
    up = FakeUpstream()
    kernel = FakeKernel(KernelDecision(True, False, []))
    resp = _call("get_customer", {"id": "c1"}, kernel, up)
    assert up.called == [("get_customer", {"id": "c1"})]
    assert resp["result"]["_meta"]["zroky"]["decision"] == "observe"


def test_protected_fails_closed_when_kernel_down():
    up = FakeUpstream()
    resp = _call("create_refund", {"amount": 600}, ExplodingKernel(), up)
    assert up.called == []  # fail-CLOSED: never forward a protected action unverified
    assert resp["result"]["isError"] is True
    assert resp["result"]["_meta"]["zroky"]["fail"] == "closed"


# ── Slice 1.5: durable-audit posture ────────────────────────────────────────


def _call_sink(name, args, kernel, upstream, sink):
    msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}}
    return handle_message(msg, session=SESSION, kernel=kernel, upstream=upstream, event_sink=sink)


def test_protected_allow_records_decision_then_updates_outcome():
    up = FakeUpstream()
    sink = RecordingSink()
    kernel = FakeKernel(KernelDecision(allowed=True, requires_approval=False, reasons=[], intent_id="i1"))
    _call_sink("create_refund", {"amount": 600}, kernel, up, sink)
    assert len(sink.records) == 1  # decision recorded before forward
    assert up.called == [("create_refund", {"amount": 600})]
    assert sink.outcomes[0][1]["execution_state"] == "succeeded"
    assert sink.outcomes[0][1]["forward_succeeded"] is True


def test_protected_forward_fails_closed_when_audit_write_fails():
    up = FakeUpstream()
    kernel = FakeKernel(KernelDecision(allowed=True, requires_approval=False, reasons=[], intent_id="i1"))
    resp = _call_sink("create_refund", {"amount": 600}, kernel, up, FailingSink())
    assert up.called == []  # never forward a protected action we cannot audit
    assert resp["result"]["isError"] is True
    assert resp["result"]["_meta"]["zroky"]["reason"] == "audit_unavailable"


def test_protected_deny_fails_closed_when_audit_write_fails():
    up = FakeUpstream()
    kernel = FakeKernel(KernelDecision(allowed=False, requires_approval=False, reasons=["over limit"], intent_id="i2"))
    resp = _call_sink("create_refund", {"amount": 999999}, kernel, up, FailingSink())
    assert up.called == []
    assert resp["result"]["isError"] is True
    assert resp["result"]["_meta"]["zroky"]["reason"] == "audit_unavailable"


def test_protected_hold_fails_closed_when_audit_write_fails():
    up = FakeUpstream()
    kernel = FakeKernel(KernelDecision(allowed=False, requires_approval=True, reasons=["approval"], intent_id="i3"))
    resp = _call_sink("access_grant_admin", {}, kernel, up, FailingSink())
    assert up.called == []
    assert resp["result"]["isError"] is True
    assert resp["result"]["_meta"]["zroky"]["reason"] == "audit_unavailable"


def test_idempotency_conflict_has_specific_reason():
    up = FakeUpstream()
    resp = _call_sink("create_refund", {"amount": 600}, ConflictKernel(), up, RecordingSink())
    assert up.called == []
    assert resp["result"]["isError"] is True
    assert resp["result"]["_meta"]["zroky"]["reason"] == "idempotency_conflict"


def test_protected_conflict_fails_closed_when_audit_write_fails():
    # The conflict is a protected oversight decision: if it cannot be durably
    # recorded, surface audit_unavailable rather than a bare conflict.
    up = FakeUpstream()
    resp = _call_sink("create_refund", {"amount": 600}, ConflictKernel(), up, FailingSink())
    assert up.called == []
    assert resp["result"]["isError"] is True
    assert resp["result"]["_meta"]["zroky"]["reason"] == "audit_unavailable"


def test_unprotected_forwards_even_when_audit_write_fails():
    up = FakeUpstream()
    kernel = FakeKernel(KernelDecision(True, False, []))
    resp = _call_sink("get_customer", {"id": "c1"}, kernel, up, FailingSink())
    assert up.called == [("get_customer", {"id": "c1"})]  # best-effort audit, not fail-closed
    assert resp["result"]["_meta"]["zroky"]["decision"] == "observe"


def test_upstream_error_marks_execution_state_unknown():
    up = FakeUpstream(raise_on="create_refund")
    sink = RecordingSink()
    kernel = FakeKernel(KernelDecision(allowed=True, requires_approval=False, reasons=[], intent_id="i1"))
    resp = _call_sink("create_refund", {"amount": 600}, kernel, up, sink)
    assert resp["result"]["isError"] is True
    assert resp["result"]["_meta"]["zroky"]["execution_state"] == "unknown"
    assert sink.outcomes[0][1]["execution_state"] == "unknown"
    assert sink.outcomes[0][1]["forward_attempted"] is True


def test_unprotected_never_consults_kernel_even_when_down():
    # Stronger than fail-open: an unprotected read short-circuits to OBSERVE
    # before the kernel is ever consulted, so a dead policy engine cannot
    # touch read traffic at all.
    up = FakeUpstream()
    resp = _call("get_customer", {"id": "c1"}, ExplodingKernel(), up)
    assert up.called == [("get_customer", {"id": "c1"})]  # agent keeps working
    assert resp["result"]["_meta"]["zroky"]["decision"] == "observe"
    assert "degraded" not in resp["result"]["_meta"]["zroky"]
