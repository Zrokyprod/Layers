from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.core.config import get_settings
from app.db.base import Base
from app.db.models import Project
from app.db.session import get_db_session, get_db_session_read
from app.main import app
from app.services.outcome_reconciliation import SourceRecord
from app.services.system_of_record_connectors import (
    ShopifyAdminConnector,
    StripePaymentConnector,
)


def _sqlite_session_factory(path: Path):
    engine = create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return engine, factory


def _seed_project(session_factory, project_id: str) -> None:
    with session_factory() as session:
        session.add(Project(id=project_id, name=project_id))
        session.commit()


def test_stripe_payment_connector_config_status_and_test_run_redact_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "PROVIDER_KEY_VAULT_KEK", "test-kek-for-stripe-payment-connector-123456"
    )
    get_settings.cache_clear()
    engine, session_factory = _sqlite_session_factory(
        tmp_path / "stripe_payment_connector.db"
    )
    _seed_project(session_factory, "proj_stripe_payment")

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def override_tenant():
        return TenantContext(
            tenant_id="proj_stripe_payment", role="admin", subject="user-stripe-pay"
        )

    def fake_fetch(self: StripePaymentConnector) -> SourceRecord:
        assert self.base_url == "https://api.stripe.com"
        assert self.path_template == "/v1/payment_intents/{record_ref}"
        assert self.bearer_token == "sk_test_payment_secret"
        return SourceRecord(
            record={
                "payment_id": self.payment_id,
                "id": self.payment_id,
                "object": "payment_intent",
                "amount_minor": 4250,
                "currency": "USD",
                "status": "succeeded",
            },
            record_found=True,
            metadata={
                "connector_type": "stripe_payment",
                "request_url": f"https://api.stripe.com/v1/payment_intents/{self.payment_id}",
                "http_status": 200,
                "attempts": 1,
                "max_attempts": 2,
                "retryable": False,
                "payment_id": self.payment_id,
                "stripe_object": "payment_intent",
            },
        )

    monkeypatch.setattr(StripePaymentConnector, "fetch", fake_fetch)
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_db_session_read] = override_db
    app.dependency_overrides[require_tenant_context] = override_tenant

    try:
        with TestClient(app) as client:
            empty = client.get("/v1/integrations/system-of-record/stripe-payment/status")
            assert empty.status_code == 200
            assert empty.json()["connected"] is False
            assert empty.json()["connector_type"] == "stripe_payment"
            assert empty.json()["readiness"]["status"] == "not_ready"

            saved = client.put(
                "/v1/integrations/system-of-record/stripe-payment/config",
                json={"bearer_token": "sk_test_payment_secret"},
            )
            assert saved.status_code == 200, saved.text
            saved_body = saved.json()
            assert saved_body["connected"] is True
            assert saved_body["base_url"] == "https://api.stripe.com"
            assert saved_body["connector_type"] == "stripe_payment"
            assert saved_body["has_bearer_token"] is True
            assert saved_body["bearer_token_last4"] == "cret"
            assert "sk_test_payment_secret" not in json.dumps(saved_body)

            tested = client.post(
                "/v1/integrations/system-of-record/stripe-payment/test",
                json={
                    "payment_id": "pi_123",
                    "claimed": {
                        "payment_id": "pi_123",
                        "amount_minor": 4250,
                        "currency": "USD",
                        "status": "succeeded",
                    },
                    "match_fields": [
                        "payment_id",
                        "amount_minor",
                        "currency",
                        "status",
                    ],
                },
            )
            assert tested.status_code == 201, tested.text
            body = tested.json()
            assert body["ok"] is True
            assert body["check"]["connector_type"] == "stripe_payment"
            assert body["check"]["system_ref"] == "stripe_payment:pi_123"
            assert body["check"]["actual"]["amount_minor"] == 4250
            assert body["check"]["metadata"]["connector_kind"] == "stripe_payment"
            assert body["connector"]["health_status"] == "healthy"
            assert body["connector"]["readiness"]["status"] == "ready"
            assert body["connector"]["readiness"]["contract"]["system_of_record"] == "stripe"
            assert "sk_test_payment_secret" not in json.dumps(body)
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        get_settings.cache_clear()


def test_shopify_connector_config_status_and_test_run_redact_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "PROVIDER_KEY_VAULT_KEK", "test-kek-for-shopify-connector-123456789"
    )
    get_settings.cache_clear()
    engine, session_factory = _sqlite_session_factory(tmp_path / "shopify_connector.db")
    _seed_project(session_factory, "proj_shopify")

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def override_tenant():
        return TenantContext(
            tenant_id="proj_shopify", role="admin", subject="user-shopify"
        )

    def fake_fetch(self: ShopifyAdminConnector) -> SourceRecord:
        assert self.base_url == "https://zroky-test.myshopify.com"
        assert self.path_template == "/admin/api/2025-01/orders/{record_ref}.json"
        assert self.record_path == "order"
        assert self.bearer_token == "shpat_test_shopify_secret"
        return SourceRecord(
            record={
                "record_ref": self.record_ref,
                "order_id": self.record_ref,
                "amount_major": 42.5,
                "currency": "USD",
                "financial_status": "paid",
                "status": "paid",
            },
            record_found=True,
            metadata={
                "connector_type": "shopify_admin",
                "request_url": (
                    "https://zroky-test.myshopify.com/admin/api/2025-01/"
                    f"orders/{self.record_ref}.json"
                ),
                "http_status": 200,
                "record_path": "order",
                "attempts": 1,
                "max_attempts": 2,
                "retryable": False,
                "record_ref": self.record_ref,
            },
        )

    monkeypatch.setattr(ShopifyAdminConnector, "fetch", fake_fetch)
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_db_session_read] = override_db
    app.dependency_overrides[require_tenant_context] = override_tenant

    try:
        with TestClient(app) as client:
            empty = client.get("/v1/integrations/system-of-record/shopify/status")
            assert empty.status_code == 200
            assert empty.json()["connected"] is False
            assert empty.json()["connector_type"] == "shopify_admin"
            assert empty.json()["readiness"]["status"] == "not_ready"

            saved = client.put(
                "/v1/integrations/system-of-record/shopify/config",
                json={
                    "base_url": "https://zroky-test.myshopify.com",
                    "bearer_token": "shpat_test_shopify_secret",
                },
            )
            assert saved.status_code == 200, saved.text
            saved_body = saved.json()
            assert saved_body["connected"] is True
            assert saved_body["base_url"] == "https://zroky-test.myshopify.com"
            assert saved_body["connector_type"] == "shopify_admin"
            assert saved_body["record_path"] == "order"
            assert saved_body["has_bearer_token"] is True
            assert saved_body["bearer_token_last4"] == "cret"
            assert "shpat_test_shopify_secret" not in json.dumps(saved_body)

            tested = client.post(
                "/v1/integrations/system-of-record/shopify/test",
                json={
                    "record_ref": "450789469",
                    "claimed": {
                        "record_ref": "450789469",
                        "order_id": "450789469",
                        "amount_major": 42.5,
                        "currency": "USD",
                        "status": "paid",
                    },
                    "match_fields": [
                        "record_ref",
                        "order_id",
                        "amount_major",
                        "currency",
                        "status",
                    ],
                },
            )
            assert tested.status_code == 201, tested.text
            body = tested.json()
            assert body["ok"] is True
            assert body["check"]["connector_type"] == "shopify_admin"
            assert body["check"]["system_ref"] == "shopify:450789469"
            assert body["check"]["actual"]["amount_major"] == 42.5
            assert body["check"]["metadata"]["connector_kind"] == "shopify_admin"
            assert body["connector"]["health_status"] == "healthy"
            assert body["connector"]["readiness"]["status"] == "ready"
            assert body["connector"]["readiness"]["contract"]["system_of_record"] == "shopify"
            assert "shpat_test_shopify_secret" not in json.dumps(body)
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        get_settings.cache_clear()
