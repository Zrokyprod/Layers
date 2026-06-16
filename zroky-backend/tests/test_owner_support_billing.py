from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import BillingEvent, Entitlement, Project, Subscription, SupportTicket, SupportTicketMessage
from app.db.session import get_db_session
from app.main import app


class _FakeRazorpayPaymentClient:
    def __init__(self, owner: "_FakeRazorpayClient") -> None:
        self._owner = owner

    def fetch(self, payment_ref: str) -> dict:
        return {
            "id": payment_ref,
            "order_id": self._owner.order_id,
            "status": self._owner.payment_status,
            "captured": self._owner.payment_status == "captured",
            "amount": 1_000,
            "currency": "INR",
            "notes": dict(self._owner.notes),
            "email": "billing@example.com",
        }


class _FakeRazorpayOrderClient:
    def __init__(self, owner: "_FakeRazorpayClient") -> None:
        self._owner = owner
        self.fetched_refs: list[str] = []

    def fetch(self, order_ref: str) -> dict:
        self.fetched_refs.append(order_ref)
        return {
            "id": order_ref,
            "status": self._owner.order_status,
            "amount": self._owner.amount,
            "currency": "INR",
            "notes": dict(self._owner.notes),
        }

    def payments(self, order_ref: str) -> dict:
        return {
            "items": [
                {
                    "id": self._owner.payment_id,
                    "order_id": order_ref,
                    "status": self._owner.payment_status,
                    "captured": self._owner.payment_status == "captured",
                    "amount": self._owner.amount,
                    "currency": "INR",
                    "notes": dict(self._owner.notes),
                }
            ]
        }


class _FakeRazorpayClient:
    def __init__(self) -> None:
        self.order_id = "rzp_order_123"
        self.payment_id = "rzp_pay_123"
        self.amount = 1_592_000
        self.payment_status = "captured"
        self.order_status = "paid"
        self.notes = {"org_id": "org_razorpay", "plan_code": "pro"}
        self.payment = _FakeRazorpayPaymentClient(self)
        self.order = _FakeRazorpayOrderClient(self)


@pytest.fixture()
def client(tmp_path: Path):
    db_path = tmp_path / "owner_support_billing.db"
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


def test_owner_support_ticket_detail_and_reply(client, monkeypatch: pytest.MonkeyPatch) -> None:
    test_client, session_factory = client
    owner_headers = _set_owner_auth(monkeypatch)
    with session_factory() as db:
        ticket = SupportTicket(
            id="ticket_1",
            tenant_id="proj_support",
            user_id="user_1",
            subject="email:user@example.com",
            email="user@example.com",
            title="Cannot connect gateway",
            description="Gateway emits but dashboard is empty.",
            category="capture",
            priority="high",
            status="open",
        )
        db.add(ticket)
        db.add(
            SupportTicketMessage(
                id="msg_1",
                ticket_id="ticket_1",
                sender_type="user",
                sender_subject="email:user@example.com",
                body="Please check my gateway.",
                is_internal=False,
            )
        )
        db.commit()

    detail = test_client.get("/v1/owner/support/tickets/ticket_1", headers=owner_headers)
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["ticket"]["description"] == "Gateway emits but dashboard is empty."
    assert payload["ticket"]["message_count"] == 1
    assert payload["messages"][0]["body"] == "Please check my gateway."

    reply = test_client.post(
        "/v1/owner/support/tickets/ticket_1/reply",
        headers=owner_headers,
        json={"body": "Checking the capture stream now.", "is_internal": True},
    )
    assert reply.status_code == 201

    detail_after = test_client.get("/v1/owner/support/tickets/ticket_1", headers=owner_headers)
    assert detail_after.status_code == 200
    messages = detail_after.json()["messages"]
    assert len(messages) == 2
    assert messages[1]["sender_type"] == "owner"
    assert messages[1]["is_internal"] is True


def test_owner_billing_accounts_include_razorpay_dashboard(client, monkeypatch: pytest.MonkeyPatch) -> None:
    test_client, session_factory = client
    owner_headers = _set_owner_auth(monkeypatch)
    now = datetime.now(UTC)
    with session_factory() as db:
        db.add(Project(id="org_1", name="Acme AI", owner_ref="acme", is_active=True))
        db.add(
            Subscription(
                id="sub_row_1",
                org_id="org_1",
                payment_provider="razorpay",
                payment_customer_ref="billing@example.com",
                payment_subscription_ref="pay_123",
                payment_request_ref="order_123",
                plan_code="pro",
                status="active",
                sla_tier="team",
                seats=5,
                current_period_end=now + timedelta(days=20),
            )
        )
        db.commit()

    res = test_client.get("/v1/owner/billing/accounts?status=active", headers=owner_headers)
    assert res.status_code == 200
    payload = res.json()
    assert payload["total"] == 1
    row = payload["items"][0]
    assert row["org_id"] == "org_1"
    assert row["project_name"] == "Acme AI"
    assert row["payment_provider"] == "razorpay"
    assert row["payment_subscription_ref"] == "pay_123"
    assert row["payment_dashboard_url"]


def test_owner_billing_payment_recovery_reports_pending_and_reconciled_events(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_client, session_factory = client
    owner_headers = _set_owner_auth(monkeypatch)
    now = datetime.now(UTC)
    with session_factory() as db:
        db.add(Project(id="org_pending", name="Pending Org", owner_ref="pending", is_active=True))
        db.add(
            Subscription(
                id="sub_pending",
                org_id="org_pending",
                payment_provider="razorpay",
                payment_request_ref="rzp_order_pending:starter",
                payment_subscription_ref=None,
                plan_code="free",
                status="active",
                updated_at=now - timedelta(minutes=20),
            )
        )
        db.add(
            BillingEvent(
                provider="razorpay",
                provider_event_id="razorpay_reconcile:rzp_pay_recovered",
                event_type="payment.reconciled",
                provider_created_at=now - timedelta(minutes=5),
                processed_at=now - timedelta(minutes=5),
                result="applied",
                affected_org_id="org_recovered",
                payload_json=json.dumps(
                    {
                        "payment_id": "rzp_pay_recovered",
                        "order_id": "rzp_order_recovered",
                        "plan_code": "pro",
                    }
                ),
            )
        )
        db.commit()

    res = test_client.get("/v1/owner/billing/payment-recovery", headers=owner_headers)

    assert res.status_code == 200
    payload = res.json()
    assert payload["pending_count"] == 1
    assert payload["stale_pending_count"] == 1
    assert payload["oldest_pending_age_seconds"] >= 15 * 60
    assert payload["pending_items"][0]["org_id"] == "org_pending"
    assert payload["pending_items"][0]["order_id"] == "rzp_order_pending"
    assert payload["pending_items"][0]["requested_plan_code"] == "starter"
    assert payload["recent_reconciled"][0]["payment_id"] == "rzp_pay_recovered"


def test_owner_can_run_razorpay_reconciliation(client, monkeypatch: pytest.MonkeyPatch) -> None:
    test_client, session_factory = client
    owner_headers = _set_owner_auth(monkeypatch)
    monkeypatch.setenv("ZROKY_EXCHANGE_RATE_USD_TO_INR", "80")
    get_settings.cache_clear()
    fake_razorpay = _FakeRazorpayClient()
    fake_razorpay.notes = {"org_id": "org_razorpay", "plan_code": "pro"}
    monkeypatch.setattr(
        "app.services.razorpay_reconciliation._razorpay_client",
        lambda: fake_razorpay,
    )
    with session_factory() as db:
        db.add(
            Subscription(
                org_id="org_razorpay",
                plan_code="free",
                status="active",
                payment_provider="razorpay",
                payment_request_ref="rzp_order_123:pro",
            )
        )
        db.commit()

    res = test_client.post("/v1/owner/billing/payments/reconcile?limit=10", headers=owner_headers)

    assert res.status_code == 200
    payload = res.json()
    assert payload["examined"] == 1
    assert payload["activated"] == 1
    with session_factory() as db:
        sub = db.scalar(select(Subscription).where(Subscription.org_id == "org_razorpay"))
        assert sub is not None
        assert sub.plan_code == "pro"
        assert sub.payment_subscription_ref == "rzp_pay_123"
        rows = db.execute(
            select(Entitlement).where(
                Entitlement.org_id == "org_razorpay",
                Entitlement.source == "plan",
            )
        ).scalars().all()
        assert len(rows) > 0


def test_owner_confirms_razorpay_payment_and_seeds_entitlements(client, monkeypatch: pytest.MonkeyPatch) -> None:
    test_client, session_factory = client
    owner_headers = _set_owner_auth(monkeypatch)
    fake_razorpay = _FakeRazorpayClient()
    monkeypatch.setattr(
        "app.api.routes._internal.owner_support_billing._razorpay_client",
        lambda: fake_razorpay,
    )
    period_end = datetime.now(UTC) + timedelta(days=30)

    res = test_client.post(
        "/v1/owner/billing/payments/confirm",
        headers=owner_headers,
        json={
            "org_id": "org_razorpay",
            "plan_code": "pro",
            "payment_ref": "rzp_pay_123",
            "customer_ref": "billing@example.com",
            "payment_request_ref": "rzp_order_123",
            "current_period_end": period_end.isoformat(),
            "seats": 10,
        },
    )

    assert res.status_code == 200
    payload = res.json()
    assert payload["ok"] is True
    assert payload["org_id"] == "org_razorpay"
    assert payload["plan_code"] == "pro"
    assert payload["payment_provider"] == "razorpay"
    assert payload["payment_subscription_ref"] == "rzp_pay_123"
    assert payload["provider_verified"] is True

    with session_factory() as db:
        sub = db.scalar(select(Subscription).where(Subscription.org_id == "org_razorpay"))
        assert sub is not None
        assert sub.status == "active"
        assert sub.seats == 10
        assert sub.payment_customer_ref == "billing@example.com"
        rows = db.execute(
            select(Entitlement).where(
                Entitlement.org_id == "org_razorpay",
                Entitlement.source == "plan",
            )
        ).scalars().all()
        assert len(rows) > 0

    replay = test_client.post(
        "/v1/owner/billing/payments/confirm",
        headers=owner_headers,
        json={
            "org_id": "org_razorpay",
            "plan_code": "pro",
            "payment_ref": "rzp_pay_123",
        },
    )
    assert replay.status_code == 200


def test_owner_confirm_rejects_uncaptured_razorpay_payment_without_entitlements(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_client, session_factory = client
    owner_headers = _set_owner_auth(monkeypatch)
    fake_razorpay = _FakeRazorpayClient()
    fake_razorpay.payment_status = "authorized"
    fake_razorpay.order_status = "attempted"
    monkeypatch.setattr(
        "app.api.routes._internal.owner_support_billing._razorpay_client",
        lambda: fake_razorpay,
    )

    res = test_client.post(
        "/v1/owner/billing/payments/confirm",
        headers=owner_headers,
        json={
            "org_id": "org_razorpay",
            "plan_code": "pro",
            "payment_ref": "rzp_pay_authorized",
            "payment_request_ref": "rzp_order_123",
        },
    )

    assert res.status_code == 409
    with session_factory() as db:
        assert db.scalar(select(Subscription).where(Subscription.org_id == "org_razorpay")) is None
        rows = db.execute(
            select(Entitlement).where(Entitlement.org_id == "org_razorpay")
        ).scalars().all()
        assert rows == []


def test_owner_confirm_normalizes_stored_checkout_order_ref(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_client, session_factory = client
    owner_headers = _set_owner_auth(monkeypatch)
    fake_razorpay = _FakeRazorpayClient()
    monkeypatch.setattr(
        "app.api.routes._internal.owner_support_billing._razorpay_client",
        lambda: fake_razorpay,
    )
    with session_factory() as db:
        db.add(
            Subscription(
                org_id="org_razorpay",
                plan_code="pro",
                status="incomplete",
                seats=1,
                payment_provider="razorpay",
                payment_request_ref="rzp_order_123:pro",
            )
        )
        db.commit()

    res = test_client.post(
        "/v1/owner/billing/payments/confirm",
        headers=owner_headers,
        json={
            "org_id": "org_razorpay",
            "plan_code": "pro",
            "payment_ref": "rzp_pay_123",
        },
    )

    assert res.status_code == 200
    assert fake_razorpay.order.fetched_refs == ["rzp_order_123"]


def test_owner_pricing_plans_exposes_backend_entitlement_contract(client, monkeypatch: pytest.MonkeyPatch) -> None:
    test_client, _ = client
    owner_headers = _set_owner_auth(monkeypatch)

    res = test_client.get("/v1/owner/pricing/plans", headers=owner_headers)

    assert res.status_code == 200
    payload = res.json()
    assert payload["source_of_truth"] == "api-contracts/pricing-plans.json"
    assert payload["canonical_plan_order"] == ["free", "starter", "pro", "enterprise"]
    assert payload["aliases"] == {"pilot": "starter", "plus": "pro"}
    assert payload["drift"] == []

    plans = {plan["code"]: plan for plan in payload["plans"]}
    assert plans["free"]["pricing"]["replay_credits"] == 0
    assert plans["starter"]["pricing"]["golden_sets"] == 5
    assert plans["pro"]["pricing"]["blocking_ci"] is True
    assert plans["enterprise"]["pricing"]["provider_key_vault"] is True
