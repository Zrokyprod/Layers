from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.api.routes import action_intents, tool_registry
from app.db.base import Base
from app.db.models import (
    ActionExecutionAttempt,
    ActionIntent,
    ActionReceipt,
    ActionRunner,
    ActionTimelineEvent,
    Project,
    RuntimePolicyDecision,
)
from app.db.session import get_db_session, get_db_session_read
from app.main import app
from app.services.entitlements import set_override_entitlement


def test_verified_action_public_routes_are_rate_limited() -> None:
    action_intents_source = inspect.getsource(action_intents)
    tool_registry_source = inspect.getsource(tool_registry)

    for limit in [
        '@limiter.limit("20/minute")',
        '@limiter.limit("120/minute")',
        '@limiter.limit("240/minute")',
    ]:
        assert limit in action_intents_source

    assert action_intents_source.count("@limiter.limit(") >= 7
    assert '@limiter.limit("120/minute")' in tool_registry_source


@pytest.fixture()
def client(tmp_path: Path):
    get_settings.cache_clear()
    db_path = tmp_path / "test_action_intents.db"
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
    with TestClient(app) as test_client:
        test_client._session_factory = factory  # type: ignore[attr-defined]
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    get_settings.cache_clear()


def _seed_project(client: TestClient, project_id: str) -> None:
    with client._session_factory() as session:  # type: ignore[attr-defined]
        session.add(Project(id=project_id, name=f"Project {project_id}", is_active=True))
        session.commit()


def _register_contract(client: TestClient, project_id: str) -> dict:
    response = client.post(
        "/v1/action-contracts",
        headers={"X-Project-Id": project_id},
        json={
            "contract_key": "customer.refund.transfer",
            "version": "1.0",
            "action_type": "customer.refund.transfer",
            "operation_kind": "TRANSFER",
            "domain_family": "customer_operations",
            "risk_class": "R3",
            "connector_family": "payment_refund",
            "schema": {
                "type": "object",
                "required": ["resource", "parameters"],
                "properties": {
                    "resource": {"type": "object"},
                    "parameters": {"type": "object"},
                },
            },
            "verification_profile": {
                "minimum_level": "V4",
                "positive_assertions": ["equals(amount_minor)", "equals(currency)"],
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _intent_payload(**overrides) -> dict:
    payload = {
        "contract_version": "customer.refund.transfer/1.0",
        "action_type": "customer.refund.transfer",
        "operation_kind": "TRANSFER",
        "environment": "production",
        "principal": {"type": "user", "id": "usr_123"},
        "actor_chain": [{"type": "agent", "id": "refund-agent", "version": "1.0.0"}],
        "purpose": {"code": "support_refund", "case_id": "case_123", "summary": "Refund customer after support approval"},
        "resource": {"type": "payment.refund", "id": "rf_123", "account": "stripe_prod"},
        "parameters": {"amount_minor": 50000, "currency": "USD"},
        "verification_profile": "payment.refund.finality/1.0",
        "trace_context": {"trace_id": "trace_123", "agent_name": "refund-agent"},
    }
    payload.update(overrides)
    return payload


def _refund_execution_plan(*, amount_minor: int = 50000) -> dict:
    return {
        "adapter": "stripe_refund",
        "operation": "refund.create",
        "target": {"refund_id": "rf_123"},
        "arguments": {"amount_minor": amount_minor, "currency": "USD"},
        "verification": {"source_of_record": "ledger_refund"},
    }


def _create_intent(
    client: TestClient,
    project_id: str,
    *,
    idempotency_key: str = "case_123_refund_1",
    **payload_overrides,
) -> dict:
    response = client.post(
        "/v1/action-intents",
        headers={"X-Project-Id": project_id, "Idempotency-Key": idempotency_key},
        json=_intent_payload(**payload_overrides),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _authorize_intent(client: TestClient, project_id: str, action_id: str) -> dict:
    pending = client.post(
        f"/v1/action-intents/{action_id}/decide",
        headers={"X-Project-Id": project_id},
    )
    assert pending.status_code == 200, pending.text
    approved = client.post(
        f"/v1/runtime-policy/approvals/{pending.json()['runtime_policy_decision_id']}/approve",
        headers={"X-Project-Id": project_id},
        json={"reason": "Source-of-record evidence reviewed."},
    )
    assert approved.status_code == 200, approved.text
    authorized = client.post(
        f"/v1/action-intents/{action_id}/decide",
        headers={"X-Project-Id": project_id},
    )
    assert authorized.status_code == 200, authorized.text
    assert authorized.json()["status"] == "authorized"
    return authorized.json()


def test_action_intent_create_is_digest_bound_and_idempotent(client: TestClient) -> None:
    project_id = "proj_action_kernel"
    _seed_project(client, project_id)
    contract = _register_contract(client, project_id)
    assert contract["schema_digest"].startswith("sha256:")
    assert contract["risk_class"] == "R3"

    payload = _intent_payload()

    first = client.post(
        "/v1/action-intents",
        headers={"X-Project-Id": project_id, "Idempotency-Key": "case_123_refund_1"},
        json=payload,
    )
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["contract_version"] == "customer.refund.transfer/1.0"
    assert body["status"] == "validated"
    assert body["intent_digest"].startswith("sha256:")
    assert body["canonical_intent"]["parameters"]["amount_minor"] == 50000
    assert body["runtime_policy_decision_id"] is None
    assert body["status_url"] == f"/v1/action-intents/{body['action_id']}"

    second = client.post(
        "/v1/action-intents",
        headers={"X-Project-Id": project_id, "Idempotency-Key": "case_123_refund_1"},
        json=payload,
    )
    assert second.status_code == 201
    assert second.json()["action_id"] == body["action_id"]
    assert second.json()["intent_digest"] == body["intent_digest"]


def test_protected_action_meters_lifecycle_usage(client: TestClient) -> None:
    project_id = "proj_action_billing_usage"
    _seed_project(client, project_id)
    _register_contract(client, project_id)
    intent = _create_intent(client, project_id)
    _authorize_intent(client, project_id, intent["action_id"])
    runner = client.post(
        "/v1/action-runners",
        headers={"X-Project-Id": project_id},
        json={
            "name": "billing-usage-runner",
            "runner_type": "customer_hosted",
            "environment": "production",
            "supported_operation_kinds": ["TRANSFER"],
        },
    )
    assert runner.status_code == 201, runner.text
    execution = client.post(
        f"/v1/action-intents/{intent['action_id']}/execution-attempts",
        headers={"X-Project-Id": project_id, "Idempotency-Key": "billing_exec_1"},
        json={
            "runner_id": runner.json()["runner_id"],
            "credential_ref": "customer-runner-secret://support/stripe-refund-prod",
            "execution_plan": _refund_execution_plan(),
        },
    )
    assert execution.status_code == 201, execution.text
    receipt = client.post(
        f"/v1/action-intents/{intent['action_id']}/receipt",
        headers={"X-Project-Id": project_id},
    )
    assert receipt.status_code == 201, receipt.text

    usage = client.get("/v1/billing/usage", headers={"X-Project-Id": project_id})
    assert usage.status_code == 200, usage.text
    body = usage.json()
    assert body["protected_actions"]["used"] == 1
    assert body["policy_checks"]["used"] == 2
    assert body["runner_executions"]["used"] == 1
    assert body["action_receipts"]["used"] == 1


def test_protected_action_quota_blocks_intent_creation(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = "proj_action_billing_blocked"
    monkeypatch.setenv("BILLING_ENFORCE_QUOTA", "true")
    get_settings.cache_clear()
    _seed_project(client, project_id)
    _register_contract(client, project_id)
    with client._session_factory() as session:  # type: ignore[attr-defined]
        set_override_entitlement(
            session,
            org_id=project_id,
            key="actions.protected.monthly_quota",
            value=0,
        )

    blocked = client.post(
        "/v1/action-intents",
        headers={"X-Project-Id": project_id, "Idempotency-Key": "quota_blocked"},
        json=_intent_payload(),
    )

    assert blocked.status_code == 402, blocked.text
    detail = blocked.json()["detail"]
    assert detail["code"] == "protected_action_quota_exceeded"
    assert detail["meter_key"] == "protected_actions"
    assert detail["entitlement_key"] == "actions.protected.monthly_quota"
    assert detail["used"] == 0
    assert detail["requested"] == 1
    assert detail["limit"] == 0


def test_action_pack_installs_launch_contracts_for_first_customer_flow(client: TestClient) -> None:
    project_id = "proj_action_pack_install"
    _seed_project(client, project_id)

    listed = client.get("/v1/action-packs", headers={"X-Project-Id": project_id})
    assert listed.status_code == 200
    packs = listed.json()["items"]
    assert [pack["id"] for pack in packs] == ["support-ops-v1", "devops-release-v1"]

    support_pack = client.get("/v1/action-packs/support-ops-v1", headers={"X-Project-Id": project_id})
    assert support_pack.status_code == 200
    assert support_pack.json()["contract_templates"][0]["contract_version"] == "customer.refund.transfer/1.0"

    installed = client.post("/v1/action-packs/support-ops-v1/install", headers={"X-Project-Id": project_id})
    assert installed.status_code == 201, installed.text
    installed_body = installed.json()
    assert installed_body["pack"]["id"] == "support-ops-v1"
    assert [item["contract"]["contract_version"] for item in installed_body["installed_contracts"]] == [
        "customer.refund.transfer/1.0",
        "customer.record.update/1.0",
    ]
    assert [item["created"] for item in installed_body["installed_contracts"]] == [True, True]
    assert installed_body["installed_contracts"][0]["contract"]["action_type"] == "refund"
    assert installed_body["installed_contracts"][0]["contract"]["connector_family"] == "ledger_refund"

    repeated = client.post("/v1/action-packs/support-ops-v1/install", headers={"X-Project-Id": project_id})
    assert repeated.status_code == 201
    assert [item["created"] for item in repeated.json()["installed_contracts"]] == [False, False]

    intent = client.post(
        "/v1/action-intents",
        headers={"X-Project-Id": project_id, "Idempotency-Key": "pack_refund_1"},
        json={
            "contract_version": "customer.refund.transfer/1.0",
            "action_type": "refund",
            "operation_kind": "TRANSFER",
            "principal": {"type": "agent", "id": "refund-agent"},
            "actor_chain": [{"type": "agent", "id": "refund-agent"}],
            "purpose": {"code": "customer_refund", "summary": "Refund customer with ledger proof"},
            "resource": {"refund_id": "rf_pack_123", "order_id": "ord_pack_123"},
            "parameters": {"amount_minor": 50000, "currency": "USD"},
            "verification_profile": "ledger_refund/v1",
        },
    )
    assert intent.status_code == 201, intent.text
    assert intent.json()["contract_version"] == "customer.refund.transfer/1.0"
    assert intent.json()["action_type"] == "refund"
    assert intent.json()["status"] == "validated"


def test_action_intent_rejects_idempotency_key_reuse_for_changed_intent(client: TestClient) -> None:
    project_id = "proj_action_kernel_conflict"
    _seed_project(client, project_id)
    _register_contract(client, project_id)

    payload = {
        "contract_version": "customer.refund.transfer/1.0",
        "action_type": "customer.refund.transfer",
        "operation_kind": "TRANSFER",
        "principal": {"type": "user", "id": "usr_123"},
        "actor_chain": [{"type": "agent", "id": "refund-agent"}],
        "resource": {"type": "payment.refund", "id": "rf_123"},
        "parameters": {"amount_minor": 50000, "currency": "USD"},
    }
    headers = {"X-Project-Id": project_id, "Idempotency-Key": "same_key"}
    assert client.post("/v1/action-intents", headers=headers, json=payload).status_code == 201

    changed = {**payload, "parameters": {"amount_minor": 75000, "currency": "USD"}}
    conflict = client.post("/v1/action-intents", headers=headers, json=changed)
    assert conflict.status_code == 409
    assert "different action intent" in conflict.json()["detail"]


def test_action_intent_requires_registered_contract_and_matching_action(client: TestClient) -> None:
    project_id = "proj_action_kernel_mismatch"
    _seed_project(client, project_id)
    _register_contract(client, project_id)

    unknown = client.post(
        "/v1/action-intents",
        headers={"X-Project-Id": project_id, "Idempotency-Key": "unknown_contract"},
        json={
            "contract_version": "crm.opportunity.stage.update/1.0",
            "action_type": "crm.opportunity.stage.update",
            "operation_kind": "UPDATE",
        },
    )
    assert unknown.status_code == 404

    mismatch = client.post(
        "/v1/action-intents",
        headers={"X-Project-Id": project_id, "Idempotency-Key": "mismatch"},
        json={
            "contract_version": "customer.refund.transfer/1.0",
            "action_type": "customer.refund.transfer",
            "operation_kind": "UPDATE",
        },
    )
    assert mismatch.status_code == 422
    assert "does not match" in mismatch.json()["detail"]


def test_action_intent_requires_idempotency_header(client: TestClient) -> None:
    project_id = "proj_action_kernel_idempotency"
    _seed_project(client, project_id)
    _register_contract(client, project_id)

    response = client.post(
        "/v1/action-intents",
        headers={"X-Project-Id": project_id},
        json={
            "contract_version": "customer.refund.transfer/1.0",
            "action_type": "customer.refund.transfer",
            "operation_kind": "TRANSFER",
        },
    )
    assert response.status_code == 400


def test_action_intent_decision_links_runtime_policy_approval(client: TestClient) -> None:
    project_id = "proj_action_kernel_policy_pending"
    _seed_project(client, project_id)
    _register_contract(client, project_id)
    intent = _create_intent(client, project_id)

    decided = client.post(
        f"/v1/action-intents/{intent['action_id']}/decide",
        headers={"X-Project-Id": project_id},
    )
    assert decided.status_code == 200, decided.text
    body = decided.json()
    assert body["status"] == "approval_pending"
    assert body["allowed"] is False
    assert body["requires_approval"] is True
    assert body["runtime_policy_decision_id"]
    assert body["reasons"] == ["sensitive action requires human approval before execution"]

    fetched = client.get(
        f"/v1/action-intents/{intent['action_id']}",
        headers={"X-Project-Id": project_id},
    )
    assert fetched.status_code == 200
    assert fetched.json()["runtime_policy_decision_id"] == body["runtime_policy_decision_id"]

    with client._session_factory() as session:  # type: ignore[attr-defined]
        row = session.get(ActionIntent, intent["action_id"])
        decision = session.get(RuntimePolicyDecision, body["runtime_policy_decision_id"])
        assert row.status == "approval_pending"
        assert row.runtime_policy_decision_id == decision.id
        assert decision.status == "pending_approval"
        assert decision.action_type == "customer.refund.transfer"


def test_high_value_action_intent_requires_dual_runtime_approval(client: TestClient) -> None:
    project_id = "proj_action_kernel_dual_approval"
    _seed_project(client, project_id)
    _register_contract(client, project_id)
    intent = _create_intent(
        client,
        project_id,
        idempotency_key="case_high_value_refund_1",
        purpose={
            "code": "support_refund",
            "case_id": "case_high_value",
            "summary": "High-value refund after support and finance review",
        },
        parameters={"amount_minor": 600000, "currency": "USD"},
        trace_context={"trace_id": "trace_high_value", "agent_name": "refund-agent"},
    )

    decided = client.post(
        f"/v1/action-intents/{intent['action_id']}/decide",
        headers={"X-Project-Id": project_id},
    )
    assert decided.status_code == 200, decided.text
    body = decided.json()
    assert body["status"] == "approval_pending"
    assert body["allowed"] is False
    assert body["requires_approval"] is True
    assert "dual-approval threshold" in " ".join(body["reasons"])

    with client._session_factory() as session:  # type: ignore[attr-defined]
        row = session.get(ActionIntent, intent["action_id"])
        decision = session.get(RuntimePolicyDecision, body["runtime_policy_decision_id"])
        assert row.status == "approval_pending"
        assert decision.status == "pending_approval"
        assert decision.required_approval_count == 2
        assert decision.approval_count == 0
        assert decision.approver_subjects_json == "[]"


def test_action_intent_authorizes_after_linked_runtime_approval(client: TestClient) -> None:
    project_id = "proj_action_kernel_policy_authorized"
    _seed_project(client, project_id)
    _register_contract(client, project_id)
    intent = _create_intent(client, project_id)
    pending = client.post(
        f"/v1/action-intents/{intent['action_id']}/decide",
        headers={"X-Project-Id": project_id},
    ).json()

    approved = client.post(
        f"/v1/runtime-policy/approvals/{pending['runtime_policy_decision_id']}/approve",
        headers={"X-Project-Id": project_id},
        json={"reason": "Refund reviewed against source-of-record evidence."},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"

    authorized = client.post(
        f"/v1/action-intents/{intent['action_id']}/decide",
        headers={"X-Project-Id": project_id},
    )
    assert authorized.status_code == 200, authorized.text
    body = authorized.json()
    assert body["status"] == "authorized"
    assert body["allowed"] is True
    assert body["requires_approval"] is False
    assert body["runtime_policy_decision_id"] != pending["runtime_policy_decision_id"]
    assert body["authorized_at"] is not None

    with client._session_factory() as session:  # type: ignore[attr-defined]
        pending_row = session.get(RuntimePolicyDecision, pending["runtime_policy_decision_id"])
        allowed_row = session.get(RuntimePolicyDecision, body["runtime_policy_decision_id"])
        assert pending_row.consumed_by_decision_id == allowed_row.id
        assert allowed_row.status == "allowed"


def test_action_intent_rejects_approval_bound_to_different_intent_digest(client: TestClient) -> None:
    project_id = "proj_action_kernel_wrong_approval_digest"
    _seed_project(client, project_id)
    _register_contract(client, project_id)
    first_intent = _create_intent(client, project_id, idempotency_key="case_123_refund_1")
    first_pending = client.post(
        f"/v1/action-intents/{first_intent['action_id']}/decide",
        headers={"X-Project-Id": project_id},
    ).json()

    approved = client.post(
        f"/v1/runtime-policy/approvals/{first_pending['runtime_policy_decision_id']}/approve",
        headers={"X-Project-Id": project_id},
        json={"reason": "First refund is approved only for its exact digest."},
    )
    assert approved.status_code == 200, approved.text

    second_intent = _create_intent(
        client,
        project_id,
        idempotency_key="case_456_refund_1",
        purpose={
            "code": "support_refund",
            "case_id": "case_456",
            "summary": "Refund a different customer after support approval",
        },
        resource={"type": "payment.refund", "id": "rf_456", "account": "stripe_prod"},
        parameters={"amount_minor": 70000, "currency": "USD"},
        trace_context={"trace_id": "trace_456", "agent_name": "refund-agent"},
    )
    assert second_intent["intent_digest"] != first_intent["intent_digest"]

    second_decision = client.post(
        f"/v1/action-intents/{second_intent['action_id']}/decide",
        headers={"X-Project-Id": project_id},
        json={"approval_id": first_pending["runtime_policy_decision_id"]},
    )
    assert second_decision.status_code == 200, second_decision.text
    body = second_decision.json()
    assert body["status"] == "approval_pending"
    assert body["allowed"] is False
    assert body["requires_approval"] is True
    assert body["runtime_policy_decision_id"] != first_pending["runtime_policy_decision_id"]

    with client._session_factory() as session:  # type: ignore[attr-defined]
        original_approval = session.get(RuntimePolicyDecision, first_pending["runtime_policy_decision_id"])
        second_row = session.get(ActionIntent, second_intent["action_id"])
        second_pending = session.get(RuntimePolicyDecision, body["runtime_policy_decision_id"])
        assert original_approval.status == "approved"
        assert original_approval.consumed_at is None
        assert original_approval.consumed_by_decision_id is None
        assert second_row.status == "approval_pending"
        assert second_row.runtime_policy_decision_id == second_pending.id
        assert second_pending.status == "pending_approval"


def test_action_intent_rejects_consumed_approval_reuse(client: TestClient) -> None:
    project_id = "proj_action_kernel_consumed_approval"
    _seed_project(client, project_id)
    _register_contract(client, project_id)
    first_intent = _create_intent(client, project_id, idempotency_key="case_123_refund_1")
    first_pending = client.post(
        f"/v1/action-intents/{first_intent['action_id']}/decide",
        headers={"X-Project-Id": project_id},
    ).json()

    approved = client.post(
        f"/v1/runtime-policy/approvals/{first_pending['runtime_policy_decision_id']}/approve",
        headers={"X-Project-Id": project_id},
        json={"reason": "Approve the first exact refund intent."},
    )
    assert approved.status_code == 200, approved.text
    first_authorized = client.post(
        f"/v1/action-intents/{first_intent['action_id']}/decide",
        headers={"X-Project-Id": project_id},
    )
    assert first_authorized.status_code == 200, first_authorized.text
    assert first_authorized.json()["status"] == "authorized"

    second_intent = _create_intent(client, project_id, idempotency_key="case_123_refund_duplicate")
    second_decision = client.post(
        f"/v1/action-intents/{second_intent['action_id']}/decide",
        headers={"X-Project-Id": project_id},
        json={"approval_id": first_pending["runtime_policy_decision_id"]},
    )
    assert second_decision.status_code == 200, second_decision.text
    body = second_decision.json()
    assert body["status"] == "approval_pending"
    assert body["allowed"] is False
    assert body["requires_approval"] is True
    assert body["runtime_policy_decision_id"] != first_pending["runtime_policy_decision_id"]
    assert body["runtime_policy_decision_id"] != first_authorized.json()["runtime_policy_decision_id"]

    with client._session_factory() as session:  # type: ignore[attr-defined]
        original_approval = session.get(RuntimePolicyDecision, first_pending["runtime_policy_decision_id"])
        second_row = session.get(ActionIntent, second_intent["action_id"])
        assert original_approval.status == "approved"
        assert original_approval.consumed_at is not None
        assert original_approval.consumed_by_decision_id == first_authorized.json()["runtime_policy_decision_id"]
        assert second_row.status == "approval_pending"
        assert second_row.runtime_policy_decision_id == body["runtime_policy_decision_id"]


def test_action_intent_denies_after_linked_runtime_rejection(client: TestClient) -> None:
    project_id = "proj_action_kernel_policy_denied"
    _seed_project(client, project_id)
    _register_contract(client, project_id)
    intent = _create_intent(client, project_id)
    pending = client.post(
        f"/v1/action-intents/{intent['action_id']}/decide",
        headers={"X-Project-Id": project_id},
    ).json()

    rejected = client.post(
        f"/v1/runtime-policy/approvals/{pending['runtime_policy_decision_id']}/reject",
        headers={"X-Project-Id": project_id},
        json={"reason": "Source-of-record refund evidence did not match."},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"

    denied = client.post(
        f"/v1/action-intents/{intent['action_id']}/decide",
        headers={"X-Project-Id": project_id},
    )
    assert denied.status_code == 200, denied.text
    body = denied.json()
    assert body["status"] == "denied"
    assert body["allowed"] is False
    assert body["requires_approval"] is False
    assert body["runtime_policy_decision_id"] == pending["runtime_policy_decision_id"]
    assert body["reasons"] == ["linked approval was rejected"]


def test_action_runner_registers_and_records_heartbeat(client: TestClient) -> None:
    project_id = "proj_action_runner_heartbeat"
    _seed_project(client, project_id)

    created = client.post(
        "/v1/action-runners",
        headers={"X-Project-Id": project_id},
        json={
            "name": "customer-ops-runner",
            "runner_type": "customer_hosted",
            "environment": "production",
            "supported_operation_kinds": ["TRANSFER", "UPDATE"],
            "credential_scope": {"allowed_prefixes": ["customer-runner-secret://support"]},
            "capability_version": "2026.06.26",
        },
    )
    assert created.status_code == 201, created.text
    runner = created.json()
    assert runner["runner_id"]
    assert runner["status"] == "registered"
    assert runner["supported_operation_kinds"] == ["TRANSFER", "UPDATE"]
    assert runner["credential_scope"]["allowed_prefixes"] == ["customer-runner-secret://support"]

    heartbeat = client.post(
        f"/v1/action-runners/{runner['runner_id']}/heartbeat",
        headers={"X-Project-Id": project_id},
        json={
            "status": "online",
            "heartbeat_payload": {"host_id": "runner-host-1", "queue_depth": 0},
            "supported_operation_kinds": ["TRANSFER"],
            "capability_version": "2026.06.26-p1",
        },
    )
    assert heartbeat.status_code == 200, heartbeat.text
    heartbeat_body = heartbeat.json()
    assert heartbeat_body["status"] == "online"
    assert heartbeat_body["last_heartbeat_at"] is not None
    assert heartbeat_body["heartbeat_payload"]["queue_depth"] == 0
    assert heartbeat_body["supported_operation_kinds"] == ["TRANSFER"]

    listed = client.get("/v1/action-runners", headers={"X-Project-Id": project_id})
    assert listed.status_code == 200
    assert listed.json()["items"][0]["runner_id"] == runner["runner_id"]

    with client._session_factory() as session:  # type: ignore[attr-defined]
        row = session.get(ActionRunner, runner["runner_id"])
        assert row.status == "online"
        assert row.last_heartbeat_at is not None


def test_execution_adapter_contracts_are_exposed(client: TestClient) -> None:
    project_id = "proj_execution_adapters"
    _seed_project(client, project_id)

    response = client.get("/v1/action-execution-adapters", headers={"X-Project-Id": project_id})

    assert response.status_code == 200, response.text
    adapters = {item["adapter"]: item for item in response.json()["items"]}
    assert {"stripe_refund", "razorpay_refund", "zendesk_ticket", "customer_message", "generic_rest"} <= set(adapters)
    assert adapters["stripe_refund"]["operation_kinds"] == ["TRANSFER"]
    assert adapters["stripe_refund"]["required_target_fields"] == ["refund_id"]
    assert adapters["stripe_refund"]["credential_boundary"] == "runner_resolves_credential_ref"
    assert adapters["stripe_refund"]["protected_credential_returned"] is False


def test_execution_attempt_requires_authorized_action_intent(client: TestClient) -> None:
    project_id = "proj_action_runner_requires_auth"
    _seed_project(client, project_id)
    _register_contract(client, project_id)
    intent = _create_intent(client, project_id)
    runner = client.post(
        "/v1/action-runners",
        headers={"X-Project-Id": project_id},
        json={
            "name": "managed-refund-runner",
            "runner_type": "managed_sandbox",
            "environment": "production",
            "supported_operation_kinds": ["TRANSFER"],
        },
    ).json()

    planned = client.post(
        f"/v1/action-intents/{intent['action_id']}/execution-attempts",
        headers={"X-Project-Id": project_id, "Idempotency-Key": "exec_refund_1"},
        json={
            "runner_id": runner["runner_id"],
            "credential_ref": "zroky-secret://payments/refund-runner",
            "execution_plan": _refund_execution_plan(),
        },
    )
    assert planned.status_code == 409
    assert "authorized before execution" in planned.json()["detail"]


def test_execution_attempt_is_plan_bound_idempotent_and_secret_safe(client: TestClient) -> None:
    project_id = "proj_action_runner_plan"
    _seed_project(client, project_id)
    _register_contract(client, project_id)
    intent = _create_intent(client, project_id)
    _authorize_intent(client, project_id, intent["action_id"])
    runner = client.post(
        "/v1/action-runners",
        headers={"X-Project-Id": project_id},
        json={
            "name": "customer-hosted-refund-runner",
            "runner_type": "customer_hosted",
            "environment": "production",
            "supported_operation_kinds": ["TRANSFER"],
            "credential_scope": {"provider": "stripe", "mode": "restricted_refund"},
        },
    ).json()

    payload = {
        "runner_id": runner["runner_id"],
        "credential_ref": "customer-runner-secret://support/stripe-refund-prod",
        "execution_plan": _refund_execution_plan(),
    }
    first = client.post(
        f"/v1/action-intents/{intent['action_id']}/execution-attempts",
        headers={"X-Project-Id": project_id, "Idempotency-Key": "exec_refund_1"},
        json=payload,
    )
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["status"] == "planned"
    assert body["attempt_number"] == 1
    assert body["plan_digest"].startswith("sha256:")
    assert body["execution_plan"]["intent_digest"] == intent["intent_digest"]
    assert body["execution_plan"]["credential_ref"] == "customer-runner-secret://support/stripe-refund-prod"
    stored_runner_plan = body["execution_plan"]["execution_plan"]
    assert stored_runner_plan["adapter"] == "stripe_refund"
    assert stored_runner_plan["verification"]["connector"] == "ledger_refund_api"
    assert stored_runner_plan["adapter_contract"]["required_result_fields"] == ["provider_ref", "status"]
    assert stored_runner_plan["adapter_contract"]["protected_credential_returned"] is False
    assert body["protected_credential_returned"] is False

    repeated = client.post(
        f"/v1/action-intents/{intent['action_id']}/execution-attempts",
        headers={"X-Project-Id": project_id, "Idempotency-Key": "exec_refund_1"},
        json=payload,
    )
    assert repeated.status_code == 201
    assert repeated.json()["attempt_id"] == body["attempt_id"]
    assert repeated.json()["plan_digest"] == body["plan_digest"]

    changed = {
        **payload,
        "execution_plan": _refund_execution_plan(amount_minor=75000),
    }
    conflict = client.post(
        f"/v1/action-intents/{intent['action_id']}/execution-attempts",
        headers={"X-Project-Id": project_id, "Idempotency-Key": "exec_refund_1"},
        json=changed,
    )
    assert conflict.status_code == 409
    assert "different execution plan" in conflict.json()["detail"]

    attempts = client.get(
        f"/v1/action-intents/{intent['action_id']}/execution-attempts",
        headers={"X-Project-Id": project_id},
    )
    assert attempts.status_code == 200
    assert [item["attempt_id"] for item in attempts.json()["items"]] == [body["attempt_id"]]

    with client._session_factory() as session:  # type: ignore[attr-defined]
        row = session.get(ActionExecutionAttempt, body["attempt_id"])
        assert row.protected_credential_returned is False
        assert row.credential_ref == "customer-runner-secret://support/stripe-refund-prod"


def test_execution_attempt_rejects_invalid_adapter_contract(client: TestClient) -> None:
    project_id = "proj_action_runner_adapter_contract"
    _seed_project(client, project_id)
    _register_contract(client, project_id)
    intent = _create_intent(client, project_id)
    _authorize_intent(client, project_id, intent["action_id"])
    runner = client.post(
        "/v1/action-runners",
        headers={"X-Project-Id": project_id},
        json={
            "name": "adapter-contract-runner",
            "runner_type": "managed_sandbox",
            "environment": "production",
            "supported_operation_kinds": ["TRANSFER"],
        },
    ).json()

    missing_adapter = client.post(
        f"/v1/action-intents/{intent['action_id']}/execution-attempts",
        headers={"X-Project-Id": project_id, "Idempotency-Key": "missing_adapter_exec"},
        json={
            "runner_id": runner["runner_id"],
            "credential_ref": "zroky-secret://payments/refund-runner",
            "execution_plan": {
                "operation": "refund.create",
                "target": {"refund_id": "rf_123"},
                "arguments": {"amount_minor": 50000, "currency": "USD"},
            },
        },
    )
    assert missing_adapter.status_code == 422
    assert "execution_plan.adapter is required" in missing_adapter.json()["detail"]

    wrong_adapter = client.post(
        f"/v1/action-intents/{intent['action_id']}/execution-attempts",
        headers={"X-Project-Id": project_id, "Idempotency-Key": "wrong_adapter_exec"},
        json={
            "runner_id": runner["runner_id"],
            "credential_ref": "zroky-secret://payments/refund-runner",
            "execution_plan": {
                "adapter": "zendesk_ticket",
                "operation": "ticket.update",
                "target": {"ticket_id": "zd_123"},
                "arguments": {"fields": {"status": "solved"}},
            },
        },
    )
    assert wrong_adapter.status_code == 422
    assert "does not support TRANSFER" in wrong_adapter.json()["detail"]

    secret_plan = _refund_execution_plan()
    secret_plan["arguments"]["api_key"] = "sk_live_should_not_be_here"
    secret_payload = client.post(
        f"/v1/action-intents/{intent['action_id']}/execution-attempts",
        headers={"X-Project-Id": project_id, "Idempotency-Key": "secret_plan_exec"},
        json={
            "runner_id": runner["runner_id"],
            "credential_ref": "zroky-secret://payments/refund-runner",
            "execution_plan": secret_plan,
        },
    )
    assert secret_payload.status_code == 422
    assert "raw secret material" in secret_payload.json()["detail"]


def test_execution_attempt_dispatch_start_and_finish_lifecycle(client: TestClient) -> None:
    project_id = "proj_action_runner_lifecycle"
    _seed_project(client, project_id)
    _register_contract(client, project_id)
    intent = _create_intent(client, project_id)
    _authorize_intent(client, project_id, intent["action_id"])
    runner = client.post(
        "/v1/action-runners",
        headers={"X-Project-Id": project_id},
        json={
            "name": "lifecycle-runner",
            "runner_type": "customer_hosted",
            "environment": "production",
            "supported_operation_kinds": ["TRANSFER"],
        },
    ).json()
    attempt = client.post(
        f"/v1/action-intents/{intent['action_id']}/execution-attempts",
        headers={"X-Project-Id": project_id, "Idempotency-Key": "lifecycle_exec_1"},
        json={
            "runner_id": runner["runner_id"],
            "credential_ref": "customer-runner-secret://support/stripe-refund-prod",
            "execution_plan": _refund_execution_plan(),
        },
    ).json()

    dispatched = client.post(
        f"/v1/action-intents/{intent['action_id']}/execution-attempts/{attempt['attempt_id']}/dispatch",
        headers={"X-Project-Id": project_id},
        json={"dispatch_metadata": {"queue": "protected-actions"}},
    )
    assert dispatched.status_code == 200, dispatched.text
    assert dispatched.json()["status"] == "dispatched"
    assert dispatched.json()["result_summary"]["dispatch"]["queue"] == "protected-actions"

    running = client.post(
        f"/v1/action-intents/{intent['action_id']}/execution-attempts/{attempt['attempt_id']}/start",
        headers={"X-Project-Id": project_id},
        json={"runner_metadata": {"runner_instance_id": "runner-1"}},
    )
    assert running.status_code == 200, running.text
    assert running.json()["status"] == "running"
    assert running.json()["started_at"] is not None

    finished = client.post(
        f"/v1/action-intents/{intent['action_id']}/execution-attempts/{attempt['attempt_id']}/finish",
        headers={"X-Project-Id": project_id},
        json={
            "final_status": "succeeded",
            "result_summary": {"provider_ref": "rf_live_123"},
        },
    )
    assert finished.status_code == 200, finished.text
    body = finished.json()
    assert body["status"] == "succeeded"
    assert body["finished_at"] is not None
    assert body["result_summary"]["provider_ref"] == "rf_live_123"
    assert body["protected_credential_returned"] is False

    invalid = client.post(
        f"/v1/action-intents/{intent['action_id']}/execution-attempts/{attempt['attempt_id']}/start",
        headers={"X-Project-Id": project_id},
        json={"runner_metadata": {"runner_instance_id": "runner-1"}},
    )
    assert invalid.status_code == 409

    timeline = client.get(
        f"/v1/action-intents/{intent['action_id']}/timeline",
        headers={"X-Project-Id": project_id},
    ).json()["items"]
    assert [item["event_type"] for item in timeline][-3:] == [
        "execution_dispatched",
        "execution_running",
        "execution_succeeded",
    ]


def test_runner_claims_next_execution_attempt(client: TestClient) -> None:
    project_id = "proj_action_runner_claim"
    _seed_project(client, project_id)
    _register_contract(client, project_id)
    intent = _create_intent(client, project_id)
    _authorize_intent(client, project_id, intent["action_id"])
    runner = client.post(
        "/v1/action-runners",
        headers={"X-Project-Id": project_id},
        json={
            "name": "claim-runner",
            "runner_type": "customer_hosted",
            "environment": "production",
            "supported_operation_kinds": ["TRANSFER"],
        },
    ).json()
    attempt = client.post(
        f"/v1/action-intents/{intent['action_id']}/execution-attempts",
        headers={"X-Project-Id": project_id, "Idempotency-Key": "claim_exec_1"},
        json={
            "runner_id": runner["runner_id"],
            "credential_ref": "customer-runner-secret://support/stripe-refund-prod",
            "execution_plan": _refund_execution_plan(),
        },
    ).json()

    claimed = client.post(
        f"/v1/action-runners/{runner['runner_id']}/execution-attempts/claim",
        headers={"X-Project-Id": project_id},
        json={"runner_metadata": {"runner_instance_id": "claim-runner-1"}},
    )
    assert claimed.status_code == 200, claimed.text
    body = claimed.json()
    assert body["attempt_id"] == attempt["attempt_id"]
    assert body["status"] == "running"
    assert body["result_summary"]["runner"]["claimed"] is True
    assert body["result_summary"]["runner"]["runner_instance_id"] == "claim-runner-1"
    assert body["protected_credential_returned"] is False

    empty = client.post(
        f"/v1/action-runners/{runner['runner_id']}/execution-attempts/claim",
        headers={"X-Project-Id": project_id},
        json={"runner_metadata": {"runner_instance_id": "claim-runner-1"}},
    )
    assert empty.status_code == 404


def test_execution_attempt_rejects_raw_credentials(client: TestClient) -> None:
    project_id = "proj_action_runner_secret_reject"
    _seed_project(client, project_id)
    _register_contract(client, project_id)
    intent = _create_intent(client, project_id)
    _authorize_intent(client, project_id, intent["action_id"])
    runner = client.post(
        "/v1/action-runners",
        headers={"X-Project-Id": project_id},
        json={
            "name": "secret-safe-runner",
            "runner_type": "managed_sandbox",
            "environment": "production",
            "supported_operation_kinds": ["TRANSFER"],
        },
    ).json()

    response = client.post(
        f"/v1/action-intents/{intent['action_id']}/execution-attempts",
        headers={"X-Project-Id": project_id, "Idempotency-Key": "raw_secret_exec"},
        json={
            "runner_id": runner["runner_id"],
            "credential_ref": "sk_live_raw_secret_value",
            "execution_plan": _refund_execution_plan(),
        },
    )
    assert response.status_code == 422
    assert "protected reference" in response.json()["detail"]


def test_action_timeline_and_signed_receipt_bind_kernel_policy_runner_and_evidence(client: TestClient) -> None:
    project_id = "proj_action_receipt"
    _seed_project(client, project_id)
    _register_contract(client, project_id)
    intent = _create_intent(client, project_id)
    _authorize_intent(client, project_id, intent["action_id"])
    runner = client.post(
        "/v1/action-runners",
        headers={"X-Project-Id": project_id},
        json={
            "name": "receipt-runner",
            "runner_type": "managed_sandbox",
            "environment": "production",
            "supported_operation_kinds": ["TRANSFER"],
        },
    ).json()
    attempt = client.post(
        f"/v1/action-intents/{intent['action_id']}/execution-attempts",
        headers={"X-Project-Id": project_id, "Idempotency-Key": "receipt_exec_1"},
        json={
            "runner_id": runner["runner_id"],
            "credential_ref": "zroky-secret://payments/refund-runner",
            "execution_plan": _refund_execution_plan(),
        },
    )
    assert attempt.status_code == 201, attempt.text

    timeline_before_receipt = client.get(
        f"/v1/action-intents/{intent['action_id']}/timeline",
        headers={"X-Project-Id": project_id},
    )
    assert timeline_before_receipt.status_code == 200
    assert [item["event_type"] for item in timeline_before_receipt.json()["items"]] == [
        "intent_created",
        "policy_decided",
        "policy_decided",
        "execution_planned",
    ]
    assert all(item["event_digest"].startswith("sha256:") for item in timeline_before_receipt.json()["items"])

    generated = client.post(
        f"/v1/action-intents/{intent['action_id']}/receipt",
        headers={"X-Project-Id": project_id},
    )
    assert generated.status_code == 201, generated.text
    receipt = generated.json()
    assert receipt["receipt_digest"].startswith("sha256:")
    assert receipt["signature_algorithm"] == "HMAC-SHA256"
    assert receipt["signature_valid"] is True
    assert receipt["receipt"]["final_status"] == "planned"
    assert receipt["receipt"]["intent"]["intent_digest"] == intent["intent_digest"]
    assert receipt["receipt"]["runner_execution"]["id"] == attempt.json()["attempt_id"]
    assert receipt["receipt"]["runner_execution"]["protected_credential_returned"] is False
    assert receipt["receipt"]["policy_decision"]["status"] == "allowed"
    assert receipt["receipt"]["evidence"]["evidence_hash"]
    assert receipt["receipt"]["signature"]["value"] == receipt["signature"]

    fetched = client.get(
        f"/v1/action-intents/{intent['action_id']}/receipt",
        headers={"X-Project-Id": project_id},
    )
    assert fetched.status_code == 200
    assert fetched.json()["receipt_digest"] == receipt["receipt_digest"]
    assert fetched.json()["signature_valid"] is True

    timeline_after_receipt = client.get(
        f"/v1/action-intents/{intent['action_id']}/timeline",
        headers={"X-Project-Id": project_id},
    )
    assert timeline_after_receipt.status_code == 200
    assert [item["event_type"] for item in timeline_after_receipt.json()["items"]][-1] == "receipt_generated"

    with client._session_factory() as session:  # type: ignore[attr-defined]
        receipt_row = session.get(ActionReceipt, receipt["receipt_id"])
        assert receipt_row.receipt_digest == receipt["receipt_digest"]
        timeline_rows = (
            session.query(ActionTimelineEvent)
            .filter(ActionTimelineEvent.project_id == project_id)
            .order_by(ActionTimelineEvent.created_at.asc())
            .all()
        )
        assert [row.event_type for row in timeline_rows][-1] == "receipt_generated"
