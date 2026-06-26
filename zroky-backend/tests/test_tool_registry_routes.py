from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import Agent, Project
from app.db.session import get_db_session, get_db_session_read
from app.main import app


@pytest.fixture()
def client(tmp_path: Path):
    get_settings.cache_clear()
    db_path = tmp_path / "test_tool_registry_routes.db"
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


def _seed_agent(
    client: TestClient,
    *,
    project_id: str,
    agent_id: str,
    name: str = "Refund Agent",
    allowed_action_types: list[str] | None = None,
    verification_connectors: list[str] | None = None,
) -> None:
    with client._session_factory() as session:  # type: ignore[attr-defined]
        session.add(
            Agent(
                id=agent_id,
                project_id=project_id,
                name=name,
                slug=name.lower().replace(" ", "-"),
                runtime_path="sdk",
                allowed_action_types_json=json.dumps(allowed_action_types or []),
                verification_connectors_json=json.dumps(verification_connectors or []),
            )
        )
        session.commit()


def _by_id(items: list[dict], item_id: str) -> dict:
    for item in items:
        if item["id"] == item_id:
            return item
    raise AssertionError(f"Missing registry item {item_id}")


def test_tool_registry_exposes_phase1_catalog_with_honest_status(client: TestClient) -> None:
    _seed_project(client, "proj_tool_registry")

    response = client.get("/v1/tools/registry", headers={"X-Project-Id": "proj_tool_registry"})

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "zroky.agent_tool_control.v1"
    assert body["project_id"] == "proj_tool_registry"
    assert [item["id"] for item in body["runtime_paths"]] == [
        "sdk",
        "customer_hosted_runner",
        "http_gateway",
        "mcp_gateway",
        "webhook",
    ]
    assert _by_id(body["runtime_paths"], "sdk")["implementation_status"] == "available"
    runner = _by_id(body["runtime_paths"], "customer_hosted_runner")
    assert runner["implementation_status"] == "available"
    assert runner["launch_tier"] == "p0"
    assert runner["backend_capability"] == "action_runner.customer_hosted"
    assert _by_id(body["runtime_paths"], "http_gateway")["implementation_status"] == "planned"
    webhook = _by_id(body["runtime_paths"], "webhook")
    assert webhook["implementation_status"] == "available"
    assert webhook["backend_capability"] == "outcome_reconciliation.saved_connector_bridge"
    assert _by_id(body["verification_connectors"], "ledger_refund")["implementation_status"] == "available"
    assert _by_id(body["verification_connectors"], "crm_record")["implementation_status"] == "available"
    generic_rest = _by_id(body["verification_connectors"], "generic_rest")
    assert generic_rest["implementation_status"] == "available"
    assert generic_rest["backend_capability"] == "system_of_record.generic_rest_api"
    assert _by_id(body["native_tool_families"], "slack_approval_alert")["implementation_status"] == "available"
    assert _by_id(body["native_tool_families"], "zroky_dashboard_approval")["implementation_status"] == "available"
    stripe = _by_id(body["native_tool_families"], "stripe_refund")
    assert stripe["implementation_status"] == "available"
    assert stripe["launch_tier"] == "p0"
    assert stripe["backend_capability"] == "runner_adapter.stripe_refund"
    assert _by_id(body["native_tool_families"], "hubspot_customer")["launch_tier"] == "p1"
    assert _by_id(body["native_tool_families"], "crewai")["launch_tier"] == "p1"
    assert _by_id(body["native_tool_families"], "connector_marketplace")["launch_tier"] == "p2"
    native_ids = {item["id"] for item in body["native_tool_families"]}
    assert "teams_approval" not in native_ids
    assert "email_approval" not in native_ids
    assert "sms_whatsapp_approval" not in native_ids
    assert "pagerduty_approval" not in native_ids
    assert "model_routing_gateway" not in native_ids
    assert "ai_observability_platform" not in native_ids
    assert "self_hosted_control_plane" not in native_ids
    assert body["recommended"]["runtime_path_ids"] == ["sdk"]
    assert body["recommended"]["verification_connector_ids"] == ["generic_rest", "webhook_callback"]


def test_tool_registry_recommends_tools_for_agent_action_profile(client: TestClient) -> None:
    _seed_project(client, "proj_tool_registry_agent")
    _seed_agent(
        client,
        project_id="proj_tool_registry_agent",
        agent_id="agent_refund",
        allowed_action_types=["refund"],
        verification_connectors=["ledger_refund"],
    )

    response = client.get(
        "/v1/tools/registry?agent_id=agent_refund",
        headers={"X-Project-Id": "proj_tool_registry_agent"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["agent_id"] == "agent_refund"
    assert body["recommended"]["action_types"] == ["refund"]
    assert body["recommended"]["runtime_path_ids"] == ["sdk", "customer_hosted_runner"]
    assert "ledger_refund" in body["recommended"]["verification_connector_ids"]
    assert "stripe_refund" in body["recommended"]["native_tool_family_ids"]
    assert "razorpay_refund" in body["recommended"]["native_tool_family_ids"]
    assert "zroky_dashboard_approval" in body["recommended"]["native_tool_family_ids"]
    assert "salesforce_customer" not in body["recommended"]["native_tool_family_ids"]


def test_tool_registry_is_project_scoped_for_agent_recommendations(client: TestClient) -> None:
    _seed_project(client, "proj_registry_alpha")
    _seed_project(client, "proj_registry_beta")
    _seed_agent(
        client,
        project_id="proj_registry_beta",
        agent_id="agent_beta_only",
        allowed_action_types=["customer_record_update"],
    )

    response = client.get(
        "/v1/tools/registry?agent_id=agent_beta_only",
        headers={"X-Project-Id": "proj_registry_alpha"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Agent profile not found"


def test_tool_registry_can_recommend_by_explicit_action_without_agent(client: TestClient) -> None:
    _seed_project(client, "proj_tool_registry_action")

    response = client.get(
        "/v1/tools/registry?action_type=deploy_change",
        headers={"X-Project-Id": "proj_tool_registry_action"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["agent_id"] is None
    assert body["action_type"] == "deploy_change"
    assert body["recommended"]["action_types"] == ["deploy_change"]
    assert "github_ci" in body["recommended"]["verification_connector_ids"]
    assert body["recommended"]["native_tool_family_ids"] == [
        "github_pr_ci_deploy",
        "slack_approval_alert",
        "zroky_dashboard_approval",
    ]
    assert "linear" not in body["recommended"]["native_tool_family_ids"]
