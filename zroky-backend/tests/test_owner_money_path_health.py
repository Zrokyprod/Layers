from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
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
    GoldenTrace,
    Issue,
    Project,
    ProviderKeyVault,
    ReplayJob,
    ReplayRun,
    Subscription,
)
from app.db.session import get_db_session
from app.main import app


@pytest.fixture()
def client(tmp_path: Path):
    db_path = tmp_path / "owner_money_path.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_db
    try:
        yield TestClient(app), session_factory
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()
        engine.dispose()


def _set_owner_auth(monkeypatch: pytest.MonkeyPatch, token: str = "owner-token") -> dict[str, str]:
    monkeypatch.setenv("REQUIRE_PROVISIONING_TOKEN", "false")
    monkeypatch.setenv("PROVISIONING_TOKEN", token)
    get_settings.cache_clear()
    return {"x-zroky-admin-token": token}


def _call(project_id: str, call_id: str, *, created_at: datetime, agent_name: str = "agent") -> Call:
    return Call(
        id=call_id,
        project_id=project_id,
        event_id=f"{call_id}:event",
        created_at=created_at,
        agent_name=agent_name,
        provider="openai",
        model="gpt-4.1-mini",
        status="completed",
        payload_json="{}",
        metadata_json=json.dumps({"source": "test"}),
    )


def test_owner_money_path_health_aggregates_real_backend_state(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_client, session_factory = client
    owner_headers = _set_owner_auth(monkeypatch)
    now = datetime.now(UTC)

    with session_factory() as db:
        db.add_all(
            [
                Project(id="proj_good", name="Good Tenant", owner_ref="good", is_active=True),
                Project(id="proj_gap", name="Gap Tenant", owner_ref="gap", is_active=True),
                Subscription(
                    id="sub_good",
                    org_id="proj_good",
                    plan_code="pro",
                    status="active",
                    current_period_end=now + timedelta(days=30),
                ),
                Subscription(
                    id="sub_gap",
                    org_id="proj_gap",
                    plan_code="pilot",
                    status="active",
                    current_period_end=now + timedelta(days=30),
                ),
                _call("proj_good", "call_good", created_at=now - timedelta(hours=1)),
                _call("proj_gap", "call_old", created_at=now - timedelta(days=3)),
                Issue(
                    id="issue_good",
                    project_id="proj_good",
                    failure_code="SCHEMA_VIOLATION",
                    prompt_fingerprint="fp_good",
                    agent_name="agent",
                    status="open",
                    severity="high",
                    occurrence_count=3,
                    first_seen_at=now - timedelta(hours=2),
                    last_seen_at=now - timedelta(hours=1),
                    sample_call_id="call_good",
                ),
                Anomaly(
                    id="anom_gap",
                    project_id="proj_gap",
                    fingerprint="fp-gap",
                    detector="SCHEMA_VIOLATION",
                    severity="medium",
                    status="open",
                    first_seen_at=now - timedelta(days=3),
                    last_seen_at=now - timedelta(days=3),
                    occurrence_count=2,
                ),
                ProviderKeyVault(
                    id="pk_good",
                    project_id="proj_good",
                    provider="openai",
                    ciphertext=b"encrypted",
                    key_fingerprint="fp_provider_good",
                    key_last4="1234",
                    is_active=True,
                ),
                GoldenSet(
                    id="gs_good",
                    project_id="proj_good",
                    name="Good Golden",
                    created_at=now,
                    updated_at=now,
                ),
                GoldenTrace(
                    id="gt_good",
                    golden_set_id="gs_good",
                    project_id="proj_good",
                    call_id="call_good",
                    status="active",
                    expected_output_text="ok",
                    created_at=now,
                    updated_at=now,
                ),
                ReplayRun(
                    id="rr_verified",
                    project_id="proj_good",
                    golden_set_id="gs_good",
                    trigger="manual",
                    status="pass",
                    summary_json=json.dumps(
                        {
                            "verified_fix": True,
                            "verification_status": "verified_fix",
                        },
                        separators=(",", ":"),
                    ),
                    created_at=now - timedelta(hours=1),
                ),
                ReplayRun(
                    id="rr_ci_fail",
                    project_id="proj_good",
                    golden_set_id="gs_good",
                    trigger="github",
                    git_sha="abc123",
                    status="fail",
                    summary_json=json.dumps({"verdict": "fail"}, separators=(",", ":")),
                    created_at=now - timedelta(hours=1),
                ),
                ReplayJob(
                    id="job_good",
                    tenant_id="proj_good",
                    call_id="call_good",
                    status="completed",
                    created_at=now - timedelta(hours=1),
                ),
            ]
        )
        db.commit()

    response = test_client.get("/v1/owner/money-path-health", headers=owner_headers)
    assert response.status_code == 200
    payload = response.json()

    assert payload["platform"]["captures_24h"] == 1
    assert payload["platform"]["issues_open"] == 2
    assert payload["platform"]["replay_runs_7d"] == 2
    assert payload["platform"]["verified_replay_runs_7d"] == 1
    assert payload["platform"]["golden_traces_active"] == 1
    assert payload["platform"]["ci_runs_7d"] == 1
    assert payload["platform"]["ci_blocks_7d"] == 1
    assert payload["platform"]["tenants_missing_provider_key"] == 1
    assert payload["platform"]["tenants_without_recent_capture"] == 1
    assert payload["platform"]["last_deployed_smoke"]["status"] == "not_configured"

    tenants = {row["project_id"]: row for row in payload["tenants"]}
    assert set(tenants) == {"proj_good", "proj_gap"}

    good = tenants["proj_good"]
    assert good["plan_code"] == "pro"
    assert good["captures_24h"] == 1
    assert good["open_issue_count"] == 1
    assert good["replay_run_count_7d"] == 2
    assert good["verified_replay_count_7d"] == 1
    assert good["golden_trace_count"] == 1
    assert good["ci_run_count_7d"] == 1
    assert good["blocking_ci_failures_7d"] == 1
    assert good["provider_key_status"] == {
        "state": "configured",
        "active_provider_count": 1,
    }
    assert good["replay_quota_status"]["state"] == "ok"
    assert good["replay_quota_status"]["used"] == 3
    assert good["next_owner_action"] == "review_blocked_ci"

    gap = tenants["proj_gap"]
    assert gap["plan_code"] == "pilot"
    assert gap["captures_24h"] == 0
    assert gap["open_issue_count"] == 1
    assert gap["provider_key_status"]["state"] == "missing"
    assert gap["next_owner_action"] == "restore_capture"


def test_owner_money_path_health_reports_deployment_smoke_evidence(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_client, session_factory = client
    owner_headers = _set_owner_auth(monkeypatch)
    now = datetime.now(UTC)

    with session_factory() as db:
        db.add(Project(id="proj_smoke", name="Smoke Tenant", owner_ref="smoke", is_active=True))
        db.add(
            _call(
                "proj_smoke",
                "call_smoke",
                created_at=now - timedelta(minutes=5),
                agent_name="deployment-smoke-agent",
            )
        )
        db.add(
            GoldenSet(
                id="gs_smoke",
                project_id="proj_smoke",
                name="Deployment smoke",
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            GoldenTrace(
                id="gt_smoke",
                golden_set_id="gs_smoke",
                project_id="proj_smoke",
                call_id="call_smoke",
                status="active",
                source_evidence_json=json.dumps({"source": "deployment-smoke"}),
                expected_output_text='{"status":"smoke-ok"}',
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            ReplayRun(
                id="rr_smoke_ci",
                project_id="proj_smoke",
                golden_set_id="gs_smoke",
                trigger="github",
                git_sha="deploy-smoke-regression",
                status="pass",
                created_at=now,
                summary_json=json.dumps({"verdict": "pass"}, separators=(",", ":")),
            )
        )
        db.commit()

    response = test_client.get("/v1/owner/money-path-health", headers=owner_headers)
    assert response.status_code == 200
    smoke = response.json()["platform"]["last_deployed_smoke"]
    assert smoke["status"] == "passed"
    assert smoke["project_id"] == "proj_smoke"
    assert smoke["call_id"] == "call_smoke"
    assert smoke["golden_trace_id"] == "gt_smoke"
    assert smoke["ci_run_id"] == "rr_smoke_ci"


def test_owner_money_path_health_requires_owner_credentials(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_client, _ = client
    _set_owner_auth(monkeypatch)

    response = test_client.get("/v1/owner/money-path-health")
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid owner credentials."
