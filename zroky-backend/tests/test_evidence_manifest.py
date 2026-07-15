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
from app.db.models import ActionContractVersion, ActionIntent, Project, RuntimePolicyDecision
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
) -> ActionIntent:
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
    session.add(intent)
    return intent


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
        "/v1/evidence/manifest?dashboard_origin=https://zroky.com",
        headers={"x-project-id": project_id},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["scope"]["total_records"] == 125
    assert payload["scope"]["exportable_records"] == 125
    assert len(payload["records"]) == 125
    assert payload["records"][0]["href"].startswith("https://zroky.com/evidence?action_id=")
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
    assert payload["records"][0]["source_label"] == "Protected action record"


def test_evidence_ledger_is_paginated_time_scoped_and_tenant_scoped(client: TestClient) -> None:
    project_id = "proj_evidence_ledger"
    now = datetime.now(timezone.utc)
    with client._session_factory() as session:  # type: ignore[attr-defined]
        session.add(Project(id=project_id, name="Evidence ledger", is_active=True))
        session.add(Project(id="proj_evidence_other", name="Other evidence", is_active=True))
        contract = _seed_contract(session, project_id)
        other_contract = _seed_contract(session, "proj_evidence_other")
        session.flush()
        for index in range(125):
            _seed_intent(
                session,
                contract=contract,
                created_at=now - timedelta(minutes=index),
                index=1_000 + index,
                project_id=project_id,
            )
        _seed_intent(
            session,
            contract=contract,
            created_at=now - timedelta(days=30),
            index=2_000,
            project_id=project_id,
        )
        _seed_intent(
            session,
            contract=other_contract,
            created_at=now,
            index=3_000,
            project_id="proj_evidence_other",
        )
        session.commit()

    first = client.get(
        "/v1/evidence/ledger?days=7&limit=100",
        headers={"x-project-id": project_id},
    )
    assert first.status_code == 200, first.text
    first_payload = first.json()
    assert first_payload["window_days"] == 7
    assert first_payload["total_in_scope"] == 125
    assert first_payload["total_matching"] == 125
    assert first_payload["counts"] == {
        "exceptions": 0,
        "export_ready": 125,
        "needs_verification": 0,
        "total": 125,
    }
    assert len(first_payload["items"]) == 100
    assert first_payload["has_more"] is True
    assert all(item["id"] != "action:act_2000" for item in first_payload["items"])

    second = client.get(
        "/v1/evidence/ledger?days=7&limit=100&offset=100",
        headers={"x-project-id": project_id},
    )
    assert second.status_code == 200, second.text
    second_payload = second.json()
    assert len(second_payload["items"]) == 25
    assert second_payload["has_more"] is False
    assert all(item["action_id"] != "act_3000" for item in [*first_payload["items"], *second_payload["items"]])


def test_evidence_ledger_does_not_classify_expected_policy_block_as_exception(client: TestClient) -> None:
    project_id = "proj_evidence_expected_block"
    now = datetime.now(timezone.utc)
    with client._session_factory() as session:  # type: ignore[attr-defined]
        session.add(Project(id=project_id, name="Expected block", is_active=True))
        contract = _seed_contract(session, project_id)
        session.flush()
        denied_intent = _seed_intent(
            session,
            contract=contract,
            created_at=now,
            index=4_000,
            project_id=project_id,
        )
        denied_intent.status = "denied"
        denied_intent.proof_status = "not_started"
        denied_intent.receipt_status = "missing"
        session.add(
            RuntimePolicyDecision(
                id="decision_expected_block",
                project_id=project_id,
                trace_id="trace_expected_block",
                call_id="call_expected_block",
                action_type="customer.access.grant",
                tool_name="customer.access.grant",
                decision="block",
                status="blocked",
                reasons_json=json.dumps(["policy denied the action"]),
                request_json=json.dumps({}),
                policy_snapshot_json=json.dumps({}),
                intended_action_json=json.dumps({"summary": "Blocked access grant"}),
                trace_context_json=json.dumps({}),
                policy_hit_json=json.dumps({}),
                business_impact_json=json.dumps({}),
                created_at=now,
            )
        )
        session.commit()

    response = client.get(
        "/v1/evidence/ledger?days=7&filter=exceptions",
        headers={"x-project-id": project_id},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["counts"]["exceptions"] == 0
    assert payload["total_in_scope"] == 2
    assert payload["total_matching"] == 0
    assert payload["items"] == []

    all_rows = client.get(
        "/v1/evidence/ledger?days=7",
        headers={"x-project-id": project_id},
    ).json()
    denied_row = next(item for item in all_rows["items"] if item["action_id"] == "act_4000")
    assert denied_row["status"] == "denied"
    assert denied_row["source_label"] == "Blocked action audit"
    assert denied_row["export_kind"] is None
    assert denied_row["exportable"] is False
