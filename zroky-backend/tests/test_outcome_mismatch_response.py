from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.db.base import Base
from app.db.models import (
    ActionContractVersion,
    ActionIntent,
    ActionReceipt,
    ActionTimelineEvent,
    OutcomeMismatchResponse,
    OutcomeReconciliationCheck,
    Project,
    ProjectAlert,
)
from app.db.session import get_db_session, get_db_session_read
from app.main import app
from app.services.outcome_mismatch_response import (
    acknowledge_mismatch_response,
    get_mismatch_response,
    list_mismatch_responses,
    mismatch_response_to_dict,
    resolve_mismatch_response,
)
from app.services.outcome_reconciliation import (
    ApiRecordConnector,
    reconcile_outcome,
    sweep_pending_reconciliation_checks,
)


def _session_factory(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'outcome_mismatch_response.db'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with factory() as session:
        session.add(Project(id="proj-mismatch", name="Mismatch Project"))
        session.commit()
    return engine, factory


def _seed_action_intent(session) -> ActionIntent:
    intent = ActionIntent(
        id="intent-mismatch",
        project_id="proj-mismatch",
        contract_version_id="contract-version-mismatch",
        contract_key="payments.refund",
        contract_version="1.0",
        action_type="refund",
        operation_kind="UPDATE",
        environment="production",
        idempotency_key="intent-mismatch-key",
        intent_digest="sha256:intent-mismatch",
        canonical_intent_json="{}",
        principal_json="{}",
        actor_chain_json="[]",
        purpose_json="{}",
        resource_json="{}",
        parameters_json="{}",
        trace_context_json="{}",
        status="authorized",
    )
    session.add(intent)
    session.commit()
    return intent


def test_confirmed_mismatch_creates_one_evidence_case_and_one_alert(tmp_path: Path) -> None:
    engine, factory = _session_factory(tmp_path)
    try:
        with factory() as session:
            intent = _seed_action_intent(session)
            row = reconcile_outcome(
                session,
                project_id="proj-mismatch",
                action_type="refund",
                system_ref="stripe:re_123",
                action_intent_id=intent.id,
                claimed={"refund_id": "re_123", "amount_usd": 50, "currency": "USD"},
                connector=ApiRecordConnector(
                    record={"refund_id": "re_123", "amount_usd": 0, "currency": "USD"},
                    record_found=True,
                ),
                idempotency_key="mismatch-once",
            )

            assert row.verdict == "mismatched"
            responses = list_mismatch_responses(session, project_id="proj-mismatch")
            assert len(responses) == 1
            response = responses[0]
            rendered = mismatch_response_to_dict(session, response)
            assert rendered["status"] == "OPEN"
            assert rendered["remediation"]["execution_state"] == "not_started"
            assert rendered["remediation"]["requires_owner_approval"] is True
            assert rendered["evidence"]["comparison"]["mismatches"][0]["field"] == "amount_usd"
            assert rendered["action_intent_id"] == intent.id
            assert session.query(ProjectAlert).filter_by(tenant_id="proj-mismatch").count() == 1
            assert session.query(ActionTimelineEvent).filter_by(
                project_id="proj-mismatch",
                action_intent_id=intent.id,
                event_type="outcome_mismatch_detected",
            ).count() == 1

            response.created_at = datetime.now(timezone.utc) - timedelta(days=45)
            session.add(response)
            session.commit()
            assert list_mismatch_responses(
                session,
                project_id="proj-mismatch",
                since=datetime.now(timezone.utc) - timedelta(days=30),
            ) == []

            receipt = ActionReceipt(
                id="receipt-mismatch",
                project_id="proj-mismatch",
                action_intent_id=intent.id,
                receipt_digest="sha256:receipt-mismatch",
                receipt_json="{}",
                signature_algorithm="Ed25519",
                signature="test-signature",
                signing_key_id="test-key",
                generated_at=datetime.now(timezone.utc),
            )
            session.add(receipt)
            session.commit()
            assert mismatch_response_to_dict(session, response)["action_receipt_id"] == receipt.id

            repeated = reconcile_outcome(
                session,
                project_id="proj-mismatch",
                action_type="refund",
                system_ref="stripe:re_123",
                claimed={"refund_id": "re_123", "amount_usd": 50, "currency": "USD"},
                connector=ApiRecordConnector(
                    record={"refund_id": "re_123", "amount_usd": 0, "currency": "USD"},
                    record_found=True,
                ),
                idempotency_key="mismatch-once",
            )
            assert repeated.id == row.id
            assert session.query(OutcomeMismatchResponse).filter_by(project_id="proj-mismatch").count() == 1
            assert session.query(ProjectAlert).filter_by(tenant_id="proj-mismatch").count() == 1
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_unverifiable_evidence_never_creates_a_mismatch_alert(tmp_path: Path) -> None:
    engine, factory = _session_factory(tmp_path)
    try:
        with factory() as session:
            row = reconcile_outcome(
                session,
                project_id="proj-mismatch",
                action_type="refund",
                claimed={"refund_id": "re_unavailable", "amount_usd": 50},
                connector=ApiRecordConnector(record=None, record_found=None),
                idempotency_key="unverifiable-no-alert",
            )

            assert row.verdict == "not_verified"
            assert list_mismatch_responses(session, project_id="proj-mismatch") == []
            assert session.query(ProjectAlert).filter_by(tenant_id="proj-mismatch").count() == 0
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_expired_pending_proof_creates_a_case_only_when_it_settles_mismatched(tmp_path: Path) -> None:
    engine, factory = _session_factory(tmp_path)
    try:
        now = datetime.now(timezone.utc)
        with factory() as session:
            session.add(
                OutcomeReconciliationCheck(
                    id="check-pending-expired",
                    project_id="proj-mismatch",
                    connector_type="generic_rest_api",
                    verdict="not_verified",
                    reason="awaiting_source_of_record",
                    proof_status="pending",
                    proof_reason_code="field_mismatch",
                    proof_deadline_at=now - timedelta(seconds=1),
                    claimed_json="{}",
                    comparison_json="{}",
                    checked_at=now - timedelta(minutes=1),
                )
            )
            session.commit()

            result = sweep_pending_reconciliation_checks(session, project_id="proj-mismatch", now=now)
            assert result.expired == 1
            case = list_mismatch_responses(session, project_id="proj-mismatch")[0]
            assert case.reconciliation_check_id == "check-pending-expired"
            assert case.status == "OPEN"
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_acknowledge_and_owner_resolution_only_change_case_state(tmp_path: Path) -> None:
    engine, factory = _session_factory(tmp_path)
    try:
        with factory() as session:
            reconciliation = reconcile_outcome(
                session,
                project_id="proj-mismatch",
                action_type="customer_update",
                claimed={"customer_id": "cus_1", "status": "disabled"},
                connector=ApiRecordConnector(
                    record={"customer_id": "cus_1", "status": "active"},
                    record_found=True,
                ),
            )
            response = get_mismatch_response(
                session,
                project_id="proj-mismatch",
                response_id=list_mismatch_responses(session, project_id="proj-mismatch")[0].id,
            )
            assert response is not None

            acknowledged = acknowledge_mismatch_response(session, response=response, actor="operator@example.com")
            assert acknowledged.status == "ACKNOWLEDGED"

            resolved = resolve_mismatch_response(
                session,
                response=acknowledged,
                resolution_code="confirmed_mismatch",
                resolution_note="Owner confirmed the SOR discrepancy.",
                actor="owner@example.com",
            )
            assert resolved.status == "RESOLVED"
            assert resolved.resolution_code == "confirmed_mismatch"
            assert resolved.remediation_json
            try:
                resolve_mismatch_response(
                    session,
                    response=resolved,
                    resolution_code="false_positive",
                    resolution_note="A later review disagreed.",
                    actor="owner@example.com",
                )
            except ValueError as exc:
                assert "already resolved" in str(exc)
            else:
                raise AssertionError("Resolved mismatch response must not allow a different resolution code.")
            alert = session.get(ProjectAlert, resolved.alert_id)
            assert alert is not None
            assert alert.status == "RESOLVED"
            assert reconciliation.verdict == "mismatched"
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_mismatch_response_api_is_tenant_scoped_and_owner_resolved(tmp_path: Path) -> None:
    engine, factory = _session_factory(tmp_path)
    role = "viewer"

    def override_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    try:
        with factory() as session:
            session.add(ActionContractVersion(
                id="contract-correction",
                project_id="proj-mismatch",
                contract_key="customer.refund.transfer",
                version="1.0",
                action_type="refund",
                operation_kind="TRANSFER",
                domain_family="customer_operations",
                schema_digest="sha256:correction-schema",
                schema_json='{"type":"object"}',
                risk_class="R3",
                verification_profile_json="{}",
                connector_family="ledger_refund",
            ))
            session.commit()
            reconcile_outcome(
                session,
                project_id="proj-mismatch",
                action_type="refund",
                claimed={"refund_id": "re_api", "amount_usd": 50},
                connector=ApiRecordConnector(
                    record={"refund_id": "re_api", "amount_usd": 5},
                    record_found=True,
                ),
            )
            response_id = list_mismatch_responses(session, project_id="proj-mismatch")[0].id

        app.dependency_overrides[get_db_session] = override_db
        app.dependency_overrides[get_db_session_read] = override_db
        app.dependency_overrides[require_tenant_context] = lambda: TenantContext(
            tenant_id="proj-mismatch", role=role, subject="owner@example.com"
        )
        with TestClient(app) as client:
            listed = client.get("/v1/outcomes/reconciliation/mismatch-responses")
            assert listed.status_code == 200
            assert listed.json()["items"][0]["id"] == response_id
            assert listed.json()["items"][0]["remediation"]["execution_state"] == "not_started"

            blocked = client.post(
                f"/v1/outcomes/reconciliation/mismatch-responses/{response_id}/resolve",
                json={
                    "resolution_code": "expected_change",
                    "resolution_note": "Another approved operator changed the record.",
                },
            )
            assert blocked.status_code == 403

            role = "member"
            correction = client.post(
                f"/v1/outcomes/reconciliation/mismatch-responses/{response_id}/corrective-action",
                headers={"Idempotency-Key": "correction-case-api-1"},
                json={
                    "contract_version": "customer.refund.transfer/1.0",
                    "action_type": "refund",
                    "operation_kind": "TRANSFER",
                    "environment": "production",
                    "resource": {"refund_id": "re_api"},
                    "parameters": {"amount_minor": 5000, "currency": "USD"},
                },
            )
            assert correction.status_code == 201, correction.text
            correction_action_id = correction.json()["action_id"]
            retried = client.post(
                f"/v1/outcomes/reconciliation/mismatch-responses/{response_id}/corrective-action",
                headers={"Idempotency-Key": "correction-case-api-1"},
                json={
                    "contract_version": "customer.refund.transfer/1.0",
                    "action_type": "refund",
                    "operation_kind": "TRANSFER",
                    "environment": "production",
                    "resource": {"refund_id": "re_api"},
                    "parameters": {"amount_minor": 5000, "currency": "USD"},
                },
            )
            assert retried.status_code == 201, retried.text
            assert retried.json()["action_id"] == correction_action_id
            with factory() as session:
                action = session.get(ActionIntent, correction_action_id)
                assert action is not None
                assert '"id":"owner@example.com"' in action.principal_json
                response = get_mismatch_response(
                    session,
                    project_id="proj-mismatch",
                    response_id=response_id,
                )
                assert response is not None
                rendered = mismatch_response_to_dict(session, response)
                assert rendered["remediation"]["corrective_action_intent_id"] == correction_action_id
                assert rendered["remediation"]["status"] == "proposed"
                assert session.query(ActionIntent).filter_by(project_id="proj-mismatch").count() == 1

            role = "owner"
            resolved = client.post(
                f"/v1/outcomes/reconciliation/mismatch-responses/{response_id}/resolve",
                json={
                    "resolution_code": "expected_change",
                    "resolution_note": "Another approved operator changed the record.",
                },
            )
            assert resolved.status_code == 200
            assert resolved.json()["status"] == "RESOLVED"
            assert resolved.json()["resolution_code"] == "expected_change"
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
