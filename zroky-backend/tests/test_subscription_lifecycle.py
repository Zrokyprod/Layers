"""Tests for Module 12 — subscription lifecycle automation (plan §11.4).

Coverage:
  - services.subscription_lifecycle
      * sweep_expired_trials
          - happy path → state transitions to (free, active)
          - eligibility filter: stripe_sub_id IS NULL (paid trials skipped)
          - eligibility filter: trial_end in future (skipped)
          - audit row written with before/after snapshots
          - sla_tier preserved across auto-downgrade
          - trial expiry sweep does NOT clear stripe_sub_id
            (that's past-due-only; here it's already NULL)
          - idempotent — second run finds no eligible rows
      * sweep_expired_past_due_grace
          - happy path → state transitions to (free, active),
            stripe_sub_id cleared
          - eligibility: current_period_end < now - grace_days
          - eligibility: rows still inside grace are skipped
          - grace_days kwarg honored
          - sla_tier preserved
  - worker.tasks.expire_* wrappers
      * BILLING_LIFECYCLE_SWEEP_ENABLED=false short-circuits
  - routes/billing.py
      * /v1/billing/me surfaces sla_tier
      * legacy_router is structurally separate from router
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import (
    AuditLogAdmin,
    Entitlement,
    Subscription,
)
from app.services.entitlements import (
    seed_plan_entitlements,
    set_trial_entitlements,
)
from app.services.subscription_lifecycle import (
    SweepResult,
    TransitionRecord,
    sweep_expired_past_due_grace,
    sweep_expired_trials,
)


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def db_session(tmp_path: Path):
    """Per-test SQLite session bound to a fresh schema."""
    db_path = tmp_path / "test_lifecycle.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _make_subscription(
    db,
    *,
    org_id: str,
    plan_code: str = "pro",
    status: str = "trialing",
    trial_end: datetime | None = None,
    current_period_end: datetime | None = None,
    stripe_sub_id: str | None = None,
    stripe_customer_id: str | None = None,
    sla_tier: str = "none",
) -> Subscription:
    """Build + commit a Subscription row with sensible test defaults.

    Also seeds plan entitlements + (if trialing) a trial overlay so the
    tests exercise the cache-invalidation path.
    """
    row = Subscription(
        id=str(uuid4()),
        org_id=org_id,
        plan_code=plan_code,
        status=status,
        seats=1,
        stripe_sub_id=stripe_sub_id,
        stripe_customer_id=stripe_customer_id,
        trial_end=trial_end,
        current_period_end=current_period_end,
        sla_tier=sla_tier,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    # Seed entitlements as the real ingestion paths would.
    seed_plan_entitlements(db, org_id=org_id, plan_code=plan_code, commit=True)
    if status == "trialing" and trial_end is not None:
        set_trial_entitlements(
            db, org_id=org_id, plan_code=plan_code, expires_at=trial_end,
        )
    return row


def _count_audit(db, *, org_id: str, action: str) -> int:
    rows = db.execute(
        select(AuditLogAdmin).where(
            AuditLogAdmin.target_type == "subscription",
            AuditLogAdmin.action == action,
        )
    ).scalars().all()
    # Filter by target_id → the subscription belonging to org_id.
    sub_id = db.execute(
        select(Subscription.id).where(Subscription.org_id == org_id)
    ).scalar_one()
    return sum(1 for r in rows if r.target_id == sub_id)


# ── trial expiry ────────────────────────────────────────────────────────────


class TestSweepExpiredTrials:
    def test_happy_path_downgrades_expired_no_card_trial(
        self, db_session
    ) -> None:
        now = datetime.now(timezone.utc)
        sub = _make_subscription(
            db_session,
            org_id="org-trial-expired",
            plan_code="pro",
            status="trialing",
            trial_end=now - timedelta(hours=1),  # expired 1h ago
            stripe_sub_id=None,  # no-card trial
        )

        result = sweep_expired_trials(db_session)

        assert result.examined == 1
        assert result.transitioned == 1
        assert result.failed == 0
        assert len(result.transitions) == 1

        transition = result.transitions[0]
        assert transition.subscription_id == sub.id
        assert transition.org_id == "org-trial-expired"
        assert transition.reason == "trial_expired"
        assert transition.before["plan_code"] == "pro"
        assert transition.before["status"] == "trialing"
        assert transition.after["plan_code"] == "free"
        assert transition.after["status"] == "active"
        assert transition.after["trial_end"] is None

        db_session.refresh(sub)
        assert sub.plan_code == "free"
        assert sub.status == "active"
        assert sub.trial_end is None

    def test_skips_paid_trial_with_stripe_sub_id(self, db_session) -> None:
        """Customers with a Stripe subscription must be left to the
        webhook (`customer.subscription.updated`) — sweeping them would
        race the event AND `_is_stale_event` would block legitimate
        post-trial upgrades."""
        now = datetime.now(timezone.utc)
        _make_subscription(
            db_session,
            org_id="org-paid-trial",
            plan_code="pro",
            status="trialing",
            trial_end=now - timedelta(hours=1),
            stripe_sub_id="sub_paid_xyz",  # has Stripe sub
        )

        result = sweep_expired_trials(db_session)

        assert result.examined == 0
        assert result.transitioned == 0

    def test_skips_future_trial_end(self, db_session) -> None:
        now = datetime.now(timezone.utc)
        _make_subscription(
            db_session,
            org_id="org-future-trial",
            plan_code="pro",
            status="trialing",
            trial_end=now + timedelta(days=5),
        )

        result = sweep_expired_trials(db_session)

        assert result.examined == 0

    def test_skips_active_subscription(self, db_session) -> None:
        """Status='active' is excluded by the eligibility filter even
        if trial_end happens to be set + in the past (legacy data)."""
        now = datetime.now(timezone.utc)
        _make_subscription(
            db_session,
            org_id="org-already-active",
            plan_code="pro",
            status="active",
            trial_end=now - timedelta(days=10),
        )

        result = sweep_expired_trials(db_session)

        assert result.examined == 0

    def test_audit_row_written(self, db_session) -> None:
        now = datetime.now(timezone.utc)
        _make_subscription(
            db_session,
            org_id="org-audit",
            plan_code="pro",
            status="trialing",
            trial_end=now - timedelta(minutes=5),
        )

        sweep_expired_trials(db_session)

        count = _count_audit(
            db_session,
            org_id="org-audit",
            action="subscription.auto_downgrade_trial",
        )
        assert count == 1

        # Spot-check the audit payload structure.
        row = db_session.execute(
            select(AuditLogAdmin).where(
                AuditLogAdmin.action == "subscription.auto_downgrade_trial",
            )
        ).scalar_one()
        assert row.actor_role == "system"
        assert row.actor_user_id is None
        assert row.target_type == "subscription"

        before = json.loads(row.before_json)
        after = json.loads(row.after_json)
        assert before["plan_code"] == "pro"
        assert before["status"] == "trialing"
        assert after["plan_code"] == "free"
        assert after["status"] == "active"

    def test_idempotent(self, db_session) -> None:
        """Second run finds no eligible rows — first run already
        transitioned the subscription out of `trialing`."""
        now = datetime.now(timezone.utc)
        _make_subscription(
            db_session,
            org_id="org-idempotent",
            plan_code="pro",
            status="trialing",
            trial_end=now - timedelta(hours=2),
        )

        first = sweep_expired_trials(db_session)
        second = sweep_expired_trials(db_session)

        assert first.transitioned == 1
        assert second.examined == 0
        assert second.transitioned == 0

    def test_sla_tier_preserved(self, db_session) -> None:
        """Per locked decision: sla_tier survives auto-downgrade so
        refund-eligibility audits remain reconstructable."""
        now = datetime.now(timezone.utc)
        sub = _make_subscription(
            db_session,
            org_id="org-sla",
            plan_code="pro",
            status="trialing",
            trial_end=now - timedelta(hours=1),
            sla_tier="team",
        )

        sweep_expired_trials(db_session)

        db_session.refresh(sub)
        assert sub.sla_tier == "team"

    def test_entitlements_reseeded_to_free(self, db_session) -> None:
        now = datetime.now(timezone.utc)
        _make_subscription(
            db_session,
            org_id="org-entitlements",
            plan_code="pro",
            status="trialing",
            trial_end=now - timedelta(hours=1),
        )

        sweep_expired_trials(db_session)

        plan_rows = db_session.execute(
            select(Entitlement).where(
                Entitlement.org_id == "org-entitlements",
                Entitlement.source == "plan",
            )
        ).scalars().all()
        # Every plan row should now reflect the free template.
        keys = {r.key: r.value_json for r in plan_rows}
        # Free has pilot.autopilot_enabled=false.
        assert json.loads(keys["pilot.autopilot_enabled"]) is False

        # Trial overlay should be cleared.
        trial_rows = db_session.execute(
            select(Entitlement).where(
                Entitlement.org_id == "org-entitlements",
                Entitlement.source == "trial",
            )
        ).scalars().all()
        assert len(trial_rows) == 0

    def test_explicit_clock_injection(self, db_session) -> None:
        now = datetime.now(timezone.utc)
        # Trial appears expired at `frozen` but not at `now`.
        frozen = now + timedelta(days=2)
        _make_subscription(
            db_session,
            org_id="org-clock",
            plan_code="pro",
            status="trialing",
            trial_end=now + timedelta(days=1),
        )

        # Default clock: not yet expired
        assert sweep_expired_trials(db_session).examined == 0
        # Injected clock: should pick it up
        assert sweep_expired_trials(db_session, now=frozen).transitioned == 1

    def test_limit_zero_rejected(self, db_session) -> None:
        with pytest.raises(ValueError, match="limit"):
            sweep_expired_trials(db_session, limit=0)


# ── past-due grace expiry ───────────────────────────────────────────────────


class TestSweepExpiredPastDueGrace:
    def test_happy_path_hard_downgrades(self, db_session) -> None:
        now = datetime.now(timezone.utc)
        sub = _make_subscription(
            db_session,
            org_id="org-past-due",
            plan_code="pro",
            status="past_due",
            current_period_end=now - timedelta(days=10),  # 10d > 7d grace
            stripe_sub_id="sub_paid_old",
            stripe_customer_id="cus_keep",
        )

        result = sweep_expired_past_due_grace(db_session)

        assert result.transitioned == 1
        db_session.refresh(sub)
        assert sub.plan_code == "free"
        assert sub.status == "active"
        # stripe_sub_id MUST be cleared so a delayed invoice.paid for
        # the old subscription cannot resurrect the customer.
        assert sub.stripe_sub_id is None
        # stripe_customer_id retained for support / future re-checkout.
        assert sub.stripe_customer_id == "cus_keep"

    def test_skips_within_grace(self, db_session) -> None:
        now = datetime.now(timezone.utc)
        _make_subscription(
            db_session,
            org_id="org-in-grace",
            plan_code="pro",
            status="past_due",
            current_period_end=now - timedelta(days=3),  # well within 7d
            stripe_sub_id="sub_in_grace",
        )

        result = sweep_expired_past_due_grace(db_session)
        assert result.examined == 0

    def test_grace_days_kwarg(self, db_session) -> None:
        now = datetime.now(timezone.utc)
        _make_subscription(
            db_session,
            org_id="org-custom-grace",
            plan_code="pro",
            status="past_due",
            current_period_end=now - timedelta(days=5),
            stripe_sub_id="sub_custom",
        )

        # Default 7d → still in grace
        assert sweep_expired_past_due_grace(db_session).examined == 0
        # 3d grace → eligible
        assert sweep_expired_past_due_grace(
            db_session, grace_days=3
        ).transitioned == 1

    def test_grace_days_zero_means_immediate(self, db_session) -> None:
        """grace_days=0 should hard-downgrade the moment
        current_period_end is in the past."""
        now = datetime.now(timezone.utc)
        _make_subscription(
            db_session,
            org_id="org-zero-grace",
            plan_code="pro",
            status="past_due",
            current_period_end=now - timedelta(seconds=1),
            stripe_sub_id="sub_zero",
        )

        result = sweep_expired_past_due_grace(db_session, grace_days=0)
        assert result.transitioned == 1

    def test_skips_active_subscription(self, db_session) -> None:
        now = datetime.now(timezone.utc)
        _make_subscription(
            db_session,
            org_id="org-still-active",
            plan_code="pro",
            status="active",
            current_period_end=now - timedelta(days=30),
            stripe_sub_id="sub_active_old_period",
        )

        result = sweep_expired_past_due_grace(db_session)
        assert result.examined == 0

    def test_skips_null_period_end(self, db_session) -> None:
        """Rows without current_period_end (rare incomplete signups)
        cannot have a deterministic grace window."""
        _make_subscription(
            db_session,
            org_id="org-no-period",
            plan_code="pro",
            status="past_due",
            current_period_end=None,
            stripe_sub_id="sub_no_period",
        )

        result = sweep_expired_past_due_grace(db_session)
        assert result.examined == 0

    def test_audit_row(self, db_session) -> None:
        now = datetime.now(timezone.utc)
        _make_subscription(
            db_session,
            org_id="org-audit-pd",
            plan_code="pro",
            status="past_due",
            current_period_end=now - timedelta(days=14),
            stripe_sub_id="sub_audit",
        )

        sweep_expired_past_due_grace(db_session)

        count = _count_audit(
            db_session,
            org_id="org-audit-pd",
            action="subscription.auto_downgrade_past_due",
        )
        assert count == 1

    def test_sla_tier_preserved(self, db_session) -> None:
        now = datetime.now(timezone.utc)
        sub = _make_subscription(
            db_session,
            org_id="org-sla-pd",
            plan_code="plus",
            status="past_due",
            current_period_end=now - timedelta(days=10),
            stripe_sub_id="sub_sla",
            sla_tier="enterprise",
        )

        sweep_expired_past_due_grace(db_session)

        db_session.refresh(sub)
        assert sub.sla_tier == "enterprise"

    def test_negative_grace_rejected(self, db_session) -> None:
        with pytest.raises(ValueError, match="grace_days"):
            sweep_expired_past_due_grace(db_session, grace_days=-1)


# ── kill-switch on the Celery wrappers ─────────────────────────────────────


class TestKillSwitch:
    def test_expire_trials_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.worker.tasks import expire_trials

        monkeypatch.setenv("BILLING_LIFECYCLE_SWEEP_ENABLED", "false")
        get_settings.cache_clear()
        try:
            result = expire_trials.run()  # type: ignore[attr-defined]
            assert result["skipped"] is True
            assert "BILLING_LIFECYCLE_SWEEP_ENABLED" in result["reason"]
        finally:
            get_settings.cache_clear()

    def test_expire_past_due_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.worker.tasks import expire_past_due_grace

        monkeypatch.setenv("BILLING_LIFECYCLE_SWEEP_ENABLED", "false")
        get_settings.cache_clear()
        try:
            result = expire_past_due_grace.run()  # type: ignore[attr-defined]
            assert result["skipped"] is True
        finally:
            get_settings.cache_clear()


# ── route surface (sla_tier in /me + router separation) ─────────────────────


class TestRouterSeparation:
    """Structural assertions so accidental re-merging of legacy paths
    into `router` is caught at test time."""

    def test_v113_paths_in_main_router_only(self) -> None:
        from app.api.routes.billing import legacy_router, router

        main_paths = {r.path for r in router.routes}
        legacy_paths = {r.path for r in legacy_router.routes}

        # §11.3 paths live exclusively on `router`.
        for path in (
            "/v1/billing/checkout",
            "/v1/billing/portal",
            "/v1/billing/webhook",
            "/v1/billing/me",
        ):
            assert path in main_paths, f"missing §11.3 path: {path}"
            assert path not in legacy_paths

    def test_legacy_paths_in_legacy_router_only(self) -> None:
        from app.api.routes.billing import legacy_router, router

        main_paths = {r.path for r in router.routes}
        legacy_paths = {r.path for r in legacy_router.routes}

        for path in (
            "/v1/billing/plans",
            "/v1/billing/subscription",
            "/v1/billing/usage",
        ):
            assert path in legacy_paths, f"legacy path missing: {path}"
            assert path not in main_paths


class TestBillingMeSlaTier:
    def test_sla_tier_in_response_model(self) -> None:
        from app.api.routes.billing import BillingMeResponse

        # The model accepts the field; default is 'none'.
        instance = BillingMeResponse(
            org_id="x", plan_code="free", status="active", seats=1,
        )
        assert instance.sla_tier == "none"

        # Custom value passes through.
        instance = BillingMeResponse(
            org_id="x", plan_code="plus", status="active", seats=10,
            sla_tier="team",
        )
        assert instance.sla_tier == "team"
