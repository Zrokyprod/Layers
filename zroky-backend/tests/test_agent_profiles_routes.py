from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import ActionRunner, PilotPolicy, Project, RuntimePolicyDecision, Subscription
from app.db.session import get_db_session, get_db_session_read
from app.main import app
from app.services.agent_profiles import ACTION_TYPE_OPERATION_KINDS
from app.services.entitlements import seed_plan_entitlements
from app.services.entitlements_resolver import invalidate_all
from app.services.pilot import parse_policy_json


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
    invalidate_all()
    with TestClient(app) as test_client:
        test_client._session_factory = factory  # type: ignore[attr-defined]
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    get_settings.cache_clear()
    invalidate_all()


def _seed_project(client: TestClient, project_id: str) -> None:
    with client._session_factory() as session:  # type: ignore[attr-defined]
        session.add(Project(id=project_id, name=f"Project {project_id}", is_active=True))
        session.commit()


def _seed_subscription(client: TestClient, *, project_id: str, plan_code: str) -> None:
    with client._session_factory() as session:  # type: ignore[attr-defined]
        session.add(
            Subscription(
                id=f"sub-{project_id}",
                org_id=project_id,
                plan_code=plan_code,
                status="active",
                seats=1,
                payment_customer_ref=f"cus_{project_id}",
                payment_subscription_ref=f"si_{project_id}",
                current_period_end=datetime.now(timezone.utc) + timedelta(days=30),
            )
        )
        seed_plan_entitlements(session, org_id=project_id, plan_code=plan_code)
        session.commit()


def _setup_metadata(
    *,
    runner_mode: str = "managed",
    credential_ref: str = "cred_prod_protected_actions",
) -> dict[str, object]:
    return {
        "setup_source": "agent_control_setup_wizard",
        "protection_state": "plan_saved",
        "readiness_preview_completed": True,
        "runtime_policy_mandate_enforced": False,
        "runner_verification": {
            "runner_mode": runner_mode,
            "credential_ref": credential_ref,
            "verifier_connector": "generic_rest",
            "source_of_record": "Primary business system API",
        },
        "readiness": {"runtime_policy_mandate_enforced": False},
        "control_binding": {"readiness": {"runtime_policy_mandate_enforced": False}},
    }


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


def test_agent_profile_free_plan_blocks_second_active_agent(client: TestClient) -> None:
    project_id = "proj_agents_limit"
    _seed_project(client, project_id)
    headers = {"X-Project-Id": project_id}

    first = client.post(
        "/v1/agents",
        headers=headers,
        json={"display_name": "Support Agent", "runtime_path": "sdk"},
    )
    second = client.post(
        "/v1/agents",
        headers=headers,
        json={"display_name": "Ops Agent", "runtime_path": "sdk"},
    )

    assert first.status_code == 201
    assert second.status_code == 402
    assert (
        second.json()["detail"]
        == "Agent limit reached for this plan (1/1). Upgrade to add more agents."
    )

    listed = client.get("/v1/agents", headers=headers)
    assert listed.status_code == 200
    body = listed.json()
    assert body["active_count"] == 1
    assert body["max_active_agents"] == 1
    assert body["limit_reached"] is True


def test_agent_profile_enterprise_plan_allows_unlimited_agents(client: TestClient) -> None:
    project_id = "proj_agents_enterprise"
    _seed_project(client, project_id)
    _seed_subscription(client, project_id=project_id, plan_code="enterprise")
    headers = {"X-Project-Id": project_id}

    for index in range(1, 7):
        created = client.post(
            "/v1/agents",
            headers=headers,
            json={"display_name": f"Enterprise Agent {index}", "runtime_path": "sdk"},
        )
        assert created.status_code == 201

    listed = client.get("/v1/agents", headers=headers)
    assert listed.status_code == 200
    body = listed.json()
    assert body["active_count"] == 6
    assert body["max_active_agents"] == -1
    assert body["limit_reached"] is False


def test_agent_profile_enforce_writes_runtime_policy_and_gate_uses_it(client: TestClient) -> None:
    project_id = "proj_agents_enforce"
    _seed_project(client, project_id)
    headers = {"X-Project-Id": project_id}

    created = client.post(
        "/v1/agents",
        headers=headers,
        json={
            "display_name": "Payments Agent",
            "runtime_path": "sdk",
            "tool_names": ["stripe.refunds.create"],
            "allowed_action_types": ["refund"],
            "risk_limits": {
                "auto_allow_amount_usd": 100,
                "approval_required_above_usd": 500,
                "deny_above_usd": 5000,
                "approval_ttl_minutes": 45,
            },
            "verification_connectors": ["ledger_refund"],
            "metadata": _setup_metadata(runner_mode="managed", credential_ref="cred_payments_runner"),
        },
    )
    assert created.status_code == 201
    agent_id = created.json()["id"]

    enforced = client.post(f"/v1/agents/{agent_id}/enforce", headers=headers)

    assert enforced.status_code == 200
    enforced_body = enforced.json()
    assert enforced_body["metadata"]["protection_state"] == "enforced"
    assert enforced_body["metadata"]["runtime_policy_mandate_enforced"] is True
    assert "readiness" not in enforced_body["metadata"]
    assert "readiness_preview_completed" not in enforced_body["metadata"]
    assert "receipt_preview_generated" not in enforced_body["metadata"]
    assert "readiness" not in enforced_body["metadata"]["control_binding"]
    assert enforced_body["metadata"]["runtime_policy_mandate"]["scope"] == "project"
    assert enforced_body["metadata"]["runtime_policy_mandate"]["runner_id"]
    assert enforced_body["metadata"]["runtime_policy_mandate"]["runner_name"] == "payments-agent-runner"
    assert enforced_body["metadata"]["runtime_policy_mandate"]["runner_type"] == "managed_sandbox"
    assert enforced_body["metadata"]["runtime_policy_mandate"]["runner_supported_operation_kinds"] == ["TRANSFER"]
    assert enforced_body["metadata"]["runtime_policy_mandate"]["runner_credential_ref"] == "cred_payments_runner"

    with client._session_factory() as session:  # type: ignore[attr-defined]
        row = session.query(PilotPolicy).filter(PilotPolicy.project_id == project_id).one()
        policy = parse_policy_json(row.policy_json)
        runner = session.get(ActionRunner, enforced_body["metadata"]["runtime_policy_mandate"]["runner_id"])
        assert runner is not None
        assert runner.name == "payments-agent-runner"
        assert runner.runner_type == "managed_sandbox"
        assert runner.status == "online"
        assert runner.supported_operation_kinds_json == '["TRANSFER"]'
        assert json.loads(runner.credential_scope_json) == {"credential_ref": "cred_payments_runner"}

    assert policy["runtime_enabled"] is True
    assert policy["runtime_allowed_tools"] == ["refund", "stripe.refunds.create"]
    assert "refund" in policy["runtime_sensitive_tools"]
    assert "stripe.refunds.create" in policy["runtime_sensitive_tools"]
    assert policy["runtime_amount_approval_threshold_usd"] == 500.0
    assert policy["runtime_amount_deny_threshold_usd"] == 5000.0
    assert policy["runtime_max_cost_usd"] == 5000.0
    assert policy["runtime_approval_ttl_minutes"] == 45

    held = client.post(
        "/v1/runtime-policy/check",
        headers=headers,
        json={
            "agent_name": "Payments Agent",
            "action_type": "refund",
            "tool_name": "refund",
            "external_action": True,
            "impact_usd": 600,
        },
    )
    assert held.status_code == 200
    assert held.json()["status"] == "pending_approval"
    assert held.json()["requires_approval"] is True

    blocked = client.post(
        "/v1/runtime-policy/check",
        headers=headers,
        json={
            "agent_name": "Payments Agent",
            "action_type": "refund",
            "tool_name": "refund",
            "external_action": True,
            "estimated_cost_usd": 6000,
        },
    )
    assert blocked.status_code == 200
    assert blocked.json()["status"] == "blocked"
    assert "exceeds runtime limit" in " ".join(blocked.json()["reasons"])


def test_runtime_policy_dry_run_after_agent_enforce_does_not_persist_decision(client: TestClient) -> None:
    project_id = "proj_agents_dry_run"
    _seed_project(client, project_id)
    headers = {"X-Project-Id": project_id}

    created = client.post(
        "/v1/agents",
        headers=headers,
        json={
            "display_name": "Dry Run Agent",
            "runtime_path": "sdk",
            "tool_names": ["internal.ops.execute"],
            "allowed_action_types": ["internal_api_mutation"],
            "risk_limits": {
                "approval_required_above_usd": 500,
                "deny_above_usd": 5000,
                "approval_ttl_minutes": 30,
            },
            "verification_connectors": ["generic_rest"],
            "metadata": _setup_metadata(runner_mode="managed", credential_ref="cred_dry_run_runner"),
        },
    )
    assert created.status_code == 201
    enforced = client.post(f"/v1/agents/{created.json()['id']}/enforce", headers=headers)
    assert enforced.status_code == 200

    dry_run = client.post(
        "/v1/runtime-policy/dry-run",
        headers=headers,
        json={
            "agent_name": "Dry Run Agent",
            "action_type": "internal_api_mutation",
            "tool_name": "internal.ops.execute",
            "external_action": True,
            "impact_usd": 600,
            "metadata": {"source": "agent_setup_policy_dry_run"},
        },
    )

    assert dry_run.status_code == 200, dry_run.text
    body = dry_run.json()
    assert body["recorded"] is False
    assert body["status"] == "pending_approval"
    assert body["requires_approval"] is True
    assert "id" not in body

    with client._session_factory() as session:  # type: ignore[attr-defined]
        count = (
            session.query(RuntimePolicyDecision)
            .filter(RuntimePolicyDecision.project_id == project_id)
            .count()
        )
    assert count == 0


def test_agent_profile_enforce_unions_project_allowed_tools_for_multiple_agents(client: TestClient) -> None:
    project_id = "proj_agents_enforce_union"
    _seed_project(client, project_id)
    _seed_subscription(client, project_id=project_id, plan_code="enterprise")
    headers = {"X-Project-Id": project_id}

    first = client.post(
        "/v1/agents",
        headers=headers,
        json={
            "display_name": "Payments Agent",
            "runtime_path": "sdk",
            "tool_names": ["stripe.refunds.create"],
            "allowed_action_types": ["refund"],
            "risk_limits": {
                "approval_required_above_usd": 500,
                "deny_above_usd": 5000,
                "approval_ttl_minutes": 45,
            },
            "verification_connectors": ["ledger_refund"],
            "metadata": _setup_metadata(runner_mode="managed", credential_ref="cred_payments_runner"),
        },
    )
    second = client.post(
        "/v1/agents",
        headers=headers,
        json={
            "display_name": "Inventory Agent",
            "runtime_path": "sdk",
            "tool_names": ["inventory.items.delete"],
            "allowed_action_types": ["internal_api_mutation"],
            "risk_limits": {
                "approval_required_above_usd": 100,
                "deny_above_usd": 1000,
                "approval_ttl_minutes": 30,
            },
            "verification_connectors": ["generic_rest"],
            "metadata": _setup_metadata(runner_mode="managed", credential_ref="cred_inventory_runner"),
        },
    )
    assert first.status_code == 201
    assert second.status_code == 201

    first_enforced = client.post(f"/v1/agents/{first.json()['id']}/enforce", headers=headers)
    second_enforced = client.post(f"/v1/agents/{second.json()['id']}/enforce", headers=headers)
    assert first_enforced.status_code == 200
    assert second_enforced.status_code == 200

    with client._session_factory() as session:  # type: ignore[attr-defined]
        row = session.query(PilotPolicy).filter(PilotPolicy.project_id == project_id).one()
        policy = parse_policy_json(row.policy_json)

    assert policy["runtime_allowed_tools"] == [
        "refund",
        "stripe.refunds.create",
        "internal_api_mutation",
        "inventory.items.delete",
    ]
    assert second_enforced.json()["metadata"]["runtime_policy_mandate"]["agent_runtime_allowed_tools"] == [
        "internal_api_mutation",
        "inventory.items.delete",
    ]
    assert second_enforced.json()["metadata"]["runtime_policy_mandate"]["project_runtime_allowed_tools"] == [
        "refund",
        "stripe.refunds.create",
        "internal_api_mutation",
        "inventory.items.delete",
    ]

    first_tool_still_allowed = client.post(
        "/v1/runtime-policy/check",
        headers=headers,
        json={
            "agent_name": "Payments Agent",
            "action_type": "refund",
            "tool_name": "stripe.refunds.create",
            "external_action": True,
            "impact_usd": 50,
        },
    )
    assert first_tool_still_allowed.status_code == 200
    assert first_tool_still_allowed.json()["status"] != "blocked"
    assert "not allowlisted" not in " ".join(first_tool_still_allowed.json()["reasons"])


def test_agent_profile_enforce_registers_customer_hosted_runner_idempotently(client: TestClient) -> None:
    project_id = "proj_agents_enforce_runner"
    _seed_project(client, project_id)
    headers = {"X-Project-Id": project_id}

    created = client.post(
        "/v1/agents",
        headers=headers,
        json={
            "display_name": "Operations Agent",
            "runtime_path": "sdk",
            "tool_names": ["internal.ops.execute", "sendgrid.messages.send"],
            "allowed_action_types": ["internal_api_mutation", "email_send"],
            "risk_limits": {
                "approval_required_above_usd": 100,
                "deny_above_usd": 1000,
                "approval_ttl_minutes": 30,
            },
            "verification_connectors": ["generic_rest"],
            "metadata": _setup_metadata(
                runner_mode="customer_hosted",
                credential_ref="cred_ops_runner_alias",
            ),
        },
    )
    assert created.status_code == 201, created.text

    first = client.post(f"/v1/agents/{created.json()['id']}/enforce", headers=headers)
    second = client.post(f"/v1/agents/{created.json()['id']}/enforce", headers=headers)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text

    metadata = second.json()["metadata"]["runtime_policy_mandate"]
    assert metadata["runner_name"] == "operations-agent-runner"
    assert metadata["runner_type"] == "customer_hosted"
    assert metadata["runner_supported_operation_kinds"] == ["UPDATE", "SEND"]
    assert metadata["runner_credential_ref"] == "cred_ops_runner_alias"
    assert "runner_ready" not in second.json()["metadata"]

    with client._session_factory() as session:  # type: ignore[attr-defined]
        runners = (
            session.query(ActionRunner)
            .filter(
                ActionRunner.project_id == project_id,
                ActionRunner.name == "operations-agent-runner",
            )
            .all()
        )
        assert len(runners) == 1
        runner = runners[0]
        assert runner.id == metadata["runner_id"]
        assert runner.status == "registered"
        assert runner.runner_type == "customer_hosted"
        assert json.loads(runner.supported_operation_kinds_json) == ["UPDATE", "SEND"]
        assert json.loads(runner.credential_scope_json) == {"credential_ref": "cred_ops_runner_alias"}


def test_agent_profile_action_type_operation_map_stays_aligned_with_setup_catalog() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    policy_catalog = repo_root / "zroky-dashboard" / "src" / "lib" / "policy-rules-view.ts"
    policy_source = policy_catalog.read_text(encoding="utf-8")
    policy_options = policy_source.split(
        "export const POLICY_ACTION_OPTIONS: PolicyActionOption[] = [",
        1,
    )[1].split("];", 1)[0]
    policy_map = dict(
        re.findall(
            r'id:\s*"([^"]+)"[\s\S]*?operationKind:\s*"([^"]+)"',
            policy_options,
        )
    )

    assert policy_map == ACTION_TYPE_OPERATION_KINDS

    setup_catalog = repo_root / "zroky-dashboard" / "src" / "lib" / "protected-agent-setup.ts"
    setup_source = setup_catalog.read_text(encoding="utf-8")
    templates_source = setup_source.split(
        "export const protectedAgentTemplates: ProtectedAgentTemplate[] = [",
        1,
    )[1].split("];", 1)[0]
    template_ids = re.findall(r'\{\s*id:\s*"([^"]+)"', templates_source)

    action_type_block = setup_source.split("function webhookBridgeActionType", 1)[1].split(
        "function operationKindForTemplate",
        1,
    )[0]
    action_type_by_template = dict(
        re.findall(r'if \(template\.id === "([^"]+)"\) return "([^"]+)";', action_type_block)
    )

    operation_kind_block = setup_source.split("function operationKindForTemplate", 1)[1].split(
        "function pythonString",
        1,
    )[0]
    operation_kind_by_template: dict[str, str] = {}
    for condition, operation_kind in re.findall(
        r'if \(([^)]+)\) return "([^"]+)";',
        operation_kind_block,
    ):
        for template_id in re.findall(r'template\.id === "([^"]+)"', condition):
            operation_kind_by_template[template_id] = operation_kind
    fallback_operation_kind = re.findall(r'return "([^"]+)";', operation_kind_block)[-1]
    setup_action_map = {
        action_type_by_template.get(template_id, "custom"): operation_kind_by_template.get(
            template_id,
            fallback_operation_kind,
        )
        for template_id in template_ids
    }

    assert setup_action_map == {
        action_type: ACTION_TYPE_OPERATION_KINDS[action_type]
        for action_type in setup_action_map
    }
