from __future__ import annotations

import json
from pathlib import Path

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
    LedgerRefundApiConnector,
    PostgresReadOnlyConnector,
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
