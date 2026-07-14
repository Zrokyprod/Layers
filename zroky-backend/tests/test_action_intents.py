from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.services.action_post_execution as action_post_execution_service
from app.core.config import get_settings
from app.api.routes import action_intents, tool_registry
from app.db.base import Base
from app.db.models import (
    ActionExecutionAttempt,
    ActionIntent,
    ActionPostExecutionJob,
    ActionReceipt,
    ActionRunner,
    ActionTimelineEvent,
    OutcomeReconciliationCheck,
    Project,
    RuntimePolicyDecision,
    SystemOfRecordConnectorConfig,
)
from app.db.session import get_db_session, get_db_session_read
from app.main import app
from app.services.action_post_execution import process_action_post_execution_jobs, sweep_stale_execution_attempts
from app.services.action_receipts import verify_receipt_json_with_public_key
from app.services.entitlements import set_override_entitlement
from app.services.outcome_reconciliation import SourceRecord
from app.services.pilot import upsert_policy
from app.services.system_of_record_connectors import GenericRestApiConnector


def _enable_sequence_risk(client: TestClient, project_id: str, *, ttl_minutes: int | None = None) -> None:
    payload: dict[str, object] = {"runtime_sequence_risk_enabled": True}
    if ttl_minutes is not None:
        payload["runtime_approval_ttl_minutes"] = ttl_minutes
    with client._session_factory() as session:  # type: ignore[attr-defined]
        upsert_policy(
            session,
            project_id=project_id,
            payload=payload,
            updated_by="test",
        )
        session.commit()


def _register_export_contract(client: TestClient, project_id: str) -> dict:
    # A deliberately NON-sensitive action: a lone export is allowed by the
    # single-action policy, so any escalation must come from the sequence rule.
    response = client.post(
        "/v1/action-contracts",
        headers={"X-Project-Id": project_id},
        json={
            "contract_key": "customer.records.export",
            "version": "1.0",
            "action_type": "customer.records.export",
            "operation_kind": "EXECUTE",
            "domain_family": "customer_operations",
            "risk_class": "R2",
            "connector_family": "generic_rest_api",
            "schema": {
                "type": "object",
                "required": ["resource", "parameters"],
                "properties": {
                    "resource": {"type": "object"},
                    "parameters": {"type": "object"},
                },
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _export_intent_payload(**overrides) -> dict:
    payload = {
        "contract_version": "customer.records.export/1.0",
        "action_type": "customer.records.export",
        "operation_kind": "EXECUTE",
        "environment": "production",
        "principal": {"type": "user", "id": "usr_777"},
        "actor_chain": [{"type": "agent", "id": "offboard-agent", "version": "1.0.0"}],
        "purpose": {"code": "offboarding", "case_id": "case_777", "summary": "Offboard departing employee"},
        "resource": {"type": "records.export", "id": "exp_1", "destination": "https://external.example.com/drop"},
        "parameters": {"scope": "all_customer_records"},
        "trace_context": {"trace_id": "trace_exfil_1", "agent_name": "offboard-agent"},
    }
    payload.update(overrides)
    return payload


def _decide(client: TestClient, project_id: str, action_id: str) -> dict:
    response = client.post(
        f"/v1/action-intents/{action_id}/decide",
        headers={"X-Project-Id": project_id},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_sequence_risk_escalates_repeated_external_export_when_enabled(client: TestClient) -> None:
    project_id = "proj_sequence_risk_on"
    _seed_project(client, project_id)
    _register_export_contract(client, project_id)
    _enable_sequence_risk(client, project_id, ttl_minutes=7)

    # First external export in the run: no prior data-gathering step, so the
    # single-action policy allows it outright.
    first = _create_intent(
        client,
        project_id,
        idempotency_key="export_1",
        **_export_intent_payload(),
    )
    first_decision = _decide(client, project_id, first["action_id"])
    assert first_decision["status"] == "authorized", first_decision

    # Second external export in the SAME run completes an exfiltration shape
    # (collect-then-send-out). The sequence rule must escalate it to approval
    # even though the identical action was just allowed.
    second = _create_intent(
        client,
        project_id,
        idempotency_key="export_2",
        **_export_intent_payload(),
    )
    second_decision = _decide(client, project_id, second["action_id"])
    assert second_decision["status"] == "approval_pending", second_decision

    decision_id = second_decision["runtime_policy_decision_id"]
    with client._session_factory() as session:  # type: ignore[attr-defined]
        row = session.get(RuntimePolicyDecision, decision_id)
        assert row is not None
        assert row.decision == "requires_approval"
        assert row.status == "pending_approval"
        assert "sequence risk" in row.reasons_json
        assert "sequence_risk" in (row.policy_hit_json or "")
        assert row.expires_at is not None
        assert row.created_at is not None
        assert 6 * 60 <= (row.expires_at - row.created_at).total_seconds() <= 8 * 60


def test_sequence_risk_is_off_by_default(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # Same scenario, flag NOT enabled: both exports stay allowed. Proves the
    # escalation is strictly opt-in and does not change default behavior.
    project_id = "proj_sequence_risk_off"
    _seed_project(client, project_id)
    _register_export_contract(client, project_id)

    def _fail_sequence_scan(*args, **kwargs):
        raise AssertionError("sequence detector should not run when the policy flag is off")

    monkeypatch.setattr("app.services.action_kernel.evaluate_sequence_risk", _fail_sequence_scan)

    first = _create_intent(client, project_id, idempotency_key="export_1", **_export_intent_payload())
    assert _decide(client, project_id, first["action_id"])["status"] == "authorized"

    second = _create_intent(client, project_id, idempotency_key="export_2", **_export_intent_payload())
    assert _decide(client, project_id, second["action_id"])["status"] == "authorized"


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


def test_planned_verifier_labels_alias_to_generic_rest_connector() -> None:
    for label in ["ticket_status", "email_delivery", "github_ci", "webhook_callback"]:
        assert action_post_execution_service._connector_alias(label) == "generic_rest_api"


def test_action_contract_rejects_invalid_operation_kind_before_db(client: TestClient) -> None:
    project_id = "proj_invalid_operation_kind"
    _seed_project(client, project_id)

    response = client.post(
        "/v1/action-contracts",
        headers={"X-Project-Id": project_id},
        json={
            "contract_key": "bad.operation.kind",
            "version": "1.0",
            "action_type": "bad.operation.kind",
            "operation_kind": "WIRE_MONEY",
            "domain_family": "payments",
            "risk_class": "R2",
            "schema": {"type": "object"},
        },
    )

    assert response.status_code == 422, response.text
    assert "operation_kind" in response.text


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


def _create_agent_profile(
    client: TestClient,
    project_id: str,
    *,
    display_name: str = "Inventory Agent",
    environment: str = "production",
) -> dict:
    response = client.post(
        "/v1/agents",
        headers={"X-Project-Id": project_id},
        json={
            "display_name": display_name,
            "runtime_path": "sdk",
            "environment": environment,
            "framework": "langgraph",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


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


def _register_inventory_contract(
    client: TestClient,
    project_id: str,
    *,
    action_type: str = "inventory.item.update",
) -> dict:
    response = client.post(
        "/v1/action-contracts",
        headers={"X-Project-Id": project_id},
        json={
            "contract_key": action_type,
            "version": "1.0",
            "action_type": action_type,
            "operation_kind": "UPDATE",
            "domain_family": "inventory_operations",
            "risk_class": "R3",
            "connector_family": "generic_rest",
            "schema": {
                "type": "object",
                "required": ["resource", "parameters"],
                "properties": {
                    "resource": {"type": "object"},
                    "parameters": {"type": "object"},
                },
            },
            "verification_profile": {"minimum_level": "V3", "source_of_record": "generic_rest_api"},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _inventory_intent_payload(*, action_type: str = "inventory.item.update", **overrides) -> dict:
    payload = {
        "contract_version": f"{action_type}/1.0",
        "action_type": action_type,
        "operation_kind": "UPDATE",
        "environment": "production",
        "principal": {"type": "agent", "id": "inventory-agent"},
        "actor_chain": [{"type": "agent", "id": "inventory-agent", "version": "1.0.0"}],
        "purpose": {"code": "inventory_update", "summary": "Update inventory item through controlled path"},
        "resource": {"type": "inventory_item", "id": "item_123", "sku": "SKU-123"},
        "parameters": {"fields": {"status": "active"}},
        "trace_context": {"trace_id": "trace_inventory_123", "agent_name": "inventory-agent"},
    }
    payload.update(overrides)
    return payload


def _generic_rest_execution_request(*, credential_pointer: str | None = "ops-default") -> dict:
    request = {
        "capability": {
            "adapter": "generic_rest",
            "operation": "rest.patch",
            "operation_kind": "UPDATE",
        },
        "execution_plan": {
            "adapter": "generic_rest",
            "operation": "rest.patch",
            "target": {"resource_ref": "item_123"},
            "arguments": {"fields": {"status": "active"}},
            "verification": {
                "connector": "generic_rest_api",
                "record_ref": "item_123",
                "claimed": {"record_ref": "item_123", "status": "active"},
                "match_fields": ["record_ref", "status"],
            },
        },
    }
    if credential_pointer is not None:
        request["credential_pointer"] = credential_pointer
    return request


def _register_auto_runner(client: TestClient, project_id: str, *, name: str = "inventory-runner") -> dict:
    response = client.post(
        "/v1/action-runners",
        headers={"X-Project-Id": project_id},
        json={
            "name": name,
            "runner_type": "customer_hosted",
            "environment": "production",
            "supported_operation_kinds": ["UPDATE"],
            "credential_scope": {
                "allowed_prefixes": ["customer-runner-secret://ops"],
                "default_credential_ref": "customer-runner-secret://ops/default",
                "credential_refs": {"ops-default": "customer-runner-secret://ops/default"},
            },
            "capability_version": "manual-smoke.v1",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


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


def test_action_contract_list_is_active_and_project_scoped(client: TestClient) -> None:
    project_id = "proj_action_contract_catalog"
    other_project_id = "proj_action_contract_catalog_other"
    _seed_project(client, project_id)
    _seed_project(client, other_project_id)
    expected = _register_contract(client, project_id)
    _register_contract(client, other_project_id)

    listed = client.get(
        "/v1/action-contracts",
        headers={"X-Project-Id": project_id},
    )

    assert listed.status_code == 200, listed.text
    assert listed.json()["total_in_page"] == 1
    assert [item["id"] for item in listed.json()["items"]] == [expected["id"]]
    assert listed.json()["items"][0]["contract_version"] == "customer.refund.transfer/1.0"


def test_action_intent_list_filters_and_paginates(client: TestClient) -> None:
    project_id = "proj_action_kernel_list"
    _seed_project(client, project_id)
    _register_contract(client, project_id)
    first = _create_intent(client, project_id, idempotency_key="list_refund_1")
    second = _create_intent(
        client,
        project_id,
        idempotency_key="list_refund_2",
        resource={"type": "payment.refund", "id": "rf_456", "account": "stripe_prod"},
        trace_context={"trace_id": "trace_list_2", "agent_name": "refund-agent"},
    )
    decided = client.post(
        f"/v1/action-intents/{first['action_id']}/decide",
        headers={"X-Project-Id": project_id},
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "approval_pending"

    listed = client.get("/v1/action-intents", headers={"X-Project-Id": project_id})
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["total_in_page"] == 2
    assert body["limit"] == 50
    assert body["offset"] == 0
    assert {item["action_id"] for item in body["items"]} == {first["action_id"], second["action_id"]}

    approval_pending = client.get(
        "/v1/action-intents",
        headers={"X-Project-Id": project_id},
        params={"status": "approval_pending"},
    )
    assert approval_pending.status_code == 200, approval_pending.text
    assert [item["action_id"] for item in approval_pending.json()["items"]] == [first["action_id"]]

    validated = client.get(
        "/v1/action-intents",
        headers={"X-Project-Id": project_id},
        params={"status": "validated", "proof_status": "not_started", "receipt_status": "missing"},
    )
    assert validated.status_code == 200, validated.text
    assert [item["action_id"] for item in validated.json()["items"]] == [second["action_id"]]

    paged = client.get(
        "/v1/action-intents",
        headers={"X-Project-Id": project_id},
        params={"limit": 1, "offset": 1},
    )
    assert paged.status_code == 200, paged.text
    assert paged.json()["total_in_page"] == 1

    invalid = client.get(
        "/v1/action-intents",
        headers={"X-Project-Id": project_id},
        params={"proof_status": "unverifiable"},
    )
    assert invalid.status_code == 422


def test_action_intent_binds_active_agent_profile(client: TestClient) -> None:
    project_id = "proj_action_agent_binding"
    _seed_project(client, project_id)
    _register_inventory_contract(client, project_id)
    agent = _create_agent_profile(client, project_id, display_name="Inventory Agent")

    created = client.post(
        "/v1/action-intents",
        headers={"X-Project-Id": project_id, "Idempotency-Key": "inventory_agent_bound"},
        json=_inventory_intent_payload(
            agent_id=agent["id"],
            trace_context={"trace_id": "trace_bound", "agent_name": "inventory-agent"},
        ),
    )

    assert created.status_code == 201, created.text
    body = created.json()
    assert body["agent_id"] == agent["id"]
    assert body["agent_profile"] == {
        "id": agent["id"],
        "display_name": "Inventory Agent",
        "slug": "inventory-agent",
        "runtime_path": "sdk",
        "environment": "production",
    }
    assert body["canonical_intent"]["agent_id"] == agent["id"]
    with client._session_factory() as session:  # type: ignore[attr-defined]
        row = session.get(ActionIntent, body["action_id"])
        assert row is not None
        assert row.agent_id == agent["id"]


def test_action_intent_rejects_agent_identity_mismatch(client: TestClient) -> None:
    project_id = "proj_action_agent_mismatch"
    _seed_project(client, project_id)
    _register_inventory_contract(client, project_id)
    agent = _create_agent_profile(client, project_id, display_name="Inventory Agent")

    created = client.post(
        "/v1/action-intents",
        headers={"X-Project-Id": project_id, "Idempotency-Key": "inventory_agent_mismatch"},
        json=_inventory_intent_payload(
            agent_id=agent["id"],
            trace_context={"trace_id": "trace_mismatch", "agent_name": "manual-ops-agent"},
        ),
    )

    assert created.status_code == 422, created.text
    assert "agent_id does not match" in created.json()["detail"]


def test_action_intent_list_filters_by_bound_agent_id(client: TestClient) -> None:
    project_id = "proj_action_agent_filter"
    _seed_project(client, project_id)
    _register_inventory_contract(client, project_id)
    agent = _create_agent_profile(client, project_id, display_name="Inventory Agent")

    bound = client.post(
        "/v1/action-intents",
        headers={"X-Project-Id": project_id, "Idempotency-Key": "inventory_agent_filter_bound"},
        json=_inventory_intent_payload(
            agent_id=agent["id"],
            trace_context={"trace_id": "trace_filter_bound", "agent_name": "inventory-agent"},
        ),
    )
    assert bound.status_code == 201, bound.text
    unbound = client.post(
        "/v1/action-intents",
        headers={"X-Project-Id": project_id, "Idempotency-Key": "inventory_agent_filter_unbound"},
        json=_inventory_intent_payload(
            trace_context={"trace_id": "trace_filter_unbound", "agent_name": "inventory-agent"}
        ),
    )
    assert unbound.status_code == 201, unbound.text

    listed = client.get(
        "/v1/action-intents",
        headers={"X-Project-Id": project_id},
        params={"agent_id": agent["id"]},
    )

    assert listed.status_code == 200, listed.text
    assert [item["action_id"] for item in listed.json()["items"]] == [bound.json()["action_id"]]


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
    assert [pack["id"] for pack in packs] == [
        "support-ops-v1",
        "devops-release-v1",
        "ecommerce-ops-v1",
        "finance-ops-v1",
        "outreach-ops-v1",
        "data-ops-v1",
    ]
    assert all(pack["quickstart_steps"] for pack in packs)

    support_pack = client.get("/v1/action-packs/support-ops-v1", headers={"X-Project-Id": project_id})
    assert support_pack.status_code == 200
    support_contracts = {
        item["contract_version"]: item for item in support_pack.json()["contract_templates"]
    }
    assert "customer.refund.transfer/1.0" in support_contracts
    assert "customer.access.grant/1.0" in support_contracts
    assert "support.ticket.close/1.0" in support_contracts
    assert "customer.message.send/1.0" in support_contracts
    assert "customer.data.export/1.0" in support_contracts

    installed = client.post("/v1/action-packs/support-ops-v1/install", headers={"X-Project-Id": project_id})
    assert installed.status_code == 201, installed.text
    installed_body = installed.json()
    assert installed_body["pack"]["id"] == "support-ops-v1"
    installed_versions = [item["contract"]["contract_version"] for item in installed_body["installed_contracts"]]
    assert "customer.refund.transfer/1.0" in installed_versions
    assert "customer.access.grant/1.0" in installed_versions
    assert "support.ticket.close/1.0" in installed_versions
    assert "customer.message.send/1.0" in installed_versions
    assert "customer.data.export/1.0" in installed_versions
    assert len(installed_versions) >= 18
    assert all(item["created"] for item in installed_body["installed_contracts"])
    assert installed_body["installed_contracts"][0]["contract"]["action_type"] == "refund"
    assert installed_body["installed_contracts"][0]["contract"]["connector_family"] == "ledger_refund"

    repeated = client.post("/v1/action-packs/support-ops-v1/install", headers={"X-Project-Id": project_id})
    assert repeated.status_code == 201
    assert all(not item["created"] for item in repeated.json()["installed_contracts"])

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


def test_ecommerce_ops_pack_installs_three_contracts(client: TestClient) -> None:
    project_id = "proj_ecommerce_pack_install"
    _seed_project(client, project_id)

    pack = client.get("/v1/action-packs/ecommerce-ops-v1", headers={"X-Project-Id": project_id})
    assert pack.status_code == 200, pack.text
    assert pack.json()["id"] == "ecommerce-ops-v1"
    assert "shopify_admin" in pack.json()["native_tool_families"]
    assert pack.json()["quickstart_steps"] == [
        "Install ecommerce-ops-v1 for the tenant.",
        "Configure Shopify Admin or commerce source-of-record connector.",
        "Call protect() before order cancel, inventory adjust, or discount issue.",
        "Verify order/customer/inventory state before marking outcome verified.",
    ]
    assert [tpl["contract_version"] for tpl in pack.json()["contract_templates"]] == [
        "commerce.order.cancel/1.0",
        "commerce.inventory.adjust/1.0",
        "commerce.discount.issue/1.0",
    ]

    installed = client.post("/v1/action-packs/ecommerce-ops-v1/install", headers={"X-Project-Id": project_id})
    assert installed.status_code == 201, installed.text
    body = installed.json()
    assert body["pack"]["id"] == "ecommerce-ops-v1"
    assert [item["contract"]["contract_version"] for item in body["installed_contracts"]] == [
        "commerce.order.cancel/1.0",
        "commerce.inventory.adjust/1.0",
        "commerce.discount.issue/1.0",
    ]
    assert [item["created"] for item in body["installed_contracts"]] == [True, True, True]
    assert [item["contract"]["action_type"] for item in body["installed_contracts"]] == [
        "order_cancel",
        "inventory_adjust",
        "discount_issue",
    ]

    # Reinstall is idempotent — no duplicate contracts.
    repeated = client.post("/v1/action-packs/ecommerce-ops-v1/install", headers={"X-Project-Id": project_id})
    assert repeated.status_code == 201
    assert [item["created"] for item in repeated.json()["installed_contracts"]] == [False, False, False]

    # A discount action intent validates against the installed contract.
    intent = client.post(
        "/v1/action-intents",
        headers={"X-Project-Id": project_id, "Idempotency-Key": "ecom_discount_1"},
        json={
            "contract_version": "commerce.discount.issue/1.0",
            "action_type": "discount_issue",
            "operation_kind": "TRANSFER",
            "principal": {"type": "agent", "id": "commerce-agent"},
            "actor_chain": [{"type": "agent", "id": "commerce-agent"}],
            "purpose": {"code": "loyalty_discount", "summary": "Issue store credit with proof"},
            "resource": {"customer_id": "cus_ecom_1", "order_id": "ord_ecom_1"},
            "parameters": {"amount_minor": 1500, "currency": "USD", "code": "WELCOME15"},
            "verification_profile": "commerce_platform/v1",
        },
    )
    assert intent.status_code == 201, intent.text
    assert intent.json()["contract_version"] == "commerce.discount.issue/1.0"
    assert intent.json()["status"] == "validated"


def test_finance_ops_pack_installs_three_contracts(client: TestClient) -> None:
    project_id = "proj_finance_pack_install"
    _seed_project(client, project_id)

    pack = client.get("/v1/action-packs/finance-ops-v1", headers={"X-Project-Id": project_id})
    assert pack.status_code == 200, pack.text
    assert pack.json()["id"] == "finance-ops-v1"
    assert "stripe_payment" in pack.json()["native_tool_families"]
    assert pack.json()["quickstart_steps"] == [
        "Install finance-ops-v1 for the tenant.",
        "Configure NetSuite, ledger, or payment source-of-record connector.",
        "Call protect() before invoice approval, journal entry, or vendor payout.",
        "Verify finance record state and payment reference before closing evidence.",
    ]
    assert [tpl["contract_version"] for tpl in pack.json()["contract_templates"]] == [
        "finance.invoice.approve/1.0",
        "finance.journal.entry/1.0",
        "finance.vendor.payout/1.0",
    ]

    installed = client.post("/v1/action-packs/finance-ops-v1/install", headers={"X-Project-Id": project_id})
    assert installed.status_code == 201, installed.text
    body = installed.json()
    assert body["pack"]["id"] == "finance-ops-v1"
    assert [item["contract"]["contract_version"] for item in body["installed_contracts"]] == [
        "finance.invoice.approve/1.0",
        "finance.journal.entry/1.0",
        "finance.vendor.payout/1.0",
    ]
    assert [item["created"] for item in body["installed_contracts"]] == [True, True, True]
    assert [item["contract"]["action_type"] for item in body["installed_contracts"]] == [
        "invoice_approve",
        "journal_entry",
        "vendor_payout",
    ]

    # Reinstall is idempotent — no duplicate contracts.
    repeated = client.post("/v1/action-packs/finance-ops-v1/install", headers={"X-Project-Id": project_id})
    assert repeated.status_code == 201
    assert [item["created"] for item in repeated.json()["installed_contracts"]] == [False, False, False]

    # A vendor payout intent validates against the installed contract.
    intent = client.post(
        "/v1/action-intents",
        headers={"X-Project-Id": project_id, "Idempotency-Key": "fin_payout_1"},
        json={
            "contract_version": "finance.vendor.payout/1.0",
            "action_type": "vendor_payout",
            "operation_kind": "TRANSFER",
            "principal": {"type": "agent", "id": "finance-agent"},
            "actor_chain": [{"type": "agent", "id": "finance-agent"}],
            "purpose": {"code": "vendor_settlement", "summary": "Pay vendor with ledger proof"},
            "resource": {"vendor_id": "ven_fin_1", "invoice_id": "inv_fin_1"},
            "parameters": {"amount_minor": 250000, "currency": "USD", "reference": "PO-9931"},
            "verification_profile": "payments_ledger/v1",
        },
    )
    assert intent.status_code == 201, intent.text
    assert intent.json()["contract_version"] == "finance.vendor.payout/1.0"
    assert intent.json()["status"] == "validated"


def test_outreach_ops_pack_installs_three_contracts(client: TestClient) -> None:
    project_id = "proj_outreach_pack_install"
    _seed_project(client, project_id)

    pack = client.get("/v1/action-packs/outreach-ops-v1", headers={"X-Project-Id": project_id})
    assert pack.status_code == 200, pack.text
    assert pack.json()["id"] == "outreach-ops-v1"
    assert pack.json()["quickstart_steps"] == [
        "Install outreach-ops-v1 for the tenant.",
        "Configure email delivery or sales-engagement source-of-record connector.",
        "Call protect() before email send, sequence enrollment, or campaign launch.",
        "Verify recipient, campaign, and delivery state before evidence publish.",
    ]
    assert [tpl["contract_version"] for tpl in pack.json()["contract_templates"]] == [
        "outreach.email.send/1.0",
        "outreach.sequence.enroll/1.0",
        "outreach.campaign.launch/1.0",
    ]

    installed = client.post("/v1/action-packs/outreach-ops-v1/install", headers={"X-Project-Id": project_id})
    assert installed.status_code == 201, installed.text
    body = installed.json()
    assert body["pack"]["id"] == "outreach-ops-v1"
    assert [item["contract"]["contract_version"] for item in body["installed_contracts"]] == [
        "outreach.email.send/1.0",
        "outreach.sequence.enroll/1.0",
        "outreach.campaign.launch/1.0",
    ]
    assert [item["created"] for item in body["installed_contracts"]] == [True, True, True]
    assert [item["contract"]["action_type"] for item in body["installed_contracts"]] == [
        "email_send",
        "sequence_enroll",
        "campaign_launch",
    ]

    # Reinstall is idempotent — no duplicate contracts.
    repeated = client.post("/v1/action-packs/outreach-ops-v1/install", headers={"X-Project-Id": project_id})
    assert repeated.status_code == 201
    assert [item["created"] for item in repeated.json()["installed_contracts"]] == [False, False, False]

    # An email send intent validates against the installed contract.
    intent = client.post(
        "/v1/action-intents",
        headers={"X-Project-Id": project_id, "Idempotency-Key": "outreach_email_1"},
        json={
            "contract_version": "outreach.email.send/1.0",
            "action_type": "email_send",
            "operation_kind": "SEND",
            "principal": {"type": "agent", "id": "outreach-agent"},
            "actor_chain": [{"type": "agent", "id": "outreach-agent"}],
            "purpose": {"code": "customer_outreach", "summary": "Send outreach email with delivery proof"},
            "resource": {"recipient": "lead@example.com", "contact_id": "cont_out_1"},
            "parameters": {"subject": "Following up", "body": "Hi there, quick follow-up."},
            "verification_profile": "email_delivery/v1",
        },
    )
    assert intent.status_code == 201, intent.text
    assert intent.json()["contract_version"] == "outreach.email.send/1.0"
    assert intent.json()["status"] == "validated"


def test_data_ops_pack_installs_three_contracts(client: TestClient) -> None:
    project_id = "proj_data_pack_install"
    _seed_project(client, project_id)

    pack = client.get("/v1/action-packs/data-ops-v1", headers={"X-Project-Id": project_id})
    assert pack.status_code == 200, pack.text
    assert pack.json()["id"] == "data-ops-v1"
    assert pack.json()["quickstart_steps"] == [
        "Install data-ops-v1 for the tenant.",
        "Configure warehouse, orchestrator, or read-only Postgres connector.",
        "Call protect() before pipeline run, record purge, or data export.",
        "Verify dataset, run status, and destination before evidence publish.",
    ]
    assert [tpl["contract_version"] for tpl in pack.json()["contract_templates"]] == [
        "data.pipeline.run/1.0",
        "data.records.purge/1.0",
        "data.export.transfer/1.0",
    ]

    installed = client.post("/v1/action-packs/data-ops-v1/install", headers={"X-Project-Id": project_id})
    assert installed.status_code == 201, installed.text
    body = installed.json()
    assert body["pack"]["id"] == "data-ops-v1"
    assert [item["contract"]["contract_version"] for item in body["installed_contracts"]] == [
        "data.pipeline.run/1.0",
        "data.records.purge/1.0",
        "data.export.transfer/1.0",
    ]
    assert [item["created"] for item in body["installed_contracts"]] == [True, True, True]
    assert [item["contract"]["action_type"] for item in body["installed_contracts"]] == [
        "pipeline_run",
        "records_purge",
        "data_export",
    ]

    # Reinstall is idempotent — no duplicate contracts.
    repeated = client.post("/v1/action-packs/data-ops-v1/install", headers={"X-Project-Id": project_id})
    assert repeated.status_code == 201
    assert [item["created"] for item in repeated.json()["installed_contracts"]] == [False, False, False]

    # A pipeline run intent validates against the installed contract.
    intent = client.post(
        "/v1/action-intents",
        headers={"X-Project-Id": project_id, "Idempotency-Key": "data_pipeline_1"},
        json={
            "contract_version": "data.pipeline.run/1.0",
            "action_type": "pipeline_run",
            "operation_kind": "EXECUTE",
            "principal": {"type": "agent", "id": "data-agent"},
            "actor_chain": [{"type": "agent", "id": "data-agent"}],
            "purpose": {"code": "scheduled_refresh", "summary": "Run analytics pipeline with warehouse proof"},
            "resource": {"pipeline_id": "pl_daily_revenue", "environment": "prod"},
            "parameters": {"run_mode": "incremental"},
            "verification_profile": "warehouse_orchestrator/v1",
        },
    )
    assert intent.status_code == 201, intent.text
    assert intent.json()["contract_version"] == "data.pipeline.run/1.0"
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


def test_execution_request_auto_plans_after_direct_authorize(client: TestClient) -> None:
    project_id = "proj_action_kernel_auto_direct"
    _seed_project(client, project_id)
    _register_inventory_contract(client, project_id)
    runner = _register_auto_runner(client, project_id)

    created = client.post(
        "/v1/action-intents",
        headers={"X-Project-Id": project_id, "Idempotency-Key": "inventory_auto_direct"},
        json=_inventory_intent_payload(execution_request=_generic_rest_execution_request()),
    )
    assert created.status_code == 201, created.text
    assert created.json()["canonical_intent"]["execution_request"]["credential_pointer"] == "ops-default"

    decided = client.post(
        f"/v1/action-intents/{created.json()['action_id']}/decide",
        headers={"X-Project-Id": project_id},
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "authorized"

    attempts = client.get(
        f"/v1/action-intents/{created.json()['action_id']}/execution-attempts",
        headers={"X-Project-Id": project_id},
    )
    assert attempts.status_code == 200, attempts.text
    items = attempts.json()["items"]
    assert len(items) == 1
    attempt = items[0]
    assert attempt["status"] == "planned"
    assert attempt["runner_id"] == runner["runner_id"]
    assert attempt["credential_ref"] == "customer-runner-secret://ops/default"
    assert attempt["idempotency_key"] == f"auto-execution:{created.json()['action_id']}"
    assert attempt["protected_credential_returned"] is False
    assert attempt["execution_plan"]["execution_plan"]["adapter"] == "generic_rest"
    assert attempt["execution_plan"]["execution_plan"]["adapter_contract"]["credential_boundary"] == "runner_resolves_credential_ref"

    claimed = client.post(
        f"/v1/action-runners/{runner['runner_id']}/execution-attempts/claim",
        headers={"X-Project-Id": project_id},
        json={"runner_metadata": {"worker": "test-runner"}},
    )
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["attempt_id"] == attempt["attempt_id"]
    assert claimed.json()["status"] == "running"


def test_execution_request_auto_plans_after_approval_auto_advance(client: TestClient) -> None:
    project_id = "proj_action_kernel_auto_approval"
    _seed_project(client, project_id)
    _register_inventory_contract(client, project_id, action_type="inventory.item.delete")
    runner = _register_auto_runner(client, project_id)

    created = client.post(
        "/v1/action-intents",
        headers={"X-Project-Id": project_id, "Idempotency-Key": "inventory_auto_approval"},
        json=_inventory_intent_payload(
            action_type="inventory.item.delete",
            purpose={"code": "inventory_delete", "summary": "Delete inventory item through controlled path"},
            execution_request=_generic_rest_execution_request(),
        ),
    )
    assert created.status_code == 201, created.text

    pending = client.post(
        f"/v1/action-intents/{created.json()['action_id']}/decide",
        headers={"X-Project-Id": project_id},
    )
    assert pending.status_code == 200, pending.text
    assert pending.json()["status"] == "approval_pending"
    assert pending.json()["runtime_policy_decision_id"]

    empty_attempts = client.get(
        f"/v1/action-intents/{created.json()['action_id']}/execution-attempts",
        headers={"X-Project-Id": project_id},
    )
    assert empty_attempts.status_code == 200, empty_attempts.text
    assert empty_attempts.json()["items"] == []

    approved = client.post(
        f"/v1/runtime-policy/approvals/{pending.json()['runtime_policy_decision_id']}/approve",
        headers={"X-Project-Id": project_id},
        json={"reason": "Inventory owner approved this exact digest."},
    )
    assert approved.status_code == 200, approved.text

    fetched = client.get(
        f"/v1/action-intents/{created.json()['action_id']}",
        headers={"X-Project-Id": project_id},
    )
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["status"] == "authorized"

    attempts = client.get(
        f"/v1/action-intents/{created.json()['action_id']}/execution-attempts",
        headers={"X-Project-Id": project_id},
    )
    assert attempts.status_code == 200, attempts.text
    items = attempts.json()["items"]
    assert len(items) == 1
    assert items[0]["status"] == "planned"
    assert items[0]["runner_id"] == runner["runner_id"]
    assert items[0]["idempotency_key"] == f"auto-execution:{created.json()['action_id']}"


@pytest.mark.parametrize(
    "execution_request",
    [
        {**_generic_rest_execution_request(), "runner_id": "runner-forbidden"},
        {**_generic_rest_execution_request(), "credential_ref": "customer-runner-secret://ops/default"},
        _generic_rest_execution_request(credential_pointer="customer-runner-secret://ops/default"),
        {
            **_generic_rest_execution_request(),
            "credential": {"pointer": "ops-default", "protected_credential_ref": "customer-runner-secret://ops/default"},
        },
    ],
)
def test_execution_request_rejects_runner_and_credential_pins(
    client: TestClient,
    execution_request: dict,
) -> None:
    project_id = "proj_action_kernel_auto_rejects_pins"
    _seed_project(client, project_id)
    _register_inventory_contract(client, project_id)

    response = client.post(
        "/v1/action-intents",
        headers={"X-Project-Id": project_id, "Idempotency-Key": f"pin_reject_{len(str(execution_request))}"},
        json=_inventory_intent_payload(execution_request=execution_request),
    )

    assert response.status_code == 422
    assert "execution_request" in response.json()["detail"]


def test_stale_planned_execution_attempt_resolves_not_verified_receipt(client: TestClient) -> None:
    project_id = "proj_action_kernel_auto_stale_planned"
    _seed_project(client, project_id)
    _register_inventory_contract(client, project_id)
    _register_auto_runner(client, project_id)

    created = client.post(
        "/v1/action-intents",
        headers={"X-Project-Id": project_id, "Idempotency-Key": "inventory_auto_stale"},
        json=_inventory_intent_payload(execution_request=_generic_rest_execution_request()),
    )
    assert created.status_code == 201, created.text
    decided = client.post(
        f"/v1/action-intents/{created.json()['action_id']}/decide",
        headers={"X-Project-Id": project_id},
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "authorized"

    with client._session_factory() as session:  # type: ignore[attr-defined]
        attempt = session.query(ActionExecutionAttempt).filter_by(
            project_id=project_id,
            action_intent_id=created.json()["action_id"],
        ).one()
        attempt.updated_at = datetime.now(timezone.utc) - timedelta(seconds=120)
        session.add(attempt)
        session.commit()

        swept = sweep_stale_execution_attempts(
            session,
            stale_after_seconds=60,
            now=datetime.now(timezone.utc),
            actor="test-stale-planned-sweeper",
        )
        assert swept["resolved"] == 1
        processed = process_action_post_execution_jobs(session, worker_id="test-stale-planned-worker", limit=10)
        assert processed["processed"] == 2

        resolved_attempt = session.query(ActionExecutionAttempt).filter_by(id=attempt.id).one()
        intent = session.query(ActionIntent).filter_by(id=created.json()["action_id"]).one()
        receipt = session.query(ActionReceipt).filter_by(action_intent_id=created.json()["action_id"]).one_or_none()
        assert resolved_attempt.status == "ambiguous"
        assert intent.proof_status == "not_verified"
        assert intent.receipt_status == "generated"
        assert receipt is not None


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

    fetched_after_approval = client.get(
        f"/v1/action-intents/{intent['action_id']}",
        headers={"X-Project-Id": project_id},
    )
    assert fetched_after_approval.status_code == 200, fetched_after_approval.text
    assert fetched_after_approval.json()["status"] == "authorized"
    assert fetched_after_approval.json()["runtime_policy_decision_id"] != pending["runtime_policy_decision_id"]

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
        first_row = session.get(ActionIntent, first_intent["action_id"])
        second_row = session.get(ActionIntent, second_intent["action_id"])
        second_pending = session.get(RuntimePolicyDecision, body["runtime_policy_decision_id"])
        assert original_approval.status == "approved"
        assert original_approval.consumed_at is not None
        assert original_approval.consumed_by_decision_id == first_row.runtime_policy_decision_id
        assert first_row.status == "authorized"
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

    fetched_after_rejection = client.get(
        f"/v1/action-intents/{intent['action_id']}",
        headers={"X-Project-Id": project_id},
    )
    assert fetched_after_rejection.status_code == 200, fetched_after_rejection.text
    assert fetched_after_rejection.json()["status"] == "denied"

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
    event_types = [item["event_type"] for item in timeline]
    assert "execution_dispatched" in event_types
    assert "execution_running" in event_types
    assert "execution_succeeded" in event_types
    assert "post_execution_queued" in event_types

    with client._session_factory() as session:  # type: ignore[attr-defined]
        job = session.query(ActionPostExecutionJob).filter_by(
            project_id=project_id,
            action_intent_id=intent["action_id"],
            execution_attempt_id=attempt["attempt_id"],
            job_type="verify_outcome",
        ).one()
        action = session.get(ActionIntent, intent["action_id"])
        assert job.status == "pending"
        assert action.proof_status == "pending"
        assert action.receipt_status == "pending"


def test_post_execution_worker_resolves_missing_connector_to_not_verified_receipt(client: TestClient) -> None:
    project_id = "proj_action_post_execution_not_verified"
    _seed_project(client, project_id)
    _register_contract(client, project_id)
    intent = _create_intent(client, project_id)
    _authorize_intent(client, project_id, intent["action_id"])
    runner = client.post(
        "/v1/action-runners",
        headers={"X-Project-Id": project_id},
        json={
            "name": "post-exec-runner",
            "runner_type": "customer_hosted",
            "environment": "production",
            "supported_operation_kinds": ["TRANSFER"],
        },
    ).json()
    attempt = client.post(
        f"/v1/action-intents/{intent['action_id']}/execution-attempts",
        headers={"X-Project-Id": project_id, "Idempotency-Key": "post_exec_missing_connector"},
        json={
            "runner_id": runner["runner_id"],
            "credential_ref": "customer-runner-secret://support/stripe-refund-prod",
            "execution_plan": _refund_execution_plan(),
        },
    ).json()
    finished = client.post(
        f"/v1/action-intents/{intent['action_id']}/execution-attempts/{attempt['attempt_id']}/finish",
        headers={"X-Project-Id": project_id},
        json={
            "final_status": "succeeded",
            "result_summary": {
                "provider_ref": "rf_live_123",
                "claimed": {"refund_id": "rf_123", "status": "succeeded"},
                "match_fields": ["refund_id", "status"],
            },
        },
    )
    assert finished.status_code == 200, finished.text

    with client._session_factory() as session:  # type: ignore[attr-defined]
        stuck = session.query(ActionPostExecutionJob).filter_by(
            project_id=project_id,
            action_intent_id=intent["action_id"],
            execution_attempt_id=attempt["attempt_id"],
            job_type="verify_outcome",
        ).one()
        stuck.status = "running"
        stuck.claimed_by = "dead-worker"
        stuck.claimed_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        stuck.lease_expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        stuck.attempt_count = 1
        session.commit()

    with client._session_factory() as session:  # type: ignore[attr-defined]
        processed = process_action_post_execution_jobs(session, worker_id="test-post-exec", limit=5)
    assert processed["processed"] == 2
    assert [item["job_type"] for item in processed["jobs"]] == ["verify_outcome", "generate_receipt"]

    with client._session_factory() as session:  # type: ignore[attr-defined]
        action = session.get(ActionIntent, intent["action_id"])
        assert action.proof_status == "not_verified"
        assert action.receipt_status == "generated"
        outcomes = session.query(OutcomeReconciliationCheck).filter_by(project_id=project_id).all()
        assert len(outcomes) == 1
        assert outcomes[0].verdict == "not_verified"
        assert outcomes[0].connector_type == "ledger_refund_api"
        assert "connector_not_configured" in outcomes[0].metadata_json
        jobs = session.query(ActionPostExecutionJob).filter_by(project_id=project_id).order_by(
            ActionPostExecutionJob.created_at.asc()
        ).all()
        assert [(job.job_type, job.status) for job in jobs] == [
            ("verify_outcome", "succeeded"),
            ("generate_receipt", "succeeded"),
        ]
        receipt = session.query(ActionReceipt).filter_by(
            project_id=project_id,
            action_intent_id=intent["action_id"],
        ).one()
        assert receipt.receipt_digest.startswith("sha256:")

    with client._session_factory() as session:  # type: ignore[attr-defined]
        repeated = process_action_post_execution_jobs(session, worker_id="test-post-exec", limit=5)
    assert repeated["processed"] == 0


def test_post_execution_worker_verifies_generic_rest_action_and_generates_receipt(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = "proj_action_post_execution_generic_rest"
    _seed_project(client, project_id)
    created = client.post(
        "/v1/action-contracts",
        headers={"X-Project-Id": project_id},
        json={
            "contract_key": "internal.workflow.execute",
            "version": "1.0",
            "action_type": "internal.workflow.execute",
            "operation_kind": "EXECUTE",
            "domain_family": "internal_operations",
            "risk_class": "R2",
            "connector_family": "generic_rest",
            "schema": {"type": "object"},
            "verification_profile": {"minimum_level": "V3"},
        },
    )
    assert created.status_code == 201, created.text
    intent_response = client.post(
        "/v1/action-intents",
        headers={"X-Project-Id": project_id, "Idempotency-Key": "workflow_exec_1"},
        json={
            "contract_version": "internal.workflow.execute/1.0",
            "action_type": "internal.workflow.execute",
            "operation_kind": "EXECUTE",
            "environment": "production",
            "principal": {"type": "agent", "id": "workflow-agent"},
            "actor_chain": [{"type": "agent", "id": "workflow-agent"}],
            "purpose": {"code": "workflow_execute", "summary": "Execute internal workflow"},
            "resource": {"type": "workflow", "id": "wf_123"},
            "parameters": {"workflow_id": "wf_123"},
            "verification_profile": "generic_rest/workflow_state/v1",
            "trace_context": {"trace_id": "trace_workflow_1", "agent_name": "workflow-agent"},
        },
    )
    assert intent_response.status_code == 201, intent_response.text
    intent = intent_response.json()
    decided = client.post(
        f"/v1/action-intents/{intent['action_id']}/decide",
        headers={"X-Project-Id": project_id},
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "authorized"

    with client._session_factory() as session:  # type: ignore[attr-defined]
        session.add(
            SystemOfRecordConnectorConfig(
                project_id=project_id,
                connector_type="generic_rest_api",
                base_url="https://records.example.com/api",
                path_template="/records/{record_ref}",
                is_active=True,
            )
        )
        session.commit()

    def fake_fetch(self: GenericRestApiConnector) -> SourceRecord:
        assert self.record_ref == "wf_123"
        return SourceRecord(
            record={
                "record_ref": "wf_123",
                "status": "completed",
                "updated_at": "2026-07-09T12:00:10+00:00",
                "updated_by": "zroky-runner",
                "request_id": "req_workflow_1",
            },
            record_found=True,
            metadata={
                "connector_type": "generic_rest_api",
                "request_url": "https://records.example.com/api/records/wf_123",
                "http_status": 200,
                "attempts": 1,
                "retryable": False,
            },
        )

    monkeypatch.setattr(GenericRestApiConnector, "fetch", fake_fetch)
    runner = client.post(
        "/v1/action-runners",
        headers={"X-Project-Id": project_id},
        json={
            "name": "generic-rest-runner",
            "runner_type": "customer_hosted",
            "environment": "production",
            "supported_operation_kinds": ["EXECUTE"],
        },
    ).json()
    attempt = client.post(
        f"/v1/action-intents/{intent['action_id']}/execution-attempts",
        headers={"X-Project-Id": project_id, "Idempotency-Key": "workflow_exec_attempt_1"},
        json={
            "runner_id": runner["runner_id"],
            "credential_ref": "customer-runner-secret://ops/workflow",
            "execution_plan": {
                "adapter": "generic_rest",
                "operation": "workflow.execute",
                "target": {"resource_ref": "wf_123"},
                "arguments": {"requested_state": "completed"},
                "verification": {
                    "connector": "generic_rest_api",
                    "record_ref": "wf_123",
                    "claimed": {
                        "record_ref": "wf_123",
                        "status": "completed",
                        "correlation_id": "req_workflow_1",
                    },
                    "match_fields": ["record_ref", "status"],
                    "proof_manifest": {
                        "schema_version": "zroky.proof_connector.v0",
                        "connector_type": "generic_rest_api",
                        "capability": "workflow.execution.proof",
                        "tier": "declarative",
                        "match_fields": ["record_ref", "status"],
                        "temporal": {
                            "action_time": "2026-07-09T12:00:00+00:00",
                            "observed_at_field": "updated_at",
                            "window_seconds": 60,
                        },
                        "causal": {
                            "actor_field": "updated_by",
                            "expected_actor": "zroky-runner",
                            "correlation_field": "request_id",
                            "expected_correlation_claim_field": "correlation_id",
                        },
                    },
                },
            },
        },
    )
    assert attempt.status_code == 201, attempt.text
    finish = client.post(
        f"/v1/action-intents/{intent['action_id']}/execution-attempts/{attempt.json()['attempt_id']}/finish",
        headers={"X-Project-Id": project_id},
        json={"final_status": "succeeded", "result_summary": {"provider_ref": "wf_123", "status": "completed"}},
    )
    assert finish.status_code == 200, finish.text

    with client._session_factory() as session:  # type: ignore[attr-defined]
        processed = process_action_post_execution_jobs(session, worker_id="test-generic-post-exec", limit=5)
    assert processed["processed"] == 2

    with client._session_factory() as session:  # type: ignore[attr-defined]
        action = session.get(ActionIntent, intent["action_id"])
        assert action.proof_status == "matched"
        assert action.receipt_status == "generated"
        outcome = session.query(OutcomeReconciliationCheck).filter_by(project_id=project_id).one()
        assert outcome.verdict == "matched"
        assert outcome.connector_type == "generic_rest_api"
        assert outcome.action_type == "internal.workflow.execute"
        assert "workflow.execution.proof" in outcome.metadata_json
        receipt = session.query(ActionReceipt).filter_by(
            project_id=project_id,
            action_intent_id=intent["action_id"],
        ).one()
        assert receipt.receipt_digest.startswith("sha256:")


def test_post_execution_connector_exception_resolves_not_verified_receipt(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = "proj_action_post_execution_connector_exception"
    _seed_project(client, project_id)
    created = client.post(
        "/v1/action-contracts",
        headers={"X-Project-Id": project_id},
        json={
            "contract_key": "internal.workflow.execute",
            "version": "1.0",
            "action_type": "internal.workflow.execute",
            "operation_kind": "EXECUTE",
            "domain_family": "internal_operations",
            "risk_class": "R2",
            "connector_family": "generic_rest",
            "schema": {"type": "object"},
            "verification_profile": {"minimum_level": "V3"},
        },
    )
    assert created.status_code == 201, created.text
    intent_response = client.post(
        "/v1/action-intents",
        headers={"X-Project-Id": project_id, "Idempotency-Key": "workflow_exec_connector_exception"},
        json={
            "contract_version": "internal.workflow.execute/1.0",
            "action_type": "internal.workflow.execute",
            "operation_kind": "EXECUTE",
            "environment": "production",
            "principal": {"type": "agent", "id": "workflow-agent"},
            "actor_chain": [{"type": "agent", "id": "workflow-agent"}],
            "purpose": {"code": "workflow_execute", "summary": "Execute internal workflow"},
            "resource": {"type": "workflow", "id": "wf_exception"},
            "parameters": {"workflow_id": "wf_exception"},
            "verification_profile": "generic_rest/workflow_state/v1",
            "trace_context": {"trace_id": "trace_workflow_exception", "agent_name": "workflow-agent"},
        },
    )
    assert intent_response.status_code == 201, intent_response.text
    intent = intent_response.json()
    decided = client.post(
        f"/v1/action-intents/{intent['action_id']}/decide",
        headers={"X-Project-Id": project_id},
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "authorized"

    with client._session_factory() as session:  # type: ignore[attr-defined]
        session.add(
            SystemOfRecordConnectorConfig(
                project_id=project_id,
                connector_type="generic_rest_api",
                base_url="https://records.example.com/api",
                path_template="/records/{record_ref}",
                is_active=True,
            )
        )
        session.commit()

    def broken_fetch(self: GenericRestApiConnector) -> SourceRecord:
        raise RuntimeError("source-of-record timed out")

    monkeypatch.setattr(GenericRestApiConnector, "fetch", broken_fetch)
    runner = client.post(
        "/v1/action-runners",
        headers={"X-Project-Id": project_id},
        json={
            "name": "generic-rest-runner-exception",
            "runner_type": "customer_hosted",
            "environment": "production",
            "supported_operation_kinds": ["EXECUTE"],
        },
    ).json()
    attempt = client.post(
        f"/v1/action-intents/{intent['action_id']}/execution-attempts",
        headers={"X-Project-Id": project_id, "Idempotency-Key": "workflow_exec_attempt_exception"},
        json={
            "runner_id": runner["runner_id"],
            "credential_ref": "customer-runner-secret://ops/workflow",
            "execution_plan": {
                "adapter": "generic_rest",
                "operation": "workflow.execute",
                "target": {"resource_ref": "wf_exception"},
                "arguments": {"requested_state": "completed"},
                "verification": {
                    "connector": "generic_rest_api",
                    "record_ref": "wf_exception",
                    "claimed": {"record_ref": "wf_exception", "status": "completed"},
                    "match_fields": ["record_ref", "status"],
                },
            },
        },
    )
    assert attempt.status_code == 201, attempt.text
    finish = client.post(
        f"/v1/action-intents/{intent['action_id']}/execution-attempts/{attempt.json()['attempt_id']}/finish",
        headers={"X-Project-Id": project_id},
        json={"final_status": "succeeded", "result_summary": {"provider_ref": "wf_exception", "status": "completed"}},
    )
    assert finish.status_code == 200, finish.text

    with client._session_factory() as session:  # type: ignore[attr-defined]
        processed = process_action_post_execution_jobs(session, worker_id="test-connector-exception", limit=5)
    assert processed["processed"] == 2
    assert [item["job_type"] for item in processed["jobs"]] == ["verify_outcome", "generate_receipt"]

    with client._session_factory() as session:  # type: ignore[attr-defined]
        action = session.get(ActionIntent, intent["action_id"])
        assert action.proof_status == "not_verified"
        assert action.receipt_status == "generated"
        outcome = session.query(OutcomeReconciliationCheck).filter_by(project_id=project_id).one()
        assert outcome.verdict == "not_verified"
        assert outcome.connector_type == "generic_rest_api"
        assert "connector_exception:RuntimeError" in outcome.metadata_json
        jobs = session.query(ActionPostExecutionJob).filter_by(project_id=project_id).order_by(
            ActionPostExecutionJob.created_at.asc()
        ).all()
        assert [(job.job_type, job.status) for job in jobs] == [
            ("verify_outcome", "succeeded"),
            ("generate_receipt", "succeeded"),
        ]
        receipt = session.query(ActionReceipt).filter_by(
            project_id=project_id,
            action_intent_id=intent["action_id"],
        ).one()
        assert receipt.receipt_digest.startswith("sha256:")


def test_verify_job_dead_resolves_not_verified_and_receipt(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = "proj_action_post_execution_verify_dead"
    _seed_project(client, project_id)
    _register_contract(client, project_id)
    intent = _create_intent(client, project_id)
    _authorize_intent(client, project_id, intent["action_id"])
    runner = client.post(
        "/v1/action-runners",
        headers={"X-Project-Id": project_id},
        json={
            "name": "verify-dead-runner",
            "runner_type": "customer_hosted",
            "environment": "production",
            "supported_operation_kinds": ["TRANSFER"],
        },
    ).json()
    attempt = client.post(
        f"/v1/action-intents/{intent['action_id']}/execution-attempts",
        headers={"X-Project-Id": project_id, "Idempotency-Key": "verify_dead_attempt"},
        json={
            "runner_id": runner["runner_id"],
            "credential_ref": "customer-runner-secret://support/stripe-refund-prod",
            "execution_plan": _refund_execution_plan(),
        },
    ).json()
    finished = client.post(
        f"/v1/action-intents/{intent['action_id']}/execution-attempts/{attempt['attempt_id']}/finish",
        headers={"X-Project-Id": project_id},
        json={
            "final_status": "succeeded",
            "result_summary": {
                "provider_ref": "rf_live_dead",
                "claimed": {"refund_id": "rf_123", "status": "succeeded"},
                "match_fields": ["refund_id", "status"],
            },
        },
    )
    assert finished.status_code == 200, finished.text

    with client._session_factory() as session:  # type: ignore[attr-defined]
        job = session.query(ActionPostExecutionJob).filter_by(
            project_id=project_id,
            action_intent_id=intent["action_id"],
            execution_attempt_id=attempt["attempt_id"],
            job_type="verify_outcome",
        ).one()
        job.max_attempts = 1
        session.commit()

    def broken_verify(db, job):  # noqa: ANN001
        raise RuntimeError("verification worker crashed")

    monkeypatch.setattr(action_post_execution_service, "_run_verify_job", broken_verify)

    with client._session_factory() as session:  # type: ignore[attr-defined]
        processed = process_action_post_execution_jobs(session, worker_id="test-verify-dead", limit=5)
    assert processed["processed"] == 2
    assert [item["job_type"] for item in processed["jobs"]] == ["verify_outcome", "generate_receipt"]
    assert processed["jobs"][0]["status"] == "dead"
    assert processed["jobs"][1]["status"] == "succeeded"

    with client._session_factory() as session:  # type: ignore[attr-defined]
        action = session.get(ActionIntent, intent["action_id"])
        assert action.proof_status == "not_verified"
        assert action.receipt_status == "generated"
        outcome = session.query(OutcomeReconciliationCheck).filter_by(project_id=project_id).one()
        assert outcome.verdict == "not_verified"
        assert "verify_job_dead:RuntimeError" in outcome.metadata_json
        receipt = session.query(ActionReceipt).filter_by(
            project_id=project_id,
            action_intent_id=intent["action_id"],
        ).one()
        assert receipt.receipt_digest.startswith("sha256:")


def test_stale_running_execution_attempt_becomes_ambiguous_not_verified_receipt(client: TestClient) -> None:
    project_id = "proj_action_runner_stale_attempt"
    _seed_project(client, project_id)
    _register_contract(client, project_id)
    intent = _create_intent(client, project_id)
    _authorize_intent(client, project_id, intent["action_id"])
    runner = client.post(
        "/v1/action-runners",
        headers={"X-Project-Id": project_id},
        json={
            "name": "stale-runner",
            "runner_type": "customer_hosted",
            "environment": "production",
            "supported_operation_kinds": ["TRANSFER"],
        },
    ).json()
    attempt = client.post(
        f"/v1/action-intents/{intent['action_id']}/execution-attempts",
        headers={"X-Project-Id": project_id, "Idempotency-Key": "stale_exec_attempt"},
        json={
            "runner_id": runner["runner_id"],
            "credential_ref": "customer-runner-secret://support/stripe-refund-prod",
            "execution_plan": _refund_execution_plan(),
        },
    ).json()
    running = client.post(
        f"/v1/action-intents/{intent['action_id']}/execution-attempts/{attempt['attempt_id']}/start",
        headers={"X-Project-Id": project_id},
        json={"runner_metadata": {"runner_instance_id": "stale-runner-1"}},
    )
    assert running.status_code == 200, running.text

    stale_at = datetime.now(timezone.utc) - timedelta(minutes=20)
    with client._session_factory() as session:  # type: ignore[attr-defined]
        row = session.get(ActionExecutionAttempt, attempt["attempt_id"])
        row.started_at = stale_at
        row.updated_at = stale_at
        session.commit()

    with client._session_factory() as session:  # type: ignore[attr-defined]
        resolved = sweep_stale_execution_attempts(
            session,
            stale_after_seconds=60,
            limit=5,
            actor="test-stale-sweeper",
            now=datetime.now(timezone.utc),
        )
    assert resolved["resolved"] == 1
    assert resolved["attempts"][0]["previous_status"] == "running"

    with client._session_factory() as session:  # type: ignore[attr-defined]
        processed = process_action_post_execution_jobs(session, worker_id="test-stale-post-exec", limit=5)
    assert processed["processed"] == 2
    assert [item["job_type"] for item in processed["jobs"]] == ["verify_outcome", "generate_receipt"]

    with client._session_factory() as session:  # type: ignore[attr-defined]
        row = session.get(ActionExecutionAttempt, attempt["attempt_id"])
        assert row.status == "ambiguous"
        assert row.finished_at is not None
        assert row.error_message == "Execution attempt timed out before runner reported a terminal status."
        action = session.get(ActionIntent, intent["action_id"])
        assert action.proof_status == "not_verified"
        assert action.receipt_status == "generated"
        outcome = session.query(OutcomeReconciliationCheck).filter_by(project_id=project_id).one()
        assert outcome.verdict == "not_verified"
        assert "execution_ambiguous" in outcome.metadata_json
        receipt = session.query(ActionReceipt).filter_by(
            project_id=project_id,
            action_intent_id=intent["action_id"],
        ).one()
        assert receipt.receipt_digest.startswith("sha256:")


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


def test_project_execution_attempts_filter_stale_claimable_attempts(client: TestClient) -> None:
    project_id = "proj_action_attempts_stale_list"
    other_project_id = "proj_action_attempts_stale_other"
    _seed_project(client, project_id)
    _seed_project(client, other_project_id)
    _register_contract(client, project_id)
    _register_contract(client, other_project_id)
    runner = client.post(
        "/v1/action-runners",
        headers={"X-Project-Id": project_id},
        json={
            "name": "stale-list-runner",
            "runner_type": "customer_hosted",
            "environment": "production",
            "supported_operation_kinds": ["TRANSFER"],
        },
    ).json()

    stale_planned_intent = _create_intent(client, project_id, idempotency_key="stale_list_planned")
    _authorize_intent(client, project_id, stale_planned_intent["action_id"])
    stale_planned = client.post(
        f"/v1/action-intents/{stale_planned_intent['action_id']}/execution-attempts",
        headers={"X-Project-Id": project_id, "Idempotency-Key": "stale_list_planned_attempt"},
        json={
            "runner_id": runner["runner_id"],
            "credential_ref": "customer-runner-secret://support/stripe-refund-prod",
            "execution_plan": _refund_execution_plan(),
        },
    ).json()

    stale_running_intent = _create_intent(client, project_id, idempotency_key="stale_list_running")
    _authorize_intent(client, project_id, stale_running_intent["action_id"])
    stale_running = client.post(
        f"/v1/action-intents/{stale_running_intent['action_id']}/execution-attempts",
        headers={"X-Project-Id": project_id, "Idempotency-Key": "stale_list_running_attempt"},
        json={
            "runner_id": runner["runner_id"],
            "credential_ref": "customer-runner-secret://support/stripe-refund-prod",
            "execution_plan": _refund_execution_plan(),
        },
    ).json()
    started = client.post(
        f"/v1/action-intents/{stale_running_intent['action_id']}/execution-attempts/{stale_running['attempt_id']}/start",
        headers={"X-Project-Id": project_id},
        json={"runner_metadata": {"worker": "stale-list-test"}},
    )
    assert started.status_code == 200, started.text

    fresh_intent = _create_intent(client, project_id, idempotency_key="stale_list_fresh")
    _authorize_intent(client, project_id, fresh_intent["action_id"])
    fresh = client.post(
        f"/v1/action-intents/{fresh_intent['action_id']}/execution-attempts",
        headers={"X-Project-Id": project_id, "Idempotency-Key": "stale_list_fresh_attempt"},
        json={
            "runner_id": runner["runner_id"],
            "credential_ref": "customer-runner-secret://support/stripe-refund-prod",
            "execution_plan": _refund_execution_plan(),
        },
    ).json()

    other_runner = client.post(
        "/v1/action-runners",
        headers={"X-Project-Id": other_project_id},
        json={
            "name": "stale-list-runner-other",
            "runner_type": "customer_hosted",
            "environment": "production",
            "supported_operation_kinds": ["TRANSFER"],
        },
    ).json()
    other_intent = _create_intent(client, other_project_id, idempotency_key="stale_list_other")
    _authorize_intent(client, other_project_id, other_intent["action_id"])
    other_attempt = client.post(
        f"/v1/action-intents/{other_intent['action_id']}/execution-attempts",
        headers={"X-Project-Id": other_project_id, "Idempotency-Key": "stale_list_other_attempt"},
        json={
            "runner_id": other_runner["runner_id"],
            "credential_ref": "customer-runner-secret://support/stripe-refund-prod",
            "execution_plan": _refund_execution_plan(),
        },
    ).json()

    with client._session_factory() as session:  # type: ignore[attr-defined]
        stale_time = datetime.now(timezone.utc) - timedelta(seconds=120)
        for attempt_id in (stale_planned["attempt_id"], stale_running["attempt_id"], other_attempt["attempt_id"]):
            row = session.get(ActionExecutionAttempt, attempt_id)
            assert row is not None
            row.updated_at = stale_time
            session.add(row)
        session.commit()

    stale = client.get(
        "/v1/action-execution-attempts",
        headers={"X-Project-Id": project_id},
        params={"status": "planned,running", "stale": "true", "stale_after_seconds": 60},
    )
    assert stale.status_code == 200, stale.text
    items = stale.json()["items"]
    assert [item["attempt_id"] for item in items] == [stale_planned["attempt_id"], stale_running["attempt_id"]]
    assert {item["status"] for item in items} == {"planned", "running"}
    assert fresh["attempt_id"] not in {item["attempt_id"] for item in items}
    assert other_attempt["attempt_id"] not in {item["attempt_id"] for item in items}

    invalid = client.get(
        "/v1/action-execution-attempts",
        headers={"X-Project-Id": project_id},
        params={"status": "planned,unknown"},
    )
    assert invalid.status_code == 422


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
    agent = _create_agent_profile(client, project_id, display_name="Refund Agent")
    intent = _create_intent(client, project_id, agent_id=agent["id"])
    scoped_rule = client.post(
        "/v1/runtime-policy/rules",
        headers={"X-Project-Id": project_id},
        json={
            "name": "Receipt proof refund rule",
            "action_type": "customer.refund.transfer",
            "policy_patch": {"runtime_max_tool_calls": 12},
        },
    )
    assert scoped_rule.status_code == 201, scoped_rule.text
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
    assert receipt["signature_algorithm"] == "Ed25519"
    assert receipt["signature_valid"] is True
    signing_key = client.get("/.well-known/zroky/action-receipt-signing-key")
    assert signing_key.status_code == 200
    public_key_payload = signing_key.json()
    assert public_key_payload["algorithm"] == "Ed25519"
    assert public_key_payload["key_id"] == receipt["signing_key_id"]
    assert receipt["receipt"]["signature"]["public_key"] == public_key_payload["public_key"]
    assert verify_receipt_json_with_public_key(
        receipt_json=receipt["signed_payload"],
        signature=receipt["signature"],
        public_key=public_key_payload["public_key"],
    ) is True
    assert verify_receipt_json_with_public_key(
        receipt_json=receipt["signed_payload"].replace('"planned"', '"tampered"', 1),
        signature=receipt["signature"],
        public_key=public_key_payload["public_key"],
    ) is False
    assert receipt["receipt"]["final_status"] == "planned"
    assert receipt["receipt"]["intent"]["intent_digest"] == intent["intent_digest"]
    assert receipt["receipt"]["intent"]["agent_id"] == agent["id"]
    assert receipt["receipt"]["intent"]["agent_profile"]["slug"] == "refund-agent"
    assert receipt["receipt"]["runner_execution"]["id"] == attempt.json()["attempt_id"]
    assert receipt["receipt"]["runner_execution"]["protected_credential_returned"] is False
    assert receipt["receipt"]["policy_decision"]["status"] == "allowed"
    assert receipt["receipt"]["policy_decision"]["policy_resolution"]["matched_rules"][0]["id"] == scoped_rule.json()["id"]
    assert (
        receipt["receipt"]["policy_decision"]["policy_snapshot"]["_runtime_policy_resolution"]["matched_rules"][0]["id"]
        == scoped_rule.json()["id"]
    )
    assert receipt["receipt"]["evidence"]["evidence_hash"]
    assert receipt["receipt"]["signature"]["value"] == receipt["signature"]
    with client._session_factory() as signature_session:  # type: ignore[attr-defined]
        receipt_row = signature_session.get(ActionReceipt, receipt["receipt_id"])
        assert receipt_row is not None
        assert receipt_row.receipt_json == receipt["signed_payload"]
        assert verify_receipt_json_with_public_key(
            receipt_json=receipt_row.receipt_json,
            signature=receipt["signature"],
            public_key=public_key_payload["public_key"],
        ) is True
        assert verify_receipt_json_with_public_key(
            receipt_json=receipt_row.receipt_json.replace('"planned"', '"tampered"', 1),
            signature=receipt["signature"],
            public_key=public_key_payload["public_key"],
        ) is False

    fetched = client.get(
        f"/v1/action-intents/{intent['action_id']}/receipt",
        headers={"X-Project-Id": project_id},
    )
    assert fetched.status_code == 200
    assert fetched.json()["receipt_digest"] == receipt["receipt_digest"]
    assert fetched.json()["signature_valid"] is True
    intent_after_receipt = client.get(
        "/v1/action-intents",
        headers={"X-Project-Id": project_id},
        params={"receipt_status": "generated"},
    )
    assert intent_after_receipt.status_code == 200
    assert intent_after_receipt.json()["items"][0]["action_id"] == intent["action_id"]
    assert intent_after_receipt.json()["items"][0]["receipt_status"] == "generated"

    timeline_after_receipt = client.get(
        f"/v1/action-intents/{intent['action_id']}/timeline",
        headers={"X-Project-Id": project_id},
    )
    assert timeline_after_receipt.status_code == 200
    assert [item["event_type"] for item in timeline_after_receipt.json()["items"]][-1] == "receipt_generated"

    with client._session_factory() as session:  # type: ignore[attr-defined]
        receipt_row = session.get(ActionReceipt, receipt["receipt_id"])
        assert receipt_row.receipt_digest == receipt["receipt_digest"]
        action_row = session.get(ActionIntent, intent["action_id"])
        assert action_row.receipt_status == "generated"
        timeline_rows = (
            session.query(ActionTimelineEvent)
            .filter(ActionTimelineEvent.project_id == project_id)
            .order_by(ActionTimelineEvent.created_at.asc())
            .all()
        )
        assert [row.event_type for row in timeline_rows][-1] == "receipt_generated"
