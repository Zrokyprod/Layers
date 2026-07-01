"""Tests for the hosted Razorpay billing surface."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.core.config import get_settings
from app.db.base import Base
from app.db.models import (
    BillingEvent,
    EventCount,
    GoldenSet,
    GoldenTrace,
    ProjectAlert,
    ReplayRun,
    Subscription,
    SystemOfRecordConnectorConfig,
)
from app.db.session import get_db_session, get_db_session_read
from app.main import app
from app.services import entitlements_resolver
from app.services.billing_metering import (
    METERING_ALERT_CATEGORY,
    current_month,
    increment_event_count,
)
from app.services.billing_plans import (
    DEFAULT_PLAN_CODE,
    InvalidPlanCodeError,
    PLAN_ENTITLEMENTS,
    PlanNotSelfServeError,
    VALID_PLAN_CODES,
    assert_self_serve_plan,
    get_plan_entitlements,
    normalize_plan_code,
)
from app.services.billing_quota import check_quota
from app.services.entitlement_catalog import (
    CANONICAL_PLAN_CODES,
    PLAN_ALIASES,
    load_pricing_contract,
)
from app.services.protected_action_billing import (
    METER_ACTION_RECEIPTS,
    METER_POLICY_CHECKS,
    METER_PROTECTED_ACTIONS,
    METER_RUNNER_EXECUTIONS,
    METER_SOURCE_MUTATIONS,
    METER_VERIFICATION_CHECKS,
    current_usage_count,
    increment_usage_meter,
)
from app.services.razorpay_reconciliation import reconcile_pending_razorpay_orders

_TEST_WEBHOOK_SECRET = "whsec_test_module_5"


@pytest.fixture(autouse=True)
def _billing_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BILLING_ENABLED", "true")
    monkeypatch.setenv("BILLING_PROVIDER", "razorpay")
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_route")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "razorpay-route-secret")
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", _TEST_WEBHOOK_SECRET)
    monkeypatch.setenv("RAZORPAY_DASHBOARD_URL", "https://dashboard.razorpay.test")
    monkeypatch.setenv("ZROKY_EXCHANGE_RATE_USD_TO_INR", "80")
    monkeypatch.setenv("BILLING_QUOTA_FAILURE_POLICY", "strict")
    get_settings.cache_clear()
    entitlements_resolver.invalidate_all()
    yield
    get_settings.cache_clear()
    entitlements_resolver.invalidate_all()


@pytest.fixture()
def client(tmp_path: Path):
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


class _FakeRazorpayOrderClient:
    def __init__(self, owner: "_FakeRazorpayClient") -> None:
        self._owner = owner
        self.last_payload: dict[str, object] | None = None

    def create(self, *, data: dict[str, object]) -> dict[str, object]:
        self.last_payload = data
        order = {
            "id": "order_test_123",
            "amount": data["amount"],
            "currency": data["currency"],
            "receipt": data["receipt"],
            "status": self._owner.order_status,
            "notes": data.get("notes") or {},
        }
        self._owner.orders[str(order["id"])] = order
        return order

    def fetch(self, order_id: str) -> dict[str, object]:
        order = self._owner.orders.get(order_id)
        if order is None:
            return {
                "id": order_id,
                "amount": 3_192_000,
                "currency": "INR",
                "status": self._owner.order_status,
                "notes": {"org_id": "org-alpha", "plan_code": "pro", "product": "zroky"},
            }
        return dict(order)

    def payments(self, order_id: str) -> dict[str, object]:
        order = self._owner.orders.get(order_id) or {}
        return {
            "items": [
                {
                    "id": self._owner.payment_id,
                    "order_id": order_id,
                    "amount": order.get("amount", 3_192_000),
                    "currency": order.get("currency", "INR"),
                    "status": self._owner.payment_status,
                    "captured": self._owner.payment_status == "captured",
                    "notes": order.get(
                        "notes",
                        {"org_id": "org-alpha", "plan_code": "pro", "product": "zroky"},
                    ),
                }
            ]
        }


class _FakeRazorpayPaymentClient:
    def __init__(self, owner: "_FakeRazorpayClient") -> None:
        self._owner = owner

    def fetch(self, payment_id: str) -> dict[str, object]:
        order = self._owner.orders.get("order_test_123") or {}
        return {
            "id": payment_id,
            "order_id": "order_test_123",
            "amount": order.get("amount", 3_192_000),
            "currency": order.get("currency", "INR"),
            "status": self._owner.payment_status,
            "captured": self._owner.payment_status == "captured",
            "notes": order.get(
                "notes",
                {"org_id": "org-alpha", "plan_code": "pro", "product": "zroky"},
            ),
        }


class _FakeRazorpayClient:
    def __init__(self) -> None:
        self.orders: dict[str, dict[str, object]] = {}
        self.payment_id = "pay_test_123"
        self.payment_status = "captured"
        self.order_status = "paid"
        self.order = _FakeRazorpayOrderClient(self)
        self.payment = _FakeRazorpayPaymentClient(self)


def _razorpay_signature(order_id: str, payment_id: str) -> str:
    return hmac.new(
        b"razorpay-route-secret",
        f"{order_id}|{payment_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _sign_webhook_payload(*, payload: bytes, secret: str = _TEST_WEBHOOK_SECRET) -> str:
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _make_event(
    *,
    event_id: str,
    event_type: str,
    org_id: str = "org-alpha",
    plan_code: str = "pro",
    payment_id: str | None = None,
    payment_status: str | None = "captured",
) -> dict:
    payment_ref = payment_id or f"pay_{event_id}"
    payment_entity = {
        "id": payment_ref,
        "order_id": f"order_{event_id}",
        "notes": {"org_id": org_id, "plan_code": plan_code},
    }
    if payment_status is not None:
        payment_entity["status"] = payment_status
        payment_entity["captured"] = payment_status == "captured"
    return {
        "id": event_id,
        "event": event_type,
        "created_at": int(time.time()),
        "payload": {
            "payment": {
                "entity": payment_entity,
            }
        },
    }


def _post_signed_webhook(client: TestClient, event: dict, *, secret: str = _TEST_WEBHOOK_SECRET):
    body = json.dumps(event).encode("utf-8")
    return client.post(
        "/v1/billing/webhook",
        content=body,
        headers={
            "X-Razorpay-Signature": _sign_webhook_payload(payload=body, secret=secret),
            "Content-Type": "application/json",
        },
    )


class TestBillingPlans:
    def test_normalize_plan_code(self) -> None:
        assert normalize_plan_code("PRO") == "pro"
        assert normalize_plan_code("  Pro ") == "pro"

    def test_normalize_invalid(self) -> None:
        with pytest.raises(InvalidPlanCodeError):
            normalize_plan_code("ultra")
        with pytest.raises(InvalidPlanCodeError):
            normalize_plan_code(None)

    def test_assert_self_serve_rules(self) -> None:
        assert assert_self_serve_plan("pro") == "pro"
        with pytest.raises(PlanNotSelfServeError):
            assert_self_serve_plan("pilot")
        with pytest.raises(PlanNotSelfServeError):
            assert_self_serve_plan("starter")
        with pytest.raises(PlanNotSelfServeError):
            assert_self_serve_plan("free")
        with pytest.raises(PlanNotSelfServeError):
            assert_self_serve_plan("enterprise")

    def test_plan_entitlements_return_copy_and_share_keys(self) -> None:
        plan = get_plan_entitlements("free")
        plan["events.monthly_quota"] = 999
        assert get_plan_entitlements("free")["events.monthly_quota"] == 5_000
        ref = set(PLAN_ENTITLEMENTS["free"].keys())
        for code in VALID_PLAN_CODES:
            assert set(PLAN_ENTITLEMENTS[code].keys()) == ref

    def test_all_plans_have_same_keys(self) -> None:
        self.test_plan_entitlements_return_copy_and_share_keys()


class TestDeprecatedCheckoutRoute:
    def test_checkout_points_to_razorpay_order(self, client: TestClient) -> None:
        response = client.post(
            "/v1/billing/checkout",
            json={"plan_code": "pro", "customer_email": "billing@example.com"},
        )
        assert response.status_code == 410
        assert "razorpay/order" in response.json()["detail"]

    def test_checkout_rejects_invalid_or_forbidden_plan(self, client: TestClient) -> None:
        assert client.post("/v1/billing/checkout", json={"plan_code": "ultra"}).status_code == 422
        assert client.post("/v1/billing/checkout", json={"plan_code": "free"}).status_code == 422
        assert client.post("/v1/billing/checkout", json={"plan_code": "starter"}).status_code == 422
        assert client.post("/v1/billing/checkout", json={"plan_code": "enterprise"}).status_code == 422

    def test_checkout_requires_admin_role(self, client: TestClient) -> None:
        _set_tenant(client, tenant_id="org-alpha", role="member")
        response = client.post("/v1/billing/checkout", json={"plan_code": "pro"})
        assert response.status_code == 403


class TestRazorpayCheckoutRoute:
    def test_create_order_tracks_pending_request(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeRazorpayClient()
        monkeypatch.setattr("app.api.routes.billing._razorpay_client", lambda: fake)

        response = client.post(
            "/v1/billing/razorpay/order",
            json={"plan_code": "pro", "customer_email": "billing@example.com"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["order_id"] == "order_test_123"
        assert body["amount"] == 3_192_000
        assert body["currency"] == "INR"
        assert body["plan_code"] == "pro"
        assert fake.order.last_payload is not None
        assert fake.order.last_payload["notes"] == {
            "org_id": "org-alpha",
            "plan_code": "pro",
            "product": "zroky",
            "customer_email": "billing@example.com",
        }

        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            sub = session.execute(
                select(Subscription).where(Subscription.org_id == "org-alpha")
            ).scalar_one()
            assert sub.payment_provider == "razorpay"
            assert sub.payment_request_ref == "order_test_123:pro"
            assert sub.payment_customer_ref == "billing@example.com"
            assert sub.plan_code == DEFAULT_PLAN_CODE

    def test_create_order_computes_plan_amount_and_tracks_pending_request(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self.test_create_order_tracks_pending_request(client, monkeypatch)

    def test_create_order_rejects_grandfathered_starter(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeRazorpayClient()
        monkeypatch.setattr("app.api.routes.billing._razorpay_client", lambda: fake)

        response = client.post("/v1/billing/razorpay/order", json={"plan_code": "starter"})

        assert response.status_code == 422
        assert fake.order.last_payload is None

    def test_verify_payment_activates_plan_after_valid_signature(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeRazorpayClient()
        monkeypatch.setattr("app.api.routes.billing._razorpay_client", lambda: fake)
        assert client.post("/v1/billing/razorpay/order", json={"plan_code": "pro"}).status_code == 200

        payment_id = "pay_test_123"
        response = client.post(
            "/v1/billing/razorpay/verify",
            json={
                "razorpay_payment_id": payment_id,
                "razorpay_order_id": "order_test_123",
                "razorpay_signature": _razorpay_signature("order_test_123", payment_id),
            },
        )

        assert response.status_code == 200
        assert response.json()["success"] is True
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            sub = session.execute(
                select(Subscription).where(Subscription.org_id == "org-alpha")
            ).scalar_one()
            assert sub.payment_provider == "razorpay"
            assert sub.payment_request_ref == "order_test_123"
            assert sub.payment_subscription_ref == payment_id
            assert sub.plan_code == "pro"
            event = session.execute(
                select(BillingEvent).where(
                    BillingEvent.provider == "razorpay",
                    BillingEvent.provider_event_id == f"razorpay_verify:{payment_id}",
                )
            ).scalar_one()
            assert event.result == "applied"

    def test_verify_payment_rejects_authorized_provider_state_without_marking_paid(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeRazorpayClient()
        fake.payment_status = "authorized"
        fake.order_status = "attempted"
        monkeypatch.setattr("app.api.routes.billing._razorpay_client", lambda: fake)
        assert client.post("/v1/billing/razorpay/order", json={"plan_code": "pro"}).status_code == 200

        payment_id = "pay_authorized"
        response = client.post(
            "/v1/billing/razorpay/verify",
            json={
                "razorpay_payment_id": payment_id,
                "razorpay_order_id": "order_test_123",
                "razorpay_signature": _razorpay_signature("order_test_123", payment_id),
            },
        )

        assert response.status_code == 409
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            sub = session.execute(
                select(Subscription).where(Subscription.org_id == "org-alpha")
            ).scalar_one()
            assert sub.payment_subscription_ref is None
            assert sub.plan_code == DEFAULT_PLAN_CODE
            assert session.execute(
                select(BillingEvent).where(
                    BillingEvent.provider == "razorpay",
                    BillingEvent.provider_event_id == f"razorpay_verify:{payment_id}",
                )
            ).scalar_one_or_none() is None

    def test_verify_payment_rejects_bad_signature_without_marking_paid(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeRazorpayClient()
        monkeypatch.setattr("app.api.routes.billing._razorpay_client", lambda: fake)
        assert client.post("/v1/billing/razorpay/order", json={"plan_code": "pro"}).status_code == 200

        response = client.post(
            "/v1/billing/razorpay/verify",
            json={
                "razorpay_payment_id": "pay_bad",
                "razorpay_order_id": "order_test_123",
                "razorpay_signature": "bad-signature",
            },
        )

        assert response.status_code == 400
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            sub = session.execute(
                select(Subscription).where(Subscription.org_id == "org-alpha")
            ).scalar_one()
            assert sub.payment_subscription_ref is None
            assert sub.plan_code == DEFAULT_PLAN_CODE


class TestRazorpayReconciliation:
    def test_reconciles_paid_pending_order_without_browser_verify(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeRazorpayClient()
        fake.payment_id = "pay_reconciled"
        monkeypatch.setattr("app.api.routes.billing._razorpay_client", lambda: fake)
        assert client.post("/v1/billing/razorpay/order", json={"plan_code": "pro"}).status_code == 200

        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            result = reconcile_pending_razorpay_orders(session, client_factory=lambda: fake)
            assert result.examined == 1
            assert result.activated == 1
            assert result.failed == 0

            sub = session.execute(
                select(Subscription).where(Subscription.org_id == "org-alpha")
            ).scalar_one()
            assert sub.payment_request_ref == "order_test_123"
            assert sub.payment_subscription_ref == "pay_reconciled"
            assert sub.status == "active"
            assert sub.plan_code == "pro"
            assert entitlements_resolver.get(session, "org-alpha", "events.monthly_quota") == 250_000

            event = session.execute(
                select(BillingEvent).where(
                    BillingEvent.provider == "razorpay",
                    BillingEvent.provider_event_id == "razorpay_reconcile:pay_reconciled",
                )
            ).scalar_one()
            assert event.result == "applied"

    def test_reconciliation_skips_order_metadata_mismatch(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _FakeRazorpayClient()
        monkeypatch.setattr("app.api.routes.billing._razorpay_client", lambda: fake)
        assert client.post("/v1/billing/razorpay/order", json={"plan_code": "pro"}).status_code == 200
        fake.orders["order_test_123"]["notes"] = {"org_id": "other-org", "plan_code": "pro"}

        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            result = reconcile_pending_razorpay_orders(session, client_factory=lambda: fake)
            assert result.examined == 1
            assert result.activated == 0
            assert result.skipped == 1
            assert result.records[0].detail == "order_org_mismatch"

            sub = session.execute(
                select(Subscription).where(Subscription.org_id == "org-alpha")
            ).scalar_one()
            assert sub.payment_subscription_ref is None
            assert sub.plan_code == DEFAULT_PLAN_CODE


class TestPortalRoute:
    def test_portal_returns_razorpay_dashboard(self, client: TestClient) -> None:
        response = client.post("/v1/billing/portal")
        assert response.status_code == 200
        body = response.json()
        assert body["org_id"] == "org-alpha"
        assert body["payment_provider"] == "razorpay"
        assert body["portal_url"] == "https://dashboard.razorpay.test"

    def test_happy_path_without_customer(self, client: TestClient) -> None:
        self.test_portal_returns_razorpay_dashboard(client)


class TestBillingQuota:
    def test_strict_quota_check_failure_denies_and_alerts(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fail_resolver(*_args, **_kwargs):
            raise RuntimeError("resolver unavailable")

        monkeypatch.setattr(
            "app.services.billing_quota.entitlements_resolver.get",
            fail_resolver,
        )

        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            decision = check_quota(session, "org-alpha")
            assert decision.allowed is False
            assert decision.reason == "check_error"

            alert = session.execute(
                select(ProjectAlert).where(
                    ProjectAlert.tenant_id == "org-alpha",
                    ProjectAlert.category == METERING_ALERT_CATEGORY,
                )
            ).scalar_one()
            assert alert.status == "OPEN"
            assert alert.source == "billing_quota"
            assert alert.slack_delivery_status == "not_connected"
            assert alert.slack_delivery_attempted_at is not None

    def test_event_counter_increment_is_portable_and_accumulates_once(
        self, client: TestClient
    ) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            assert increment_event_count(session, "org-alpha", amount=2) is True
            assert increment_event_count(session, "org-alpha", amount=3) is True

            row = session.execute(
                select(EventCount).where(
                    EventCount.tenant_id == "org-alpha",
                    EventCount.month == current_month(),
                )
            ).scalar_one()
            assert row.event_count == 5

    def test_hosted_usage_endpoint_returns_calls_replay_goldens_and_metering(
        self, client: TestClient
    ) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            sub = Subscription(
                org_id="org-alpha",
                payment_provider="razorpay",
                plan_code="pro",
                status="active",
                seats=3,
            )
            golden_set = GoldenSet(project_id="org-alpha", name="Launch goldens")
            connector = SystemOfRecordConnectorConfig(
                project_id="org-alpha",
                connector_type="ledger_refund_api",
                base_url="https://ledger.test",
            )
            session.add_all([sub, golden_set, connector])
            session.flush()
            session.add_all(
                [
                    GoldenTrace(
                        golden_set_id=golden_set.id,
                        project_id="org-alpha",
                        status="active",
                        expected_output_text="approved",
                    ),
                    GoldenTrace(
                        golden_set_id=golden_set.id,
                        project_id="org-alpha",
                        status="active",
                        expected_output_text="blocked",
                    ),
                    ReplayRun(
                        project_id="org-alpha",
                        golden_set_id=golden_set.id,
                        trigger="manual",
                        status="pass",
                    ),
                ]
            )
            session.commit()
            entitlements_resolver.invalidate("org-alpha")
            assert increment_event_count(session, "org-alpha", amount=42) is True
            assert increment_usage_meter(session, "org-alpha", METER_PROTECTED_ACTIONS, amount=7) is True
            assert increment_usage_meter(session, "org-alpha", METER_POLICY_CHECKS, amount=11) is True
            assert increment_usage_meter(session, "org-alpha", METER_RUNNER_EXECUTIONS, amount=5) is True
            assert increment_usage_meter(session, "org-alpha", METER_ACTION_RECEIPTS, amount=4) is True
            assert increment_usage_meter(session, "org-alpha", METER_VERIFICATION_CHECKS, amount=9) is True
            assert increment_usage_meter(session, "org-alpha", METER_SOURCE_MUTATIONS, amount=13) is True
            session.commit()

        response = client.get("/v1/billing/usage")
        assert response.status_code == 200
        body = response.json()
        assert body["tenant_id"] == "org-alpha"
        assert body["plan_code"] == "pro"
        assert body["calls"]["used"] == 42
        assert body["calls"]["limit"] == 250_000
        assert body["replay"]["used"] == 1
        assert body["replay"]["limit"] == 500
        assert body["goldens"]["used"] == 2
        assert body["goldens"]["limit"] == 2_500
        assert body["golden_sets"]["used"] == 1
        assert body["golden_sets"]["limit"] == 25
        assert body["protected_actions"]["used"] == 7
        assert body["protected_actions"]["limit"] == 25_000
        assert body["policy_checks"]["used"] == 11
        assert body["policy_checks"]["limit"] == 100_000
        assert body["runner_executions"]["used"] == 5
        assert body["runner_executions"]["limit"] == 25_000
        assert body["action_receipts"]["used"] == 4
        assert body["action_receipts"]["limit"] == 25_000
        assert body["verification_checks"]["used"] == 9
        assert body["verification_checks"]["limit"] == 50_000
        assert body["source_mutations"]["used"] == 13
        assert body["source_mutations"]["limit"] == 100_000
        assert body["active_connectors"]["used"] == 1
        assert body["active_connectors"]["limit"] == 10
        assert body["metering_health"]["state"] == "ok"

    def test_named_usage_meter_increment_is_portable_and_accumulates_once(
        self, client: TestClient
    ) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            assert increment_usage_meter(session, "org-alpha", METER_PROTECTED_ACTIONS, amount=2) is True
            assert increment_usage_meter(session, "org-alpha", METER_PROTECTED_ACTIONS, amount=3) is True
            session.commit()

            assert (
                current_usage_count(session, "org-alpha", METER_PROTECTED_ACTIONS)
                == 5
            )


class TestWebhookRoute:
    def test_payment_captured_applies_subscription(self, client: TestClient) -> None:
        response = _post_signed_webhook(
            client,
            _make_event(event_id="evt_paid", event_type="payment.captured", plan_code="pro"),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["received"] is True
        assert body["duplicate"] is False
        assert body["result"] == "applied"

        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            sub = session.execute(
                select(Subscription).where(Subscription.org_id == "org-alpha")
            ).scalar_one()
            assert sub.payment_provider == "razorpay"
            assert sub.payment_subscription_ref == "pay_evt_paid"
            assert sub.plan_code == "pro"

    def test_happy_path_payment_succeeded(self, client: TestClient) -> None:
        response = _post_signed_webhook(
            client,
            _make_event(event_id="evt_succeeded", event_type="payment.succeeded"),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["received"] is True
        assert body["duplicate"] is False
        assert body["result"] == "applied"

    def test_payment_authorized_webhook_does_not_activate_subscription(
        self, client: TestClient
    ) -> None:
        response = _post_signed_webhook(
            client,
            _make_event(
                event_id="evt_authorized",
                event_type="payment.authorized",
                payment_status="authorized",
            ),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["received"] is True
        assert body["duplicate"] is False
        assert body["result"] == "skipped"

        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            assert session.execute(
                select(Subscription).where(Subscription.org_id == "org-alpha")
            ).scalar_one_or_none() is None

    def test_duplicate_webhook_is_idempotent(self, client: TestClient) -> None:
        event = _make_event(
            event_id="evt_dup",
            event_type="payment.captured",
            payment_id="pay_duplicate",
        )
        first = _post_signed_webhook(client, event)
        second = _post_signed_webhook(client, event)
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["duplicate"] is False
        assert second.json()["duplicate"] is True

    def test_idempotent_replay(self, client: TestClient) -> None:
        self.test_duplicate_webhook_is_idempotent(client)

    def test_rejects_invalid_signature(self, client: TestClient) -> None:
        body = json.dumps(_make_event(event_id="evt_bad", event_type="payment.succeeded")).encode("utf-8")
        response = client.post(
            "/v1/billing/webhook",
            content=body,
            headers={"X-Razorpay-Signature": "bad", "Content-Type": "application/json"},
        )
        assert response.status_code == 400

    def test_billing_disabled_returns_503(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BILLING_ENABLED", "false")
        get_settings.cache_clear()
        response = _post_signed_webhook(
            client,
            _make_event(event_id="evt_off", event_type="payment.succeeded"),
        )
        assert response.status_code == 503

    def test_unknown_event_recorded_as_skipped(self, client: TestClient) -> None:
        response = _post_signed_webhook(
            client,
            _make_event(event_id="evt_unknown", event_type="customer.created"),
        )
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
        assert body["payment_provider"] == "razorpay"
        assert body["payment_customer_ref"] is None
        assert body["payment_subscription_ref"] is None
        assert body["payment_request_ref"] is None

    def test_returns_existing_subscription(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        current_period_end = datetime.now(timezone.utc) + timedelta(days=20)
        with factory() as session:
            session.add(
                Subscription(
                    org_id="org-alpha",
                    plan_code="pro",
                    status="active",
                    seats=10,
                    payment_provider="razorpay",
                    payment_customer_ref="billing@example.com",
                    payment_subscription_ref="pay_x",
                    payment_request_ref="order_x",
                    current_period_end=current_period_end,
                )
            )
            session.commit()

        response = client.get("/v1/billing/me")
        assert response.status_code == 200
        body = response.json()
        assert body["plan_code"] == "pro"
        assert body["seats"] == 10
        assert body["payment_provider"] == "razorpay"
        assert body["payment_subscription_ref"] == "pay_x"


class TestInvariants:
    def test_plan_codes_match_tier_matrix(self) -> None:
        contract = load_pricing_contract()
        assert tuple(contract["canonical_plan_order"]) == CANONICAL_PLAN_CODES
        assert contract["aliases"] == PLAN_ALIASES
        assert set(VALID_PLAN_CODES) == set(CANONICAL_PLAN_CODES) | set(PLAN_ALIASES)
        assert set(PLAN_ENTITLEMENTS) == set(VALID_PLAN_CODES)
