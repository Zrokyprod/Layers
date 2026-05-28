"""
Tests for `app/services/entitlements_resolver.py` (Module 6).

Coverage:
  - `_truthy`: bool/int/str/None/sentinel-unlimited semantics
  - `_resolve_from_db`: precedence merge override > trial > plan,
    expired-row filtering, missing-subscription free fallback
  - `resolve_all`: returns merged dict; idempotent across calls
  - `has` / `get`: convenience wrappers
  - `get_plan_code`: falls back to free when no subscription
  - `invalidate` / `invalidate_all`: drops in-memory cache
  - cross-org tenant isolation
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import Entitlement, Subscription
from app.services import entitlements_resolver
from app.services.billing_plans import PLAN_ENTITLEMENTS
from app.services.entitlements import (
    seed_plan_entitlements,
    set_override_entitlement,
    set_trial_entitlements,
)
from app.services.entitlements_resolver import (
    _SOURCE_RANK,
    _resolve_from_db,
    _truthy,
    get,
    get_plan_code,
    has,
    invalidate,
    invalidate_all,
    resolve_all,
)


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "test_entitlements_resolver.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = factory()
    # Memory cache survives across tests in the same process — reset
    # before each test so previous test state doesn't bleed in.
    invalidate_all()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
        invalidate_all()


def _seed_subscription(db, *, org_id: str, plan_code: str) -> Subscription:
    sub = Subscription(
        id=f"sub-{org_id}",
        org_id=org_id,
        plan_code=plan_code,
        status="active",
        seats=1,
        stripe_customer_id=f"cus_{org_id}",
        stripe_sub_id=f"si_{org_id}",
        current_period_end=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db.add(sub)
    db.commit()
    return sub


# ── _truthy ─────────────────────────────────────────────────────────────────


class TestTruthy:
    def test_bool_passes_through(self) -> None:
        assert _truthy(True) is True
        assert _truthy(False) is False

    def test_int_nonzero_is_true(self) -> None:
        assert _truthy(100) is True
        assert _truthy(1) is True

    def test_int_zero_is_false(self) -> None:
        assert _truthy(0) is False

    def test_unlimited_sentinel_is_truthy(self) -> None:
        # -1 is the _UNLIMITED sentinel from billing_plans; the resolver
        # treats it as "no cap" which means True for has() purposes.
        assert _truthy(-1) is True

    def test_nonempty_string_is_true(self) -> None:
        assert _truthy("engineer") is True
        assert _truthy("executive") is True

    def test_empty_string_is_false(self) -> None:
        assert _truthy("") is False
        assert _truthy("   ") is False

    def test_none_is_false(self) -> None:
        assert _truthy(None) is False

    def test_list_dict_truthy(self) -> None:
        assert _truthy([1]) is True
        assert _truthy({"a": 1}) is True
        assert _truthy([]) is False
        assert _truthy({}) is False


# ── _resolve_from_db ────────────────────────────────────────────────────────


class TestResolveFromDb:
    def test_no_subscription_returns_free_template(self, db_session) -> None:
        resolved = _resolve_from_db(db_session, "org-unknown")
        assert resolved == PLAN_ENTITLEMENTS["free"]

    def test_subscription_only_returns_plan_template(self, db_session) -> None:
        _seed_subscription(db_session, org_id="org-1", plan_code="pro")
        resolved = _resolve_from_db(db_session, "org-1")
        assert resolved == PLAN_ENTITLEMENTS["pro"]

    def test_plan_rows_override_template(self, db_session) -> None:
        _seed_subscription(db_session, org_id="org-1", plan_code="free")
        seed_plan_entitlements(db_session, org_id="org-1", plan_code="pro")
        resolved = _resolve_from_db(db_session, "org-1")
        # Should reflect plan rows (pro values), not the subscription
        # plan_code template (free values).
        assert resolved["pilot.autopilot_enabled"] is True

    def test_trial_overlays_plan(self, db_session) -> None:
        _seed_subscription(db_session, org_id="org-1", plan_code="free")
        seed_plan_entitlements(db_session, org_id="org-1", plan_code="free")
        set_trial_entitlements(
            db_session,
            org_id="org-1",
            plan_code="pro",
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        resolved = _resolve_from_db(db_session, "org-1")
        # Trial trumps plan
        assert resolved["pilot.autopilot_enabled"] is True

    def test_override_trumps_trial(self, db_session) -> None:
        _seed_subscription(db_session, org_id="org-1", plan_code="free")
        seed_plan_entitlements(db_session, org_id="org-1", plan_code="free")
        set_trial_entitlements(
            db_session,
            org_id="org-1",
            plan_code="pro",  # trial says autopilot=True
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        set_override_entitlement(
            db_session,
            org_id="org-1",
            key="pilot.autopilot_enabled",
            value=False,  # override says False
        )
        resolved = _resolve_from_db(db_session, "org-1")
        # Override is highest precedence
        assert resolved["pilot.autopilot_enabled"] is False

    def test_expired_trial_filtered(self, db_session) -> None:
        _seed_subscription(db_session, org_id="org-1", plan_code="free")
        seed_plan_entitlements(db_session, org_id="org-1", plan_code="free")
        # Manually insert an expired trial row (set_trial_entitlements
        # rejects past dates, so we go direct to ORM).
        db_session.add(
            Entitlement(
                org_id="org-1",
                key="pilot.autopilot_enabled",
                value_json="true",
                source="trial",
                expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            )
        )
        db_session.commit()
        resolved = _resolve_from_db(db_session, "org-1")
        # Expired trial should be ignored, plan value wins
        assert resolved["pilot.autopilot_enabled"] is False

    def test_tenant_isolation(self, db_session) -> None:
        _seed_subscription(db_session, org_id="org-A", plan_code="pro")
        _seed_subscription(db_session, org_id="org-B", plan_code="free")
        resolved_a = _resolve_from_db(db_session, "org-A")
        resolved_b = _resolve_from_db(db_session, "org-B")
        assert resolved_a["pilot.autopilot_enabled"] is True
        assert resolved_b["pilot.autopilot_enabled"] is False

    def test_unknown_plan_code_falls_back_to_free(self, db_session) -> None:
        sub = _seed_subscription(db_session, org_id="org-1", plan_code="free")
        # Corrupt the plan_code to simulate schema drift
        sub.plan_code = "bogus_plan"
        db_session.add(sub)
        db_session.commit()
        resolved = _resolve_from_db(db_session, "org-1")
        assert resolved == PLAN_ENTITLEMENTS["free"]

    def test_source_rank_constants(self) -> None:
        # Source rank ordering is part of the contract — guard against
        # accidental reordering in a future refactor.
        assert _SOURCE_RANK["override"] > _SOURCE_RANK["trial"]
        assert _SOURCE_RANK["trial"] > _SOURCE_RANK["plan"]


# ── resolve_all / has / get ─────────────────────────────────────────────────


class TestResolveAll:
    def test_returns_dict(self, db_session) -> None:
        _seed_subscription(db_session, org_id="org-1", plan_code="pro")
        resolved = resolve_all(db_session, "org-1")
        assert isinstance(resolved, dict)
        assert resolved == PLAN_ENTITLEMENTS["pro"]

    def test_empty_org_id_returns_free(self, db_session) -> None:
        resolved = resolve_all(db_session, "")
        assert resolved == PLAN_ENTITLEMENTS["free"]

    def test_non_string_org_id_returns_free(self, db_session) -> None:
        resolved = resolve_all(db_session, None)  # type: ignore[arg-type]
        assert resolved == PLAN_ENTITLEMENTS["free"]

    def test_cache_is_warm_on_second_call(self, db_session) -> None:
        _seed_subscription(db_session, org_id="org-1", plan_code="pro")
        first = resolve_all(db_session, "org-1")
        # Mutate the DB; cache should still serve the original
        seed_plan_entitlements(db_session, org_id="org-1", plan_code="free")
        # The seed_plan write invalidates the cache, so this call
        # WILL see the new free-tier values. Without invalidation it
        # would have served stale pro values.
        second = resolve_all(db_session, "org-1")
        assert first["pilot.autopilot_enabled"] is True
        assert second["pilot.autopilot_enabled"] is False


class TestHasGet:
    def test_has_bool_true(self, db_session) -> None:
        _seed_subscription(db_session, org_id="org-1", plan_code="pro")
        assert has(db_session, "org-1", "pilot.autopilot_enabled") is True

    def test_has_bool_false(self, db_session) -> None:
        _seed_subscription(db_session, org_id="org-1", plan_code="free")
        assert has(db_session, "org-1", "pilot.autopilot_enabled") is False

    def test_has_int_quota(self, db_session) -> None:
        _seed_subscription(db_session, org_id="org-1", plan_code="pro")
        # pro.replay.monthly_runs = 100
        assert has(db_session, "org-1", "replay.monthly_runs") is True

    def test_has_zero_quota_is_false(self, db_session) -> None:
        _seed_subscription(db_session, org_id="org-1", plan_code="free")
        # free.replay.monthly_runs = 0
        assert has(db_session, "org-1", "replay.monthly_runs") is False

    def test_has_unknown_key_is_false(self, db_session) -> None:
        _seed_subscription(db_session, org_id="org-1", plan_code="enterprise")
        assert has(db_session, "org-1", "totally.fake.key") is False

    def test_get_returns_raw_value(self, db_session) -> None:
        _seed_subscription(db_session, org_id="org-1", plan_code="pro")
        assert get(db_session, "org-1", "replay.monthly_runs") == 100

    def test_get_default_for_missing_key(self, db_session) -> None:
        _seed_subscription(db_session, org_id="org-1", plan_code="free")
        assert get(db_session, "org-1", "x.not.a.key", default="fallback") == "fallback"

    def test_get_enum_value(self, db_session) -> None:
        _seed_subscription(db_session, org_id="org-1", plan_code="plus")
        assert get(db_session, "org-1", "digest.audience") == "executive"


# ── plan_code resolution ────────────────────────────────────────────────────


class TestGetPlanCode:
    def test_returns_subscription_plan(self, db_session) -> None:
        _seed_subscription(db_session, org_id="org-1", plan_code="pro")
        assert get_plan_code(db_session, "org-1") == "pro"

    def test_returns_free_when_no_subscription(self, db_session) -> None:
        assert get_plan_code(db_session, "org-unknown") == "free"

    def test_returns_free_when_plan_code_empty(self, db_session) -> None:
        sub = _seed_subscription(db_session, org_id="org-1", plan_code="pro")
        sub.plan_code = ""
        db_session.add(sub)
        db_session.commit()
        assert get_plan_code(db_session, "org-1") == "free"


# ── invalidation ────────────────────────────────────────────────────────────


class TestInvalidate:
    def test_invalidate_drops_cache(self, db_session) -> None:
        _seed_subscription(db_session, org_id="org-1", plan_code="pro")
        # Prime the cache
        resolve_all(db_session, "org-1")
        # Mutate DB without going through the write API (no auto-invalidation)
        sub = db_session.query(Subscription).filter_by(org_id="org-1").one()
        sub.plan_code = "free"
        db_session.add(sub)
        db_session.commit()
        # Cache still has pro
        assert (
            resolve_all(db_session, "org-1")["pilot.autopilot_enabled"] is True
        )
        invalidate("org-1")
        # Now resolves to free
        assert (
            resolve_all(db_session, "org-1")["pilot.autopilot_enabled"] is False
        )

    def test_invalidate_empty_org_id_noop(self, db_session) -> None:
        # Should not raise.
        invalidate("")
        invalidate(None)  # type: ignore[arg-type]

    def test_invalidate_all_clears_memory(self, db_session) -> None:
        _seed_subscription(db_session, org_id="org-1", plan_code="pro")
        _seed_subscription(db_session, org_id="org-2", plan_code="free")
        resolve_all(db_session, "org-1")
        resolve_all(db_session, "org-2")
        invalidate_all()
        # Next call hits DB; correctness unchanged but cache was wiped.
        assert resolve_all(db_session, "org-1") == PLAN_ENTITLEMENTS["pro"]


# ── write-side hooks (Module 5 + invalidate) ────────────────────────────────


class TestCacheInvalidationOnWrites:
    """Verify the entitlements.py write paths drop the resolver cache."""

    def test_seed_plan_invalidates(self, db_session) -> None:
        _seed_subscription(db_session, org_id="org-1", plan_code="free")
        # Prime cache with free
        assert (
            resolve_all(db_session, "org-1")["pilot.autopilot_enabled"] is False
        )
        # Seed pro plan rows — the write hook should invalidate
        seed_plan_entitlements(db_session, org_id="org-1", plan_code="pro")
        assert (
            resolve_all(db_session, "org-1")["pilot.autopilot_enabled"] is True
        )

    def test_set_trial_invalidates(self, db_session) -> None:
        _seed_subscription(db_session, org_id="org-1", plan_code="free")
        seed_plan_entitlements(db_session, org_id="org-1", plan_code="free")
        # Prime
        assert (
            resolve_all(db_session, "org-1")["pilot.autopilot_enabled"] is False
        )
        # Trial should be visible immediately, not after the 60s TTL
        set_trial_entitlements(
            db_session,
            org_id="org-1",
            plan_code="pro",
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        assert (
            resolve_all(db_session, "org-1")["pilot.autopilot_enabled"] is True
        )

    def test_set_override_invalidates(self, db_session) -> None:
        _seed_subscription(db_session, org_id="org-1", plan_code="pro")
        seed_plan_entitlements(db_session, org_id="org-1", plan_code="pro")
        # Prime
        assert (
            resolve_all(db_session, "org-1")["pilot.autopilot_enabled"] is True
        )
        # Override flips it off; should be visible immediately
        set_override_entitlement(
            db_session,
            org_id="org-1",
            key="pilot.autopilot_enabled",
            value=False,
        )
        assert (
            resolve_all(db_session, "org-1")["pilot.autopilot_enabled"] is False
        )
