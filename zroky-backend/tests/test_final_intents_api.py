from __future__ import annotations

import pytest
import importlib
import json
from datetime import UTC, datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.db.base import Base
from app.db.models import AuditLog, FinalDomainOutboxJob, FinalEvidenceBundle
from app.db.session import get_db_session
from app.main import app


@pytest.fixture()
def client():
    importlib.import_module("app.db.models")

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)

    def override_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db_session] = override_db
    role = {"value": "member"}
    project = {"value": "proj_test"}
    app.dependency_overrides[require_tenant_context] = lambda: TenantContext(
        tenant_id=project["value"],
        role=role["value"],
        subject="tester",
    )
    with TestClient(app) as test_client:
        test_client.tenant_role = role
        test_client.tenant_project = project
        test_client._session_factory = SessionLocal
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def test_trusted_intent_create_read_and_idempotent_replay(client: TestClient) -> None:
    payload = {
        "environment": "Production",
        "agent_ref": "agent-1",
        "intent": {"action": "send_invoice", "invoice_id": "inv_123"},
    }
    headers = {"Idempotency-Key": "intent-key-1"}

    created = client.post("/v1/intents", json=payload, headers=headers)
    assert created.status_code == 201
    body = created.json()
    assert body["project_id"] == "proj_test"
    assert body["environment"] == "production"
    assert body["intent"] == payload["intent"]

    replay = client.post("/v1/intents", json=payload, headers=headers)
    assert replay.status_code == 201
    assert replay.json()["id"] == body["id"]

    fetched = client.get(f"/v1/intents/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == body["id"]


def test_trusted_intent_requires_idempotency_key(client: TestClient) -> None:
    response = client.post("/v1/intents", json={"intent": {"action": "x"}})
    assert response.status_code == 400


def test_trusted_intent_idempotency_key_rejects_changed_payload(client: TestClient) -> None:
    headers = {"Idempotency-Key": "same-key"}
    first = client.post("/v1/intents", json={"intent": {"action": "a"}}, headers=headers)
    assert first.status_code == 201

    changed = client.post("/v1/intents", json={"intent": {"action": "b"}}, headers=headers)
    assert changed.status_code == 409


def test_final_intent_read_rejects_cross_tenant_project_context(client: TestClient) -> None:
    client.tenant_project["value"] = "proj_alpha"
    created = client.post(
        "/v1/intents",
        json={"intent": {"action": "tenant_scoped_action"}},
        headers={"Idempotency-Key": "tenant-negative-intent-alpha"},
    )
    assert created.status_code == 201, created.text
    intent_id = created.json()["id"]

    client.tenant_project["value"] = "proj_beta"
    cross_project = client.get(f"/v1/intents/{intent_id}")

    assert cross_project.status_code == 404

    client.tenant_project["value"] = "proj_alpha"
    same_project = client.get(f"/v1/intents/{intent_id}")
    assert same_project.status_code == 200
    assert same_project.json()["project_id"] == "proj_alpha"


def test_recovery_dispatch_claim_rejects_cross_tenant_worker_context(client: TestClient) -> None:
    executor_ref = "customer-recovery-executor://ops/tenant-negative"
    with client._session_factory() as session:
        session.add(
            FinalDomainOutboxJob(
                id="outbox_tenant_negative_alpha",
                project_id="proj_alpha",
                environment="production",
                job_type="execute_recovery",
                aggregate_type="recovery_plan",
                aggregate_id="recovery_plan_alpha",
                idempotency_key="tenant-negative-recovery-alpha",
                status="pending",
                payload_json=json.dumps({"executor_ref": executor_ref}),
            )
        )
        session.commit()

    client.tenant_project["value"] = "proj_beta"
    cross_project = client.post(
        "/v1/recovery/dispatch/claim",
        json={"executor_ref": executor_ref, "lease_seconds": 300},
    )
    assert cross_project.status_code == 404

    client.tenant_project["value"] = "proj_alpha"
    same_project = client.post(
        "/v1/recovery/dispatch/claim",
        json={"executor_ref": executor_ref, "lease_seconds": 300},
    )
    assert same_project.status_code == 200, same_project.text
    assert same_project.json()["outbox_job_id"] == "outbox_tenant_negative_alpha"


def test_policy_check_defaults_to_observe_only_and_can_be_read(client: TestClient) -> None:
    created = client.post(
        "/v1/intents",
        json={"intent": {"action": "send_invoice"}},
        headers={"Idempotency-Key": "policy-intent-1"},
    ).json()

    checked = client.post("/v1/policy/check", json={"intent_id": created["id"]})
    assert checked.status_code == 201
    decision = checked.json()
    assert decision["decision"] == "observe_only"
    assert decision["decision_detail"]["source"] == "safe_default"

    fetched = client.get(f"/v1/policy/decisions/{decision['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == decision["id"]


def test_observe_only_workflow_runs_end_to_end_with_signed_evidence(client: TestClient) -> None:
    client.tenant_role["value"] = "admin"
    pack = {
        "schema_version": "zroky.workflow_assurance_pack.v1",
        "workflow_key": "support-refund-observe",
        "version": "1.0.0",
        "intent_schema": {"type": "object"},
        "object_types": [{"key": "ticket", "schema": {"type": "object"}}],
        "effects": [{"key": "ticket_observed", "object_type": "ticket", "predicate": "ticket.mutation == false"}],
        "source_bindings": [
            {
                "key": "zendesk_ticket_read",
                "connector_capability": "zendesk.ticket.read",
                "object_type": "ticket",
                "freshness_seconds": 300,
            }
        ],
        "recovery_playbooks": [],
    }
    published = client.post("/v1/assurance-packs", json={"environment": "production", "pack": pack})
    assert published.status_code == 201, published.text

    intent = client.post(
        "/v1/intents",
        json={
            "environment": "production",
            "agent_ref": "support-agent",
            "intent": {
                "workflow_key": "support-refund-observe",
                "action": "summarize_refund_ticket",
                "ticket_id": "TCK-100",
            },
        },
        headers={"Idempotency-Key": "observe-only-workflow-intent"},
    )
    assert intent.status_code == 201, intent.text
    intent_body = intent.json()

    checked = client.post("/v1/policy/check", json={"intent_id": intent_body["id"]})
    assert checked.status_code == 201, checked.text
    decision = checked.json()
    assert decision["decision"] == "observe_only"
    assert decision["decision_detail"]["source"] == "safe_default"

    run = client.post(
        "/v1/runs",
        json={
            "environment": "production",
            "external_run_id": "support-refund-run-100",
            "workflow_key": "support-refund-observe",
            "agent_ref": "support-agent",
            "status": "succeeded",
            "run": {
                "provider": "langgraph",
                "trace_id": "trace-support-refund-100",
                "steps": [
                    {"name": "read_ticket", "effect": "read_only"},
                    {"name": "summarize_ticket", "effect": "read_only"},
                ],
            },
        },
        headers={"Idempotency-Key": "observe-only-workflow-run"},
    )
    assert run.status_code == 201, run.text
    run_body = run.json()
    assert run_body["workflow_key"] == "support-refund-observe"
    assert run_body["status"] == "succeeded"

    bundle = client.post(
        "/v1/evidence/bundles",
        json={
            "environment": "production",
            "subject_type": "run",
            "subject_id": run_body["id"],
            "bundle": {
                "schema_version": "zroky.final_evidence_bundle.v1",
                "intent": intent_body,
                "policy": decision,
                "observations": [{"ticket_status": "resolved", "mutation": False}],
                "snapshot": run_body,
                "incident": {"created": False},
                "recovery": {"required": False},
            },
        },
    )
    assert bundle.status_code == 201, bundle.text
    bundle_body = bundle.json()
    assert bundle_body["signature"]["payload_digest"] == f"sha256:{bundle_body['bundle_digest']}"

    verified = client.get(f"/v1/evidence/bundles/{bundle_body['id']}/verify")
    assert verified.status_code == 200, verified.text
    assert verified.json()["verification_status"] == "pass"


def test_policy_forced_decisions_require_admin_role(client: TestClient) -> None:
    created = client.post(
        "/v1/intents",
        json={"intent": {"action": "wire_money"}},
        headers={"Idempotency-Key": "policy-intent-2"},
    ).json()

    forbidden = client.post("/v1/policy/check", json={"intent_id": created["id"], "decision": "deny"})
    assert forbidden.status_code == 403

    client.tenant_role["value"] = "admin"
    for decision in ("allow", "deny", "approval_required", "observe_only"):
        response = client.post(
            "/v1/policy/check",
            json={"intent_id": created["id"], "decision": decision, "reason": "test"},
        )
        assert response.status_code == 201
        assert response.json()["decision"] == decision


def test_policy_approval_required_creates_digest_bound_requirement(client: TestClient) -> None:
    created = client.post(
        "/v1/intents",
        json={"intent": {"action": "wire_money", "amount": 1000}},
        headers={"Idempotency-Key": "approval-intent-1"},
    ).json()

    client.tenant_role["value"] = "admin"
    response = client.post(
        "/v1/policy/check",
        json={"intent_id": created["id"], "decision": "approval_required"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["decision"] == "approval_required"
    assert len(body["approval_requirements"]) == 1
    approval = body["approval_requirements"][0]
    assert approval["required_role"] == "admin"
    assert approval["status"] == "pending"
    assert approval["binding_digest"]

    fetched = client.get(f"/v1/policy/decisions/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["approval_requirements"][0]["binding_digest"] == approval["binding_digest"]

    approvals = client.get("/v1/policy/approval-requirements")
    assert approvals.status_code == 200
    assert approvals.json()["items"][0]["binding_digest"] == approval["binding_digest"]


def test_final_approval_resolution_requires_role_and_binding_digest(client: TestClient) -> None:
    intent = client.post(
        "/v1/intents",
        json={"intent": {"action": "refund", "amount": 1000}},
        headers={"Idempotency-Key": "approval-resolution-1"},
    ).json()

    client.tenant_role["value"] = "admin"
    decision = client.post(
        "/v1/policy/check",
        json={"intent_id": intent["id"], "decision": "approval_required"},
    ).json()
    approval = decision["approval_requirements"][0]

    listed = client.get("/v1/approvals")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["id"] == approval["id"]

    bad_digest = client.post(
        f"/v1/approvals/{approval['id']}/approve",
        json={"binding_digest": "wrong"},
    )
    assert bad_digest.status_code == 409

    client.tenant_role["value"] = "member"
    forbidden = client.post(
        f"/v1/approvals/{approval['id']}/approve",
        json={"binding_digest": approval["binding_digest"]},
    )
    assert forbidden.status_code == 403

    client.tenant_role["value"] = "admin"
    approved = client.post(
        f"/v1/approvals/{approval['id']}/approve",
        json={"binding_digest": approval["binding_digest"]},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    fetched_intent = client.get(f"/v1/intents/{intent['id']}")
    assert fetched_intent.status_code == 200
    assert fetched_intent.json()["status"] == "authorized"


def test_final_approval_deny_blocks_bound_intent(client: TestClient) -> None:
    intent = client.post(
        "/v1/intents",
        json={"intent": {"action": "refund", "amount": 2500}},
        headers={"Idempotency-Key": "approval-deny-1"},
    ).json()

    client.tenant_role["value"] = "admin"
    decision = client.post(
        "/v1/policy/check",
        json={"intent_id": intent["id"], "decision": "approval_required"},
    ).json()
    approval = decision["approval_requirements"][0]

    denied = client.post(
        f"/v1/approvals/{approval['id']}/deny",
        json={"binding_digest": approval["binding_digest"]},
    )
    assert denied.status_code == 200
    assert denied.json()["status"] == "denied"

    fetched_intent = client.get(f"/v1/intents/{intent['id']}")
    assert fetched_intent.status_code == 200
    assert fetched_intent.json()["status"] == "policy_denied"


def _publish_stripe_refund_pack(client: TestClient) -> dict:
    client.tenant_role["value"] = "admin"
    response = client.post(
        "/v1/assurance-packs",
        json={
            "environment": "production",
            "pack": {
                "schema_version": "zroky.workflow_assurance_pack.v1",
                "workflow_key": "stripe-refund-test-loop",
                "version": "1.0.0",
                "intent_schema": {"type": "object"},
                "object_types": [{"key": "refund", "schema": {"type": "object"}}],
                "effects": [
                    {
                        "key": "stripe_refund_succeeded",
                        "object_type": "refund",
                        "predicate": "refund.status == 'succeeded'",
                    }
                ],
                "source_bindings": [
                    {
                        "key": "stripe_refund_read",
                        "connector_capability": "stripe.refund.read",
                        "object_type": "refund",
                        "freshness_seconds": 300,
                    }
                ],
                "recovery_playbooks": [],
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _authorize_stripe_refund_intent(client: TestClient, *, refund_id: str, amount: int, key: str) -> tuple[dict, dict]:
    intent = client.post(
        "/v1/intents",
        json={
            "environment": "production",
            "agent_ref": "stripe-test-agent",
            "intent": {
                "workflow_key": "stripe-refund-test-loop",
                "action": "stripe.refund.create",
                "charge_id": f"ch_{key}",
                "refund_id": refund_id,
                "amount": amount,
                "currency": "usd",
            },
        },
        headers={"Idempotency-Key": f"stripe-intent-{key}"},
    )
    assert intent.status_code == 201, intent.text
    intent_body = intent.json()

    client.tenant_role["value"] = "admin"
    decision = client.post(
        "/v1/policy/check",
        json={"intent_id": intent_body["id"], "decision": "approval_required", "reason": "stripe test refund"},
    )
    assert decision.status_code == 201, decision.text
    decision_body = decision.json()
    approval = decision_body["approval_requirements"][0]
    approved = client.post(
        f"/v1/approvals/{approval['id']}/approve",
        json={"binding_digest": approval["binding_digest"]},
    )
    assert approved.status_code == 200, approved.text
    assert client.get(f"/v1/intents/{intent_body['id']}").json()["status"] == "authorized"
    return intent_body, decision_body


def test_stripe_refund_test_loop_verifies_real_sor_and_catches_false_success(client: TestClient) -> None:
    pack = _publish_stripe_refund_pack(client)
    intent_ok, decision_ok = _authorize_stripe_refund_intent(client, refund_id="re_stripe_ok", amount=1200, key="ok")
    run_ok = client.post(
        "/v1/runs",
        json={
            "environment": "production",
            "external_run_id": "stripe-run-ok",
            "intent_id": intent_ok["id"],
            "workflow_key": "stripe-refund-test-loop",
            "agent_ref": "stripe-test-agent",
            "status": "succeeded",
            "run": {"claimed": {"refund_id": "re_stripe_ok", "status": "succeeded"}},
        },
        headers={"Idempotency-Key": "stripe-run-ok"},
    )
    assert run_ok.status_code == 201, run_ok.text
    observation_ok = client.post(
        "/v1/observations",
        json={
            "environment": "production",
            "run_id": run_ok.json()["id"],
            "intent_id": intent_ok["id"],
            "source_kind": "stripe_refund",
            "observed_object_ref": "stripe:refund:re_stripe_ok",
            "observed_state": {"refund_id": "re_stripe_ok", "status": "succeeded", "amount": 1200, "currency": "usd"},
            "provenance": {"source_binding": "stripe_refund_read", "stripe_object": "refund", "mode": "test"},
            "observed_at": "2026-07-22T10:00:00Z",
            "read_at": "2026-07-22T10:00:05Z",
        },
    )
    assert observation_ok.status_code == 201, observation_ok.text
    graph_ok = client.post(f"/v1/runs/{run_ok.json()['id']}/outcome-graph", json={"assurance_pack_id": pack["id"]})
    assert graph_ok.status_code == 201, graph_ok.text
    assert graph_ok.json()["verification_status"] == "verified"
    assert graph_ok.json()["graph"]["classification"] == "verified"

    evidence = client.post(
        "/v1/evidence/bundles",
        json={
            "environment": "production",
            "subject_type": "run",
            "subject_id": run_ok.json()["id"],
            "bundle": {
                "schema_version": "zroky.final_evidence_bundle.v1",
                "intent": intent_ok,
                "policy": decision_ok,
                "observations": [observation_ok.json()],
                "snapshot": graph_ok.json(),
                "incident": {"created": False},
                "recovery": {"required": False},
            },
        },
    )
    assert evidence.status_code == 201, evidence.text
    verified_evidence = client.get(f"/v1/evidence/bundles/{evidence.json()['id']}/verify")
    assert verified_evidence.status_code == 200, verified_evidence.text
    assert verified_evidence.json()["verification_status"] == "pass"

    intent_bad, _decision_bad = _authorize_stripe_refund_intent(client, refund_id="re_stripe_missing", amount=1200, key="bad")
    run_bad = client.post(
        "/v1/runs",
        json={
            "environment": "production",
            "external_run_id": "stripe-run-bad",
            "intent_id": intent_bad["id"],
            "workflow_key": "stripe-refund-test-loop",
            "agent_ref": "stripe-test-agent",
            "status": "succeeded",
            "run": {"claimed": {"refund_id": "re_stripe_missing", "status": "succeeded"}},
        },
        headers={"Idempotency-Key": "stripe-run-bad"},
    )
    assert run_bad.status_code == 201, run_bad.text
    graph_bad = client.post(f"/v1/runs/{run_bad.json()['id']}/outcome-graph", json={"assurance_pack_id": pack["id"]})
    assert graph_bad.status_code == 201, graph_bad.text
    assert graph_bad.json()["verification_status"] == "failed"
    assert graph_bad.json()["graph"]["classification"] == "missing"
    incidents = client.get("/v1/incidents")
    assert incidents.status_code == 200
    assert any(item["outcome_graph_id"] == graph_bad.json()["id"] and item["status"] == "open" for item in incidents.json())


def test_run_intake_declares_external_run_without_execution_ownership(client: TestClient) -> None:
    payload = {
        "environment": "Production",
        "external_run_id": "run_ext_1",
        "workflow_key": "refund-workflow",
        "agent_ref": "agent-1",
        "status": "running",
        "run": {"provider": "langgraph", "trace_id": "trace_1"},
    }
    headers = {"Idempotency-Key": "run-key-1"}

    created = client.post("/v1/runs", json=payload, headers=headers)
    assert created.status_code == 201
    body = created.json()
    assert body["project_id"] == "proj_test"
    assert body["environment"] == "production"
    assert body["external_run_id"] == "run_ext_1"
    assert body["run"] == payload["run"]

    replay = client.post("/v1/runs", json=payload, headers=headers)
    assert replay.status_code == 201
    assert replay.json()["id"] == body["id"]

    changed = client.post("/v1/runs", json={**payload, "run": {"trace_id": "changed"}}, headers=headers)
    assert changed.status_code == 409

    fetched = client.get(f"/v1/runs/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == body["id"]

    listed = client.get("/v1/runs")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["id"] == body["id"]


def test_cloudevents_run_declared_normalizes_to_run(client: TestClient) -> None:
    response = client.post(
        "/v1/events/cloudevents",
        json={
            "specversion": "1.0",
            "id": "event-run-1",
            "source": "agent://langgraph",
            "type": "com.zroky.run.declared",
            "data": {
                "environment": "production",
                "external_run_id": "ce-run-1",
                "status": "declared",
                "run": {"trace_id": "trace-ce-1"},
            },
        },
    )
    assert response.status_code == 202
    body = response.json()
    assert body["accepted"] is True
    assert body["normalized_type"] == "run"

    fetched = client.get(f"/v1/runs/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["external_run_id"] == "ce-run-1"


def test_otlp_json_trace_intake_normalizes_spans_to_runs(client: TestClient) -> None:
    response = client.post(
        "/v1/events/otlp/v1/traces",
        json={
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": {"stringValue": "agent-service"}},
                            {"key": "deployment.environment", "value": {"stringValue": "staging"}},
                        ],
                    },
                    "scopeSpans": [
                        {
                            "spans": [
                                {
                                    "traceId": "trace-otlp-1",
                                    "spanId": "span-1",
                                    "attributes": [
                                        {"key": "zroky.workflow.name", "value": {"stringValue": "support-flow"}},
                                        {"key": "zroky.agent.name", "value": {"stringValue": "agent-otlp"}},
                                    ],
                                },
                            ],
                        },
                    ],
                },
            ],
        },
    )
    assert response.status_code == 202
    body = response.json()
    assert body["accepted"] is True
    assert body["count"] == 1

    fetched = client.get(f"/v1/runs/{body['ids'][0]}")
    assert fetched.status_code == 200
    run = fetched.json()
    assert run["environment"] == "staging"
    assert run["external_run_id"] == "trace-otlp-1"
    assert run["workflow_key"] == "support-flow"


def test_mcp_tool_import_creates_untrusted_capability_draft(client: TestClient) -> None:
    response = client.post(
        "/v1/events/mcp/tools/import",
        json={
            "environment": "production",
            "source_ref": "mcp://demo",
            "tools": [
                {
                    "name": "stripe.refund",
                    "description": "Issue a Stripe refund",
                    "inputSchema": {"type": "object", "properties": {"payment_id": {"type": "string"}}},
                },
            ],
        },
    )
    assert response.status_code == 201
    item = response.json()["imported"][0]
    assert item["capability_key"] == "stripe.refund"
    assert item["trust_status"] == "draft_untrusted"
    assert item["trusted_for_recovery"] is False


def test_a2a_agent_card_import_creates_untrusted_capability_draft(client: TestClient) -> None:
    response = client.post(
        "/v1/events/a2a/agent-card/import",
        json={
            "environment": "production",
            "source_ref": "https://agent.example/.well-known/agent-card.json",
            "card": {
                "name": "refund-agent",
                "description": "Handles refund workflows",
                "skills": [
                    {"id": "refund.create", "name": "Create refund", "description": "Draft a refund"},
                    {"id": "refund.status", "name": "Refund status"},
                ],
            },
        },
    )
    assert response.status_code == 201
    imported = response.json()["imported"]
    assert [item["capability_key"] for item in imported] == ["refund.create", "refund.status"]
    assert {item["trust_status"] for item in imported} == {"draft_untrusted"}
    assert {item["trusted_for_recovery"] for item in imported} == {False}


def test_final_evidence_bundle_export_stores_redacted_payload(client: TestClient) -> None:
    response = client.post(
        "/v1/evidence/bundles",
        json={
            "environment": "production",
            "subject_type": "run",
            "subject_id": "run_1",
            "bundle": {
                "schema_version": "zroky.final_evidence_bundle.v1",
                "intent": {},
                "policy": {},
                "observations": [],
                "snapshot": {
                    "summary": "Customer alice@example.com requested refund",
                },
                "incident": {},
                "recovery": {},
                "customer_email": "alice@example.com",
                "api_key": "sk-test-secret-that-must-not-leak",
            },
        },
    )
    assert response.status_code == 201, response.text
    bundle = response.json()["bundle"]
    assert bundle["customer_email"] == "[REDACTED_EMAIL]"
    assert bundle["api_key"] == "[REDACTED_KEY]"
    assert bundle["snapshot"]["summary"] == "Customer [REDACTED_EMAIL] requested refund"
    assert "alice@example.com" not in str(bundle)
    assert "sk-test-secret" not in str(bundle)

    fetched = client.get(f"/v1/evidence/bundles/{response.json()['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["bundle"] == bundle


def test_workflow_assurance_pack_schema_and_immutable_version(client: TestClient) -> None:
    client.tenant_role["value"] = "admin"
    pack = {
        "schema_version": "zroky.workflow_assurance_pack.v1",
        "workflow_key": "refund-workflow",
        "version": "1.0.0",
        "intent_schema": {"type": "object"},
        "object_types": [{"key": "refund", "schema": {"type": "object"}}],
        "effects": [{"key": "refund_created", "object_type": "refund", "predicate": "refund.status == 'created'"}],
        "source_bindings": [
            {
                "key": "stripe_refund_read",
                "connector_capability": "stripe.refund.read",
                "object_type": "refund",
                "freshness_seconds": 300,
            }
        ],
        "recovery_playbooks": [{"key": "retry_refund", "incident_type": "missing_refund", "steps": []}],
    }

    valid = client.post("/v1/assurance-packs/validate", json={"pack": pack})
    assert valid.status_code == 200
    assert valid.json()["valid"] is True

    created = client.post("/v1/assurance-packs", json={"environment": "production", "pack": pack})
    assert created.status_code == 201
    body = created.json()
    assert body["workflow_key"] == "refund-workflow"
    assert body["version"] == "1.0.0"
    assert body["pack_digest"]

    replay = client.post("/v1/assurance-packs", json={"environment": "production", "pack": pack})
    assert replay.status_code == 201
    assert replay.json()["id"] == body["id"]

    changed = {**pack, "effects": [{**pack["effects"][0], "predicate": "false"}]}
    conflict = client.post("/v1/assurance-packs", json={"environment": "production", "pack": changed})
    assert conflict.status_code == 409

    fetched = client.get(f"/v1/assurance-packs/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["pack"] == pack

    playbooks = client.get("/v1/recovery/playbooks")
    assert playbooks.status_code == 200
    item = playbooks.json()["items"][0]
    assert item["workflow_key"] == "refund-workflow"
    assert item["version"] == "1.0.0"
    assert item["key"] == "retry_refund"
    assert item["incident_type"] == "missing_refund"
    assert item["playbook_digest"].startswith("sha256:")

    fetched_playbook = client.get("/v1/recovery/playbooks/refund-workflow/1.0.0/retry_refund")
    assert fetched_playbook.status_code == 200
    assert fetched_playbook.json()["playbook_digest"] == item["playbook_digest"]


def test_new_workflow_shape_publishes_without_backend_code_change(client: TestClient) -> None:
    client.tenant_role["value"] = "admin"
    pack = {
        "schema_version": "zroky.workflow_assurance_pack.v1",
        "workflow_key": "procurement-approval-branching",
        "version": "1.0.0",
        "intent_schema": {"type": "object", "required": ["purchase_request_id"]},
        "object_types": [
            {"key": "purchase_request", "schema": {"type": "object"}},
            {"key": "vendor_risk", "schema": {"type": "object"}},
        ],
        "effects": [
            {
                "key": "purchase_request_approved",
                "object_type": "purchase_request",
                "predicate": "purchase_request.status == 'approved'",
            },
            {
                "key": "vendor_risk_checked",
                "object_type": "vendor_risk",
                "predicate": "vendor_risk.level != 'blocked'",
            },
        ],
        "source_bindings": [
            {
                "key": "erp_purchase_request",
                "connector_capability": "erp.purchase_request.read",
                "object_type": "purchase_request",
                "freshness_seconds": 300,
            },
            {
                "key": "grc_vendor_risk",
                "connector_capability": "grc.vendor_risk.read",
                "object_type": "vendor_risk",
                "freshness_seconds": 900,
            },
        ],
        "recovery_playbooks": [
            {
                "key": "rollback_purchase_request",
                "incident_type": "unauthorized_procurement_approval",
                "steps": [{"kind": "notify_owner"}, {"kind": "reverse_approval"}],
            }
        ],
    }

    valid = client.post("/v1/assurance-packs/validate", json={"pack": pack})
    assert valid.status_code == 200, valid.text
    assert valid.json()["valid"] is True

    created = client.post("/v1/assurance-packs", json={"environment": "production", "pack": pack})
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["workflow_key"] == "procurement-approval-branching"
    assert body["pack"]["source_bindings"][1]["connector_capability"] == "grc.vendor_risk.read"

    playbooks = client.get("/v1/recovery/playbooks")
    assert playbooks.status_code == 200, playbooks.text
    assert playbooks.json()["items"][0]["workflow_key"] == "procurement-approval-branching"


def test_assurance_pack_predicate_evaluator_is_bounded(client: TestClient) -> None:
    allowed = client.post(
        "/v1/assurance-packs/predicates/evaluate",
        json={
            "predicate": "refund.status == 'created' && refund.amount <= 100",
            "context": {"refund": {"status": "created", "amount": 42}},
        },
    )
    assert allowed.status_code == 200
    assert allowed.json()["result"] is True

    denied = client.post(
        "/v1/assurance-packs/predicates/evaluate",
        json={
            "predicate": "refund.status == 'created' && refund.amount <= 100",
            "context": {"refund": {"status": "created", "amount": 142}},
        },
    )
    assert denied.status_code == 200
    assert denied.json()["result"] is False

    unsafe = client.post(
        "/v1/assurance-packs/predicates/evaluate",
        json={"predicate": "__import__('os').system('echo bad')", "context": {}},
    )
    assert unsafe.status_code == 422


def test_assurance_pack_simulation_covers_required_cases(client: TestClient) -> None:
    pack = {
        "schema_version": "zroky.workflow_assurance_pack.v1",
        "workflow_key": "refund-workflow",
        "version": "1.0.0",
        "object_types": [{"key": "refund", "schema": {"type": "object"}}],
        "effects": [{"key": "refund_created", "object_type": "refund", "predicate": "refund.status == 'created'"}],
        "source_bindings": [
            {
                "key": "stripe_refund_read",
                "connector_capability": "stripe.refund.read",
                "object_type": "refund",
                "freshness_seconds": 300,
            }
        ],
    }
    response = client.post(
        "/v1/assurance-packs/simulate",
        json={
            "pack": pack,
            "cases": {
                "success": {"objects": {"refund": {"status": "created"}}},
                "missing": {"objects": {}},
                "wrong": {"objects": {"refund": {"status": "failed"}}},
                "duplicate": {"objects": {"refund": {"status": "created"}}},
                "stale": {"objects": {"refund": {"status": "created"}}, "stale_bindings": ["stripe_refund_read"]},
                "conflict": {"objects": {"refund": {"status": "created"}}, "conflicts": ["refund.status"]},
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["missing_cases"] == []
    assert body["results"]["success"]["passed"] is True
    assert body["results"]["missing"]["failures"] == ["missing:refund"]
    assert body["results"]["wrong"]["failures"] == ["wrong:refund_created"]
    assert body["results"]["stale"]["failures"] == ["stale:stripe_refund_read"]
    assert body["results"]["conflict"]["failures"] == ["conflict:refund.status"]


def test_customer_read_relay_prepare_command_is_tenant_scoped_and_digest_bound(client: TestClient) -> None:
    response = client.post(
        "/v1/relay-protocol/read-commands/prepare",
        json={
            "environment": "Production",
            "source_binding": "ledger_refunds",
            "connector_capability": "refund.read",
            "object_ref": "refund:rf_123",
            "selector": {"refund_id": "rf_123"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "zroky.customer_read_relay.v1"
    assert body["project_id"] == "proj_test"
    assert body["environment"] == "production"
    assert body["operation"] == "read"
    assert body["command_digest"]
    assert "url" not in body


def test_customer_read_relay_command_rejects_transport_or_secret_fields(client: TestClient) -> None:
    response = client.post(
        "/v1/relay-protocol/read-commands/prepare",
        json={
            "source_binding": "ledger_refunds",
            "connector_capability": "refund.read",
            "object_ref": "refund:rf_123",
            "selector": {"url": "https://ledger.example/refunds/rf_123", "token": "secret"},
        },
    )

    assert response.status_code == 422


def test_immutable_observation_create_read_and_digest_replay(client: TestClient) -> None:
    payload = {
        "environment": "Production",
        "source_kind": "generic_rest",
        "observed_object_ref": "refund:rf_123",
        "observed_state": {"refund_id": "rf_123", "status": "posted"},
        "provenance": {
            "source_binding": "ledger_refunds",
            "connector_capability": "refund.read",
            "command_digest": "digest_1",
        },
        "observed_at": "2026-07-21T10:00:00Z",
        "read_at": "2026-07-21T10:01:00Z",
        "max_freshness_seconds": 300,
    }

    created = client.post("/v1/observations", json=payload)
    assert created.status_code == 201
    body = created.json()
    assert body["project_id"] == "proj_test"
    assert body["environment"] == "production"
    assert body["observation"]["observed_state"] == payload["observed_state"]
    assert body["observation"]["provenance"]["command_digest"] == "digest_1"
    assert body["observation"]["freshness"] == {
        "age_seconds": 60,
        "max_freshness_seconds": 300,
        "fresh": True,
    }

    replay = client.post("/v1/observations", json=payload)
    assert replay.status_code == 201
    assert replay.json()["id"] == body["id"]

    fetched = client.get(f"/v1/observations/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["observation_digest"] == body["observation_digest"]


def test_observation_marks_stale_authoritative_read(client: TestClient) -> None:
    response = client.post(
        "/v1/observations",
        json={
            "source_kind": "postgres_read",
            "observed_object_ref": "refund:rf_stale",
            "observed_state": {"refund_id": "rf_stale", "status": "posted"},
            "provenance": {"source_binding": "finance_db"},
            "observed_at": "2026-07-21T10:00:00Z",
            "read_at": "2026-07-21T10:10:00Z",
            "max_freshness_seconds": 300,
        },
    )

    assert response.status_code == 201
    freshness = response.json()["observation"]["freshness"]
    assert freshness["age_seconds"] == 600
    assert freshness["fresh"] is False


def test_outcome_graph_snapshot_builds_expected_vs_actual_effects(client: TestClient) -> None:
    intent = client.post(
        "/v1/intents",
        json={"intent": {"refund_id": "rf_graph"}},
        headers={"Idempotency-Key": "graph-intent-1"},
    ).json()
    run = client.post(
        "/v1/runs",
        json={
            "intent_id": intent["id"],
            "workflow_key": "refund-workflow",
            "run": {"trace_id": "trace_graph"},
        },
        headers={"Idempotency-Key": "graph-run-1"},
    ).json()
    client.tenant_role["value"] = "admin"
    pack = {
        "schema_version": "zroky.workflow_assurance_pack.v1",
        "workflow_key": "refund-workflow",
        "version": "1.0.0",
        "object_types": [{"key": "refund", "schema": {"type": "object"}}],
        "effects": [{"key": "refund_posted", "object_type": "refund", "predicate": "refund.status == 'posted'"}],
        "source_bindings": [
            {
                "key": "ledger_refunds",
                "connector_capability": "refund.read",
                "object_type": "refund",
                "freshness_seconds": 300,
            }
        ],
    }
    client.post("/v1/assurance-packs", json={"pack": pack})
    client.post(
        "/v1/observations",
        json={
            "intent_id": intent["id"],
            "source_kind": "generic_rest",
            "observed_object_ref": "refund:rf_graph",
            "observed_state": {"refund_id": "rf_graph", "status": "posted"},
            "provenance": {"source_binding": "ledger_refunds"},
            "observed_at": "2026-07-21T10:00:00Z",
            "read_at": "2026-07-21T10:00:05Z",
        },
    )

    response = client.post(f"/v1/runs/{run['id']}/outcome-graph", json={})

    assert response.status_code == 201
    graph = response.json()["graph"]
    assert graph["workflow_key"] == "refund-workflow"
    assert graph["expected_effects"] == [
        {"effect_key": "refund_posted", "object_type": "refund", "predicate": "refund.status == 'posted'"}
    ]
    assert graph["actual_effects"][0]["matched"] is True
    assert graph["actual_effects"][0]["observed"] is True
    assert graph["classification"] == "verified"
    assert response.json()["verification_status"] == "verified"


def test_non_verified_outcome_graph_creates_open_incident(client: TestClient) -> None:
    intent = client.post(
        "/v1/intents",
        json={"intent": {"refund_id": "rf_bad"}},
        headers={"Idempotency-Key": "incident-intent-1"},
    ).json()
    run = client.post(
        "/v1/runs",
        json={"intent_id": intent["id"], "workflow_key": "incident-workflow", "run": {}},
        headers={"Idempotency-Key": "incident-run-1"},
    ).json()
    client.tenant_role["value"] = "admin"
    client.post(
        "/v1/assurance-packs",
        json={
            "pack": {
                "schema_version": "zroky.workflow_assurance_pack.v1",
                "workflow_key": "incident-workflow",
                "version": "1.0.0",
                "object_types": [{"key": "refund", "schema": {"type": "object"}}],
                "effects": [{"key": "refund_posted", "object_type": "refund", "predicate": "refund.status == 'posted'"}],
                "source_bindings": [
                    {
                        "key": "ledger_refunds",
                        "connector_capability": "refund.read",
                        "object_type": "refund",
                        "freshness_seconds": 300,
                    }
                ],
            }
        },
    )
    client.post(
        "/v1/observations",
        json={
            "intent_id": intent["id"],
            "source_kind": "generic_rest",
            "observed_object_ref": "refund:rf_bad",
            "observed_state": {"refund_id": "rf_bad", "status": "failed"},
            "provenance": {"source_binding": "ledger_refunds"},
            "observed_at": "2026-07-21T10:00:00Z",
            "read_at": "2026-07-21T10:00:05Z",
        },
    )

    graph_response = client.post(f"/v1/runs/{run['id']}/outcome-graph", json={})
    assert graph_response.status_code == 201
    assert graph_response.json()["graph"]["classification"] == "wrong"
    assert graph_response.json()["verification_status"] == "failed"

    incidents = client.get("/v1/incidents")
    assert incidents.status_code == 200
    body = incidents.json()
    assert len(body) == 1
    assert body[0]["outcome_graph_id"] == graph_response.json()["id"]
    assert body[0]["status"] == "open"
    assert body[0]["severity"] == "high"
    assert body[0]["incident"]["deviation_type"] == "wrong"
    assert body[0]["incident"]["owner_path"] == ["operations", "workflow_owner"]

    fetched = client.get(f"/v1/incidents/{body[0]['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == body[0]["id"]


def test_incident_recovery_execution_queues_customer_executor(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    intent = client.post(
        "/v1/intents",
        json={"intent": {"refund_id": "rf_recover"}},
        headers={"Idempotency-Key": "recover-intent-1"},
    ).json()
    client.tenant_role["value"] = "admin"
    approval_gate = client.post(
        "/v1/policy/check",
        json={"intent_id": intent["id"], "decision": "approval_required", "reason": "recovery workflow validation"},
    )
    assert approval_gate.status_code == 201, approval_gate.text
    assert approval_gate.json()["decision"] == "approval_required"
    assert approval_gate.json()["approval_requirements"][0]["binding_digest"]
    run = client.post(
        "/v1/runs",
        json={"intent_id": intent["id"], "workflow_key": "recover-workflow", "run": {}},
        headers={"Idempotency-Key": "recover-run-1"},
    ).json()
    client.post(
        "/v1/assurance-packs",
        json={
            "pack": {
                "schema_version": "zroky.workflow_assurance_pack.v1",
                "workflow_key": "recover-workflow",
                "version": "1.0.0",
                "object_types": [{"key": "refund", "schema": {"type": "object"}}],
                "effects": [{"key": "refund_posted", "object_type": "refund", "predicate": "refund.status == 'posted'"}],
                "source_bindings": [
                    {
                        "key": "ledger_refunds",
                        "connector_capability": "refund.read",
                        "object_type": "refund",
                        "freshness_seconds": 300,
                    }
                ],
            }
        },
    )
    client.post(
        "/v1/observations",
        json={
            "intent_id": intent["id"],
            "source_kind": "generic_rest",
            "observed_object_ref": "refund:rf_recover",
            "observed_state": {"refund_id": "rf_recover", "status": "failed"},
            "provenance": {"source_binding": "ledger_refunds"},
            "observed_at": "2026-07-21T10:00:00Z",
            "read_at": "2026-07-21T10:00:05Z",
        },
    )
    client.post(f"/v1/runs/{run['id']}/outcome-graph", json={})
    incident = client.get("/v1/incidents").json()[0]

    client.post(f"/v1/incidents/{incident['id']}/assign", json={"owner": "tester"})
    client.tenant_role["value"] = "admin"
    same_owner = client.post(
        f"/v1/incidents/{incident['id']}/execute-recovery",
        json={"executor_ref": "customer-recovery-executor://ops/refund", "plan": {"step": "retry_refund"}},
        headers={"Idempotency-Key": "recover-exec-same-owner"},
    )
    assert same_owner.status_code == 409
    client.post(f"/v1/incidents/{incident['id']}/assign", json={"owner": "ops-lead"})

    client.tenant_role["value"] = "member"
    forbidden = client.post(
        f"/v1/incidents/{incident['id']}/execute-recovery",
        json={"executor_ref": "customer-recovery-executor://ops/refund", "plan": {"step": "retry_refund"}},
        headers={"Idempotency-Key": "recover-exec-1"},
    )
    assert forbidden.status_code == 403

    client.tenant_role["value"] = "admin"
    dispatched = client.post(
        f"/v1/incidents/{incident['id']}/execute-recovery",
        json={"executor_ref": "customer-recovery-executor://ops/refund", "plan": {"step": "retry_refund"}},
        headers={"Idempotency-Key": "recover-exec-1"},
    )
    assert dispatched.status_code == 201, dispatched.text
    body = dispatched.json()
    assert body["execution_status"] == "dispatched"
    assert body["incident"]["status"] == "recovering"
    assert body["incident"]["incident"]["recovery_execution"]["executor_ref"] == "customer-recovery-executor://ops/refund"
    with client._session_factory() as session:  # type: ignore[attr-defined]
        audit = session.query(AuditLog).filter_by(tenant_id="proj_test", diagnosis_id=incident["id"]).one()
        assert audit.action == "recovery_execute_requested"
        assert json.loads(audit.metadata_json)["executor_ref"] == "customer-recovery-executor://ops/refund"

    replay = client.post(
        f"/v1/incidents/{incident['id']}/execute-recovery",
        json={"executor_ref": "customer-recovery-executor://ops/refund", "plan": {"step": "retry_refund"}},
        headers={"Idempotency-Key": "recover-exec-1"},
    )
    assert replay.status_code == 201
    assert replay.json()["recovery_plan_id"] == body["recovery_plan_id"]
    assert replay.json()["outbox_job_id"] == body["outbox_job_id"]

    claim = client.post(
        "/v1/recovery/dispatch/claim",
        json={"executor_ref": "customer-recovery-executor://ops/refund", "lease_seconds": 300},
    )
    assert claim.status_code == 200, claim.text
    dispatch = claim.json()
    assert dispatch["outbox_job_id"] == body["outbox_job_id"]
    assert dispatch["recovery_plan_id"] == body["recovery_plan_id"]
    assert dispatch["executor_ref"] == "customer-recovery-executor://ops/refund"
    assert dispatch["nonce"]
    assert dispatch["fencing_token"].startswith(f"{body['outbox_job_id']}:1")
    assert dispatch["signed_payload"]["nonce"] == dispatch["nonce"]
    assert dispatch["signature"]

    replay_claim = client.post(
        "/v1/recovery/dispatch/claim",
        json={"executor_ref": "customer-recovery-executor://ops/refund", "lease_seconds": 300},
    )
    assert replay_claim.status_code == 404

    client.post(
        "/v1/observations",
        json={
            "intent_id": intent["id"],
            "source_kind": "generic_rest",
            "observed_object_ref": "refund:rf_recover",
            "observed_state": {"refund_id": "rf_recover", "status": "posted"},
            "provenance": {"source_binding": "ledger_refunds"},
            "observed_at": "2026-07-21T10:10:00Z",
            "read_at": "2026-07-21T10:10:05Z",
        },
    )

    class ExpiredLeaseDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz or UTC) + timedelta(hours=1)

    import app.api.routes.recovery as recovery_routes

    monkeypatch.setattr(recovery_routes, "datetime", ExpiredLeaseDateTime)
    reconstructed = client.post(
        "/v1/recovery/dispatch/reconstruct-unknown",
        json={"outbox_job_id": body["outbox_job_id"]},
    )
    assert reconstructed.status_code == 200, reconstructed.text
    reconstruction = reconstructed.json()
    assert reconstruction["outbox_job_id"] == body["outbox_job_id"]
    assert reconstruction["recovery_plan_id"] == body["recovery_plan_id"]
    assert reconstruction["reconstruction_status"] == "verified"
    assert reconstruction["recovery_execution_status"] == "succeeded"
    assert reconstruction["incident_status"] == "resolved"


def test_recovery_plan_compiler_excludes_already_satisfied_effects(client: TestClient) -> None:
    intent = client.post(
        "/v1/intents",
        json={"intent": {"refund_id": "rf_compile"}},
        headers={"Idempotency-Key": "compile-intent-1"},
    ).json()
    run = client.post(
        "/v1/runs",
        json={"intent_id": intent["id"], "workflow_key": "compile-workflow", "run": {}},
        headers={"Idempotency-Key": "compile-run-1"},
    ).json()
    client.tenant_role["value"] = "admin"
    client.post(
        "/v1/assurance-packs",
        json={
            "pack": {
                "schema_version": "zroky.workflow_assurance_pack.v1",
                "workflow_key": "compile-workflow",
                "version": "1.0.0",
                "object_types": [
                    {"key": "refund", "schema": {"type": "object"}},
                    {"key": "email", "schema": {"type": "object"}},
                ],
                "effects": [
                    {"key": "refund_posted", "object_type": "refund", "predicate": "refund.status == 'posted'"},
                    {"key": "email_sent", "object_type": "email", "predicate": "email.status == 'sent'"},
                ],
                "source_bindings": [
                    {
                        "key": "ledger_refunds",
                        "connector_capability": "refund.read",
                        "object_type": "refund",
                        "freshness_seconds": 300,
                    },
                    {
                        "key": "email_events",
                        "connector_capability": "email.read",
                        "object_type": "email",
                        "freshness_seconds": 300,
                    },
                ],
                "recovery_playbooks": [
                    {
                        "key": "finish_customer_notification",
                        "incident_type": "missing",
                        "steps": [
                            {"effect_key": "refund_posted", "operation": "do_not_repeat_refund"},
                            {"effect_key": "email_sent", "operation": "send_customer_email"},
                        ],
                    }
                ],
            }
        },
    )
    client.post(
        "/v1/observations",
        json={
            "intent_id": intent["id"],
            "source_kind": "generic_rest",
            "observed_object_ref": "refund:rf_compile",
            "observed_state": {"refund_id": "rf_compile", "status": "posted"},
            "provenance": {"source_binding": "ledger_refunds"},
            "observed_at": "2026-07-21T10:00:00Z",
            "read_at": "2026-07-21T10:00:05Z",
        },
    )
    graph = client.post(f"/v1/runs/{run['id']}/outcome-graph", json={}).json()
    assert graph["verification_status"] == "failed"
    incident = client.get("/v1/incidents").json()[0]

    compiled = client.post(
        "/v1/recovery/compile-plan",
        json={"incident_id": incident["id"], "playbook_key": "finish_customer_notification"},
    )

    assert compiled.status_code == 200, compiled.text
    body = compiled.json()
    assert body["included_effects"] == ["email_sent"]
    assert body["skipped_effects"] == ["refund_posted"]
    assert body["plan"]["target_effects"] == ["email_sent"]
    assert body["plan"]["steps"] == [{"effect_key": "email_sent", "operation": "send_customer_email"}]
    assert body["plan_digest"].startswith("sha256:")


def test_final_evidence_bundle_requires_final_sections(client: TestClient) -> None:
    bundle = {
        "intent": {"id": "intent_1"},
        "policy": {"decision": "allowed"},
        "observations": [{"id": "obs_1"}],
        "snapshot": {"classification": "verified"},
        "incident": {"id": "incident_1"},
        "recovery": {"status": "succeeded"},
    }
    created = client.post(
        "/v1/evidence/bundles",
        json={"subject_type": "incident", "subject_id": "incident_1", "bundle": bundle},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["bundle"]["schema_version"] == "zroky.final_evidence_bundle.v1"
    assert body["bundle"]["intent"] == {"id": "intent_1"}
    assert len(body["bundle_digest"]) == 64
    assert body["signature"]["payload_digest"] == f"sha256:{body['bundle_digest']}"
    assert body["signature"]["payload_type"] == "application/vnd.zroky.final-evidence-bundle+json"
    from app.services.action_receipts import verify_receipt_json_with_public_key

    assert verify_receipt_json_with_public_key(
        receipt_json=json.dumps(body["bundle"], sort_keys=True, separators=(",", ":"), default=str),
        signature=body["signature"]["signature"],
        public_key=body["signature"]["public_key"],
    )
    verified = client.get(f"/v1/evidence/bundles/{body['id']}/verify")
    assert verified.status_code == 200
    assert verified.json()["verification_status"] == "pass"

    with client._session_factory() as session:  # type: ignore[attr-defined]
        row = session.get(FinalEvidenceBundle, body["id"])
        assert row is not None
        tampered = json.loads(row.bundle_json)
        tampered["recovery"] = {"status": "tampered"}
        row.bundle_json = json.dumps(tampered, sort_keys=True, separators=(",", ":"), default=str)
        session.commit()
    tamper_check = client.get(f"/v1/evidence/bundles/{body['id']}/verify")
    assert tamper_check.status_code == 200
    assert tamper_check.json()["verification_status"] == "fail"

    rejected = client.post(
        "/v1/evidence/bundles",
        json={"subject_type": "incident", "subject_id": "incident_2", "bundle": {**bundle, "recovery": "missing"}},
    )
    assert rejected.status_code == 400


def test_manual_incident_resolution_requires_fresh_verified_graph(client: TestClient) -> None:
    intent = client.post(
        "/v1/intents",
        json={"intent": {"refund_id": "rf_manual"}},
        headers={"Idempotency-Key": "manual-intent-1"},
    ).json()
    run = client.post(
        "/v1/runs",
        json={"intent_id": intent["id"], "workflow_key": "manual-workflow", "run": {}},
        headers={"Idempotency-Key": "manual-run-1"},
    ).json()
    client.tenant_role["value"] = "admin"
    client.post(
        "/v1/assurance-packs",
        json={
            "pack": {
                "schema_version": "zroky.workflow_assurance_pack.v1",
                "workflow_key": "manual-workflow",
                "version": "1.0.0",
                "object_types": [{"key": "refund", "schema": {"type": "object"}}],
                "effects": [{"key": "refund_posted", "object_type": "refund", "predicate": "refund.status == 'posted'"}],
                "source_bindings": [
                    {
                        "key": "ledger_refunds",
                        "connector_capability": "refund.read",
                        "object_type": "refund",
                        "freshness_seconds": 300,
                    }
                ],
            }
        },
    )
    client.post(
        "/v1/observations",
        json={
            "intent_id": intent["id"],
            "source_kind": "generic_rest",
            "observed_object_ref": "refund:rf_manual",
            "observed_state": {"refund_id": "rf_manual", "status": "failed"},
            "provenance": {"source_binding": "ledger_refunds"},
            "observed_at": "2026-07-21T10:00:00Z",
            "read_at": "2026-07-21T10:00:05Z",
        },
    )
    failed_graph = client.post(f"/v1/runs/{run['id']}/outcome-graph", json={}).json()
    incident = client.get("/v1/incidents").json()[0]

    assign = client.post(f"/v1/incidents/{incident['id']}/assign", json={"owner": "ops@example.com"})
    assert assign.status_code == 200
    assert assign.json()["incident"]["owner"] == "ops@example.com"

    blocked = client.post(
        f"/v1/incidents/{incident['id']}/resolve-manually",
        json={"verified_outcome_graph_id": failed_graph["id"], "note": "fixed"},
    )
    assert blocked.status_code == 409

    client.post(
        "/v1/observations",
        json={
            "intent_id": intent["id"],
            "source_kind": "generic_rest",
            "observed_object_ref": "refund:rf_manual",
            "observed_state": {"refund_id": "rf_manual", "status": "posted"},
            "provenance": {"source_binding": "ledger_refunds"},
            "observed_at": "2026-07-21T10:01:00Z",
            "read_at": "2026-07-21T10:01:05Z",
        },
    )
    verified_graph = client.post(f"/v1/runs/{run['id']}/outcome-graph", json={}).json()
    assert verified_graph["verification_status"] == "verified"

    resolved = client.post(
        f"/v1/incidents/{incident['id']}/resolve-manually",
        json={"verified_outcome_graph_id": verified_graph["id"], "note": "manual fix verified"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"
    assert resolved.json()["incident"]["manual_resolution"]["verified_outcome_graph_id"] == verified_graph["id"]
