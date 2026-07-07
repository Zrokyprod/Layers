from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import AuditLog, Entitlement, Project, Subscription
from app.db.session import get_db_session
from app.main import app
from app.api.routes._internal import owner_plan_grants


@pytest.fixture()
def client(tmp_path: Path):
    db_path = tmp_path / "owner_plan_grants.db"
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


def _owner_headers(
    monkeypatch: pytest.MonkeyPatch,
    token: str = "owner-token",
    app_env: str = "development",
) -> dict[str, str]:
    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.setenv("REQUIRE_PROVISIONING_TOKEN", "false")
    monkeypatch.setenv("PROVISIONING_TOKEN", token)
    get_settings.cache_clear()
    return {"x-zroky-admin-token": token}


def _seed_free_org(session_factory, org_id: str = "org_grant_1", name: str = "Grant Co") -> None:
    with session_factory() as db:
        db.add(Project(id=org_id, name=name, owner_ref="grant", is_active=True))
        db.add(
            Subscription(
                id="sub_grant_1",
                org_id=org_id,
                payment_provider="razorpay",
                payment_customer_ref="billing@grant.co",
                plan_code="free",
                status="active",
            )
        )
        db.commit()


def _challenge(test_client, headers, org_id: str, plan: str) -> dict:
    res = test_client.post(
        "/v1/owner/plan-grants/challenge",
        headers=headers,
        json={"org_id": org_id, "target_plan_code": plan},
    )
    assert res.status_code == 200, res.text
    return res.json()


def test_challenge_and_commit_flips_plan_and_writes_audit(client, monkeypatch: pytest.MonkeyPatch) -> None:
    test_client, session_factory = client
    headers = _owner_headers(monkeypatch)
    _seed_free_org(session_factory)

    ch = _challenge(test_client, headers, "org_grant_1", "team")
    assert ch["current_plan_code"] == "free"
    assert ch["target_plan_code"] == "team"
    assert ch["delivery"] == "response"
    assert ch["dev_code"] and len(ch["dev_code"]) == 6

    commit = test_client.post(
        "/v1/owner/plan-grants",
        headers=headers,
        json={
            "challenge_id": ch["challenge_id"],
            "code": ch["dev_code"],
            "typed_confirmation": "org_grant_1",
            "org_id": "org_grant_1",
            "target_plan_code": "team",
            "reason": "Design partner comp upgrade",
            "duration_kind": "permanent",
        },
    )
    assert commit.status_code == 200, commit.text
    body = commit.json()
    assert body["ok"] is True
    assert body["previous_plan_code"] == "free"
    assert body["plan_code"] == "team"

    with session_factory() as db:
        sub = db.scalar(select(Subscription).where(Subscription.org_id == "org_grant_1"))
        assert sub is not None and sub.plan_code == "team" and sub.status == "active"
        # Entitlements were re-seeded to the team template.
        plan_rows = db.execute(
            select(Entitlement).where(
                Entitlement.org_id == "org_grant_1", Entitlement.source == "plan"
            )
        ).scalars().all()
        assert plan_rows, "plan entitlements should be seeded"
        keys = {row.key for row in plan_rows}
        assert any(key.startswith("pro.") for key in keys)
        # Audit row recorded.
        audit = db.scalar(select(AuditLog).where(AuditLog.action == "owner.plan.override"))
        assert audit is not None
        meta = json.loads(audit.metadata_json)
        assert meta["previous_plan_code"] == "free"
        assert meta["plan_code"] == "team"

    # History endpoint surfaces the grant.
    audit_res = test_client.get("/v1/owner/plan-grants/audit?org_id=org_grant_1", headers=headers)
    assert audit_res.status_code == 200
    items = audit_res.json()["items"]
    assert len(items) == 1
    assert items[0]["plan_code"] == "team"


def test_commit_is_single_use_and_rejects_replay(client, monkeypatch: pytest.MonkeyPatch) -> None:
    test_client, session_factory = client
    headers = _owner_headers(monkeypatch)
    _seed_free_org(session_factory)

    ch = _challenge(test_client, headers, "org_grant_1", "team")
    payload = {
        "challenge_id": ch["challenge_id"],
        "code": ch["dev_code"],
        "typed_confirmation": "org_grant_1",
        "org_id": "org_grant_1",
        "target_plan_code": "team",
        "reason": "first",
        "duration_kind": "permanent",
    }
    first = test_client.post("/v1/owner/plan-grants", headers=headers, json=payload)
    assert first.status_code == 200
    replay = test_client.post("/v1/owner/plan-grants", headers=headers, json=payload)
    assert replay.status_code == 401


def test_commit_rejects_wrong_code(client, monkeypatch: pytest.MonkeyPatch) -> None:
    test_client, session_factory = client
    headers = _owner_headers(monkeypatch)
    _seed_free_org(session_factory)

    ch = _challenge(test_client, headers, "org_grant_1", "team")
    res = test_client.post(
        "/v1/owner/plan-grants",
        headers=headers,
        json={
            "challenge_id": ch["challenge_id"],
            "code": "000000" if ch["dev_code"] != "000000" else "111111",
            "typed_confirmation": "org_grant_1",
            "org_id": "org_grant_1",
            "target_plan_code": "team",
            "reason": "x",
            "duration_kind": "permanent",
        },
    )
    assert res.status_code == 401


def test_commit_rejects_typed_confirmation_mismatch(client, monkeypatch: pytest.MonkeyPatch) -> None:
    test_client, session_factory = client
    headers = _owner_headers(monkeypatch)
    _seed_free_org(session_factory)

    ch = _challenge(test_client, headers, "org_grant_1", "team")
    res = test_client.post(
        "/v1/owner/plan-grants",
        headers=headers,
        json={
            "challenge_id": ch["challenge_id"],
            "code": ch["dev_code"],
            "typed_confirmation": "wrong-org",
            "org_id": "org_grant_1",
            "target_plan_code": "team",
            "reason": "x",
            "duration_kind": "permanent",
        },
    )
    assert res.status_code == 422


def test_commit_rejects_target_swap(client, monkeypatch: pytest.MonkeyPatch) -> None:
    """A challenge minted for team cannot be redeemed to grant a different plan."""
    test_client, session_factory = client
    headers = _owner_headers(monkeypatch)
    _seed_free_org(session_factory)

    ch = _challenge(test_client, headers, "org_grant_1", "team")
    res = test_client.post(
        "/v1/owner/plan-grants",
        headers=headers,
        json={
            "challenge_id": ch["challenge_id"],
            "code": ch["dev_code"],
            "typed_confirmation": "org_grant_1",
            "org_id": "org_grant_1",
            "target_plan_code": "starter",
            "reason": "x",
            "duration_kind": "permanent",
        },
    )
    assert res.status_code == 422


def test_challenge_rejects_unknown_plan(client, monkeypatch: pytest.MonkeyPatch) -> None:
    test_client, session_factory = client
    headers = _owner_headers(monkeypatch)
    _seed_free_org(session_factory)

    res = test_client.post(
        "/v1/owner/plan-grants/challenge",
        headers=headers,
        json={"org_id": "org_grant_1", "target_plan_code": "platinum"},
    )
    assert res.status_code == 422


def test_production_challenge_requires_durable_store(client, monkeypatch: pytest.MonkeyPatch) -> None:
    test_client, session_factory = client
    headers = _owner_headers(monkeypatch, app_env="production")
    _seed_free_org(session_factory)
    monkeypatch.setattr(owner_plan_grants, "_redis_ok", lambda: False)

    res = test_client.post(
        "/v1/owner/plan-grants/challenge",
        headers=headers,
        json={"org_id": "org_grant_1", "target_plan_code": "pro"},
    )

    assert res.status_code == 503
    assert res.json()["detail"] == "Owner plan grant challenge store unavailable."


def test_production_challenge_does_not_fallback_to_response_code(client, monkeypatch: pytest.MonkeyPatch) -> None:
    test_client, session_factory = client
    headers = _owner_headers(monkeypatch, app_env="production")
    _seed_free_org(session_factory)
    monkeypatch.setattr(owner_plan_grants, "_store_challenge", lambda challenge_id, record: None)
    monkeypatch.setattr(owner_plan_grants, "_delete_challenge", lambda challenge_id: None)
    monkeypatch.setattr(owner_plan_grants, "_email_owner_code", lambda *args, **kwargs: False)

    res = test_client.post(
        "/v1/owner/plan-grants/challenge",
        headers=headers,
        json={"org_id": "org_grant_1", "target_plan_code": "pro"},
    )

    assert res.status_code == 503
    assert res.json()["detail"] == "Owner verification code could not be delivered."


def test_endpoints_require_owner_auth(client, monkeypatch: pytest.MonkeyPatch) -> None:
    test_client, session_factory = client
    # Configure a provisioning token but send no header — must be rejected.
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("REQUIRE_PROVISIONING_TOKEN", "false")
    monkeypatch.setenv("PROVISIONING_TOKEN", "owner-token")
    get_settings.cache_clear()
    _seed_free_org(session_factory)

    res = test_client.post(
        "/v1/owner/plan-grants/challenge",
        json={"org_id": "org_grant_1", "target_plan_code": "pro"},
    )
    assert res.status_code == 401
