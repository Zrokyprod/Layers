from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import Agent, AgentRelease, Call, Environment, GoldenSet, GoldenTrace
from app.db.session import get_db_session, get_db_session_read
from app.main import app


@pytest.fixture()
def client(tmp_path: Path):
    get_settings.cache_clear()
    db_path = tmp_path / "test_contracts_routes.db"
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


@pytest.fixture(autouse=True)
def _grant_goldens_entitlement(monkeypatch):
    from app.services import entitlements_resolver

    monkeypatch.setattr(entitlements_resolver, "has", lambda db, org_id, key: True)
    monkeypatch.setattr(entitlements_resolver, "get", lambda db, org_id, key, default=None: default)
    monkeypatch.setattr(entitlements_resolver, "get_plan_code", lambda db, org_id: "pro")


def _seed_release_and_fixture(session, project_id: str) -> tuple[str, str]:
    env = Environment(id=str(uuid4()), project_id=project_id, name="production", type="production")
    agent = Agent(id=str(uuid4()), project_id=project_id, name="Refund Agent", slug="refund-agent")
    release = AgentRelease(
        id=str(uuid4()),
        project_id=project_id,
        agent_id=agent.id,
        environment_id=env.id,
        git_sha="broken-sha",
        prompt_version="refund-v1",
        tool_schema_hash="refund-tools-v1",
        release_fingerprint=uuid4().hex,
    )
    fixture = GoldenSet(id=str(uuid4()), project_id=project_id, name="Refund fixtures", blocks_ci=True)
    session.add_all([env, agent, release, fixture])
    session.commit()
    return release.id, fixture.id


def test_contract_version_activation_requires_pinned_manual_proof(client: TestClient) -> None:
    project_id = "proj-contracts-activation"
    headers = {"X-Project-Id": project_id}
    with client._session_factory() as session:  # type: ignore[attr-defined]
        release_id, fixture_id = _seed_release_and_fixture(session, project_id)

    created = client.post(
        "/v1/contracts",
        headers=headers,
        json={"name": "refund-status-required", "severity": "critical"},
    )
    assert created.status_code == 201
    contract_id = created.json()["id"]

    draft_version = client.post(
        f"/v1/contracts/{contract_id}/versions",
        headers=headers,
        json={
            "fixture_set_id": fixture_id,
            "baseline_release_id": release_id,
            "spec_json": {"schema": "regression_contract_v1", "assertions": [{"must_call": "get_refund_status"}]},
        },
    )
    assert draft_version.status_code == 201

    blocked = client.post(
        f"/v1/contracts/{contract_id}/versions/{draft_version.json()['id']}/activate",
        headers=headers,
    )
    assert blocked.status_code == 409
    assert "incident_confirmation_required" in blocked.json()["detail"]["blockers"]
    assert "baseline_reproduction_required" in blocked.json()["detail"]["blockers"]

    proven_version = client.post(
        f"/v1/contracts/{contract_id}/versions",
        headers=headers,
        json={
            "fixture_set_id": fixture_id,
            "baseline_release_id": release_id,
            "trial_policy": {"required_trials": 10, "critical_violation_tolerance": 0},
            "spec_json": {
                "schema": "regression_contract_v1",
                "assertions": [{"must_call": "get_refund_status"}],
                "proof": {
                    "incident_confirmed": True,
                    "baseline_reproduced": True,
                    "candidate_verified": True,
                    "required_trials": 10,
                    "critical_violations": 0,
                    "fixture_pinned": True,
                    "evaluator_bundle_pinned": True,
                    "candidate_sha": "fix-sha",
                },
            },
        },
    )
    assert proven_version.status_code == 201

    activated = client.post(
        f"/v1/contracts/{contract_id}/versions/{proven_version.json()['id']}/activate",
        headers=headers,
    )
    assert activated.status_code == 200
    assert activated.json()["approved_at"] is not None

    detail = client.get(f"/v1/contracts/{contract_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["status"] == "active"
    assert detail.json()["active_version_id"] == proven_version.json()["id"]


def test_import_goldens_migrates_golden_contract_json_to_contract_version(client: TestClient) -> None:
    project_id = "proj-contracts-import"
    headers = {"X-Project-Id": project_id}
    with client._session_factory() as session:  # type: ignore[attr-defined]
        release_id, fixture_id = _seed_release_and_fixture(session, project_id)
        call = Call(
            id="call-import",
            project_id=project_id,
            event_id="event-import",
            agent_release_id=release_id,
            created_at=datetime.now(timezone.utc),
            agent_name="Refund Agent",
            provider="openai",
            model="gpt-4o",
            status="completed",
            payload_json="{}",
        )
        trace = GoldenTrace(
            id=str(uuid4()),
            golden_set_id=fixture_id,
            project_id=project_id,
            call_id=call.id,
            status="active",
            criteria_json=json.dumps(
                {
                    "golden_contract_v1": {
                        "severity": "critical",
                        "tool_sequence": ["get_refund_status"],
                    }
                }
            ),
        )
        session.add_all([call, trace])
        session.commit()

    imported = client.post("/v1/contracts/import-goldens", headers=headers)
    assert imported.status_code == 200
    payload = imported.json()
    assert payload["imported_count"] == 1
    version = payload["versions"][0]
    assert version["fixture_set_id"] == fixture_id
    assert version["baseline_release_id"] == release_id
    assert version["spec_json"]["imported_from"] == "golden_contract_v1"
