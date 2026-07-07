from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import (
    ActionContractVersion,
    ActionIntent,
    ActionReceipt,
    OutcomeReconciliationCheck,
    Project,
    RuntimePolicyDecision,
    SourceMutationRecord,
)
from app.db.session import get_db_session, get_db_session_read
from app.main import app


@pytest.fixture()
def client(tmp_path: Path):
    get_settings.cache_clear()
    db_path = tmp_path / "test_home_summary.db"
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


def _seed_contract(session, project_id: str) -> ActionContractVersion:
    contract = ActionContractVersion(
        id=f"contract_{project_id}",
        project_id=project_id,
        contract_key="customer.access.grant.v1",
        version="1",
        action_type="customer.access.grant",
        operation_kind="GRANT",
        domain_family="support",
        schema_digest="sha256:schema",
        schema_json=json.dumps({"type": "object"}),
        risk_class="R2",
        verification_profile_json=json.dumps({}),
    )
    session.add(contract)
    return contract


def _seed_intent(session, *, project_id: str, contract: ActionContractVersion, index: int, created_at: datetime) -> ActionIntent:
    intent = ActionIntent(
        id=f"act_{index}",
        project_id=project_id,
        contract_version_id=contract.id,
        contract_key=contract.contract_key,
        contract_version=contract.version,
        action_type=contract.action_type,
        operation_kind=contract.operation_kind,
        environment="production",
        idempotency_key=f"idem_{index}",
        intent_digest=f"sha256:intent-{index}",
        canonical_intent_json=json.dumps({"action": "customer.access.grant", "index": index}),
        principal_json=json.dumps({"id": "support-agent"}),
        actor_chain_json=json.dumps([]),
        purpose_json=json.dumps({"summary": "Grant access"}),
        resource_json=json.dumps({"id": f"customer_{index}"}),
        parameters_json=json.dumps({"role": "viewer"}),
        proof_status="matched",
        receipt_status="generated",
        created_at=created_at,
    )
    session.add(intent)
    return intent


def test_home_summary_uses_exact_window_counts_not_list_caps(client: TestClient) -> None:
    project_id = "proj_home_summary"
    now = datetime.now(timezone.utc)
    with client._session_factory() as session:  # type: ignore[attr-defined]
        session.add(Project(id=project_id, name="Home summary", is_active=True))
        contract = _seed_contract(session, project_id)
        session.flush()

        first_intent: ActionIntent | None = None
        for index in range(80):
            intent = _seed_intent(
                session,
                project_id=project_id,
                contract=contract,
                index=index,
                created_at=now - timedelta(days=1),
            )
            first_intent = first_intent or intent

        assert first_intent is not None
        session.add(
            ActionReceipt(
                id="receipt_1",
                project_id=project_id,
                action_intent_id=first_intent.id,
                receipt_digest="sha256:receipt",
                receipt_json=json.dumps({"receipt": True}),
                signature="sig",
                signing_key_id="key_1",
                generated_at=now - timedelta(hours=1),
            )
        )
        session.add_all(
            [
                RuntimePolicyDecision(
                    id="decision_pending",
                    project_id=project_id,
                    decision="requires_approval",
                    status="pending_approval",
                    reasons_json=json.dumps(["sequence risk detected"]),
                    policy_hit_json=json.dumps({"sequence_risk": {"matched": True}}),
                    created_at=now - timedelta(hours=2),
                ),
                RuntimePolicyDecision(
                    id="decision_old_pending",
                    project_id=project_id,
                    decision="requires_approval",
                    status="pending_approval",
                    reasons_json=json.dumps([]),
                    created_at=now - timedelta(days=45),
                ),
                OutcomeReconciliationCheck(
                    id="outcome_matched",
                    project_id=project_id,
                    connector_type="generic_rest",
                    verdict="matched",
                    claimed_json=json.dumps({}),
                    comparison_json=json.dumps({}),
                    checked_at=now - timedelta(hours=1),
                ),
                OutcomeReconciliationCheck(
                    id="outcome_mismatch",
                    project_id=project_id,
                    connector_type="generic_rest",
                    verdict="mismatched",
                    claimed_json=json.dumps({}),
                    comparison_json=json.dumps({}),
                    checked_at=now - timedelta(hours=1),
                ),
                SourceMutationRecord(
                    id="mutation_bypass",
                    project_id=project_id,
                    source_system="stripe",
                    mutation_id="evt_bypass",
                    classification="policy_bypass",
                    occurred_at=now - timedelta(hours=1),
                ),
            ]
        )
        session.commit()

    response = client.get("/v1/home/summary?days=30", headers={"x-project-id": project_id})
    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == project_id
    assert body["window_days"] == 30
    assert body["metrics"]["controlled_actions"] == 80
    assert body["metrics"]["pending_approvals"] == 2
    assert body["metrics"]["verified_outcomes"] == 1
    assert body["metrics"]["outcome_checks"] == 2
    assert body["metrics"]["receipts_generated"] == 1
    assert body["metrics"]["bypass_mutations"] == 1
    assert body["metrics"]["unreceipted_mutations"] == 1
    assert body["metrics"]["sequence_risks"] == 1
