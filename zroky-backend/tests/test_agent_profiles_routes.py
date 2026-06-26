from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import Project
from app.db.session import get_db_session, get_db_session_read
from app.main import app


@pytest.fixture()
def client(tmp_path: Path):
    get_settings.cache_clear()
    db_path = tmp_path / "test_agent_profiles_routes.db"
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


def test_agent_profile_crud_is_project_scoped(client: TestClient) -> None:
    _seed_project(client, "proj_agents_alpha")
    _seed_project(client, "proj_agents_beta")

    created = client.post(
        "/v1/agents",
        headers={"X-Project-Id": "proj_agents_alpha"},
        json={
            "display_name": "Refund Agent",
            "description": "Issues customer refunds with proof.",
            "runtime_path": "sdk",
            "framework": "langgraph",
            "environment": "production",
            "model_provider": "openai",
            "model_name": "gpt-4.1",
            "tool_names": ["stripe.refunds.create", "stripe.refunds.retrieve"],
            "allowed_action_types": ["refund"],
            "blocked_action_types": ["deploy_change"],
            "risk_limits": {"max_refund_usd": 100},
            "verification_connectors": ["ledger_refund", "webhook_callback"],
            "metadata": {"owner": "support-ops"},
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["schema_version"] == "zroky.agent_tool_control.v1"
    assert body["project_id"] == "proj_agents_alpha"
    assert body["display_name"] == "Refund Agent"
    assert body["slug"] == "refund-agent"
    assert body["runtime_path"] == "sdk"
    assert body["allowed_action_types"] == ["refund"]
    assert body["blocked_action_types"] == ["deploy_change"]
    assert body["risk_limits"] == {"max_refund_usd": 100}
    assert body["verification_connectors"] == ["ledger_refund", "webhook_callback"]
    assert body["is_active"] is True

    agent_id = body["id"]

    alpha_list = client.get("/v1/agents", headers={"X-Project-Id": "proj_agents_alpha"})
    beta_list = client.get("/v1/agents", headers={"X-Project-Id": "proj_agents_beta"})
    assert alpha_list.status_code == 200
    assert beta_list.status_code == 200
    assert [item["id"] for item in alpha_list.json()["items"]] == [agent_id]
    assert beta_list.json()["items"] == []

    foreign_detail = client.get(f"/v1/agents/{agent_id}", headers={"X-Project-Id": "proj_agents_beta"})
    assert foreign_detail.status_code == 404

    updated = client.patch(
        f"/v1/agents/{agent_id}",
        headers={"X-Project-Id": "proj_agents_alpha"},
        json={
            "runtime_path": "http_gateway",
            "tool_names": ["stripe.refunds.create"],
            "allowed_action_types": ["refund", "payment_adjustment"],
            "verification_connectors": ["ledger_refund", "generic_rest"],
        },
    )
    assert updated.status_code == 200
    assert updated.json()["runtime_path"] == "http_gateway"
    assert updated.json()["tool_names"] == ["stripe.refunds.create"]
    assert updated.json()["allowed_action_types"] == ["refund", "payment_adjustment"]
    assert updated.json()["verification_connectors"] == ["ledger_refund", "generic_rest"]

    deleted = client.delete(f"/v1/agents/{agent_id}", headers={"X-Project-Id": "proj_agents_alpha"})
    assert deleted.status_code == 200
    assert deleted.json()["is_active"] is False

    active_list = client.get("/v1/agents", headers={"X-Project-Id": "proj_agents_alpha"})
    inactive_list = client.get(
        "/v1/agents?include_inactive=true",
        headers={"X-Project-Id": "proj_agents_alpha"},
    )
    assert active_list.json()["items"] == []
    assert [item["id"] for item in inactive_list.json()["items"]] == [agent_id]


def test_agent_profile_validates_action_and_connector_contract(client: TestClient) -> None:
    _seed_project(client, "proj_agents_validation")

    invalid_action = client.post(
        "/v1/agents",
        headers={"X-Project-Id": "proj_agents_validation"},
        json={
            "display_name": "Risky Agent",
            "allowed_action_types": ["refund"],
            "blocked_action_types": ["refund"],
        },
    )
    assert invalid_action.status_code == 422
    assert "both allowed and blocked" in str(invalid_action.json()["detail"])

    invalid_connector = client.post(
        "/v1/agents",
        headers={"X-Project-Id": "proj_agents_validation"},
        json={
            "display_name": "Connector Agent",
            "verification_connectors": ["unknown_crm"],
        },
    )
    assert invalid_connector.status_code == 422
    assert "Unsupported verification connector" in str(invalid_connector.json()["detail"])


def test_agent_profile_duplicate_names_conflict(client: TestClient) -> None:
    _seed_project(client, "proj_agents_duplicate")
    headers = {"X-Project-Id": "proj_agents_duplicate"}
    payload = {"display_name": "Refund Agent", "runtime_path": "sdk"}

    first = client.post("/v1/agents", headers=headers, json=payload)
    second = client.post("/v1/agents", headers=headers, json=payload)

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["detail"] == "Agent profile already exists for this name."
