"""Tests for Module 5 — Stripe-aligned billing surface.

Coverage:
  - services.billing_plans   — vocab, validators, price-id resolver
  - services.entitlements    — seed/clear/upsert primitives
  - services.stripe_gateway  — webhook signature verify (HMAC), stub
                               gateway behaviour
  - services.stripe_sync     — dispatch_event idempotency + per-event
                               handlers (checkout, sub.updated,
                               sub.deleted, invoice.paid,
                               invoice.payment_failed, unknown)
  - routes/billing.py        — POST /checkout, /portal, /webhook;
                               GET /me; 422 / 404 / 502 / 503 mapping
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api.dependencies.tenant import (
    TenantContext,
    require_tenant_context,
)
from app.core.config import get_settings
from app.db.base import Base
from app.db.models import (
    Entitlement,
    StripeEvent,
    Subscription,
)
from app.db.session import get_db_session, get_db_session_read
from app.main import app
from app.services.billing_plans import (
    DEFAULT_PLAN_CODE,
    InvalidPlanCodeError,
    PLAN_ENTITLEMENTS,
    PlanNotSelfServeError,
    StripePriceNotConfiguredError,
    VALID_PLAN_CODES,
    assert_self_serve_plan,
    get_plan_entitlements,
    normalize_plan_code,
    parse_price_map,
    resolve_stripe_price_id,
)
from app.services.entitlements import (
    clear_plan_entitlements,
    clear_trial_entitlements,
    list_entitlements,
    parse_entitlement_value,
    seed_plan_entitlements,
    set_override_entitlement,
    set_trial_entitlements,
    upsert_entitlement,
)
from app.services.stripe_gateway import (
    LiveStripeGateway,
    StubStripeGateway,
    WebhookSignatureError,
    get_stripe_gateway,
    sign_webhook_payload,
    verify_webhook_signature,
)
from app.services.stripe_sync import (
    HANDLED_EVENT_TYPES,
    EventDispatchResult,
    dispatch_event,
)


_TEST_WEBHOOK_SECRET = "whsec_test_module_5"
_TEST_STRIPE_KEY = "sk_test_module_5"


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _billing_settings(monkeypatch: pytest.MonkeyPatch):
    """Default billing config for tests: enabled, with stub gateway, with
    a complete price map for the three self-serve plans."""
    monkeypatch.setenv("BILLING_ENABLED", "true")
    monkeypatch.setenv("STRIPE_API_KEY", "")  # empty → stub gateway
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", _TEST_WEBHOOK_SECRET)
    monkeypatch.setenv(
        "STRIPE_PRICE_IDS_JSON",
        json.dumps(
            {
                "pro": "price_pro_test",
                "plus": "price_plus_test",
            }
        ),
    )
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "test_billing_svc.db"
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


@pytest.fixture()
def client(tmp_path: Path):
    """Test client with admin tenant context auto-granted.

    We override `require_tenant_context` so tests don't need a JWT —
    the route's `require_tenant_role('admin')` resolves through this
    override and returns the test tenant_id.
    """
    db_path = tmp_path / "test_billing_route.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    # Default tenant id for tests; individual tests can mutate `_tenant`
    state = {"tenant_id": "org-alpha", "role": "admin"}

    def override_tenant():
        return TenantContext(
            tenant_id=state["tenant_id"],
            role=state["role"],
            subject="user-test",
        )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_db_session_read] = override_db
    app.dependency_overrides[require_tenant_context] = override_tenant

    with TestClient(app) as test_client:
        test_client._session_factory = session_factory  # type: ignore[attr-defined]
        test_client._tenant_state = state  # type: ignore[attr-defined]
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _set_tenant(client: TestClient, *, tenant_id: str, role: str = "admin") -> None:
    client._tenant_state["tenant_id"] = tenant_id  # type: ignore[attr-defined]
    client._tenant_state["role"] = role  # type: ignore[attr-defined]


# ── billing_plans ────────────────────────────────────────────────────────────


class TestBillingPlans:
    def test_normalize_plan_code(self) -> None:
        assert normalize_plan_code("PRO") == "pro"
        assert normalize_plan_code("  Pro ") == "pro"

    def test_normalize_invalid(self) -> None:
        with pytest.raises(InvalidPlanCodeError):
            normalize_plan_code("ultra")
        with pytest.raises(InvalidPlanCodeError):
            normalize_plan_code(None)

    def test_assert_self_serve_rejects_free(self) -> None:
        with pytest.raises(PlanNotSelfServeError):
            assert_self_serve_plan("free")

    def test_assert_self_serve_rejects_enterprise(self) -> None:
        with pytest.raises(PlanNotSelfServeError):
            assert_self_serve_plan("enterprise")

    def test_assert_self_serve_accepts_paid_tiers(self) -> None:
        for code in ("pro", "plus"):
            assert assert_self_serve_plan(code) == code

    def test_resolve_price_id_happy(self) -> None:
        assert resolve_stripe_price_id("pro") == "price_pro_test"

    def test_resolve_price_id_missing_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("STRIPE_PRICE_IDS_JSON", "{}")
        get_settings.cache_clear()
        with pytest.raises(StripePriceNotConfiguredError):
            resolve_stripe_price_id("pro")

    def test_get_plan_entitlements_returns_copy(self) -> None:
        a = get_plan_entitlements("free")
        a["events.monthly_quota"] = 999
        b = get_plan_entitlements("free")
        assert b["events.monthly_quota"] == 50_000  # not mutated

    def test_all_plans_have_same_keys(self) -> None:
        ref = set(PLAN_ENTITLEMENTS["free"].keys())
        for plan in VALID_PLAN_CODES:
            assert set(PLAN_ENTITLEMENTS[plan].keys()) == ref

    def test_parse_price_map_garbage(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("STRIPE_PRICE_IDS_JSON", "{not-json")
        get_settings.cache_clear()
        assert parse_price_map() == {}

    def test_parse_price_map_non_object(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("STRIPE_PRICE_IDS_JSON", "[1,2,3]")
        get_settings.cache_clear()
        assert parse_price_map() == {}


# ── entitlements service ────────────────────────────────────────────────────


class TestEntitlementsService:
    def test_seed_plan(self, db_session) -> None:
        rows = seed_plan_entitlements(db_session, org_id="o1", plan_code="pro")
        assert len(rows) == len(PLAN_ENTITLEMENTS["pro"])
        for row in rows:
            assert row.source == "plan"
            assert row.org_id == "o1"

        # Idempotent re-seed of same plan replaces (still N rows)
        rows2 = seed_plan_entitlements(db_session, org_id="o1", plan_code="pro")
        all_plan = db_session.execute(
            select(Entitlement).where(
                Entitlement.org_id == "o1",
                Entitlement.source == "plan",
            )
        ).scalars().all()
        assert len(all_plan) == len(rows2)

    def test_seed_plan_replaces_old_plan_rows(self, db_session) -> None:
        seed_plan_entitlements(db_session, org_id="o1", plan_code="pro")
        seed_plan_entitlements(db_session, org_id="o1", plan_code="free")
        rows = list_entitlements(db_session, org_id="o1")
        plan_rows = [r for r in rows if r.source == "plan"]
        for row in plan_rows:
            if row.key == "pilot.autopilot_enabled":
                assert parse_entitlement_value(row.value_json) is False  # free

    def test_clear_plan(self, db_session) -> None:
        seed_plan_entitlements(db_session, org_id="o1", plan_code="pro")
        deleted = clear_plan_entitlements(db_session, org_id="o1")
        assert deleted == len(PLAN_ENTITLEMENTS["pro"])
        rows = list_entitlements(db_session, org_id="o1")
        assert all(r.source != "plan" for r in rows)

    def test_set_trial_overlay(self, db_session) -> None:
        expires = datetime.now(timezone.utc) + timedelta(days=14)
        rows = set_trial_entitlements(
            db_session, org_id="o1", plan_code="plus", expires_at=expires,
        )
        assert all(r.source == "trial" for r in rows)
        assert all(r.expires_at is not None for r in rows)

    def test_clear_trial(self, db_session) -> None:
        expires = datetime.now(timezone.utc) + timedelta(days=14)
        set_trial_entitlements(
            db_session, org_id="o1", plan_code="plus", expires_at=expires,
        )
        deleted = clear_trial_entitlements(db_session, org_id="o1")
        assert deleted == len(PLAN_ENTITLEMENTS["plus"])

    def test_override_upsert(self, db_session) -> None:
        row1 = set_override_entitlement(
            db_session, org_id="o1", key="pilot.autopilot_enabled", value=True,
        )
        assert parse_entitlement_value(row1.value_json) is True
        row2 = set_override_entitlement(
            db_session, org_id="o1", key="pilot.autopilot_enabled", value=False,
        )
        assert row1.id == row2.id  # same row, updated
        assert parse_entitlement_value(row2.value_json) is False

    def test_upsert_invalid_source(self, db_session) -> None:
        with pytest.raises(ValueError, match="source"):
            upsert_entitlement(
                db_session, org_id="o1", key="x", value=1, source="bogus",
            )

    def test_invalid_plan_in_seed(self, db_session) -> None:
        with pytest.raises(InvalidPlanCodeError):
            seed_plan_entitlements(db_session, org_id="o1", plan_code="bogus")

    def test_parse_value_robust(self) -> None:
        assert parse_entitlement_value(None) is None
        assert parse_entitlement_value("") is None
        assert parse_entitlement_value("not-json") is None
        assert parse_entitlement_value('"hello"') == "hello"
        assert parse_entitlement_value("42") == 42
        assert parse_entitlement_value("true") is True

    def test_per_source_independence(self, db_session) -> None:
        # Same (org, key) can have all three sources simultaneously.
        seed_plan_entitlements(db_session, org_id="o1", plan_code="free")
        set_override_entitlement(
            db_session, org_id="o1", key="pilot.autopilot_enabled", value=True,
        )
        set_trial_entitlements(
            db_session, org_id="o1", plan_code="pro",
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        rows = [
            r for r in list_entitlements(db_session, org_id="o1")
            if r.key == "pilot.autopilot_enabled"
        ]
        sources = sorted(r.source for r in rows)
        assert sources == ["override", "plan", "trial"]


# ── stripe_gateway: webhook signature ───────────────────────────────────────


class TestWebhookSignature:
    def test_round_trip(self) -> None:
        body = b'{"id":"evt_1","type":"invoice.paid"}'
        header = sign_webhook_payload(payload=body, secret=_TEST_WEBHOOK_SECRET)
        event = verify_webhook_signature(
            payload=body, header=header, secret=_TEST_WEBHOOK_SECRET,
        )
        assert event["id"] == "evt_1"

    def test_missing_header(self) -> None:
        with pytest.raises(WebhookSignatureError, match="missing"):
            verify_webhook_signature(
                payload=b"{}", header=None, secret=_TEST_WEBHOOK_SECRET,
            )

    def test_missing_secret(self) -> None:
        with pytest.raises(WebhookSignatureError):
            verify_webhook_signature(
                payload=b"{}", header="t=1,v1=abc", secret="",
            )

    def test_malformed_header(self) -> None:
        with pytest.raises(WebhookSignatureError, match="missing required"):
            verify_webhook_signature(
                payload=b"{}", header="just-some-string",
                secret=_TEST_WEBHOOK_SECRET,
            )

    def test_invalid_timestamp(self) -> None:
        with pytest.raises(WebhookSignatureError, match="integer"):
            verify_webhook_signature(
                payload=b"{}", header="t=abc,v1=abc",
                secret=_TEST_WEBHOOK_SECRET,
            )

    def test_replay_outside_tolerance(self) -> None:
        body = b'{"id":"evt_old"}'
        ts = int(time.time()) - 600  # 10 min old
        header = sign_webhook_payload(
            payload=body, secret=_TEST_WEBHOOK_SECRET, timestamp=ts,
        )
        with pytest.raises(WebhookSignatureError, match="tolerance"):
            verify_webhook_signature(
                payload=body, header=header,
                secret=_TEST_WEBHOOK_SECRET, tolerance=300,
            )

    def test_tampered_body_rejected(self) -> None:
        body = b'{"id":"evt_x"}'
        header = sign_webhook_payload(payload=body, secret=_TEST_WEBHOOK_SECRET)
        with pytest.raises(WebhookSignatureError, match="HMAC"):
            verify_webhook_signature(
                payload=b'{"id":"tampered"}',
                header=header, secret=_TEST_WEBHOOK_SECRET,
            )

    def test_wrong_secret(self) -> None:
        body = b'{"id":"evt_y"}'
        header = sign_webhook_payload(payload=body, secret=_TEST_WEBHOOK_SECRET)
        with pytest.raises(WebhookSignatureError, match="HMAC"):
            verify_webhook_signature(
                payload=body, header=header, secret="whsec_other",
            )

    def test_payload_must_be_object(self) -> None:
        body = b"[1,2,3]"
        header = sign_webhook_payload(payload=body, secret=_TEST_WEBHOOK_SECRET)
        with pytest.raises(WebhookSignatureError, match="object"):
            verify_webhook_signature(
                payload=body, header=header, secret=_TEST_WEBHOOK_SECRET,
            )

    def test_non_utf8_payload(self) -> None:
        body = b"\xff\xfe\xfd"
        header = sign_webhook_payload(payload=body, secret=_TEST_WEBHOOK_SECRET)
        with pytest.raises(WebhookSignatureError):
            verify_webhook_signature(
                payload=body, header=header, secret=_TEST_WEBHOOK_SECRET,
            )


# ── stripe_gateway: stub + factory ──────────────────────────────────────────


class TestStripeGatewayFactory:
    def test_stub_when_billing_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BILLING_ENABLED", "false")
        get_settings.cache_clear()
        gw = get_stripe_gateway()
        assert isinstance(gw, StubStripeGateway)
        assert gw.is_live is False

    def test_stub_when_api_key_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BILLING_ENABLED", "true")
        monkeypatch.setenv("STRIPE_API_KEY", "")
        get_settings.cache_clear()
        gw = get_stripe_gateway()
        assert isinstance(gw, StubStripeGateway)

    def test_live_when_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BILLING_ENABLED", "true")
        monkeypatch.setenv("STRIPE_API_KEY", _TEST_STRIPE_KEY)
        get_settings.cache_clear()
        gw = get_stripe_gateway()
        assert isinstance(gw, LiveStripeGateway)
        assert gw.is_live is True

    def test_stub_checkout_records_call(self) -> None:
        gw = StubStripeGateway()
        result = gw.create_checkout_session(
            org_id="o1", plan_code="pro", price_id="price_pro_test",
            success_url="https://x/s", cancel_url="https://x/c",
            customer_email="a@b.com",
        )
        assert result.id.startswith("cs_stub_")
        assert "stub.stripe.local" in result.url
        assert gw.last_checkout is not None
        assert gw.last_checkout["org_id"] == "o1"
        assert gw.last_checkout["plan_code"] == "pro"

    def test_stub_portal_records_call(self) -> None:
        gw = StubStripeGateway()
        result = gw.create_portal_session(
            customer_id="cus_xyz", return_url="https://x/return",
        )
        assert result.id.startswith("bps_stub_")
        assert "return_to=https://x/return" in result.url


# ── stripe_sync: dispatch_event ─────────────────────────────────────────────


def _make_event(
    *,
    event_id: str,
    event_type: str,
    obj: dict | None = None,
    created: int | None = None,
) -> dict:
    return {
        "id": event_id,
        "type": event_type,
        "created": created if created is not None else int(time.time()),
        "data": {"object": obj or {}},
    }


class TestStripeSyncDispatch:
    def test_handled_vocab(self) -> None:
        assert "checkout.session.completed" in HANDLED_EVENT_TYPES
        assert "invoice.paid" in HANDLED_EVENT_TYPES
        assert "customer.subscription.deleted" in HANDLED_EVENT_TYPES

    def test_idempotent_duplicate(self, db_session) -> None:
        event = _make_event(
            event_id="evt_dup_1",
            event_type="checkout.session.completed",
            obj={
                "metadata": {"org_id": "o1", "plan_code": "pro"},
                "customer": "cus_1", "subscription": "sub_1",
            },
        )
        first = dispatch_event(db_session, event)
        assert first.duplicate is False
        assert first.result == "applied"
        # Second dispatch of same event_id short-circuits as duplicate
        second = dispatch_event(db_session, event)
        assert second.duplicate is True
        # Still only one stripe_events row
        rows = db_session.execute(select(StripeEvent)).scalars().all()
        assert len(rows) == 1

    def test_checkout_seeds_subscription_and_entitlements(
        self, db_session
    ) -> None:
        event = _make_event(
            event_id="evt_chk_1",
            event_type="checkout.session.completed",
            obj={
                "metadata": {"org_id": "o-alpha", "plan_code": "pro"},
                "customer": "cus_alpha",
                "subscription": "sub_alpha",
            },
        )
        result = dispatch_event(db_session, event)
        assert result.result == "applied"
        assert result.affected_org_id == "o-alpha"

        sub = db_session.execute(
            select(Subscription).where(Subscription.org_id == "o-alpha")
        ).scalar_one()
        assert sub.plan_code == "pro"
        assert sub.status == "active"
        assert sub.stripe_customer_id == "cus_alpha"
        assert sub.stripe_sub_id == "sub_alpha"

        ent_rows = db_session.execute(
            select(Entitlement).where(
                Entitlement.org_id == "o-alpha", Entitlement.source == "plan",
            )
        ).scalars().all()
        assert len(ent_rows) == len(PLAN_ENTITLEMENTS["pro"])

    def test_subscription_updated_changes_status(self, db_session) -> None:
        # First seed via checkout
        dispatch_event(db_session, _make_event(
            event_id="evt_pre",
            event_type="checkout.session.completed",
            obj={
                "metadata": {"org_id": "o-beta", "plan_code": "pro"},
                "customer": "cus_beta", "subscription": "sub_beta",
            },
        ))

        # Then sub.updated bumps to active+plus
        dispatch_event(db_session, _make_event(
            event_id="evt_upd_1",
            event_type="customer.subscription.updated",
            obj={
                "id": "sub_beta",
                "customer": "cus_beta",
                "status": "active",
                "metadata": {"org_id": "o-beta", "plan_code": "plus"},
                "current_period_end": int(time.time()) + 30 * 86400,
            },
            created=int(time.time()) + 100,
        ))

        sub = db_session.execute(
            select(Subscription).where(Subscription.org_id == "o-beta")
        ).scalar_one()
        assert sub.plan_code == "plus"
        assert sub.status == "active"
        assert sub.current_period_end is not None

    def test_subscription_trialing_writes_trial_overlay(self, db_session) -> None:
        trial_end = int(time.time()) + 14 * 86400
        dispatch_event(db_session, _make_event(
            event_id="evt_trial_1",
            event_type="customer.subscription.created",
            obj={
                "id": "sub_trial",
                "customer": "cus_trial",
                "status": "trialing",
                "metadata": {"org_id": "o-trial", "plan_code": "plus"},
                "trial_end": trial_end,
                "current_period_end": trial_end,
            },
        ))
        trial_rows = db_session.execute(
            select(Entitlement).where(
                Entitlement.org_id == "o-trial",
                Entitlement.source == "trial",
            )
        ).scalars().all()
        assert len(trial_rows) == len(PLAN_ENTITLEMENTS["plus"])
        assert all(r.expires_at is not None for r in trial_rows)

    def test_subscription_deleted_clears_entitlements(self, db_session) -> None:
        # Seed
        dispatch_event(db_session, _make_event(
            event_id="evt_seed",
            event_type="checkout.session.completed",
            obj={
                "metadata": {"org_id": "o-del", "plan_code": "pro"},
                "customer": "cus_del", "subscription": "sub_del",
            },
        ))
        # Delete
        dispatch_event(db_session, _make_event(
            event_id="evt_del",
            event_type="customer.subscription.deleted",
            obj={
                "id": "sub_del",
                "customer": "cus_del",
                "status": "canceled",
                "metadata": {"org_id": "o-del", "plan_code": "pro"},
            },
            created=int(time.time()) + 1000,
        ))
        sub = db_session.execute(
            select(Subscription).where(Subscription.org_id == "o-del")
        ).scalar_one()
        assert sub.status == "canceled"
        plan_rows = db_session.execute(
            select(Entitlement).where(
                Entitlement.org_id == "o-del", Entitlement.source == "plan",
            )
        ).scalars().all()
        assert plan_rows == []

    def test_invoice_payment_failed_flips_past_due(self, db_session) -> None:
        dispatch_event(db_session, _make_event(
            event_id="evt_pf_seed",
            event_type="checkout.session.completed",
            obj={
                "metadata": {"org_id": "o-pf", "plan_code": "pro"},
                "customer": "cus_pf", "subscription": "sub_pf",
            },
        ))
        dispatch_event(db_session, _make_event(
            event_id="evt_pf_fail",
            event_type="invoice.payment_failed",
            obj={
                "subscription": "sub_pf",
                "metadata": {"org_id": "o-pf"},
            },
        ))
        sub = db_session.execute(
            select(Subscription).where(Subscription.org_id == "o-pf")
        ).scalar_one()
        assert sub.status == "past_due"

    def test_invoice_paid_recovers_from_past_due(self, db_session) -> None:
        dispatch_event(db_session, _make_event(
            event_id="evt_ip_seed",
            event_type="checkout.session.completed",
            obj={
                "metadata": {"org_id": "o-ip", "plan_code": "pro"},
                "customer": "cus_ip", "subscription": "sub_ip",
            },
        ))
        dispatch_event(db_session, _make_event(
            event_id="evt_ip_fail",
            event_type="invoice.payment_failed",
            obj={"subscription": "sub_ip"},
        ))
        dispatch_event(db_session, _make_event(
            event_id="evt_ip_paid",
            event_type="invoice.paid",
            obj={
                "subscription": "sub_ip",
                "period_end": int(time.time()) + 30 * 86400,
            },
        ))
        sub = db_session.execute(
            select(Subscription).where(Subscription.org_id == "o-ip")
        ).scalar_one()
        assert sub.status == "active"

    def test_unknown_event_type_skipped(self, db_session) -> None:
        result = dispatch_event(db_session, _make_event(
            event_id="evt_unknown",
            event_type="customer.created",
            obj={"id": "cus_xyz"},
        ))
        assert result.result == "skipped"
        log_row = db_session.execute(
            select(StripeEvent).where(
                StripeEvent.stripe_event_id == "evt_unknown"
            )
        ).scalar_one()
        assert log_row.result == "skipped"

    def test_missing_org_id_skipped(self, db_session) -> None:
        result = dispatch_event(db_session, _make_event(
            event_id="evt_no_org",
            event_type="checkout.session.completed",
            obj={"customer": "cus_anon"},  # no metadata.org_id
        ))
        assert result.result == "skipped"

    def test_malformed_event_raises(self, db_session) -> None:
        with pytest.raises(ValueError, match="id or type"):
            dispatch_event(db_session, {"data": {}})

    def test_stale_subscription_update_dropped(self, db_session) -> None:
        # Initial subscription created at a "later" timestamp
        future_ts = int(time.time()) + 1_000_000
        dispatch_event(db_session, _make_event(
            event_id="evt_stale_seed",
            event_type="customer.subscription.updated",
            obj={
                "id": "sub_stale",
                "customer": "cus_stale",
                "status": "active",
                "metadata": {"org_id": "o-stale", "plan_code": "pro"},
            },
            created=future_ts,
        ))
        # An OLDER event arrives — must be dropped
        old_ts = int(time.time()) - 1000
        result = dispatch_event(db_session, _make_event(
            event_id="evt_stale_old",
            event_type="customer.subscription.updated",
            obj={
                "id": "sub_stale",
                "customer": "cus_stale",
                "status": "canceled",
                "metadata": {"org_id": "o-stale", "plan_code": "free"},
            },
            created=old_ts,
        ))
        assert result.result == "skipped"
        sub = db_session.execute(
            select(Subscription).where(Subscription.org_id == "o-stale")
        ).scalar_one()
        # Status from the FIRST (newer) event still wins
        assert sub.status == "active"


# ── routes ──────────────────────────────────────────────────────────────────


class TestCheckoutRoute:
    def test_happy_path_uses_stub_gateway(self, client: TestClient) -> None:
        response = client.post(
            "/v1/billing/checkout",
            json={"plan_code": "pro"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["plan_code"] == "pro"
        assert body["org_id"] == "org-alpha"
        assert body["session_id"].startswith("cs_stub_")
        assert "stub.stripe.local" in body["checkout_url"]

    def test_plan_normalisation(self, client: TestClient) -> None:
        response = client.post(
            "/v1/billing/checkout", json={"plan_code": "  PRO "},
        )
        assert response.status_code == 200
        assert response.json()["plan_code"] == "pro"

    def test_422_invalid_plan(self, client: TestClient) -> None:
        response = client.post(
            "/v1/billing/checkout", json={"plan_code": "ultra"},
        )
        assert response.status_code == 422

    def test_422_free_plan(self, client: TestClient) -> None:
        response = client.post(
            "/v1/billing/checkout", json={"plan_code": "free"},
        )
        assert response.status_code == 422

    def test_422_enterprise_plan(self, client: TestClient) -> None:
        response = client.post(
            "/v1/billing/checkout", json={"plan_code": "enterprise"},
        )
        assert response.status_code == 422

    def test_503_billing_disabled(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BILLING_ENABLED", "false")
        get_settings.cache_clear()
        response = client.post(
            "/v1/billing/checkout", json={"plan_code": "pro"},
        )
        assert response.status_code == 503

    def test_503_missing_price_id(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("STRIPE_PRICE_IDS_JSON", "{}")
        get_settings.cache_clear()
        response = client.post(
            "/v1/billing/checkout", json={"plan_code": "pro"},
        )
        assert response.status_code == 503

    def test_403_when_role_below_admin(self, client: TestClient) -> None:
        _set_tenant(client, tenant_id="org-alpha", role="member")
        response = client.post(
            "/v1/billing/checkout", json={"plan_code": "pro"},
        )
        assert response.status_code == 403


class TestPortalRoute:
    def test_404_when_no_customer_yet(self, client: TestClient) -> None:
        response = client.post("/v1/billing/portal")
        assert response.status_code == 404

    def test_happy_path_after_checkout(self, client: TestClient) -> None:
        # Seed a Subscription with a stripe_customer_id by simulating checkout webhook
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            session.add(Subscription(
                org_id="org-alpha",
                plan_code="pro",
                status="active",
                seats=10,
                stripe_customer_id="cus_existing",
                stripe_sub_id="sub_existing",
            ))
            session.commit()

        response = client.post("/v1/billing/portal")
        assert response.status_code == 200
        body = response.json()
        assert body["org_id"] == "org-alpha"
        assert body["session_id"].startswith("bps_stub_")
        assert "stub.stripe.local/portal/" in body["portal_url"]

    def test_503_billing_disabled(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BILLING_ENABLED", "false")
        get_settings.cache_clear()
        response = client.post("/v1/billing/portal")
        assert response.status_code == 503

    def test_403_when_role_below_admin(self, client: TestClient) -> None:
        _set_tenant(client, tenant_id="org-alpha", role="member")
        response = client.post("/v1/billing/portal")
        assert response.status_code == 403


class TestWebhookRoute:
    def _post_event(
        self, client: TestClient, event: dict, *, secret: str = _TEST_WEBHOOK_SECRET
    ):
        body = json.dumps(event).encode("utf-8")
        header = sign_webhook_payload(payload=body, secret=secret)
        return client.post(
            "/v1/billing/webhook",
            content=body,
            headers={
                "Stripe-Signature": header,
                "Content-Type": "application/json",
            },
        )

    def test_happy_path_checkout(self, client: TestClient) -> None:
        event = _make_event(
            event_id="evt_hook_1",
            event_type="checkout.session.completed",
            obj={
                "metadata": {"org_id": "org-webhook", "plan_code": "pro"},
                "customer": "cus_hook", "subscription": "sub_hook",
            },
        )
        response = self._post_event(client, event)
        assert response.status_code == 200
        body = response.json()
        assert body["received"] is True
        assert body["duplicate"] is False
        assert body["result"] == "applied"
        assert body["affected_org_id"] == "org-webhook"

    def test_idempotent_replay(self, client: TestClient) -> None:
        event = _make_event(
            event_id="evt_replay_1",
            event_type="checkout.session.completed",
            obj={
                "metadata": {"org_id": "org-replay", "plan_code": "pro"},
                "customer": "cus_r", "subscription": "sub_r",
            },
        )
        first = self._post_event(client, event)
        assert first.status_code == 200
        assert first.json()["duplicate"] is False
        second = self._post_event(client, event)
        assert second.status_code == 200
        assert second.json()["duplicate"] is True

    def test_400_missing_signature(self, client: TestClient) -> None:
        body = b'{"id":"evt_x","type":"checkout.session.completed","created":1,"data":{"object":{}}}'
        response = client.post(
            "/v1/billing/webhook",
            content=body,
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400

    def test_400_wrong_signature(self, client: TestClient) -> None:
        event = _make_event(event_id="evt_wrong", event_type="invoice.paid")
        response = self._post_event(client, event, secret="whsec_other")
        assert response.status_code == 400

    def test_400_tampered_body(self, client: TestClient) -> None:
        event = _make_event(event_id="evt_tamper", event_type="invoice.paid")
        body = json.dumps(event).encode("utf-8")
        header = sign_webhook_payload(
            payload=body, secret=_TEST_WEBHOOK_SECRET,
        )
        # Send a different body with the signature for the original
        response = client.post(
            "/v1/billing/webhook",
            content=b'{"id":"evt_other","type":"invoice.paid","created":1,"data":{}}',
            headers={
                "Stripe-Signature": header,
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 400

    def test_503_billing_disabled(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BILLING_ENABLED", "false")
        get_settings.cache_clear()
        event = _make_event(event_id="evt_off", event_type="invoice.paid")
        response = self._post_event(client, event)
        assert response.status_code == 503

    def test_503_secret_unset(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "")
        get_settings.cache_clear()
        event = _make_event(event_id="evt_no_secret", event_type="invoice.paid")
        response = self._post_event(client, event)
        assert response.status_code == 503

    def test_unknown_event_recorded_as_skipped(self, client: TestClient) -> None:
        event = _make_event(
            event_id="evt_unknown_route",
            event_type="customer.created",
            obj={"id": "cus_xyz"},
        )
        response = self._post_event(client, event)
        assert response.status_code == 200
        assert response.json()["result"] == "skipped"


class TestBillingMeRoute:
    def test_creates_free_shell_on_first_call(self, client: TestClient) -> None:
        _set_tenant(client, tenant_id="org-fresh", role="viewer")
        response = client.get("/v1/billing/me")
        assert response.status_code == 200
        body = response.json()
        assert body["org_id"] == "org-fresh"
        assert body["plan_code"] == DEFAULT_PLAN_CODE
        assert body["status"] == "active"
        assert body["seats"] == 1
        assert body["stripe_customer_id"] is None
        # plan_template reflects free tier
        assert body["plan_template"]["events.monthly_quota"] == 50_000

    def test_returns_existing_subscription(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        cpe = datetime.now(timezone.utc) + timedelta(days=20)
        with factory() as session:
            session.add(Subscription(
                org_id="org-alpha",
                plan_code="pro",
                status="active",
                seats=10,
                stripe_customer_id="cus_x",
                stripe_sub_id="sub_x",
                current_period_end=cpe,
            ))
            session.commit()

        response = client.get("/v1/billing/me")
        assert response.status_code == 200
        body = response.json()
        assert body["plan_code"] == "pro"
        assert body["seats"] == 10
        assert body["stripe_customer_id"] == "cus_x"
        assert body["plan_template"]["pilot.autopilot_enabled"] is True

    def test_works_with_viewer_role(self, client: TestClient) -> None:
        _set_tenant(client, tenant_id="org-alpha", role="viewer")
        response = client.get("/v1/billing/me")
        assert response.status_code == 200


# ── invariants ──────────────────────────────────────────────────────────────


class TestInvariants:
    def test_plan_codes_match_tier_matrix(self) -> None:
        # Plan §11.1 binding tiers
        assert VALID_PLAN_CODES == frozenset(
            {"free", "pro", "plus", "enterprise"}
        )

    def test_handled_event_types_mirror_plan_section_113(self) -> None:
        # Plan §11.3 enumerates exactly these 5 event types (we also
        # treat customer.subscription.created the same as updated)
        required = {
            "checkout.session.completed",
            "customer.subscription.updated",
            "customer.subscription.deleted",
            "invoice.paid",
            "invoice.payment_failed",
        }
        assert required.issubset(HANDLED_EVENT_TYPES)
