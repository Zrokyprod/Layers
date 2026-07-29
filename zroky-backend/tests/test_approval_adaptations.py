from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.core.config import get_settings
from app.db.base import Base
from app.db.models import ActionIntent, RuntimePolicyDecision
from app.db.session import get_db_session, get_db_session_read
from app.main import app
from app.services.action_kernel import build_runtime_policy_payload, decide_action_intent
from app.services.approval_adaptations import revoke_active_rules_for_proof_failure
from app.services.pilot import DEFAULT_POLICY, upsert_policy
from app.services.runtime_policy import evaluate_runtime_policy


PROJECT_ID = "proj_approval_adaptation"


@pytest.fixture()
def client(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'approval_adaptation.db'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    state = {"role": "owner", "subject": "owner-1"}

    def override_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    def override_tenant():
        return TenantContext(tenant_id=PROJECT_ID, role=state["role"], subject=state["subject"])

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_db_session_read] = override_db
    app.dependency_overrides[require_tenant_context] = override_tenant
    with TestClient(app) as test_client:
        test_client._session_factory = factory  # type: ignore[attr-defined]
        test_client._tenant_state = state  # type: ignore[attr-defined]
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _seed_policy(client: TestClient) -> None:
    with client._session_factory() as session:  # type: ignore[attr-defined]
        policy = dict(DEFAULT_POLICY)
        policy["runtime_sensitive_tools"] = ["customer_update"]
        policy["runtime_sensitive_actions_require_approval"] = True
        upsert_policy(session, project_id=PROJECT_ID, payload=policy, updated_by="test")


def _action(*, suffix: str, proof_status: str = "matched", operation_kind: str = "UPDATE") -> ActionIntent:
    return ActionIntent(
        id=f"intent-{suffix}",
        project_id=PROJECT_ID,
        agent_id="agent-1",
        contract_version_id="contract-version-1",
        contract_key="crm.customer.update",
        contract_version="1.0",
        action_type="customer_update",
        operation_kind=operation_kind,
        environment="production",
        idempotency_key=f"idem-{suffix}",
        intent_digest=f"digest-{suffix}",
        canonical_intent_json="{}",
        principal_json=json.dumps({"id": "agent-1", "type": "agent"}),
        actor_chain_json=json.dumps([{ "id": "agent-1", "type": "agent" }]),
        purpose_json=json.dumps({"summary": "Correct customer address"}),
        resource_json=json.dumps({"id": "customer-42", "type": "customer"}),
        parameters_json=json.dumps({"address": "verified-address"}),
        trace_context_json=json.dumps({"agent_name": "agent-1"}),
        status="authorized" if proof_status else "validated",
        proof_status=proof_status or "not_started",
        receipt_status="generated" if proof_status == "matched" else "missing",
    )


def _seed_human_approved_evidence(
    client: TestClient,
    *,
    count: int = 5,
    mismatched_index: int | None = None,
    operation_kind: str = "UPDATE",
) -> None:
    with client._session_factory() as session:  # type: ignore[attr-defined]
        for index in range(count):
            approval_id = f"approval-{operation_kind.lower()}-{index}"
            allowed_id = f"allowed-{operation_kind.lower()}-{index}"
            proof_status = "mismatched" if index == mismatched_index else "matched"
            action = _action(
                suffix=f"{operation_kind.lower()}-{index}",
                proof_status=proof_status,
                operation_kind=operation_kind,
            )
            action.runtime_policy_decision_id = allowed_id
            session.add(
                RuntimePolicyDecision(
                    id=approval_id,
                    project_id=PROJECT_ID,
                    decision="requires_approval",
                    status="approved",
                    reasons_json="[]",
                    required_approval_count=1,
                    approval_count=1,
                    approver_subjects_json=json.dumps(["owner-1"]),
                )
            )
            session.add(
                RuntimePolicyDecision(
                    id=allowed_id,
                    project_id=PROJECT_ID,
                    decision="allow",
                    status="allowed",
                    reasons_json="[]",
                    request_json=json.dumps({"approval_id": approval_id}),
                    required_approval_count=0,
                    approval_count=0,
                    approver_subjects_json="[]",
                )
            )
            session.add(action)
        session.commit()


def _add_new_action(client: TestClient, suffix: str) -> ActionIntent:
    action = _action(suffix=suffix, proof_status="")
    with client._session_factory() as session:  # type: ignore[attr-defined]
        session.add(action)
        session.commit()
        session.refresh(action)
        return action


def test_verified_pattern_requires_owner_activation_and_flag(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_policy(client)
    _seed_human_approved_evidence(client)

    recommendations = client.get("/v1/approval-adaptations/recommendations")
    assert recommendations.status_code == 200
    body = recommendations.json()
    assert body["enforcement_enabled"] is False
    assert len(body["items"]) == 1
    candidate = body["items"][0]
    assert candidate["approved_count"] == 5
    assert candidate["matched_count"] == 5
    assert candidate["operation_kind"] == "UPDATE"

    client._tenant_state["role"] = "admin"  # type: ignore[attr-defined]
    assert client.post(
        f"/v1/approval-adaptations/recommendations/{candidate['scope_hash']}/activate",
        json={"duration_days": 30},
    ).status_code == 403
    client._tenant_state["role"] = "owner"  # type: ignore[attr-defined]

    activated = client.post(
        f"/v1/approval-adaptations/recommendations/{candidate['scope_hash']}/activate",
        json={"duration_days": 30},
    )
    assert activated.status_code == 201, activated.text
    rule = activated.json()
    assert rule["status"] == "active"
    assert rule["enforcement_enabled"] is False

    without_flag = _add_new_action(client, "without-flag")
    with client._session_factory() as session:  # type: ignore[attr-defined]
        result = evaluate_runtime_policy(
            session,
            project_id=PROJECT_ID,
            payload=build_runtime_policy_payload(without_flag),
            allow_approval_adaptation=True,
        )
    assert result.requires_approval is True

    monkeypatch.setenv("APPROVAL_ADAPTATION_ENABLED", "true")
    get_settings.cache_clear()
    try:
        with_flag = _add_new_action(client, "with-flag")
        with client._session_factory() as session:  # type: ignore[attr-defined]
            direct_result = evaluate_runtime_policy(
                session,
                project_id=PROJECT_ID,
                payload=build_runtime_policy_payload(with_flag),
            )
        assert direct_result.requires_approval is True
        with client._session_factory() as session:  # type: ignore[attr-defined]
            result = decide_action_intent(
                session,
                project_id=PROJECT_ID,
                action_id=with_flag.id,
            )
        assert result.allowed is True
        assert result.requires_approval is False
        assert "bounded approval adaptation rule" in result.reasons[0]
        assert result.row.status == "authorized"
        assert rule["id"] in result.runtime_result.decision.policy_snapshot_json

        revoked = client.post(
            f"/v1/approval-adaptations/rules/{rule['id']}/revoke",
            json={"reason": "Observed a changed business process."},
        )
        assert revoked.status_code == 200
        assert revoked.json()["status"] == "revoked"

        after_revoke = _add_new_action(client, "after-revoke")
        with client._session_factory() as session:  # type: ignore[attr-defined]
            result = decide_action_intent(
                session,
                project_id=PROJECT_ID,
                action_id=after_revoke.id,
            )
        assert result.requires_approval is True
    finally:
        monkeypatch.delenv("APPROVAL_ADAPTATION_ENABLED", raising=False)
        get_settings.cache_clear()


def test_mismatch_and_high_risk_history_never_become_recommendations(client: TestClient) -> None:
    _seed_human_approved_evidence(client, mismatched_index=4)
    _seed_human_approved_evidence(client, operation_kind="TRANSFER")

    recommendations = client.get("/v1/approval-adaptations/recommendations")
    assert recommendations.status_code == 200
    assert recommendations.json()["items"] == []


@pytest.mark.parametrize("proof_status", ["mismatched", "not_verified"])
def test_final_proof_failure_automatically_revokes_matching_active_rule(
    client: TestClient,
    proof_status: str,
) -> None:
    _seed_human_approved_evidence(client)
    candidate = client.get("/v1/approval-adaptations/recommendations").json()["items"][0]
    rule = client.post(
        f"/v1/approval-adaptations/recommendations/{candidate['scope_hash']}/activate",
        json={"duration_days": 30},
    ).json()
    action = _add_new_action(client, "proof-mismatch")

    with client._session_factory() as session:  # type: ignore[attr-defined]
        current = session.get(ActionIntent, action.id)
        revoked = revoke_active_rules_for_proof_failure(
            session,
            intent=current,
            proof_status=proof_status,
        )
        revoked_ids = [row.id for row in revoked]
        session.commit()
    assert revoked_ids == [rule["id"]]

    listed = client.get("/v1/approval-adaptations/rules")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["status"] == "revoked"
    assert listed.json()["items"][0]["revoked_by_subject"] == f"system:proof-{proof_status}"
