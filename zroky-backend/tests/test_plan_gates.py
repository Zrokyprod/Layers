"""
Tests for `app/api/dependencies/entitlements.py:require_entitlement`
and the wired 402 plan-gates on /v1/pilot/*, /v1/goldens/*,
/v1/replay/runs/*, and /v1/calls/{id}/mark-golden (Module 6).

The other Module 4 test files (test_pilot.py, test_goldens.py,
test_replay_runs.py) bypass the gate via an autouse fixture. THIS
file does NOT bypass — every test exercises the real
require_entitlement code path.

Coverage:
  - Gate denies free-tier orgs with 402 + X-Zroky-Plan-Hint header
  - Gate allows pro/plus/enterprise orgs (real DB rows)
  - X-Zroky-Plan-Hint reflects current plan_code on both pass and fail
  - 402 body shape matches plan §10.x contract (detail, required_entitlement,
    current_plan, upgrade_hint_url)
  - require_entitlement validates `key` argument at construction time
  - min_value path (numeric quota threshold)
  - Override entitlement unlocks a Free org without changing plan_code
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import Subscription
from app.db.session import get_db_session, get_db_session_read
from app.main import app
from app.services.entitlements import (
    seed_plan_entitlements,
    set_override_entitlement,
)
from app.services.entitlements_resolver import invalidate_all


PROJECT_HEADER = "X-Project-Id"
PLAN_HINT_HEADER = "X-Zroky-Plan-Hint"


# ── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture()
def client(tmp_path: Path):
    get_settings.cache_clear()
    db_path = tmp_path / "test_plan_gates.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )

    def override_get_db_session():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_db_session_read] = override_get_db_session
    invalidate_all()  # clean memory cache between tests

    with TestClient(app) as test_client:
        test_client._factory = factory  # type: ignore[attr-defined]
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    get_settings.cache_clear()
    invalidate_all()


def _seed_org(client: TestClient, *, org_id: str, plan_code: str) -> None:
    """Write a Subscription row + plan-source entitlement rows for `org_id`."""
    factory = client._factory  # type: ignore[attr-defined]
    session = factory()
    try:
        session.add(
            Subscription(
                id=f"sub-{org_id}",
                org_id=org_id,
                plan_code=plan_code,
                status="active",
                seats=1,
                stripe_customer_id=f"cus_{org_id}",
                stripe_sub_id=f"si_{org_id}",
                current_period_end=datetime.now(timezone.utc) + timedelta(days=30),
            )
        )
        session.commit()
        seed_plan_entitlements(session, org_id=org_id, plan_code=plan_code)
    finally:
        session.close()


# ── 402 denial path ─────────────────────────────────────────────────────────


class TestGate402Denial:
    def test_free_org_blocked_from_pilot(self, client: TestClient) -> None:
        _seed_org(client, org_id="free-org", plan_code="free")
        response = client.get(
            "/v1/pilot/actions",
            headers={PROJECT_HEADER: "free-org"},
        )
        assert response.status_code == 402
        body = response.json()
        # FastAPI wraps `detail=` in {"detail": <our_dict>}
        detail = body["detail"]
        assert detail["required_entitlement"] == "pilot.autopilot_enabled"
        assert detail["current_plan"] == "free"
        assert "upgrade_hint_url" in detail
        assert "pilot.autopilot_enabled" in detail["upgrade_hint_url"]

    def test_free_org_blocked_from_goldens(self, client: TestClient) -> None:
        _seed_org(client, org_id="free-org", plan_code="free")
        response = client.get(
            "/v1/goldens",
            headers={PROJECT_HEADER: "free-org"},
        )
        assert response.status_code == 402

    def test_free_org_blocked_from_replay_runs(self, client: TestClient) -> None:
        _seed_org(client, org_id="free-org", plan_code="free")
        response = client.get(
            "/v1/replay/runs",
            headers={PROJECT_HEADER: "free-org"},
        )
        assert response.status_code == 402

    def test_plus_org_allowed_through_pilot(self, client: TestClient) -> None:
        # Plus carries the full pilot feature gate.
        _seed_org(client, org_id="plus-org", plan_code="plus")
        response = client.get(
            "/v1/pilot/actions",
            headers={PROJECT_HEADER: "plus-org"},
        )
        assert response.status_code == 200
        assert response.headers.get(PLAN_HINT_HEADER) == "plus"

    def test_402_includes_plan_hint_header(self, client: TestClient) -> None:
        _seed_org(client, org_id="free-org", plan_code="free")
        response = client.get(
            "/v1/pilot/actions",
            headers={PROJECT_HEADER: "free-org"},
        )
        assert response.status_code == 402
        assert response.headers.get(PLAN_HINT_HEADER) == "free"

    def test_org_without_subscription_falls_back_to_free(
        self, client: TestClient
    ) -> None:
        # No _seed_org call — org has no subscription row at all. Resolver
        # treats this as free-tier. Gate should still 402.
        response = client.get(
            "/v1/pilot/actions",
            headers={PROJECT_HEADER: "ghost-org"},
        )
        assert response.status_code == 402
        assert response.json()["detail"]["current_plan"] == "free"


# ── allow path ──────────────────────────────────────────────────────────────


class TestGateAllow:
    def test_pro_org_allowed_through_pilot(self, client: TestClient) -> None:
        _seed_org(client, org_id="pro-org", plan_code="pro")
        response = client.get(
            "/v1/pilot/actions",
            headers={PROJECT_HEADER: "pro-org"},
        )
        assert response.status_code == 200
        assert response.headers.get(PLAN_HINT_HEADER) == "pro"

    def test_plus_org_allowed_through_goldens(self, client: TestClient) -> None:
        _seed_org(client, org_id="plus-org", plan_code="plus")
        response = client.get(
            "/v1/goldens",
            headers={PROJECT_HEADER: "plus-org"},
        )
        assert response.status_code == 200
        assert response.headers.get(PLAN_HINT_HEADER) == "plus"

    def test_enterprise_org_allowed_through_replay(
        self, client: TestClient
    ) -> None:
        _seed_org(client, org_id="ent-org", plan_code="enterprise")
        response = client.get(
            "/v1/replay/runs",
            headers={PROJECT_HEADER: "ent-org"},
        )
        assert response.status_code == 200
        assert response.headers.get(PLAN_HINT_HEADER) == "enterprise"

    def test_override_unlocks_free_org(self, client: TestClient) -> None:
        # Founder Console hook: a free-tier customer can be granted
        # pilot.autopilot_enabled via an override row without changing plan.
        _seed_org(client, org_id="free-grant-org", plan_code="free")
        factory = client._factory  # type: ignore[attr-defined]
        session = factory()
        try:
            set_override_entitlement(
                session,
                org_id="free-grant-org",
                key="pilot.autopilot_enabled",
                value=True,
            )
        finally:
            session.close()

        response = client.get(
            "/v1/pilot/actions",
            headers={PROJECT_HEADER: "free-grant-org"},
        )
        assert response.status_code == 200
        # Plan hint is still 'free' — override doesn't change plan_code,
        # only flips an individual entitlement.
        assert response.headers.get(PLAN_HINT_HEADER) == "free"


# ── require_entitlement factory validation ──────────────────────────────────


class TestRequireEntitlementFactory:
    def test_empty_key_rejected(self) -> None:
        from app.api.dependencies.entitlements import require_entitlement
        with pytest.raises(ValueError, match="non-empty"):
            require_entitlement("")
        with pytest.raises(ValueError, match="non-empty"):
            require_entitlement("   ")

    def test_unknown_key_warns_but_builds(self, caplog) -> None:
        from app.api.dependencies.entitlements import require_entitlement
        # Should warn but not raise — Founder Console can author ad-hoc keys.
        dep = require_entitlement("custom.feature.flag")
        assert callable(dep)
        # Warning should have been logged
        assert any(
            "custom.feature.flag" in record.message
            for record in caplog.records
            if record.levelname == "WARNING"
        )

    def test_known_key_builds_silently(self, caplog) -> None:
        from app.api.dependencies.entitlements import require_entitlement
        dep = require_entitlement("pilot.autopilot_enabled")
        assert callable(dep)
        # No warning for plan-bound keys
        assert not any(
            "pilot.autopilot_enabled" in record.message
            for record in caplog.records
            if record.levelname == "WARNING"
        )


# ── min_value path ──────────────────────────────────────────────────────────


class TestMinValueGate:
    """Verify the numeric-threshold variant via direct dependency
    invocation. (No route uses min_value yet; the contract is plumbed
    for forthcoming quota-checking endpoints.)"""

    def test_pro_passes_min_replay_runs(self, client: TestClient) -> None:
        from app.api.dependencies.entitlements import require_entitlement
        from app.services import entitlements_resolver
        from fastapi import Response

        _seed_org(client, org_id="pro-org", plan_code="pro")
        factory = client._factory  # type: ignore[attr-defined]
        session = factory()
        try:
            # pro.replay.monthly_runs = 1_000, so it passes min_value=100.
            value_or_raise = require_entitlement(
                "replay.monthly_runs", min_value=100,
            )
            from app.api.dependencies.tenant import TenantContext
            ctx = TenantContext(tenant_id="pro-org", role="member", subject=None)
            response = Response()
            result = value_or_raise(response, ctx, session)
            assert result is not None
        finally:
            session.close()

    def test_unlimited_sentinel_passes_any_min(self, client: TestClient) -> None:
        from app.api.dependencies.entitlements import require_entitlement
        from fastapi import Response

        _seed_org(client, org_id="ent-org", plan_code="enterprise")
        factory = client._factory  # type: ignore[attr-defined]
        session = factory()
        try:
            dep = require_entitlement("replay.monthly_runs", min_value=10**9)
            from app.api.dependencies.tenant import TenantContext
            ctx = TenantContext(tenant_id="ent-org", role="member", subject=None)
            response = Response()
            # _UNLIMITED == -1 should pass any threshold
            result = dep(response, ctx, session)
            assert result == -1
        finally:
            session.close()
