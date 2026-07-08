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
from app.db.models import ActionContractVersion, ActionIntent, Project
from app.db.session import get_db_session, get_db_session_read
from app.main import app


@pytest.fixture()
def client(tmp_path: Path):
    get_settings.cache_clear()
    db_path = tmp_path / "test_evidence_manifest.db"
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


def _seed_intent(
    session,
    *,
    contract: ActionContractVersion,
    created_at: datetime,
    index: int,
    project_id: str,
) -> None:
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
            canonical_intent_json=json.dumps(
                {
                    "purpose": {"summary": "Grant customer access"},
                    "resource": {"label": f"customer_{index}"},
                    "trace_context": {"trace_id": f"trace_{index}"},
                }
            ),
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


def test_evidence_manifest_uses_exact_server_side_scope_not_client_caps(client: TestClient) -> None:
    project_id = "proj_evidence_manifest"
    now = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)
    with client._session_factory() as session:  # type: ignore[attr-defined]
        session.add(Project(id=project_id, name="Evidence manifest", is_active=True))
        session.add(Project(id="proj_other", name="Other", is_active=True))
        contract = _seed_contract(session, project_id)
        other_contract = _seed_contract(session, "proj_other")
        session.flush()
        for index in range(125):
            _seed_intent(
                session,
                contract=contract,
                created_at=now - timedelta(minutes=index),
                index=index,
                project_id=project_id,
            )
        for index in range(3):
            _seed_intent(
                session,
                contract=other_contract,
                created_at=now - timedelta(minutes=index),
                index=500 + index,
                project_id="proj_other",
            )
        session.commit()

    response = client.get(
        "/v1/evidence/manifest?dashboard_origin=https://app.zroky.com",
        headers={"x-project-id": project_id},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["scope"]["total_records"] == 125
    assert payload["scope"]["exportable_records"] == 125
    assert len(payload["records"]) == 125
    assert payload["records"][0]["href"].startswith("https://app.zroky.com/evidence?action_id=")
    assert all(record["action_id"].startswith("act_") for record in payload["records"])


def test_evidence_manifest_filters_by_date_and_status_on_server(client: TestClient) -> None:
    project_id = "proj_evidence_manifest_filter"
    with client._session_factory() as session:  # type: ignore[attr-defined]
        session.add(Project(id=project_id, name="Evidence manifest filter", is_active=True))
        contract = _seed_contract(session, project_id)
        session.flush()
        _seed_intent(
            session,
            contract=contract,
            created_at=datetime(2026, 7, 7, 10, 0, tzinfo=timezone.utc),
            index=1,
            project_id=project_id,
        )
        _seed_intent(
            session,
            contract=contract,
            created_at=datetime(2026, 7, 6, 10, 0, tzinfo=timezone.utc),
            index=2,
            project_id=project_id,
        )
        pending = ActionIntent(
            id="act_pending",
            project_id=project_id,
            contract_version_id=contract.id,
            contract_key=contract.contract_key,
            contract_version=contract.version,
            action_type=contract.action_type,
            operation_kind=contract.operation_kind,
            environment="production",
            idempotency_key="idem_pending",
            intent_digest="sha256:intent-pending",
            canonical_intent_json=json.dumps({"purpose": {"summary": "Pending access"}}),
            principal_json=json.dumps({"id": "support-agent"}),
            actor_chain_json=json.dumps([]),
            purpose_json=json.dumps({}),
            resource_json=json.dumps({}),
            parameters_json=json.dumps({}),
            proof_status="not_verified",
            receipt_status="missing",
            created_at=datetime(2026, 7, 7, 11, 0, tzinfo=timezone.utc),
        )
        session.add(pending)
        session.commit()

    response = client.get(
        "/v1/evidence/manifest?filter=needs_verification&start_date=2026-07-07&end_date=2026-07-07",
        headers={"x-project-id": project_id},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["scope"]["total_records"] == 1
    assert payload["records"][0]["id"] == "action:act_pending"
    assert payload["records"][0]["status"] == "not_verified"
