from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import Project, Subscription, SupportTicket, SupportTicketMessage
from app.db.session import get_db_session
from app.main import app


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
        engine.dispose()


def test_owner_support_ticket_detail_and_reply(client) -> None:
    test_client, session_factory = client
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

    detail = test_client.get("/v1/owner/support/tickets/ticket_1")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["ticket"]["description"] == "Gateway emits but dashboard is empty."
    assert payload["ticket"]["message_count"] == 1
    assert payload["messages"][0]["body"] == "Please check my gateway."

    reply = test_client.post(
        "/v1/owner/support/tickets/ticket_1/reply",
        json={"body": "Checking the capture stream now.", "is_internal": True},
    )
    assert reply.status_code == 201

    detail_after = test_client.get("/v1/owner/support/tickets/ticket_1")
    assert detail_after.status_code == 200
    messages = detail_after.json()["messages"]
    assert len(messages) == 2
    assert messages[1]["sender_type"] == "owner"
    assert messages[1]["is_internal"] is True


def test_owner_billing_accounts_include_stripe_links(client) -> None:
    test_client, session_factory = client
    now = datetime.now(UTC)
    with session_factory() as db:
        db.add(Project(id="org_1", name="Acme AI", owner_ref="acme", is_active=True))
        db.add(
            Subscription(
                id="sub_row_1",
                org_id="org_1",
                stripe_customer_id="cus_123",
                stripe_sub_id="sub_123",
                plan_code="pro",
                status="active",
                sla_tier="team",
                seats=5,
                current_period_end=now + timedelta(days=20),
            )
        )
        db.commit()

    res = test_client.get("/v1/owner/billing/accounts?status=active")
    assert res.status_code == 200
    payload = res.json()
    assert payload["total"] == 1
    row = payload["items"][0]
    assert row["org_id"] == "org_1"
    assert row["project_name"] == "Acme AI"
    assert row["stripe_customer_url"].endswith("/customers/cus_123")
    assert row["stripe_subscription_url"].endswith("/subscriptions/sub_123")
