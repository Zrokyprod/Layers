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
    db_path = tmp_path / "test_actions_lifecycle_summary.db"
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
        contract_key="customer.access.grant",
        version="1.0",
        action_type="customer.access.grant",
        operation_kind="UPDATE",
        domain_family="support",
        schema_digest="sha256:schema",
        schema_json=json.dumps({"type": "object"}),
        risk_class="R2",
        verification_profile_json=json.dumps({}),
    )
    session.add(contract)
    return contract


def _seed_intent(session, *, project_id: str, contract: ActionContractVersion, index: int, created_at: datetime) -> None:
    session.add(
        ActionIntent(
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
    )


def test_actions_lifecycle_summary_collapses_action_page_sources(client: TestClient) -> None:
    project_id = "proj_actions_lifecycle_summary"
    now = datetime.now(timezone.utc)
    with client._session_factory() as session:  # type: ignore[attr-defined]
        session.add(Project(id=project_id, name="Actions summary", is_active=True))
        contract = _seed_contract(session, project_id)
        session.flush()

        for index in range(105):
            _seed_intent(
                session,
                project_id=project_id,
                contract=contract,
                index=index,
                created_at=now - timedelta(days=1),
            )

        session.add_all(
            [
                RuntimePolicyDecision(
                    id="decision_pending",
                    project_id=project_id,
                    decision="requires_approval",
                    status="pending_approval",
                    reasons_json=json.dumps(["approval required"]),
                    created_at=now - timedelta(hours=2),
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
                    id="outcome_unverified",
                    project_id=project_id,
                    connector_type="generic_rest",
                    verdict="not_verified",
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

    response = client.get("/v1/actions/lifecycle-summary?days=30&limit=100", headers={"x-project-id": project_id})
    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == project_id
    assert body["window_days"] == 30
    assert body["row_limit"] == 100
    assert body["source_totals"]["intents"] == 105
    assert body["source_totals"]["approvals"] == 1
    assert body["source_totals"]["outcomes"] == 2
    assert body["source_totals"]["mutations"] == 1
    assert body["truncated"] is True
    assert body["truncated_sources"] == ["intents"]
    assert body["metrics"]["controlled_actions"] == 105
    assert body["metrics"]["held_actions"] == 1
    assert body["metrics"]["matched_outcomes"] == 1
    assert body["metrics"]["not_verified_outcomes"] == 1
    assert body["metrics"]["bypass_risk"] == 1
    assert len(body["data"]["intents"]) == 100
    assert len(body["data"]["approvals"]) == 1
    assert len(body["data"]["outcomes"]) == 2
    assert len(body["data"]["mutations"]) == 1
    assert body["sources"]["lifecycle_summary"] is True
