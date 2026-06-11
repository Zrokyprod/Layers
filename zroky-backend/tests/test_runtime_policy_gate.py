from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.db.base import Base
from app.db.models import RuntimePolicyDecision, TraceSpan
from app.db.session import get_db_session, get_db_session_read
from app.main import app
from app.services.pilot import DEFAULT_POLICY, upsert_policy


@pytest.fixture()
def client(tmp_path: Path):
    db_path = tmp_path / "runtime_policy.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    state = {"tenant_id": "proj_runtime_a", "role": "admin", "subject": "user-runtime"}

    def override_tenant():
        return TenantContext(
            tenant_id=state["tenant_id"],
            role=state["role"],
            subject=state["subject"],
        )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_db_session_read] = override_db
    app.dependency_overrides[require_tenant_context] = override_tenant

    with TestClient(app) as test_client:
        test_client._session_factory = session_factory  # type: ignore[attr-defined]
        test_client._tenant_state = state  # type: ignore[attr-defined]
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _set_tenant(client: TestClient, *, tenant_id: str, role: str = "admin") -> None:
    client._tenant_state["tenant_id"] = tenant_id  # type: ignore[attr-defined]
    client._tenant_state["role"] = role  # type: ignore[attr-defined]


def _set_policy(client: TestClient, tenant_id: str, **overrides) -> None:
    session_factory = client._session_factory  # type: ignore[attr-defined]
    with session_factory() as session:
        payload = dict(DEFAULT_POLICY)
        payload.update(overrides)
        upsert_policy(session, project_id=tenant_id, payload=payload, updated_by="test")


def test_sensitive_action_requires_approval_and_is_visible_in_trace(client: TestClient) -> None:
    response = client.post(
        "/v1/runtime-policy/check",
        json={
            "trace_id": "trace-refund-1",
            "agent_name": "refund-agent",
            "action_type": "refund",
            "tool_name": "refund_payment",
            "tool_args": {"order_id": "ord_123"},
            "external_action": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["allowed"] is False
    assert body["requires_approval"] is True
    assert body["status"] == "pending_approval"
    assert body["approval_queue_item"]["id"] == body["id"]

    listed = client.get("/v1/runtime-policy/approvals")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["id"] == body["id"]
    listed_all = client.get("/v1/runtime-policy/approvals?status=all")
    assert listed_all.status_code == 200
    assert listed_all.json()["items"][0]["id"] == body["id"]

    session_factory = client._session_factory  # type: ignore[attr-defined]
    with session_factory() as session:
        span = session.execute(
            select(TraceSpan).where(
                TraceSpan.project_id == "proj_runtime_a",
                TraceSpan.trace_id == "trace-refund-1",
                TraceSpan.span_type == "policy",
            )
        ).scalar_one()
        assert "sensitive action requires human approval" in span.policy_json


def test_approved_sensitive_action_allows_followup_check(client: TestClient) -> None:
    pending = client.post(
        "/v1/runtime-policy/check",
        json={
            "trace_id": "trace-email-1",
            "action_type": "email",
            "tool_name": "send_email",
            "tool_args": {"template": "receipt"},
            "external_action": True,
        },
    ).json()

    approved = client.post(
        f"/v1/runtime-policy/approvals/{pending['id']}/approve",
        json={"reason": "Verified customer requested this receipt."},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    allowed = client.post(
        "/v1/runtime-policy/check",
        json={
            "trace_id": "trace-email-1",
            "action_type": "email",
            "tool_name": "send_email",
            "tool_args": {"template": "receipt"},
            "external_action": True,
            "approval_id": pending["id"],
        },
    )
    assert allowed.status_code == 200
    assert allowed.json()["allowed"] is True
    assert allowed.json()["status"] == "allowed"


def test_kill_switch_blocks_every_runtime_action(client: TestClient) -> None:
    kill = client.post("/v1/runtime-policy/kill-switch", json={"enabled": True})
    assert kill.status_code == 200
    assert kill.json()["enabled"] is True

    response = client.post(
        "/v1/runtime-policy/check",
        json={"trace_id": "trace-kill", "action_type": "search", "tool_name": "search_docs"},
    )
    assert response.status_code == 200
    assert response.json()["allowed"] is False
    assert response.json()["status"] == "blocked"
    assert "project kill switch is enabled" in response.json()["reasons"]


def test_limits_and_allowed_tools_block_before_execution(client: TestClient) -> None:
    _set_policy(
        client,
        "proj_runtime_a",
        runtime_allowed_tools=["safe_search"],
        runtime_max_tool_calls=2,
        runtime_max_retries=1,
        runtime_max_cost_usd=0.05,
    )

    response = client.post(
        "/v1/runtime-policy/check",
        json={
            "trace_id": "trace-limits",
            "action_type": "tool",
            "tool_name": "delete_user",
            "tool_call_count": 3,
            "retry_count": 2,
            "estimated_cost_usd": 0.25,
        },
    )

    assert response.status_code == 200
    reasons = " ".join(response.json()["reasons"])
    assert response.json()["status"] == "blocked"
    assert "not allowlisted" in reasons
    assert "tool call count" in reasons
    assert "retry count" in reasons
    assert "estimated action cost" in reasons


def test_pii_leak_to_external_action_is_blocked_and_masked(client: TestClient) -> None:
    response = client.post(
        "/v1/runtime-policy/check",
        json={
            "trace_id": "trace-pii",
            "action_type": "email",
            "tool_name": "send_email",
            "output_text": "Send receipt to customer alice@example.com",
            "external_action": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "blocked"
    assert "PII" in " ".join(body["reasons"])
    assert "alice@example.com" not in str(body["request"])


def test_approval_queue_is_project_scoped(client: TestClient) -> None:
    created = client.post(
        "/v1/runtime-policy/check",
        json={
            "trace_id": "trace-scope",
            "action_type": "refund",
            "tool_name": "refund_payment",
            "external_action": True,
        },
    )
    assert created.status_code == 200

    _set_tenant(client, tenant_id="proj_runtime_b")
    listed = client.get("/v1/runtime-policy/approvals")
    assert listed.status_code == 200
    assert listed.json()["items"] == []

    reject_foreign = client.post(
        f"/v1/runtime-policy/approvals/{created.json()['id']}/reject",
        json={"reason": "wrong project cannot reject"},
    )
    assert reject_foreign.status_code == 404

    session_factory = client._session_factory  # type: ignore[attr-defined]
    with session_factory() as session:
        decisions = session.execute(select(RuntimePolicyDecision)).scalars().all()
        assert len(decisions) == 1
        assert decisions[0].project_id == "proj_runtime_a"
