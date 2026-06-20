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
from app.services.system_of_record_connectors import LedgerRefundApiConnector


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
    monkeypatch.setenv("PROVIDER_KEY_VAULT_KEK", "test-kek-for-sor-connectors-1234567890")
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

            status = client.get("/v1/integrations/system-of-record/ledger-refund/status")
            assert status.status_code == 200
            assert status.json()["base_url"] == "https://ledger.example.com/api"
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
            assert body["connector"]["last_tested_at"] is not None
            assert "ledger-secret-token" not in json.dumps(body)
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        get_settings.cache_clear()


def test_ledger_refund_connector_rejects_unsafe_saved_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROVIDER_KEY_VAULT_KEK", "test-kek-for-sor-connectors-1234567890")
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
        return TenantContext(
            tenant_id="proj_sor_bad", role="admin", subject="user-sor"
        )

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
