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
    Anomaly,
    Call,
    GoldenSet,
    OutcomeEvent,
    OutcomeReconciliationCheck,
    Project,
    ProjectMembership,
    ReplayRun,
    RuntimePolicyDecision,
    User,
)
from app.db.session import get_db_session, get_db_session_read
from app.main import app
from app.services import entitlements_resolver
from app.services.security import issue_access_token


AUTH_SECRET = "tenant-route-scoping-secret"


@pytest.fixture()
def client_ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AUTH_JWT_SECRET", AUTH_SECRET)
    monkeypatch.setenv("ALLOW_PROJECT_HEADER_CONTEXT", "false")
    monkeypatch.setenv("JWT_ISSUER", "")
    monkeypatch.setenv("JWT_AUDIENCE", "")
    get_settings.cache_clear()
    entitlements_resolver.invalidate_all()
    from app.services.billing_plans import PLAN_ENTITLEMENTS

    pro_entitlements = dict(PLAN_ENTITLEMENTS["pro"])
    monkeypatch.setattr(entitlements_resolver, "has", lambda db, org_id, key: True)
    monkeypatch.setattr(entitlements_resolver, "get", lambda db, org_id, key, default=None: pro_entitlements.get(key, default))
    monkeypatch.setattr(entitlements_resolver, "resolve_all", lambda db, org_id: dict(pro_entitlements))
    monkeypatch.setattr(entitlements_resolver, "get_plan_code", lambda db, org_id: "pro")

    engine = create_engine(
        f"sqlite:///{tmp_path / 'tenant-route-scoping.db'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def override_get_db_session():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_db_session_read] = override_get_db_session

    with TestClient(app) as client:
        client._session_factory = factory  # type: ignore[attr-defined]
        yield client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    get_settings.cache_clear()
    entitlements_resolver.invalidate_all()


def _headers(token: str, project_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Project-Id": project_id}


def _seed_two_project_user(factory) -> str:
    now = datetime.now(timezone.utc)
    with factory() as session:
        user = User(subject="user:phase2", email="phase2@example.com", is_active=True)
        session.add(user)
        session.flush()

        for project_id, name in [("proj_alpha", "Alpha Project"), ("proj_beta", "Beta Project")]:
            session.add(Project(id=project_id, name=name, owner_ref=user.subject, is_active=True))
            session.flush()
            session.add(
                ProjectMembership(
                    project_id=project_id,
                    user_id=user.id,
                    role="owner",
                    is_active=True,
                )
            )
            session.add(
                Call(
                    id=f"call_{project_id}",
                    project_id=project_id,
                    event_id=f"evt_{project_id}",
                    created_at=now,
                    agent_name=f"agent-{project_id}",
                    call_type="chat",
                    provider="openai",
                    model="gpt-4o-mini",
                    status="failed",
                    error_code="TOOL_CALL_FAILURE",
                    payload_json=json.dumps({"response": f"output-{project_id}"}),
                )
            )
            session.add(
                Anomaly(
                    id=f"issue_{project_id}",
                    project_id=project_id,
                    fingerprint=f"fp_{project_id}",
                    detector="TOOL_CALL_FAILURE",
                    severity="high",
                    status="open",
                    first_seen_at=now - timedelta(minutes=5),
                    last_seen_at=now,
                    occurrence_count=2,
                    sample_call_ids_json=json.dumps([f"call_{project_id}"]),
                    evidence_json=json.dumps(
                        {
                            "failure_code": "TOOL_CALL_FAILURE",
                            "agent_name": f"agent-{project_id}",
                            "blast_radius_usd": 2.5,
                        },
                        separators=(",", ":"),
                    ),
                )
            )
            session.add(
                GoldenSet(
                    id=f"golden_{project_id}",
                    project_id=project_id,
                    name=f"Golden {project_id}",
                )
            )
            session.add(
                ReplayRun(
                    id=f"run_{project_id}",
                    project_id=project_id,
                    golden_set_id=f"golden_{project_id}",
                    trigger="manual",
                    status="pass",
                    summary_json=json.dumps(
                        {
                            "trace_count_at_dispatch": 1,
                            "trace_count_executed": 1,
                            "pass_count": 1,
                            "verification_status": "verified_fix",
                            "verified_fix": True,
                            "replay_mode": "real",
                        },
                        separators=(",", ":"),
                    ),
                )
            )
            session.add(
                RuntimePolicyDecision(
                    id=f"decision_{project_id}",
                    project_id=project_id,
                    trace_id=f"trace_{project_id}",
                    call_id=f"call_{project_id}",
                    agent_name=f"refund-agent-{project_id}",
                    action_type="refund",
                    tool_name="refund_payment",
                    decision="allow",
                    status="allowed",
                    reasons_json=json.dumps(["within_mandate"]),
                    request_json=json.dumps({"amount_usd": 42.5, "project_id": project_id}),
                    policy_snapshot_json=json.dumps({"max_refund_usd": 100}),
                    intended_action_json=json.dumps({"refund_id": f"refund_{project_id}"}),
                    trace_context_json=json.dumps({"trace_id": f"trace_{project_id}"}),
                    policy_hit_json=json.dumps({"rule": "refund_limit"}),
                    business_impact_json=json.dumps({"amount_usd": 42.5}),
                )
            )
            session.add(
                OutcomeReconciliationCheck(
                    id=f"orc_{project_id}",
                    project_id=project_id,
                    call_id=f"call_{project_id}",
                    trace_id=f"trace_{project_id}",
                    runtime_policy_decision_id=f"decision_{project_id}",
                    action_type="refund",
                    connector_type="ledger_refund_api",
                    system_ref=f"refund_{project_id}",
                    verdict="matched",
                    reason="ledger refund matched",
                    amount_usd=42.5,
                    currency="USD",
                    claimed_json=json.dumps({"refund_id": f"refund_{project_id}", "amount_usd": 42.5}),
                    actual_json=json.dumps({"refund_id": f"refund_{project_id}", "amount_usd": 42.5}),
                    comparison_json=json.dumps({"amount_usd": {"matched": True}}),
                    idempotency_key=f"orc-key-{project_id}",
                    checked_at=now,
                )
            )
            session.add(
                OutcomeEvent(
                    id=f"outcome_{project_id}",
                    project_id=project_id,
                    call_id=f"call_{project_id}",
                    outcome_type="refund_issued",
                    amount_usd=42.5,
                    source="api",
                    external_ref=f"refund_{project_id}",
                    idempotency_key=f"outcome-key-{project_id}",
                    occurred_at=now,
                )
            )

        session.commit()
        token = issue_access_token(
            user_id=user.id,
            email=user.email,
            subject=user.subject,
            expire_hours=1,
            secret=AUTH_SECRET,
        )
        return token


def _seed_single_project_user(factory) -> str:
    with factory() as session:
        user = User(subject="user:single-project", email="single@example.com", is_active=True)
        session.add(user)
        session.flush()
        session.add(Project(id="proj_single", name="Single Project", owner_ref=user.subject, is_active=True))
        session.flush()
        session.add(
            ProjectMembership(
                project_id="proj_single",
                user_id=user.id,
                role="owner",
                is_active=True,
            )
        )
        session.commit()
        token = issue_access_token(
            user_id=user.id,
            email=user.email,
            subject=user.subject,
            expire_hours=1,
            secret=AUTH_SECRET,
        )
        return token


def test_same_session_switches_core_project_scoped_surfaces(client_ctx: TestClient) -> None:
    token = _seed_two_project_user(client_ctx._session_factory)  # type: ignore[attr-defined]

    alpha_headers = _headers(token, "proj_alpha")
    beta_headers = _headers(token, "proj_beta")

    alpha_calls = client_ctx.get("/v1/calls", headers=alpha_headers)
    beta_calls = client_ctx.get("/v1/calls", headers=beta_headers)
    assert alpha_calls.status_code == 200
    assert beta_calls.status_code == 200
    assert [item["call_id"] for item in alpha_calls.json()["items"]] == ["call_proj_alpha"]
    assert [item["call_id"] for item in beta_calls.json()["items"]] == ["call_proj_beta"]

    alpha_issues = client_ctx.get("/v1/issues", headers=alpha_headers)
    beta_issues = client_ctx.get("/v1/issues", headers=beta_headers)
    assert [item["id"] for item in alpha_issues.json()["items"]] == ["issue_proj_alpha"]
    assert [item["id"] for item in beta_issues.json()["items"]] == ["issue_proj_beta"]

    alpha_goldens = client_ctx.get("/v1/goldens", headers=alpha_headers)
    beta_goldens = client_ctx.get("/v1/goldens", headers=beta_headers)
    assert [item["id"] for item in alpha_goldens.json()["items"]] == ["golden_proj_alpha"]
    assert [item["id"] for item in beta_goldens.json()["items"]] == ["golden_proj_beta"]

    alpha_replay = client_ctx.get("/v1/replay/runs", headers=alpha_headers)
    beta_replay = client_ctx.get("/v1/replay/runs", headers=beta_headers)
    assert [item["id"] for item in alpha_replay.json()["items"]] == ["run_proj_alpha"]
    assert [item["id"] for item in beta_replay.json()["items"]] == ["run_proj_beta"]

    alpha_billing = client_ctx.get("/v1/billing/me", headers=alpha_headers)
    beta_billing = client_ctx.get("/v1/billing/me", headers=beta_headers)
    assert alpha_billing.status_code == 200
    assert beta_billing.status_code == 200
    assert alpha_billing.json()["org_id"] == "proj_alpha"
    assert beta_billing.json()["org_id"] == "proj_beta"

    alpha_team = client_ctx.get("/v1/projects/proj_alpha/memberships", headers=alpha_headers)
    beta_team = client_ctx.get("/v1/projects/proj_beta/memberships", headers=beta_headers)
    assert alpha_team.status_code == 200
    assert beta_team.status_code == 200
    assert {item["project_id"] for item in alpha_team.json()} == {"proj_alpha"}
    assert {item["project_id"] for item in beta_team.json()} == {"proj_beta"}

    alpha_policy = client_ctx.get("/v1/runtime-policy/approvals?status=all", headers=alpha_headers)
    beta_policy = client_ctx.get("/v1/runtime-policy/approvals?status=all", headers=beta_headers)
    assert alpha_policy.status_code == 200
    assert beta_policy.status_code == 200
    assert [item["id"] for item in alpha_policy.json()["items"]] == ["decision_proj_alpha"]
    assert [item["id"] for item in beta_policy.json()["items"]] == ["decision_proj_beta"]

    beta_evidence = client_ctx.get(
        "/v1/runtime-policy/decisions/decision_proj_beta/evidence",
        headers=beta_headers,
    )
    assert beta_evidence.status_code == 200
    assert beta_evidence.json()["project_id"] == "proj_beta"
    assert beta_evidence.json()["outcome_reconciliation"][0]["id"] == "orc_proj_beta"

    foreign_evidence = client_ctx.get(
        "/v1/runtime-policy/decisions/decision_proj_beta/evidence",
        headers=alpha_headers,
    )
    assert foreign_evidence.status_code == 404

    alpha_reconciliation = client_ctx.get("/v1/outcomes/reconciliation", headers=alpha_headers)
    beta_reconciliation = client_ctx.get("/v1/outcomes/reconciliation", headers=beta_headers)
    assert alpha_reconciliation.status_code == 200
    assert beta_reconciliation.status_code == 200
    assert [item["id"] for item in alpha_reconciliation.json()["items"]] == ["orc_proj_alpha"]
    assert [item["id"] for item in beta_reconciliation.json()["items"]] == ["orc_proj_beta"]

    foreign_reconciliation_by_call = client_ctx.get(
        "/v1/outcomes/reconciliation/by-call/call_proj_beta",
        headers=alpha_headers,
    )
    assert foreign_reconciliation_by_call.status_code == 200
    assert foreign_reconciliation_by_call.json()["items"] == []

    foreign_reconciliation_detail = client_ctx.get(
        "/v1/outcomes/reconciliation/orc_proj_beta",
        headers=alpha_headers,
    )
    assert foreign_reconciliation_detail.status_code == 404

    alpha_outcomes_by_call = client_ctx.get("/v1/outcomes/by-call/call_proj_beta", headers=alpha_headers)
    beta_outcomes_by_call = client_ctx.get("/v1/outcomes/by-call/call_proj_beta", headers=beta_headers)
    assert alpha_outcomes_by_call.status_code == 200
    assert beta_outcomes_by_call.status_code == 200
    assert alpha_outcomes_by_call.json() == []
    assert [item["outcome_type"] for item in beta_outcomes_by_call.json()] == ["refund_issued"]


def test_project_delete_soft_deactivates_project_and_removes_from_user_list(client_ctx: TestClient) -> None:
    token = _seed_two_project_user(client_ctx._session_factory)  # type: ignore[attr-defined]

    response = client_ctx.request(
        "DELETE",
        "/v1/projects/proj_beta",
        headers=_headers(token, "proj_beta"),
        json={"confirm_project_name": "Beta Project"},
    )

    assert response.status_code == 200
    assert response.json()["project_id"] == "proj_beta"
    assert response.json()["is_active"] is False

    projects = client_ctx.get("/v1/auth/me/projects", headers={"Authorization": f"Bearer {token}"})
    assert projects.status_code == 200
    assert [project["project_id"] for project in projects.json()] == ["proj_alpha"]


def test_project_delete_blocks_only_active_project(client_ctx: TestClient) -> None:
    token = _seed_single_project_user(client_ctx._session_factory)  # type: ignore[attr-defined]

    response = client_ctx.request(
        "DELETE",
        "/v1/projects/proj_single",
        headers=_headers(token, "proj_single"),
        json={"confirm_project_name": "Single Project"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Create or switch to another active project before deleting your only project."


def test_current_user_project_create_respects_plan_limit(
    client_ctx: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(entitlements_resolver, "resolve_all", lambda db, org_id: {"max_projects": 3})
    token = _seed_two_project_user(client_ctx._session_factory)  # type: ignore[attr-defined]

    created = client_ctx.post(
        "/v1/auth/me/projects",
        headers=_headers(token, "proj_alpha"),
        json={"name": "Gamma Agent"},
    )
    assert created.status_code == 201
    created_body = created.json()
    assert created_body["project_name"] == "Gamma Agent"
    assert created_body["role"] == "owner"

    blocked = client_ctx.post(
        "/v1/auth/me/projects",
        headers=_headers(token, "proj_alpha"),
        json={"name": "Delta Agent"},
    )
    assert blocked.status_code == 402
    assert blocked.json()["detail"] == "Project limit reached for this plan (3/3). Upgrade to add more projects."


def test_project_path_rejects_selected_project_mismatch(client_ctx: TestClient) -> None:
    token = _seed_two_project_user(client_ctx._session_factory)  # type: ignore[attr-defined]

    response = client_ctx.get(
        "/v1/projects/proj_beta/memberships",
        headers=_headers(token, "proj_alpha"),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Selected project does not match requested project."
