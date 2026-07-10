"""Integration tests for the production-dark MCP ingress (Slice 1).

These exercise the REAL stack — FastAPI route, tenant auth, a live SQLite
DB, and the real ``action_kernel`` policy path — with only the upstream MCP
server faked (via a dependency override, so no network). They prove Zroky
can sit in the agent's tool-call path safely:

  * flag off              → route inert (404)
  * path project vs auth  → mismatched project is rejected (403)
  * unprotected tool      → bypasses the kernel, forwards upstream
  * protected + allow     → forwards upstream
  * protected + withheld  → does NOT forward (approval required)
  * protected + no gate   → fail-CLOSED, does NOT forward
  * unprotected + no gate → still forwards (fail-open)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sqlalchemy import select

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import (
    ActionExecutionAttempt,
    ActionPostExecutionJob,
    ActionReceipt,
    McpInterceptionEvent,
    McpToolBinding,
    OutcomeReconciliationCheck,
    Project,
)
from app.db.session import get_db_session, get_db_session_read
from app.main import app
from app.mcp.routes import get_mcp_upstream
from app.services.action_post_execution import process_action_post_execution_jobs
from app.services.pilot import upsert_policy


class FakeUpstream:
    """Stand-in for the real upstream MCP server."""

    def __init__(self, raise_on: str | None = None, verification: dict | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self._raise_on = raise_on
        self.verification = verification

    def list_tools(self) -> list[dict]:
        return [{"name": "create_refund"}, {"name": "get_customer"}]

    def call_tool(self, name: str, arguments: dict) -> dict:
        if self._raise_on is not None and name == self._raise_on:
            raise RuntimeError("upstream boom")
        self.calls.append((name, arguments))
        result = {"content": [{"type": "text", "text": f"ran {name}"}], "isError": False}
        if self.verification is not None:
            result["_meta"] = {"zroky": {"verification": dict(self.verification)}}
        return result


@pytest.fixture()
def fake_upstream() -> FakeUpstream:
    return FakeUpstream()


@pytest.fixture()
def client(tmp_path: Path, fake_upstream: FakeUpstream, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MCP_INTERCEPTION_ENABLED", "true")
    get_settings.cache_clear()

    db_path = tmp_path / "test_mcp_ingress.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def override():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override
    app.dependency_overrides[get_db_session_read] = override
    app.dependency_overrides[get_mcp_upstream] = lambda: fake_upstream
    with TestClient(app) as test_client:
        test_client._session_factory = factory  # type: ignore[attr-defined]
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    get_settings.cache_clear()


# ── helpers ────────────────────────────────────────────────────────────────


def _seed_project(client: TestClient, project_id: str) -> None:
    with client._session_factory() as session:  # type: ignore[attr-defined]
        session.add(Project(id=project_id, name=f"Project {project_id}", is_active=True))
        session.commit()


def _register_contract(
    client: TestClient,
    project_id: str,
    *,
    action_type: str,
    operation_kind: str,
    contract_key: str | None = None,
) -> str:
    key = contract_key or f"{action_type}.contract"
    resp = client.post(
        "/v1/action-contracts",
        headers={"X-Project-Id": project_id},
        json={
            "contract_key": key,
            "version": "1.0",
            "action_type": action_type,
            "operation_kind": operation_kind,
            "domain_family": "mcp_ops",
            "risk_class": "R2",
            "connector_family": "generic_rest_api",
            "schema": {"type": "object", "properties": {}},
        },
    )
    assert resp.status_code == 201, resp.text
    return key


def _add_binding(client: TestClient, project_id: str, **kwargs) -> None:
    with client._session_factory() as session:  # type: ignore[attr-defined]
        session.add(McpToolBinding(project_id=project_id, **kwargs))
        session.commit()


def _events(client: TestClient, project_id: str) -> list[McpInterceptionEvent]:
    with client._session_factory() as session:  # type: ignore[attr-defined]
        return list(
            session.execute(
                select(McpInterceptionEvent).where(McpInterceptionEvent.project_id == project_id)
            ).scalars().all()
        )


def _set_sensitive_approval(client: TestClient, project_id: str, *, required: bool, tools: list[str] | None = None) -> None:
    payload: dict[str, object] = {"runtime_sensitive_actions_require_approval": required}
    if tools is not None:
        payload["runtime_sensitive_tools"] = tools
    with client._session_factory() as session:  # type: ignore[attr-defined]
        upsert_policy(session, project_id=project_id, payload=payload, updated_by="test")
        session.commit()


def _call(client: TestClient, project_id: str, tool: str, args: dict, *, auth_project: str | None = None) -> dict:
    return client.post(
        f"/v1/mcp/{project_id}",
        headers={"X-Project-Id": auth_project or project_id},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": args}},
    ).json()


def _zroky_meta(response: dict) -> dict:
    return response["result"]["_meta"]["zroky"]


# ── tests ──────────────────────────────────────────────────────────────────


def test_flag_off_route_is_inert(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    _seed_project(client, "proj_off")
    monkeypatch.setenv("MCP_INTERCEPTION_ENABLED", "false")
    get_settings.cache_clear()
    resp = client.post(
        "/v1/mcp/proj_off",
        headers={"X-Project-Id": "proj_off"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )
    assert resp.status_code == 404


def test_path_project_must_match_authorized_tenant(client: TestClient, fake_upstream: FakeUpstream):
    _seed_project(client, "proj_a")
    _seed_project(client, "proj_b")
    # Authorized as proj_b, but addressing proj_a in the path.
    resp = client.post(
        "/v1/mcp/proj_a",
        headers={"X-Project-Id": "proj_b"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )
    assert resp.status_code == 403
    assert fake_upstream.calls == []


def test_project_allowlist_keeps_non_canary_projects_inert(
    client: TestClient,
    fake_upstream: FakeUpstream,
    monkeypatch: pytest.MonkeyPatch,
):
    _seed_project(client, "proj_allowed")
    _seed_project(client, "proj_blocked")
    monkeypatch.setenv("MCP_INTERCEPTION_PROJECT_ALLOWLIST", "proj_allowed")
    get_settings.cache_clear()
    blocked = client.post(
        "/v1/mcp/proj_blocked",
        headers={"X-Project-Id": "proj_blocked"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )
    assert blocked.status_code == 404
    allowed = client.post(
        "/v1/mcp/proj_allowed",
        headers={"X-Project-Id": "proj_allowed"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )
    assert allowed.status_code == 200
    assert fake_upstream.calls == []


def test_unprotected_tool_bypasses_kernel_and_forwards(client: TestClient, fake_upstream: FakeUpstream):
    _seed_project(client, "proj_read")
    # No contract registered at all — an unprotected read must not need one.
    resp = _call(client, "proj_read", "get_customer", {"id": "c1"})
    assert fake_upstream.calls == [("get_customer", {"id": "c1"})]
    assert _zroky_meta(resp)["decision"] == "observe"


def test_protected_allow_forwards_upstream(client: TestClient, fake_upstream: FakeUpstream):
    project = "proj_allow"
    _seed_project(client, project)
    _register_contract(client, project, action_type="inventory_adjust", operation_kind="UPDATE")
    _set_sensitive_approval(client, project, required=False)  # nothing gated to approval
    resp = _call(client, project, "adjust_inventory", {"sku": "X", "delta": -1})
    assert fake_upstream.calls == [("adjust_inventory", {"sku": "X", "delta": -1})]
    meta = _zroky_meta(resp)
    assert meta["decision"] == "allow"
    assert meta["intent_id"]


def test_protected_withheld_does_not_forward(client: TestClient, fake_upstream: FakeUpstream):
    project = "proj_hold"
    _seed_project(client, project)
    _register_contract(client, project, action_type="refund", operation_kind="TRANSFER")
    _set_sensitive_approval(client, project, required=True, tools=["refund"])
    resp = _call(client, project, "create_refund", {"amount": 600})
    assert fake_upstream.calls == []  # policy withheld allow → never reached the SOR
    meta = _zroky_meta(resp)
    assert meta["decision"] == "hold"
    assert meta["approval_ref"]
    assert meta["remediation"] == {
        "reason_code": "approval_required",
        "retryable": False,
        "next_actions": [{"type": "await_approval", "approval_ref": meta["approval_ref"]}],
    }
    assert "reasons" not in meta


def test_protected_without_contract_fails_closed(client: TestClient, fake_upstream: FakeUpstream):
    project = "proj_nocontract"
    _seed_project(client, project)
    # 'create_refund' classifies as the protected 'refund' action, but no
    # contract is onboarded → the adapter raises → proxy fail-CLOSES.
    resp = _call(client, project, "create_refund", {"amount": 600})
    assert fake_upstream.calls == []
    meta = _zroky_meta(resp)
    assert resp["result"]["isError"] is True
    assert meta["decision"] == "deny"
    assert meta["fail"] == "closed"
    assert meta["remediation"] == {
        "reason_code": "gate_unavailable",
        "retryable": True,
        "retry_after_seconds": 30,
        "next_actions": [{"type": "retry_later"}],
    }


def test_unprotected_forwards_even_without_contract(client: TestClient, fake_upstream: FakeUpstream):
    # Fail-open sibling of the above: an unprotected read on an un-onboarded
    # project still works (the kernel is never consulted).
    project = "proj_readonly"
    _seed_project(client, project)
    resp = _call(client, project, "list_orders", {})
    assert fake_upstream.calls == [("list_orders", {})]
    assert _zroky_meta(resp)["decision"] == "observe"


def test_tools_list_passthrough_and_annotation(client: TestClient):
    _seed_project(client, "proj_list")
    resp = client.post(
        "/v1/mcp/proj_list",
        headers={"X-Project-Id": "proj_list"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    ).json()
    tools = {t["name"]: t["_meta"]["zroky"]["protected"] for t in resp["result"]["tools"]}
    assert tools == {"create_refund": True, "get_customer": False}


# ── Slice 1.5: idempotency semantics ────────────────────────────────────────


def _call_with_headers(client, project, tool, args, headers) -> dict:
    return client.post(
        f"/v1/mcp/{project}",
        headers={"X-Project-Id": project, **headers},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": args}},
    ).json()


def test_caller_idempotency_token_dedupes_to_same_intent(client: TestClient):
    project = "proj_idem"
    _seed_project(client, project)
    _register_contract(client, project, action_type="inventory_adjust", operation_kind="UPDATE")
    _set_sensitive_approval(client, project, required=False)
    r1 = _call_with_headers(client, project, "adjust_inventory", {"sku": "X"}, {"Idempotency-Key": "tok-1"})
    r2 = _call_with_headers(client, project, "adjust_inventory", {"sku": "X"}, {"Idempotency-Key": "tok-1"})
    assert _zroky_meta(r1)["intent_id"] == _zroky_meta(r2)["intent_id"]  # same logical action


def test_no_token_produces_distinct_intents(client: TestClient):
    project = "proj_noidem"
    _seed_project(client, project)
    _register_contract(client, project, action_type="inventory_adjust", operation_kind="UPDATE")
    _set_sensitive_approval(client, project, required=False)
    r1 = _call(client, project, "adjust_inventory", {"sku": "X"})
    r2 = _call(client, project, "adjust_inventory", {"sku": "X"})
    # No caller token → two identical calls are two DISTINCT actions (never
    # silently collapsed by an argument hash).
    assert _zroky_meta(r1)["intent_id"] != _zroky_meta(r2)["intent_id"]


def test_reused_idempotency_token_with_different_intent_is_specific_conflict(
    client: TestClient, fake_upstream: FakeUpstream
):
    project = "proj_idem_conflict"
    _seed_project(client, project)
    _register_contract(client, project, action_type="inventory_adjust", operation_kind="UPDATE")
    _set_sensitive_approval(client, project, required=False)
    first = _call_with_headers(
        client, project, "adjust_inventory", {"sku": "X"}, {"Idempotency-Key": "tok-conflict"}
    )
    second = _call_with_headers(
        client, project, "adjust_inventory", {"sku": "Y"}, {"Idempotency-Key": "tok-conflict"}
    )
    assert _zroky_meta(first)["decision"] == "allow"
    assert second["result"]["isError"] is True
    assert _zroky_meta(second)["reason"] == "idempotency_conflict"
    assert fake_upstream.calls == [("adjust_inventory", {"sku": "X"})]


# ── Slice 1.5: durable interception events ──────────────────────────────────


def test_allow_writes_durable_event(client: TestClient):
    project = "proj_evt_allow"
    _seed_project(client, project)
    _register_contract(client, project, action_type="inventory_adjust", operation_kind="UPDATE")
    _set_sensitive_approval(client, project, required=False)
    _call(client, project, "adjust_inventory", {"sku": "X"})
    events = _events(client, project)
    assert len(events) == 1
    assert events[0].decision == "allow"
    assert events[0].forward_attempted is True
    assert events[0].forward_succeeded is True
    assert events[0].execution_state == "succeeded"
    assert events[0].intent_id


def test_protected_allow_queues_async_receipt_and_worker_links_event(
    client: TestClient, fake_upstream: FakeUpstream
):
    project = "proj_mcp_receipt"
    _seed_project(client, project)
    _register_contract(client, project, action_type="inventory_adjust", operation_kind="UPDATE")
    _set_sensitive_approval(client, project, required=False)
    resp = _call(client, project, "adjust_inventory", {"sku": "X", "delta": -1})
    meta = _zroky_meta(resp)
    assert meta["decision"] == "allow"
    assert meta["post_execution_status"] == "queued"
    assert meta["receipt_status"] == "pending"
    assert meta["proof_status"] == "pending"
    assert "receipt_id" not in meta

    with client._session_factory() as session:  # type: ignore[attr-defined]
        assert session.query(ActionReceipt).filter_by(project_id=project).count() == 0
        attempt = session.query(ActionExecutionAttempt).filter_by(project_id=project).one()
        assert attempt.status == "succeeded"
        job = session.get(ActionPostExecutionJob, meta["post_execution_job_id"])
        assert job is not None
        assert job.job_type == "verify_outcome"
        assert job.status == "pending"

    event = _events(client, project)[0]
    assert event.action_receipt_id is None
    assert event.proof_status == "pending"

    with client._session_factory() as session:  # type: ignore[attr-defined]
        processed = process_action_post_execution_jobs(session, worker_id="test-mcp-worker", limit=5)
        assert processed["processed"] == 2
        receipt = session.query(ActionReceipt).filter_by(project_id=project).one()
        receipt_id = receipt.id
        receipt_digest = receipt.receipt_digest
        assert receipt.receipt_digest.startswith("sha256:")
        assert json.loads(receipt.receipt_json)["verification"]["status"] == "unverifiable"
        outcome = session.query(OutcomeReconciliationCheck).filter_by(project_id=project).one()
        assert outcome.verdict == "not_verified"

    event = _events(client, project)[0]
    assert event.action_receipt_id == receipt_id
    assert event.receipt_digest == receipt_digest
    assert event.proof_status == "not_verified"


def test_protected_allow_verifies_against_explicit_upstream_sor_hint(
    client: TestClient, fake_upstream: FakeUpstream
):
    project = "proj_mcp_verified"
    fake_upstream.verification = {
        "claimed": {"record_ref": "inv_1", "status": "completed"},
        "actual": {"record_ref": "inv_1", "status": "completed"},
        "match_fields": ["record_ref", "status"],
        "connector_type": "mcp_tool_result",
        "system_ref": "inventory:inv_1",
    }
    _seed_project(client, project)
    _register_contract(client, project, action_type="inventory_adjust", operation_kind="UPDATE")
    _set_sensitive_approval(client, project, required=False)
    resp = _call(client, project, "adjust_inventory", {"sku": "X", "delta": -1})
    meta = _zroky_meta(resp)
    assert meta["post_execution_status"] == "queued"
    assert meta["proof_status"] == "pending"
    assert meta["receipt_status"] == "pending"

    with client._session_factory() as session:  # type: ignore[attr-defined]
        assert session.query(ActionReceipt).filter_by(project_id=project).count() == 0
        processed = process_action_post_execution_jobs(session, worker_id="test-mcp-worker", limit=5)
        assert processed["processed"] == 2
        outcome = session.query(OutcomeReconciliationCheck).filter_by(project_id=project).one()
        assert outcome.verdict == "matched"
        receipt = session.query(ActionReceipt).filter_by(project_id=project).one()
        receipt_id = receipt.id
        assert json.loads(receipt.receipt_json)["verification"]["status"] == "verified"

    event = _events(client, project)[0]
    assert event.action_receipt_id == receipt_id
    assert event.proof_status == "matched"


def test_hold_writes_durable_event_even_though_blocked(client: TestClient):
    # Compliance: blocked/held attempts MUST be durably recorded, not just allows.
    project = "proj_evt_hold"
    _seed_project(client, project)
    _register_contract(client, project, action_type="refund", operation_kind="TRANSFER")
    _set_sensitive_approval(client, project, required=True, tools=["refund"])
    _call(client, project, "create_refund", {"amount": 600})
    events = _events(client, project)
    assert len(events) == 1
    assert events[0].decision == "hold"
    assert events[0].forward_attempted is False
    assert events[0].execution_state == "not_attempted"


# ── Slice 1.5: durable project tool bindings ────────────────────────────────


def test_binding_maps_arbitrary_tool_to_exact_contract(client: TestClient, fake_upstream: FakeUpstream):
    project = "proj_binding"
    _seed_project(client, project)
    key = _register_contract(
        client, project, action_type="account_status_change", operation_kind="UPDATE",
        contract_key="acme.account.suspend",
    )
    _set_sensitive_approval(client, project, required=False)
    # A tool name the heuristics would NOT recognise, pinned by durable config.
    _add_binding(
        client, project, tool_name="acme_suspend_account", action_type="account_status_change",
        contract_key=key, contract_version="1.0", protected=True,
    )
    resp = _call(client, project, "acme_suspend_account", {"account": "a1"})
    meta = _zroky_meta(resp)
    assert meta["decision"] == "allow"
    assert fake_upstream.calls == [("acme_suspend_account", {"account": "a1"})]
    assert _events(client, project)[0].binding_source == "exact"


def test_binding_fail_open_override_forwards_without_contract(client: TestClient, fake_upstream: FakeUpstream):
    project = "proj_binding_open"
    _seed_project(client, project)
    # Protected tool, NO contract, but the binding overrides posture to fail-open.
    _add_binding(
        client, project, tool_name="risky_tool", action_type="access_grant",
        protected=True, fail_posture="fail_open",
    )
    resp = _call(client, project, "risky_tool", {})
    assert fake_upstream.calls == [("risky_tool", {})]  # posture override → forwarded
    assert _zroky_meta(resp).get("degraded") is True


def test_binding_contract_key_divergent_action_type_fails_closed(client: TestClient, fake_upstream: FakeUpstream):
    project = "proj_divergent"
    _seed_project(client, project)
    # Contract exists for account_status_change...
    _register_contract(
        client, project, action_type="account_status_change", operation_kind="UPDATE",
        contract_key="acme.suspend",
    )
    # ...but the binding points that contract_key at a DIFFERENT action_type.
    _add_binding(
        client, project, tool_name="misconfigured_tool", action_type="access_grant",
        contract_key="acme.suspend", protected=True,
    )
    resp = _call(client, project, "misconfigured_tool", {})
    # action_type is enforced even with a pinned contract_key → no contract
    # resolves → fail-closed, no divergence between audit and execution.
    assert fake_upstream.calls == []
    assert resp["result"]["isError"] is True


# ── Slice 1.5: upstream error mapping ───────────────────────────────────────


@pytest.fixture()
def failing_upstream() -> FakeUpstream:
    return FakeUpstream(raise_on="get_customer")


def test_upstream_error_is_mapped_and_recorded(tmp_path: Path, failing_upstream: FakeUpstream, monkeypatch: pytest.MonkeyPatch):
    # Build a client wired to the failing upstream.
    monkeypatch.setenv("MCP_INTERCEPTION_ENABLED", "true")
    get_settings.cache_clear()
    engine = create_engine(f"sqlite:///{tmp_path/'e.db'}", connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def override():
        s = factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db_session] = override
    app.dependency_overrides[get_db_session_read] = override
    app.dependency_overrides[get_mcp_upstream] = lambda: failing_upstream
    try:
        with TestClient(app) as client:
            client._session_factory = factory  # type: ignore[attr-defined]
            _seed_project(client, "proj_up")
            resp = _call(client, "proj_up", "get_customer", {"id": "c1"})
            meta = _zroky_meta(resp)
            assert resp["result"]["isError"] is True
            assert meta["execution_state"] == "unknown"
            assert meta["remediation"] == {
                "reason_code": "execution_unknown",
                "retryable": False,
                "next_actions": [{"type": "check_execution_status"}],
            }
            assert "upstream_error" not in meta
            events = _events(client, "proj_up")
            assert events[0].forward_attempted is True
            assert events[0].forward_succeeded is False
            assert events[0].execution_state == "unknown"  # side-effect is NOT provably "not done"
            assert events[0].upstream_error == "upstream boom"
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        get_settings.cache_clear()
