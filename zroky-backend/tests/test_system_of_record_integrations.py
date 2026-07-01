from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.core.config import get_settings
from app.db.base import Base
from app.db.models import Project
from app.db.session import get_db_session, get_db_session_read
from app.main import app
from app.services.entitlements import set_override_entitlement
from app.services.outcome_reconciliation import SourceRecord
from app.services.system_of_record_connectors import (
    CustomerRecordApiConnector,
    GenericRestApiConnector,
    HubSpotCrmConnector,
    JiraIssueConnector,
    LedgerRefundApiConnector,
    NetSuiteFinanceConnector,
    PostgresReadOnlyConnector,
    RazorpayRefundConnector,
    SalesforceCrmConnector,
    StripeRefundConnector,
    ZendeskTicketConnector,
    ZohoCrmConnector,
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


def test_ledger_refund_connector_config_status_and_test_run_redact_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "PROVIDER_KEY_VAULT_KEK", "test-kek-for-sor-connectors-1234567890"
    )
    get_settings.cache_clear()
    engine, session_factory = _sqlite_session_factory(tmp_path / "sor_connector.db")
    _seed_project(session_factory, "proj_sor_connector")

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def override_tenant():
        return TenantContext(
            tenant_id="proj_sor_connector", role="admin", subject="user-sor"
        )

    def fake_fetch(self: LedgerRefundApiConnector) -> SourceRecord:
        assert self.base_url == "https://ledger.example.com/api"
        assert self.path_template == "/refunds/{refund_id}"
        assert self.record_path == "data"
        assert self.bearer_token == "ledger-secret-token"
        assert self.max_attempts == 2
        return SourceRecord(
            record={
                "refund_id": self.refund_id,
                "amount_usd": "42.50",
                "currency": "usd",
                "status": "posted",
            },
            record_found=True,
            metadata={
                "connector_type": "ledger_refund_api",
                "request_url": f"https://ledger.example.com/api/refunds/{self.refund_id}",
                "http_status": 200,
                "record_path": "data",
                "attempts": 1,
                "max_attempts": 2,
                "retryable": False,
                "refund_id": self.refund_id,
            },
        )

    monkeypatch.setattr(LedgerRefundApiConnector, "fetch", fake_fetch)
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_db_session_read] = override_db
    app.dependency_overrides[require_tenant_context] = override_tenant

    try:
        with TestClient(app) as client:
            empty = client.get("/v1/integrations/system-of-record/ledger-refund/status")
            assert empty.status_code == 200
            assert empty.json()["connected"] is False
            assert empty.json()["readiness"]["status"] == "not_ready"
            assert "connector config has not been saved" in empty.json()["readiness"][
                "blockers"
            ]

            saved = client.put(
                "/v1/integrations/system-of-record/ledger-refund/config",
                json={
                    "base_url": "https://ledger.example.com/api",
                    "path_template": "/refunds/{refund_id}",
                    "record_path": "data",
                    "bearer_token": "ledger-secret-token",
                },
            )
            assert saved.status_code == 200
            saved_body = saved.json()
            assert saved_body["connected"] is True
            assert saved_body["has_bearer_token"] is True
            assert saved_body["bearer_token_last4"] == "oken"
            assert "ledger-secret-token" not in json.dumps(saved_body)

            status = client.get(
                "/v1/integrations/system-of-record/ledger-refund/status"
            )
            assert status.status_code == 200
            assert status.json()["base_url"] == "https://ledger.example.com/api"
            assert status.json()["health_status"] == "not_verified"
            assert status.json()["readiness"]["status"] == "not_ready"
            assert "latest connector test did not reconcile as matched" in status.json()[
                "readiness"
            ]["blockers"]
            assert "ledger-secret-token" not in json.dumps(status.json())

            tested = client.post(
                "/v1/integrations/system-of-record/ledger-refund/test",
                json={
                    "refund_id": "rf_live",
                    "claimed": {
                        "refund_id": "rf_live",
                        "amount_usd": 42.5,
                        "currency": "USD",
                        "status": "posted",
                    },
                },
            )
            assert tested.status_code == 201
            body = tested.json()
            assert body["ok"] is True
            assert body["check"]["verdict"] == "matched"
            assert body["check"]["metadata"]["source"] == "saved_connector_test"
            assert body["check"]["metadata"]["connector"]["http_status"] == 200
            assert body["connector"]["health_status"] == "healthy"
            assert body["connector"]["last_verdict"] == "matched"
            assert body["connector"]["last_http_status"] == 200
            assert body["connector"]["last_error"] is None
            assert body["connector"]["last_tested_at"] is not None
            assert body["connector"]["readiness"]["status"] == "ready"
            assert body["connector"]["readiness"]["blockers"] == []
            assert body["connector"]["readiness"]["contract"]["system_of_record"] == (
                "ledger_refund"
            )
            assert "ledger-secret-token" not in json.dumps(body)
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        get_settings.cache_clear()


def test_stripe_refund_connector_config_status_and_test_run_redact_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "PROVIDER_KEY_VAULT_KEK", "test-kek-for-stripe-connectors-1234567890"
    )
    get_settings.cache_clear()
    engine, session_factory = _sqlite_session_factory(tmp_path / "stripe_connector.db")
    _seed_project(session_factory, "proj_stripe_refund")

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def override_tenant():
        return TenantContext(
            tenant_id="proj_stripe_refund", role="admin", subject="user-stripe"
        )

    def fake_fetch(self: StripeRefundConnector) -> SourceRecord:
        assert self.base_url == "https://api.stripe.com"
        assert self.path_template == "/v1/refunds/{refund_id}"
        assert self.bearer_token == "sk_test_stripe_secret"
        return SourceRecord(
            record={
                "id": self.refund_id,
                "refund_id": self.refund_id,
                "stripe_refund_id": self.refund_id,
                "object": "refund",
                "amount": 4250,
                "amount_usd": 42.5,
                "currency": "usd",
                "status": "succeeded",
                "charge": "ch_123",
                "charge_id": "ch_123",
            },
            record_found=True,
            metadata={
                "connector_type": "stripe_refund",
                "request_url": "https://api.stripe.com/v1/refunds/re_123",
                "http_status": 200,
                "attempts": 1,
                "max_attempts": 2,
                "retryable": False,
                "refund_id": self.refund_id,
                "stripe_object": "refund",
            },
        )

    monkeypatch.setattr(StripeRefundConnector, "fetch", fake_fetch)
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_db_session_read] = override_db
    app.dependency_overrides[require_tenant_context] = override_tenant

    try:
        with TestClient(app) as client:
            empty = client.get("/v1/integrations/system-of-record/stripe-refund/status")
            assert empty.status_code == 200
            assert empty.json()["connected"] is False
            assert empty.json()["connector_type"] == "stripe_refund"
            assert empty.json()["readiness"]["status"] == "not_ready"

            saved = client.put(
                "/v1/integrations/system-of-record/stripe-refund/config",
                json={"bearer_token": "sk_test_stripe_secret"},
            )
            assert saved.status_code == 200, saved.text
            saved_body = saved.json()
            assert saved_body["connected"] is True
            assert saved_body["base_url"] == "https://api.stripe.com"
            assert saved_body["connector_type"] == "stripe_refund"
            assert saved_body["has_bearer_token"] is True
            assert saved_body["bearer_token_last4"] == "cret"
            assert "sk_test_stripe_secret" not in json.dumps(saved_body)

            tested = client.post(
                "/v1/integrations/system-of-record/stripe-refund/test",
                json={
                    "refund_id": "re_123",
                    "claimed": {
                        "refund_id": "re_123",
                        "amount_usd": 42.5,
                        "currency": "USD",
                        "status": "succeeded",
                    },
                    "match_fields": ["refund_id", "amount_usd", "currency", "status"],
                },
            )
            assert tested.status_code == 201, tested.text
            body = tested.json()
            assert body["ok"] is True
            assert body["check"]["connector_type"] == "stripe_refund"
            assert body["check"]["system_ref"] == "stripe:refund:re_123"
            assert body["check"]["actual"]["amount_usd"] == 42.5
            assert body["check"]["metadata"]["connector_kind"] == "stripe_refund"
            assert body["connector"]["health_status"] == "healthy"
            assert body["connector"]["readiness"]["status"] == "ready"
            assert body["connector"]["readiness"]["contract"]["system_of_record"] == "stripe"
            assert "sk_test_stripe_secret" not in json.dumps(body)
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        get_settings.cache_clear()


def test_razorpay_refund_connector_config_status_and_test_run_redact_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "PROVIDER_KEY_VAULT_KEK", "test-kek-for-razorpay-connectors-123456"
    )
    get_settings.cache_clear()
    engine, session_factory = _sqlite_session_factory(tmp_path / "razorpay_connector.db")
    _seed_project(session_factory, "proj_razorpay_refund")

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def override_tenant():
        return TenantContext(
            tenant_id="proj_razorpay_refund", role="admin", subject="user-razorpay"
        )

    def fake_fetch(self: RazorpayRefundConnector) -> SourceRecord:
        assert self.base_url == "https://api.razorpay.com"
        assert self.path_template == "/v1/refunds/{refund_id}"
        assert self.key_id == "rzp_test_key"
        assert self.key_secret == "razorpay-secret"
        assert self.refund_id == "rfnd_123"
        return SourceRecord(
            record={
                "id": self.refund_id,
                "refund_id": self.refund_id,
                "razorpay_refund_id": self.refund_id,
                "payment_id": "pay_123",
                "razorpay_payment_id": "pay_123",
                "amount": 4250,
                "amount_minor": 4250,
                "amount_major": "42.5",
                "currency": "INR",
                "status": "processed",
                "receipt": "rcpt_123",
            },
            record_found=True,
            metadata={
                "connector_type": "razorpay_refund",
                "request_url": "https://api.razorpay.com/v1/refunds/rfnd_123",
                "http_status": 200,
                "attempts": 1,
                "max_attempts": 2,
                "retryable": False,
                "refund_id": self.refund_id,
                "razorpay_object": "refund",
            },
        )

    monkeypatch.setattr(RazorpayRefundConnector, "fetch", fake_fetch)
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_db_session_read] = override_db
    app.dependency_overrides[require_tenant_context] = override_tenant

    try:
        with TestClient(app) as client:
            empty = client.get("/v1/integrations/system-of-record/razorpay-refund/status")
            assert empty.status_code == 200
            assert empty.json()["connected"] is False
            assert empty.json()["connector_type"] == "razorpay_refund"
            assert empty.json()["readiness"]["status"] == "not_ready"

            saved = client.put(
                "/v1/integrations/system-of-record/razorpay-refund/config",
                json={
                    "key_id": "rzp_test_key",
                    "key_secret": "razorpay-secret",
                },
            )
            assert saved.status_code == 200, saved.text
            saved_body = saved.json()
            assert saved_body["connected"] is True
            assert saved_body["base_url"] == "https://api.razorpay.com"
            assert saved_body["connector_type"] == "razorpay_refund"
            assert saved_body["has_bearer_token"] is True
            assert saved_body["bearer_token_last4"] == "cret"
            assert saved_body["query"]["key_id"] == "rzp_test_key"
            assert "razorpay-secret" not in json.dumps(saved_body)

            tested = client.post(
                "/v1/integrations/system-of-record/razorpay-refund/test",
                json={
                    "refund_id": "rfnd_123",
                    "claimed": {
                        "refund_id": "rfnd_123",
                        "amount_minor": 4250,
                        "amount_major": "42.5",
                        "currency": "INR",
                        "status": "processed",
                    },
                    "match_fields": ["refund_id", "amount_minor", "currency", "status"],
                },
            )
            assert tested.status_code == 201, tested.text
            body = tested.json()
            assert body["ok"] is True
            assert body["check"]["connector_type"] == "razorpay_refund"
            assert body["check"]["system_ref"] == "razorpay:refund:rfnd_123"
            assert body["check"]["actual"]["amount_minor"] == 4250
            assert body["check"]["metadata"]["connector_kind"] == "razorpay_refund"
            assert body["connector"]["health_status"] == "healthy"
            assert body["connector"]["readiness"]["status"] == "ready"
            assert body["connector"]["readiness"]["contract"]["system_of_record"] == "razorpay"
            assert "razorpay-secret" not in json.dumps(body)
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        get_settings.cache_clear()


def test_netsuite_finance_connector_config_status_and_test_run_redact_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "PROVIDER_KEY_VAULT_KEK", "test-kek-for-netsuite-connectors-123456"
    )
    get_settings.cache_clear()
    engine, session_factory = _sqlite_session_factory(tmp_path / "netsuite_connector.db")
    _seed_project(session_factory, "proj_netsuite_finance")

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def override_tenant():
        return TenantContext(
            tenant_id="proj_netsuite_finance", role="admin", subject="user-netsuite"
        )

    def fake_fetch(self: NetSuiteFinanceConnector) -> SourceRecord:
        assert self.base_url == "https://example.suitetalk.api.netsuite.com"
        assert self.path_template == "/services/rest/record/v1/{record_type}/{record_ref}"
        assert self.bearer_token == "netsuite-token-secret"
        assert self.record_type == "vendorBill"
        assert self.record_ref == "12345"
        return SourceRecord(
            record={
                "id": self.record_ref,
                "netsuite_record_id": self.record_ref,
                "record_ref": self.record_ref,
                "record_type": self.record_type,
                "tran_id": "VB1001",
                "amount_minor": 125000,
                "amount_major": "1250",
                "currency": "USD",
                "status": "approved",
                "entity_id": "vendor_1",
            },
            record_found=True,
            metadata={
                "connector_type": "netsuite_finance",
                "request_url": (
                    "https://example.suitetalk.api.netsuite.com/services/rest/"
                    f"record/v1/{self.record_type}/{self.record_ref}"
                ),
                "http_status": 200,
                "attempts": 1,
                "max_attempts": 2,
                "retryable": False,
                "record_type": self.record_type,
                "record_ref": self.record_ref,
            },
        )

    monkeypatch.setattr(NetSuiteFinanceConnector, "fetch", fake_fetch)
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_db_session_read] = override_db
    app.dependency_overrides[require_tenant_context] = override_tenant

    try:
        with TestClient(app) as client:
            empty = client.get("/v1/integrations/system-of-record/netsuite-finance/status")
            assert empty.status_code == 200
            assert empty.json()["connected"] is False
            assert empty.json()["connector_type"] == "netsuite_finance"
            assert empty.json()["readiness"]["status"] == "not_ready"

            saved = client.put(
                "/v1/integrations/system-of-record/netsuite-finance/config",
                json={
                    "base_url": "https://example.suitetalk.api.netsuite.com",
                    "bearer_token": "netsuite-token-secret",
                },
            )
            assert saved.status_code == 200, saved.text
            saved_body = saved.json()
            assert saved_body["connected"] is True
            assert saved_body["base_url"] == "https://example.suitetalk.api.netsuite.com"
            assert saved_body["connector_type"] == "netsuite_finance"
            assert saved_body["has_bearer_token"] is True
            assert saved_body["bearer_token_last4"] == "cret"
            assert "netsuite-token-secret" not in json.dumps(saved_body)

            tested = client.post(
                "/v1/integrations/system-of-record/netsuite-finance/test",
                json={
                    "record_type": "vendorBill",
                    "record_ref": "12345",
                    "claimed": {
                        "netsuite_record_id": "12345",
                        "record_type": "vendorBill",
                        "tran_id": "VB1001",
                        "amount_minor": 125000,
                        "amount_major": "1250",
                        "currency": "USD",
                        "status": "approved",
                    },
                    "match_fields": [
                        "netsuite_record_id",
                        "record_type",
                        "tran_id",
                        "amount_minor",
                        "currency",
                        "status",
                    ],
                },
            )
            assert tested.status_code == 201, tested.text
            body = tested.json()
            assert body["ok"] is True
            assert body["check"]["connector_type"] == "netsuite_finance"
            assert body["check"]["system_ref"] == "netsuite:vendorBill:12345"
            assert body["check"]["actual"]["amount_minor"] == 125000
            assert body["check"]["metadata"]["connector_kind"] == "netsuite_finance"
            assert body["connector"]["health_status"] == "healthy"
            assert body["connector"]["readiness"]["status"] == "ready"
            assert body["connector"]["readiness"]["contract"]["system_of_record"] == "netsuite"
            assert "netsuite-token-secret" not in json.dumps(body)
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        get_settings.cache_clear()


def test_system_of_record_connector_quota_blocks_second_active_connector(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "PROVIDER_KEY_VAULT_KEK", "test-kek-for-sor-quota-1234567890"
    )
    monkeypatch.setenv("BILLING_ENFORCE_QUOTA", "true")
    get_settings.cache_clear()
    engine, session_factory = _sqlite_session_factory(tmp_path / "sor_connector_quota.db")
    project_id = "proj_sor_connector_quota"
    _seed_project(session_factory, project_id)
    with session_factory() as session:
        set_override_entitlement(
            session,
            org_id=project_id,
            key="connectors.system_of_record.max",
            value=1,
        )

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def override_tenant():
        return TenantContext(
            tenant_id=project_id,
            role="admin",
            subject="user-sor-quota",
        )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_db_session_read] = override_db
    app.dependency_overrides[require_tenant_context] = override_tenant

    try:
        with TestClient(app) as client:
            first = client.put(
                "/v1/integrations/system-of-record/ledger-refund/config",
                json={
                    "base_url": "https://ledger.example.com/api",
                    "path_template": "/refunds/{refund_id}",
                    "bearer_token": "ledger-secret-token",
                },
            )
            assert first.status_code == 200, first.text

            blocked = client.put(
                "/v1/integrations/system-of-record/customer-record/config",
                json={
                    "base_url": "https://crm.example.com/api",
                    "path_template": "/customers/{customer_id}",
                    "bearer_token": "crm-secret-token",
                },
            )
            assert blocked.status_code == 402, blocked.text
            detail = blocked.json()["detail"]
            assert detail["code"] == "protected_action_quota_exceeded"
            assert detail["meter_key"] == "active_connectors"
            assert detail["entitlement_key"] == "connectors.system_of_record.max"
            assert detail["used"] == 1
            assert detail["limit"] == 1
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        get_settings.cache_clear()


def test_generic_rest_connector_config_status_and_test_run_redact_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "PROVIDER_KEY_VAULT_KEK", "test-kek-for-generic-rest-connectors-123456"
    )
    get_settings.cache_clear()
    engine, session_factory = _sqlite_session_factory(tmp_path / "generic_rest_connector.db")
    _seed_project(session_factory, "proj_generic_rest")

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def override_tenant():
        return TenantContext(
            tenant_id="proj_generic_rest", role="admin", subject="user-generic"
        )

    def fake_fetch(self: GenericRestApiConnector) -> SourceRecord:
        assert self.base_url == "https://internal.example.com/api"
        assert self.path_template == "/orders/{record_ref}"
        assert self.record_path == "data"
        assert self.bearer_token == "generic-secret-token"
        return SourceRecord(
            record={
                "record_ref": self.record_ref,
                "status": "approved",
                "total_usd": 118.42,
            },
            record_found=True,
            metadata={
                "connector_type": "generic_rest_api",
                "request_url": f"https://internal.example.com/api/orders/{self.record_ref}",
                "http_status": 200,
                "record_path": "data",
                "attempts": 1,
                "max_attempts": 2,
                "retryable": False,
                "record_ref": self.record_ref,
            },
        )

    monkeypatch.setattr(GenericRestApiConnector, "fetch", fake_fetch)
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_db_session_read] = override_db
    app.dependency_overrides[require_tenant_context] = override_tenant

    try:
        with TestClient(app) as client:
            empty = client.get("/v1/integrations/system-of-record/generic-rest/status")
            assert empty.status_code == 200
            assert empty.json()["connected"] is False
            assert empty.json()["connector_type"] == "generic_rest_api"
            assert empty.json()["readiness"]["status"] == "not_ready"

            saved = client.put(
                "/v1/integrations/system-of-record/generic-rest/config",
                json={
                    "base_url": "https://internal.example.com/api",
                    "path_template": "/orders/{record_ref}",
                    "record_path": "data",
                    "bearer_token": "generic-secret-token",
                },
            )
            assert saved.status_code == 200
            saved_body = saved.json()
            assert saved_body["connected"] is True
            assert saved_body["connector_type"] == "generic_rest_api"
            assert saved_body["has_bearer_token"] is True
            assert "generic-secret-token" not in json.dumps(saved_body)

            tested = client.post(
                "/v1/integrations/system-of-record/generic-rest/test",
                json={
                    "record_ref": "ord_1001",
                    "claimed": {
                        "record_ref": "ord_1001",
                        "status": "approved",
                        "total_usd": 118.42,
                    },
                    "action_type": "internal_api_mutation",
                    "match_fields": ["status", "total_usd"],
                },
            )
            assert tested.status_code == 201
            body = tested.json()
            assert body["ok"] is True
            assert body["check"]["connector_type"] == "generic_rest_api"
            assert body["check"]["system_ref"] == "generic:ord_1001"
            assert body["check"]["verdict"] == "matched"
            assert body["check"]["metadata"]["connector_kind"] == "generic_rest_api"
            assert body["connector"]["health_status"] == "healthy"
            assert body["connector"]["readiness"]["status"] == "ready"
            assert "generic-secret-token" not in json.dumps(body)
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        get_settings.cache_clear()


def test_postgres_read_connector_config_status_and_test_run_redact_dsn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "PROVIDER_KEY_VAULT_KEK", "test-kek-for-postgres-read-connectors-123456"
    )
    get_settings.cache_clear()
    engine, session_factory = _sqlite_session_factory(tmp_path / "postgres_read_connector.db")
    _seed_project(session_factory, "proj_postgres_read_connector")

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def override_tenant():
        return TenantContext(
            tenant_id="proj_postgres_read_connector",
            role="admin",
            subject="user-postgres-read",
        )

    def fake_fetch(self: PostgresReadOnlyConnector) -> SourceRecord:
        assert self.database_url == (
            "postgresql://readonly:pg-secret@db.example.com/app"
        )
        assert self.query == (
            "SELECT ticket_id, status FROM tickets WHERE ticket_id = :ticket_id"
        )
        assert self.params == {"ticket_id": "t_1001"}
        return SourceRecord(
            record={"ticket_id": "t_1001", "status": "closed"},
            record_found=True,
            metadata={
                "connector_type": "postgres_read",
                "adapter": "postgresql_readonly",
                "database_host": "db.example.com",
                "query_digest": "test-query-digest",
                "read_only": True,
                "record_found": True,
                "attempts": 1,
                "retryable": False,
            },
        )

    monkeypatch.setattr(PostgresReadOnlyConnector, "fetch", fake_fetch)
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_db_session_read] = override_db
    app.dependency_overrides[require_tenant_context] = override_tenant

    try:
        with TestClient(app) as client:
            empty = client.get("/v1/integrations/system-of-record/postgres-read/status")
            assert empty.status_code == 200
            assert empty.json()["connected"] is False
            assert empty.json()["connector_type"] == "postgres_read"
            assert empty.json()["readiness"]["status"] == "not_ready"

            saved = client.put(
                "/v1/integrations/system-of-record/postgres-read/config",
                json={
                    "database_url": (
                        "postgresql://readonly:pg-secret@db.example.com/app"
                    ),
                    "read_query": (
                        "SELECT ticket_id, status FROM tickets "
                        "WHERE ticket_id = :ticket_id"
                    ),
                },
            )
            assert saved.status_code == 200, saved.text
            saved_body = saved.json()
            assert saved_body["connected"] is True
            assert saved_body["connector_type"] == "postgres_read"
            assert saved_body["base_url"] == "postgresql://db.example.com/app"
            assert saved_body["has_database_url"] is True
            assert saved_body["database_url_last4"] == "/app"
            assert saved_body["has_read_query"] is True
            assert saved_body["read_query_digest"]
            assert saved_body["has_bearer_token"] is False
            assert saved_body["readiness"]["status"] == "not_ready"
            assert "pg-secret" not in json.dumps(saved_body)
            assert "SELECT ticket_id" not in json.dumps(saved_body)

            tested = client.post(
                "/v1/integrations/system-of-record/postgres-read/test",
                json={
                    "claimed": {"ticket_id": "t_1001", "status": "closed"},
                    "params": {"ticket_id": "t_1001"},
                    "action_type": "ticket_update",
                    "system_ref": "postgres:tickets:t_1001",
                },
            )
            assert tested.status_code == 201, tested.text
            body = tested.json()
            assert body["ok"] is True
            assert body["check"]["connector_type"] == "postgres_read"
            assert body["check"]["system_ref"] == "postgres:tickets:t_1001"
            assert body["check"]["verdict"] == "matched"
            assert body["check"]["metadata"]["source"] == "saved_connector_test"
            assert body["check"]["metadata"]["connector"]["read_only"] is True
            assert body["connector"]["health_status"] == "healthy"
            assert body["connector"]["last_verdict"] == "matched"
            assert body["connector"]["last_http_status"] is None
            assert body["connector"]["readiness"]["status"] == "ready"
            assert body["connector"]["readiness"]["blockers"] == []
            assert body["connector"]["readiness"]["contract"]["adapter"] == (
                "postgresql_readonly"
            )
            assert "pg-secret" not in json.dumps(body)
            assert "SELECT ticket_id" not in json.dumps(body)
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        get_settings.cache_clear()


def test_customer_record_connector_config_status_and_test_run_redact_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "PROVIDER_KEY_VAULT_KEK", "test-kek-for-sor-connectors-1234567890"
    )
    get_settings.cache_clear()
    engine, session_factory = _sqlite_session_factory(tmp_path / "sor_crm_connector.db")
    _seed_project(session_factory, "proj_sor_crm")

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def override_tenant():
        return TenantContext(tenant_id="proj_sor_crm", role="admin", subject="user-sor")

    def fake_fetch(self: CustomerRecordApiConnector) -> SourceRecord:
        assert self.base_url == "https://crm.example.com/api"
        assert self.path_template == "/customers/{customer_id}"
        assert self.record_path == "data"
        assert self.bearer_token == "crm-secret-token"
        assert self.max_attempts == 2
        return SourceRecord(
            record={
                "customer_id": self.customer_id,
                "email": "owner@example.com",
                "status": "active",
                "account_id": "acct_1001",
            },
            record_found=True,
            metadata={
                "connector_type": "customer_record_api",
                "request_url": f"https://crm.example.com/api/customers/{self.customer_id}",
                "http_status": 200,
                "record_path": "data",
                "attempts": 1,
                "max_attempts": 2,
                "retryable": False,
                "customer_id": self.customer_id,
            },
        )

    monkeypatch.setattr(CustomerRecordApiConnector, "fetch", fake_fetch)
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_db_session_read] = override_db
    app.dependency_overrides[require_tenant_context] = override_tenant

    try:
        with TestClient(app) as client:
            empty = client.get(
                "/v1/integrations/system-of-record/customer-record/status"
            )
            assert empty.status_code == 200
            assert empty.json()["connected"] is False
            assert empty.json()["connector_type"] == "customer_record_api"
            assert empty.json()["readiness"]["status"] == "not_ready"

            saved = client.put(
                "/v1/integrations/system-of-record/customer-record/config",
                json={
                    "base_url": "https://crm.example.com/api",
                    "path_template": "/customers/{customer_id}",
                    "record_path": "data",
                    "bearer_token": "crm-secret-token",
                },
            )
            assert saved.status_code == 200
            saved_body = saved.json()
            assert saved_body["connected"] is True
            assert saved_body["has_bearer_token"] is True
            assert saved_body["bearer_token_last4"] == "oken"
            assert "crm-secret-token" not in json.dumps(saved_body)

            tested = client.post(
                "/v1/integrations/system-of-record/customer-record/test",
                json={
                    "customer_id": "cus_1001",
                    "claimed": {
                        "customer_id": "cus_1001",
                        "email": "owner@example.com",
                        "status": "active",
                        "account_id": "acct_1001",
                    },
                },
            )
            assert tested.status_code == 201
            body = tested.json()
            assert body["ok"] is True
            assert body["check"]["verdict"] == "matched"
            assert body["check"]["system_ref"] == "crm:cus_1001"
            assert body["check"]["metadata"]["source"] == "saved_connector_test"
            assert body["check"]["metadata"]["connector"]["http_status"] == 200
            assert body["connector"]["health_status"] == "healthy"
            assert body["connector"]["last_verdict"] == "matched"
            assert body["connector"]["last_http_status"] == 200
            assert body["connector"]["last_tested_at"] is not None
            assert body["connector"]["readiness"]["status"] == "ready"
            assert body["connector"]["readiness"]["blockers"] == []
            assert body["connector"]["readiness"]["contract"]["system_of_record"] == (
                "customer_record"
            )
            assert "crm-secret-token" not in json.dumps(body)
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        get_settings.cache_clear()


def test_hubspot_crm_connector_config_status_and_test_run_redact_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "PROVIDER_KEY_VAULT_KEK", "test-kek-for-hubspot-connectors-1234567890"
    )
    get_settings.cache_clear()
    engine, session_factory = _sqlite_session_factory(tmp_path / "hubspot_connector.db")
    _seed_project(session_factory, "proj_hubspot_crm")

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def override_tenant():
        return TenantContext(
            tenant_id="proj_hubspot_crm", role="admin", subject="user-hubspot"
        )

    def fake_fetch(self: HubSpotCrmConnector) -> SourceRecord:
        assert self.base_url == "https://api.hubapi.com"
        assert self.path_template == "/crm/v3/objects/contacts/{record_ref}"
        assert self.bearer_token == "hubspot-private-app-token"
        assert self.query is not None
        assert self.query["idProperty"] == "email"
        return SourceRecord(
            record={
                "id": "12345",
                "properties": {
                    "email": self.record_ref,
                    "firstname": "Ada",
                    "lifecyclestage": "customer",
                    "hs_object_id": "12345",
                },
                "archived": False,
            },
            record_found=True,
            metadata={
                "connector_type": "hubspot_crm",
                "request_url": (
                    "https://api.hubapi.com/crm/v3/objects/contacts/"
                    f"{self.record_ref}"
                ),
                "http_status": 200,
                "attempts": 1,
                "max_attempts": 2,
                "retryable": False,
                "record_ref": self.record_ref,
                "hubspot_object": "contacts",
                "id_property": "email",
            },
        )

    monkeypatch.setattr(HubSpotCrmConnector, "fetch", fake_fetch)
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_db_session_read] = override_db
    app.dependency_overrides[require_tenant_context] = override_tenant

    try:
        with TestClient(app) as client:
            empty = client.get("/v1/integrations/system-of-record/hubspot-crm/status")
            assert empty.status_code == 200
            assert empty.json()["connected"] is False
            assert empty.json()["connector_type"] == "hubspot_crm"
            assert empty.json()["readiness"]["status"] == "not_ready"

            saved = client.put(
                "/v1/integrations/system-of-record/hubspot-crm/config",
                json={
                    "query": {
                        "properties": "email,firstname,lifecyclestage,hs_object_id",
                        "idProperty": "email",
                    },
                    "bearer_token": "hubspot-private-app-token",
                },
            )
            assert saved.status_code == 200
            saved_body = saved.json()
            assert saved_body["connected"] is True
            assert saved_body["base_url"] == "https://api.hubapi.com"
            assert saved_body["connector_type"] == "hubspot_crm"
            assert saved_body["query"]["idProperty"] == "email"
            assert saved_body["has_bearer_token"] is True
            assert saved_body["bearer_token_last4"] == "oken"
            assert "hubspot-private-app-token" not in json.dumps(saved_body)

            tested = client.post(
                "/v1/integrations/system-of-record/hubspot-crm/test",
                json={
                    "record_ref": "owner@example.com",
                    "claimed": {
                        "email": "owner@example.com",
                        "firstname": "Ada",
                        "lifecyclestage": "customer",
                    },
                    "match_fields": ["email", "firstname", "lifecyclestage"],
                },
            )
            assert tested.status_code == 201
            body = tested.json()
            assert body["ok"] is True
            assert body["check"]["connector_type"] == "hubspot_crm"
            assert body["check"]["system_ref"] == "hubspot:contact:owner@example.com"
            assert body["check"]["verdict"] == "matched"
            assert body["check"]["metadata"]["connector_kind"] == "hubspot_crm"
            assert body["check"]["metadata"]["connector"]["http_status"] == 200
            assert body["connector"]["health_status"] == "healthy"
            assert body["connector"]["readiness"]["status"] == "ready"
            assert body["connector"]["readiness"]["contract"]["oauth_status"] == "planned"
            assert "hubspot-private-app-token" not in json.dumps(body)
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        get_settings.cache_clear()


def test_salesforce_crm_connector_config_status_and_test_run_redact_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "PROVIDER_KEY_VAULT_KEK", "test-kek-for-salesforce-connectors-1234567890"
    )
    get_settings.cache_clear()
    engine, session_factory = _sqlite_session_factory(tmp_path / "salesforce_connector.db")
    _seed_project(session_factory, "proj_salesforce_crm")

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def override_tenant():
        return TenantContext(
            tenant_id="proj_salesforce_crm", role="admin", subject="user-salesforce"
        )

    def fake_fetch(self: SalesforceCrmConnector) -> SourceRecord:
        assert self.base_url == "https://example.my.salesforce.com"
        assert self.path_template == "/services/data/v60.0/sobjects/{object_type}/{record_ref}"
        assert self.object_type == "Account"
        assert self.record_ref == "001000000000000AAA"
        assert self.bearer_token == "salesforce-bearer-token"
        assert self.query is not None
        assert self.query["fields"] == "Id,Name,Status"
        return SourceRecord(
            record={
                "Id": self.record_ref,
                "salesforce_id": self.record_ref,
                "record_ref": self.record_ref,
                "object_type": "Account",
                "Name": "Acme",
                "Status": "Active",
            },
            record_found=True,
            metadata={
                "connector_type": "salesforce_crm",
                "request_url": (
                    "https://example.my.salesforce.com/services/data/v60.0/"
                    f"sobjects/Account/{self.record_ref}"
                ),
                "http_status": 200,
                "attempts": 1,
                "max_attempts": 2,
                "retryable": False,
                "record_ref": self.record_ref,
                "salesforce_object": "Account",
            },
        )

    monkeypatch.setattr(SalesforceCrmConnector, "fetch", fake_fetch)
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_db_session_read] = override_db
    app.dependency_overrides[require_tenant_context] = override_tenant

    try:
        with TestClient(app) as client:
            empty = client.get("/v1/integrations/system-of-record/salesforce-crm/status")
            assert empty.status_code == 200
            assert empty.json()["connected"] is False
            assert empty.json()["connector_type"] == "salesforce_crm"
            assert empty.json()["readiness"]["status"] == "not_ready"

            saved = client.put(
                "/v1/integrations/system-of-record/salesforce-crm/config",
                json={
                    "base_url": "https://example.my.salesforce.com",
                    "query": {"fields": "Id,Name,Status"},
                    "bearer_token": "salesforce-bearer-token",
                },
            )
            assert saved.status_code == 200
            saved_body = saved.json()
            assert saved_body["connected"] is True
            assert saved_body["base_url"] == "https://example.my.salesforce.com"
            assert saved_body["connector_type"] == "salesforce_crm"
            assert saved_body["query"]["fields"] == "Id,Name,Status"
            assert saved_body["has_bearer_token"] is True
            assert saved_body["bearer_token_last4"] == "oken"
            assert "salesforce-bearer-token" not in json.dumps(saved_body)

            tested = client.post(
                "/v1/integrations/system-of-record/salesforce-crm/test",
                json={
                    "object_type": "Account",
                    "record_ref": "001000000000000AAA",
                    "claimed": {
                        "salesforce_id": "001000000000000AAA",
                        "Name": "Acme",
                        "Status": "Active",
                    },
                    "match_fields": ["salesforce_id", "Name", "Status"],
                },
            )
            assert tested.status_code == 201
            body = tested.json()
            assert body["ok"] is True
            assert body["check"]["connector_type"] == "salesforce_crm"
            assert body["check"]["system_ref"] == "salesforce:Account:001000000000000AAA"
            assert body["check"]["verdict"] == "matched"
            assert body["check"]["metadata"]["connector_kind"] == "salesforce_crm"
            assert body["check"]["metadata"]["object_type"] == "Account"
            assert body["check"]["metadata"]["connector"]["http_status"] == 200
            assert body["connector"]["health_status"] == "healthy"
            assert body["connector"]["readiness"]["status"] == "ready"
            assert body["connector"]["readiness"]["contract"]["oauth_status"] == "planned"
            assert "salesforce-bearer-token" not in json.dumps(body)
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        get_settings.cache_clear()

def test_zoho_crm_connector_config_status_and_test_run_redact_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "PROVIDER_KEY_VAULT_KEK", "test-kek-for-zoho-connectors-1234567890"
    )
    get_settings.cache_clear()
    engine, session_factory = _sqlite_session_factory(tmp_path / "zoho_connector.db")
    _seed_project(session_factory, "proj_zoho_crm")

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def override_tenant():
        return TenantContext(
            tenant_id="proj_zoho_crm", role="admin", subject="user-zoho"
        )

    def fake_fetch(self: ZohoCrmConnector) -> SourceRecord:
        assert self.base_url == "https://www.zohoapis.com"
        assert self.path_template == "/crm/v8/{module_name}/{record_ref}"
        assert self.module_name == "Contacts"
        assert self.record_ref == "1234567890000000001"
        assert self.bearer_token == "zoho-bearer-token"
        assert self.query is not None
        assert self.query["fields"] == "id,Full_Name,Email"
        return SourceRecord(
            record={
                "id": self.record_ref,
                "zoho_record_id": self.record_ref,
                "record_ref": self.record_ref,
                "module_name": "Contacts",
                "Full_Name": "Owner Example",
                "Email": "owner@example.com",
            },
            record_found=True,
            metadata={
                "connector_type": "zoho_crm",
                "request_url": (
                    "https://www.zohoapis.com/crm/v8/"
                    f"Contacts/{self.record_ref}"
                ),
                "http_status": 200,
                "attempts": 1,
                "max_attempts": 2,
                "retryable": False,
                "record_ref": self.record_ref,
                "zoho_module": "Contacts",
            },
        )

    monkeypatch.setattr(ZohoCrmConnector, "fetch", fake_fetch)
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_db_session_read] = override_db
    app.dependency_overrides[require_tenant_context] = override_tenant

    try:
        with TestClient(app) as client:
            empty = client.get("/v1/integrations/system-of-record/zoho-crm/status")
            assert empty.status_code == 200
            assert empty.json()["connected"] is False
            assert empty.json()["connector_type"] == "zoho_crm"
            assert empty.json()["readiness"]["status"] == "not_ready"

            saved = client.put(
                "/v1/integrations/system-of-record/zoho-crm/config",
                json={
                    "base_url": "https://www.zohoapis.com",
                    "query": {"fields": "id,Full_Name,Email"},
                    "bearer_token": "zoho-bearer-token",
                },
            )
            assert saved.status_code == 200
            saved_body = saved.json()
            assert saved_body["connected"] is True
            assert saved_body["base_url"] == "https://www.zohoapis.com"
            assert saved_body["connector_type"] == "zoho_crm"
            assert saved_body["query"]["fields"] == "id,Full_Name,Email"
            assert saved_body["has_bearer_token"] is True
            assert saved_body["bearer_token_last4"] == "oken"
            assert "zoho-bearer-token" not in json.dumps(saved_body)

            tested = client.post(
                "/v1/integrations/system-of-record/zoho-crm/test",
                json={
                    "module_name": "Contacts",
                    "record_ref": "1234567890000000001",
                    "claimed": {
                        "zoho_record_id": "1234567890000000001",
                        "Full_Name": "Owner Example",
                        "Email": "owner@example.com",
                    },
                    "match_fields": ["zoho_record_id", "Full_Name", "Email"],
                },
            )
            assert tested.status_code == 201
            body = tested.json()
            assert body["ok"] is True
            assert body["check"]["connector_type"] == "zoho_crm"
            assert body["check"]["system_ref"] == "zoho:Contacts:1234567890000000001"
            assert body["check"]["verdict"] == "matched"
            assert body["check"]["metadata"]["connector_kind"] == "zoho_crm"
            assert body["check"]["metadata"]["module_name"] == "Contacts"
            assert body["check"]["metadata"]["connector"]["http_status"] == 200
            assert body["connector"]["health_status"] == "healthy"
            assert body["connector"]["readiness"]["status"] == "ready"
            assert body["connector"]["readiness"]["contract"]["oauth_status"] == "available"
            assert "zoho-bearer-token" not in json.dumps(body)
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        get_settings.cache_clear()


def test_zoho_crm_oauth_start_and_callback_store_refresh_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "PROVIDER_KEY_VAULT_KEK", "test-kek-for-zoho-oauth-connectors-1234567890"
    )
    monkeypatch.setenv("OAUTH_STATE_SECRET", "test-oauth-state-secret")
    monkeypatch.setenv("ZOHO_CLIENT_ID", "zoho-client-id")
    monkeypatch.setenv("ZOHO_CLIENT_SECRET", "zoho-client-secret")
    monkeypatch.setenv(
        "ZOHO_OAUTH_REDIRECT_URL",
        "http://testserver/v1/integrations/system-of-record/zoho-crm/oauth/callback",
    )
    monkeypatch.setenv("ZOHO_ACCOUNTS_BASE_URL", "https://accounts.zoho.in")
    monkeypatch.setenv("FRONTEND_URL", "http://localhost:3000")
    get_settings.cache_clear()
    engine, session_factory = _sqlite_session_factory(tmp_path / "zoho_oauth.db")
    _seed_project(session_factory, "proj_zoho_oauth")

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def override_tenant():
        return TenantContext(
            tenant_id="proj_zoho_oauth", role="admin", subject="user-zoho-oauth"
        )

    def fake_exchange_zoho_code(*, code: str, settings) -> dict[str, str]:
        assert code == "auth-code"
        assert settings.ZOHO_CLIENT_ID == "zoho-client-id"
        return {
            "access_token": "zoho-access-token",
            "refresh_token": "zoho-refresh-token",
            "api_domain": "https://www.zohoapis.in",
        }

    monkeypatch.setattr(
        "app.api.routes.system_of_record_integrations.exchange_zoho_code",
        fake_exchange_zoho_code,
    )
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_db_session_read] = override_db
    app.dependency_overrides[require_tenant_context] = override_tenant

    try:
        with TestClient(app) as client:
            started = client.get(
                "/v1/integrations/system-of-record/zoho-crm/oauth/start"
            )
            assert started.status_code == 200
            authorization_url = started.json()["authorization_url"]
            parsed = urlparse(authorization_url)
            query = parse_qs(parsed.query)
            assert parsed.scheme == "https"
            assert parsed.netloc == "accounts.zoho.in"
            assert parsed.path == "/oauth/v2/auth"
            assert query["client_id"] == ["zoho-client-id"]
            assert query["scope"] == ["ZohoCRM.modules.READ"]
            assert query["access_type"] == ["offline"]
            assert query["prompt"] == ["consent"]
            state = query["state"][0]

            completed = client.get(
                "/v1/integrations/system-of-record/zoho-crm/oauth/callback",
                params={"code": "auth-code", "state": state},
                follow_redirects=False,
            )
            assert completed.status_code in {302, 303, 307}
            assert completed.headers["location"] == (
                "http://localhost:3000/integrations?connector=zoho_crm&oauth=success"
            )

            status_response = client.get(
                "/v1/integrations/system-of-record/zoho-crm/status"
            )
            assert status_response.status_code == 200
            body = status_response.json()
            assert body["connected"] is True
            assert body["base_url"] == "https://www.zohoapis.in"
            assert body["has_bearer_token"] is True
            assert body["bearer_token_last4"] == "oken"
            assert body["has_oauth_refresh_token"] is True
            assert body["oauth_refresh_token_last4"] == "oken"
            dumped = json.dumps(body)
            assert "zoho-access-token" not in dumped
            assert "zoho-refresh-token" not in dumped
            assert body["readiness"]["contract"]["oauth_status"] == "available"

            def fake_refresh_token(*, refresh_token: str, settings) -> str:
                assert refresh_token == "zoho-refresh-token"
                return "zoho-refreshed-access-token"

            def fake_fetch(self: ZohoCrmConnector) -> SourceRecord:
                assert self.bearer_token == "zoho-refreshed-access-token"
                return SourceRecord(
                    record={
                        "id": self.record_ref,
                        "zoho_record_id": self.record_ref,
                        "Email": "owner@example.com",
                    },
                    record_found=True,
                    metadata={
                        "connector_type": "zoho_crm",
                        "http_status": 200,
                        "attempts": 1,
                        "retryable": False,
                    },
                )

            monkeypatch.setattr(
                "app.services.zoho_oauth.refresh_zoho_access_token",
                fake_refresh_token,
            )
            monkeypatch.setattr(ZohoCrmConnector, "fetch", fake_fetch)
            tested = client.post(
                "/v1/integrations/system-of-record/zoho-crm/test",
                json={
                    "module_name": "Contacts",
                    "record_ref": "1234567890000000001",
                    "claimed": {
                        "zoho_record_id": "1234567890000000001",
                        "Email": "owner@example.com",
                    },
                    "match_fields": ["zoho_record_id", "Email"],
                },
            )
            assert tested.status_code == 201
            assert tested.json()["ok"] is True
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        get_settings.cache_clear()


def test_zendesk_ticket_connector_config_status_and_test_run_redact_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "PROVIDER_KEY_VAULT_KEK", "test-kek-for-zendesk-connectors-1234567890"
    )
    get_settings.cache_clear()
    engine, session_factory = _sqlite_session_factory(tmp_path / "zendesk_connector.db")
    _seed_project(session_factory, "proj_zendesk_ticket")

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def override_tenant():
        return TenantContext(
            tenant_id="proj_zendesk_ticket", role="admin", subject="user-zendesk"
        )

    def fake_fetch(self: ZendeskTicketConnector) -> SourceRecord:
        assert self.base_url == "https://example.zendesk.com"
        assert self.path_template == "/api/v2/tickets/{record_ref}.json"
        assert self.basic_auth_username == "agent@example.com/token"
        assert self.basic_auth_password == "zendesk-api-token"
        return SourceRecord(
            record={
                "id": 12345,
                "ticket_id": "12345",
                "status": "solved",
                "subject": "Order question",
                "requester_id": 9001,
            },
            record_found=True,
            metadata={
                "connector_type": "zendesk_ticket",
                "request_url": (
                    "https://example.zendesk.com/api/v2/tickets/"
                    f"{self.record_ref}.json"
                ),
                "http_status": 200,
                "attempts": 1,
                "max_attempts": 2,
                "retryable": False,
                "record_ref": self.record_ref,
                "zendesk_object": "ticket",
            },
        )

    monkeypatch.setattr(ZendeskTicketConnector, "fetch", fake_fetch)
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_db_session_read] = override_db
    app.dependency_overrides[require_tenant_context] = override_tenant

    try:
        with TestClient(app) as client:
            empty = client.get("/v1/integrations/system-of-record/zendesk-ticket/status")
            assert empty.status_code == 200
            assert empty.json()["connected"] is False
            assert empty.json()["connector_type"] == "zendesk_ticket"
            assert empty.json()["readiness"]["status"] == "not_ready"

            saved = client.put(
                "/v1/integrations/system-of-record/zendesk-ticket/config",
                json={
                    "base_url": "https://example.zendesk.com",
                    "auth_username": "agent@example.com",
                    "bearer_token": "zendesk-api-token",
                },
            )
            assert saved.status_code == 200
            saved_body = saved.json()
            assert saved_body["connected"] is True
            assert saved_body["base_url"] == "https://example.zendesk.com"
            assert saved_body["connector_type"] == "zendesk_ticket"
            assert saved_body["query"]["auth_username"] == "agent@example.com"
            assert saved_body["has_bearer_token"] is True
            assert saved_body["bearer_token_last4"] == "oken"
            assert "zendesk-api-token" not in json.dumps(saved_body)

            tested = client.post(
                "/v1/integrations/system-of-record/zendesk-ticket/test",
                json={
                    "record_ref": "12345",
                    "claimed": {
                        "ticket_id": "12345",
                        "status": "solved",
                        "subject": "Order question",
                    },
                    "match_fields": ["ticket_id", "status", "subject"],
                },
            )
            assert tested.status_code == 201
            body = tested.json()
            assert body["ok"] is True
            assert body["check"]["connector_type"] == "zendesk_ticket"
            assert body["check"]["system_ref"] == "zendesk:ticket:12345"
            assert body["check"]["verdict"] == "matched"
            assert body["check"]["metadata"]["connector_kind"] == "zendesk_ticket"
            assert body["check"]["metadata"]["connector"]["http_status"] == 200
            assert body["connector"]["health_status"] == "healthy"
            assert body["connector"]["readiness"]["status"] == "ready"
            assert body["connector"]["readiness"]["contract"]["oauth_status"] == "planned"
            assert "zendesk-api-token" not in json.dumps(body)
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        get_settings.cache_clear()


def test_jira_issue_connector_config_status_and_test_run_redact_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "PROVIDER_KEY_VAULT_KEK", "test-kek-for-jira-connectors-1234567890"
    )
    get_settings.cache_clear()
    engine, session_factory = _sqlite_session_factory(tmp_path / "jira_connector.db")
    _seed_project(session_factory, "proj_jira_issue")

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def override_tenant():
        return TenantContext(
            tenant_id="proj_jira_issue", role="admin", subject="user-jira"
        )

    def fake_fetch(self: JiraIssueConnector) -> SourceRecord:
        assert self.base_url == "https://example.atlassian.net"
        assert self.path_template == "/rest/api/3/issue/{record_ref}"
        assert self.basic_auth_username == "agent@example.com"
        assert self.basic_auth_password == "jira-api-token"
        return SourceRecord(
            record={
                "jira_issue_key": "JSM-123",
                "issue_key": "JSM-123",
                "status": "Done",
                "summary": "Provision access",
            },
            record_found=True,
            metadata={
                "connector_type": "jira_issue",
                "request_url": (
                    "https://example.atlassian.net/rest/api/3/issue/"
                    f"{self.record_ref}"
                ),
                "http_status": 200,
                "attempts": 1,
                "max_attempts": 2,
                "retryable": False,
                "record_ref": self.record_ref,
                "jira_object": "issue",
            },
        )

    monkeypatch.setattr(JiraIssueConnector, "fetch", fake_fetch)
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_db_session_read] = override_db
    app.dependency_overrides[require_tenant_context] = override_tenant

    try:
        with TestClient(app) as client:
            empty = client.get("/v1/integrations/system-of-record/jira-issue/status")
            assert empty.status_code == 200
            assert empty.json()["connected"] is False
            assert empty.json()["connector_type"] == "jira_issue"
            assert empty.json()["readiness"]["status"] == "not_ready"

            saved = client.put(
                "/v1/integrations/system-of-record/jira-issue/config",
                json={
                    "base_url": "https://example.atlassian.net",
                    "auth_username": "agent@example.com",
                    "bearer_token": "jira-api-token",
                },
            )
            assert saved.status_code == 200
            saved_body = saved.json()
            assert saved_body["connected"] is True
            assert saved_body["base_url"] == "https://example.atlassian.net"
            assert saved_body["connector_type"] == "jira_issue"
            assert saved_body["query"]["auth_username"] == "agent@example.com"
            assert saved_body["has_bearer_token"] is True
            assert saved_body["bearer_token_last4"] == "oken"
            assert "jira-api-token" not in json.dumps(saved_body)

            tested = client.post(
                "/v1/integrations/system-of-record/jira-issue/test",
                json={
                    "record_ref": "JSM-123",
                    "claimed": {
                        "jira_issue_key": "JSM-123",
                        "status": "Done",
                        "summary": "Provision access",
                    },
                    "match_fields": ["jira_issue_key", "status", "summary"],
                },
            )
            assert tested.status_code == 201
            body = tested.json()
            assert body["ok"] is True
            assert body["check"]["connector_type"] == "jira_issue"
            assert body["check"]["system_ref"] == "jira:issue:JSM-123"
            assert body["check"]["verdict"] == "matched"
            assert body["check"]["metadata"]["connector_kind"] == "jira_issue"
            assert body["check"]["metadata"]["connector"]["http_status"] == 200
            assert body["connector"]["health_status"] == "healthy"
            assert body["connector"]["readiness"]["status"] == "ready"
            assert body["connector"]["readiness"]["contract"]["oauth_status"] == "planned"
            assert "jira-api-token" not in json.dumps(body)
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        get_settings.cache_clear()


def test_ledger_refund_connector_config_and_test_run_are_tenant_scoped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "PROVIDER_KEY_VAULT_KEK", "test-kek-for-sor-connectors-1234567890"
    )
    get_settings.cache_clear()
    engine, session_factory = _sqlite_session_factory(
        tmp_path / "sor_connector_tenant_scope.db"
    )
    _seed_project(session_factory, "proj_sor_alpha")
    _seed_project(session_factory, "proj_sor_beta")
    fetches: list[tuple[str, str]] = []

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def override_tenant(request: Request):
        tenant_id = request.headers.get("x-zroky-test-project", "proj_sor_alpha")
        return TenantContext(
            tenant_id=tenant_id, role="admin", subject=f"user-{tenant_id}"
        )

    def fake_fetch(self: LedgerRefundApiConnector) -> SourceRecord:
        fetches.append((self.base_url, self.refund_id))
        assert self.base_url == "https://alpha-ledger.example.com/api"
        assert self.bearer_token == "alpha-secret-token"
        return SourceRecord(
            record={
                "refund_id": self.refund_id,
                "amount_usd": 42.5,
                "currency": "USD",
                "status": "posted",
            },
            record_found=True,
            metadata={
                "connector_type": "ledger_refund_api",
                "request_url": f"https://alpha-ledger.example.com/api/refunds/{self.refund_id}",
                "http_status": 200,
                "attempts": 1,
                "max_attempts": 2,
                "retryable": False,
                "refund_id": self.refund_id,
            },
        )

    monkeypatch.setattr(LedgerRefundApiConnector, "fetch", fake_fetch)
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_db_session_read] = override_db
    app.dependency_overrides[require_tenant_context] = override_tenant

    try:
        with TestClient(app) as client:
            alpha_headers = {"x-zroky-test-project": "proj_sor_alpha"}
            beta_headers = {"x-zroky-test-project": "proj_sor_beta"}

            saved = client.put(
                "/v1/integrations/system-of-record/ledger-refund/config",
                headers=alpha_headers,
                json={
                    "base_url": "https://alpha-ledger.example.com/api",
                    "path_template": "/refunds/{refund_id}",
                    "bearer_token": "alpha-secret-token",
                },
            )
            assert saved.status_code == 200
            assert saved.json()["connected"] is True

            beta_status = client.get(
                "/v1/integrations/system-of-record/ledger-refund/status",
                headers=beta_headers,
            )
            assert beta_status.status_code == 200
            assert beta_status.json()["connected"] is False
            assert beta_status.json()["base_url"] is None

            beta_test = client.post(
                "/v1/integrations/system-of-record/ledger-refund/test",
                headers=beta_headers,
                json={
                    "refund_id": "rf_alpha",
                    "claimed": {
                        "refund_id": "rf_alpha",
                        "amount_usd": 42.5,
                        "currency": "USD",
                        "status": "posted",
                    },
                },
            )
            assert beta_test.status_code == 404
            assert fetches == []

            alpha_test = client.post(
                "/v1/integrations/system-of-record/ledger-refund/test",
                headers=alpha_headers,
                json={
                    "refund_id": "rf_alpha",
                    "claimed": {
                        "refund_id": "rf_alpha",
                        "amount_usd": 42.5,
                        "currency": "USD",
                        "status": "posted",
                    },
                },
            )
            assert alpha_test.status_code == 201
            body = alpha_test.json()
            assert body["ok"] is True
            assert body["check"]["project_id"] == "proj_sor_alpha"
            assert body["check"]["verdict"] == "matched"
            assert (
                body["connector"]["base_url"]
                == "https://alpha-ledger.example.com/api"
            )
            assert body["connector"]["readiness"]["status"] == "ready"
            assert fetches == [("https://alpha-ledger.example.com/api", "rf_alpha")]
            assert "alpha-secret-token" not in json.dumps(body)

            beta_status_after = client.get(
                "/v1/integrations/system-of-record/ledger-refund/status",
                headers=beta_headers,
            )
            assert beta_status_after.status_code == 200
            assert beta_status_after.json()["connected"] is False
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        get_settings.cache_clear()


def test_ledger_refund_connector_rejects_unsafe_saved_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "PROVIDER_KEY_VAULT_KEK", "test-kek-for-sor-connectors-1234567890"
    )
    get_settings.cache_clear()
    engine, session_factory = _sqlite_session_factory(tmp_path / "sor_bad_config.db")
    _seed_project(session_factory, "proj_sor_bad")

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def override_tenant():
        return TenantContext(tenant_id="proj_sor_bad", role="admin", subject="user-sor")

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_db_session_read] = override_db
    app.dependency_overrides[require_tenant_context] = override_tenant

    try:
        with TestClient(app) as client:
            response = client.put(
                "/v1/integrations/system-of-record/ledger-refund/config",
                json={
                    "base_url": "http://ledger.example.com/api",
                    "path_template": "/refunds/{refund_id}",
                },
            )
            assert response.status_code == 422
            assert "must use https" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        get_settings.cache_clear()


def test_ledger_refund_connector_status_surfaces_degraded_health_after_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "PROVIDER_KEY_VAULT_KEK", "test-kek-for-sor-connectors-1234567890"
    )
    get_settings.cache_clear()
    engine, session_factory = _sqlite_session_factory(
        tmp_path / "sor_connector_degraded.db"
    )
    _seed_project(session_factory, "proj_sor_degraded")

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def override_tenant():
        return TenantContext(
            tenant_id="proj_sor_degraded", role="admin", subject="user-sor"
        )

    def fake_fetch(self: LedgerRefundApiConnector) -> SourceRecord:
        return SourceRecord(
            record=None,
            record_found=None,
            metadata={
                "connector_type": "ledger_refund_api",
                "request_url": f"https://ledger.example.com/api/refunds/{self.refund_id}",
                "record_path": "data",
                "error": "ReadTimeout",
                "error_code": "connector_timeout",
                "attempts": 2,
                "max_attempts": 2,
                "retryable": True,
                "refund_id": self.refund_id,
            },
        )

    monkeypatch.setattr(LedgerRefundApiConnector, "fetch", fake_fetch)
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_db_session_read] = override_db
    app.dependency_overrides[require_tenant_context] = override_tenant

    try:
        with TestClient(app) as client:
            saved = client.put(
                "/v1/integrations/system-of-record/ledger-refund/config",
                json={
                    "base_url": "https://ledger.example.com/api",
                    "path_template": "/refunds/{refund_id}",
                    "record_path": "data",
                    "bearer_token": "ledger-secret-token",
                },
            )
            assert saved.status_code == 200

            tested = client.post(
                "/v1/integrations/system-of-record/ledger-refund/test",
                json={
                    "refund_id": "rf_timeout",
                    "claimed": {"refund_id": "rf_timeout", "amount_usd": 42.5},
                },
            )

            assert tested.status_code == 201
            body = tested.json()
            assert body["ok"] is False
            assert body["check"]["verdict"] == "not_verified"
            assert body["check"]["metadata"]["connector"]["error"] == "ReadTimeout"
            assert body["check"]["metadata"]["connector"]["error_code"] == "connector_timeout"
            assert body["connector"]["health_status"] == "degraded"
            assert body["connector"]["last_verdict"] == "not_verified"
            assert body["connector"]["last_error"] == "ReadTimeout"
            assert body["connector"]["last_error_code"] == "connector_timeout"
            assert body["connector"]["last_attempts"] == 2
            assert body["connector"]["last_retryable"] is True
            assert body["connector"]["readiness"]["status"] == "not_ready"
            assert "latest connector test did not return a 2xx HTTP response" in body[
                "connector"
            ]["readiness"]["blockers"]
            assert "ledger-secret-token" not in json.dumps(body)
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        get_settings.cache_clear()


def test_ledger_refund_connector_status_surfaces_auth_failure_taxonomy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "PROVIDER_KEY_VAULT_KEK", "test-kek-for-sor-connectors-1234567890"
    )
    get_settings.cache_clear()
    engine, session_factory = _sqlite_session_factory(
        tmp_path / "sor_connector_auth_failed.db"
    )
    _seed_project(session_factory, "proj_sor_auth_failed")

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def override_tenant():
        return TenantContext(
            tenant_id="proj_sor_auth_failed", role="admin", subject="user-sor"
        )

    def fake_fetch(self: LedgerRefundApiConnector) -> SourceRecord:
        return SourceRecord(
            record=None,
            record_found=None,
            metadata={
                "connector_type": "ledger_refund_api",
                "request_url": f"https://ledger.example.com/api/refunds/{self.refund_id}",
                "http_status": 401,
                "record_path": "data",
                "error": "http_error",
                "error_code": "auth_failed",
                "attempts": 1,
                "max_attempts": 2,
                "retryable": False,
                "refund_id": self.refund_id,
            },
        )

    monkeypatch.setattr(LedgerRefundApiConnector, "fetch", fake_fetch)
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_db_session_read] = override_db
    app.dependency_overrides[require_tenant_context] = override_tenant

    try:
        with TestClient(app) as client:
            saved = client.put(
                "/v1/integrations/system-of-record/ledger-refund/config",
                json={
                    "base_url": "https://ledger.example.com/api",
                    "path_template": "/refunds/{refund_id}",
                    "record_path": "data",
                    "bearer_token": "ledger-secret-token",
                },
            )
            assert saved.status_code == 200

            tested = client.post(
                "/v1/integrations/system-of-record/ledger-refund/test",
                json={
                    "refund_id": "rf_auth_failed",
                    "claimed": {"refund_id": "rf_auth_failed", "amount_usd": 42.5},
                },
            )

            assert tested.status_code == 201
            body = tested.json()
            assert body["ok"] is False
            assert body["check"]["verdict"] == "not_verified"
            assert body["check"]["metadata"]["connector"]["http_status"] == 401
            assert body["check"]["metadata"]["connector"]["error_code"] == "auth_failed"
            assert body["connector"]["health_status"] == "auth_failed"
            assert body["connector"]["last_verdict"] == "not_verified"
            assert body["connector"]["last_error"] == "http_error"
            assert body["connector"]["last_error_code"] == "auth_failed"
            assert body["connector"]["last_http_status"] == 401
            assert body["connector"]["last_attempts"] == 1
            assert body["connector"]["last_retryable"] is False
            assert body["connector"]["readiness"]["status"] == "not_ready"
            assert "latest connector test has an error code" in body["connector"][
                "readiness"
            ]["blockers"]
            assert "ledger-secret-token" not in json.dumps(body)
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        get_settings.cache_clear()


def test_customer_record_connector_rejects_unsafe_saved_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "PROVIDER_KEY_VAULT_KEK", "test-kek-for-sor-connectors-1234567890"
    )
    get_settings.cache_clear()
    engine, session_factory = _sqlite_session_factory(
        tmp_path / "sor_crm_bad_config.db"
    )
    _seed_project(session_factory, "proj_sor_crm_bad")

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def override_tenant():
        return TenantContext(
            tenant_id="proj_sor_crm_bad", role="admin", subject="user-sor"
        )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_db_session_read] = override_db
    app.dependency_overrides[require_tenant_context] = override_tenant

    try:
        with TestClient(app) as client:
            response = client.put(
                "/v1/integrations/system-of-record/customer-record/config",
                json={
                    "base_url": "http://crm.example.com/api",
                    "path_template": "/customers/{customer_id}",
                },
            )
            assert response.status_code == 422
            assert "must use https" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        get_settings.cache_clear()
