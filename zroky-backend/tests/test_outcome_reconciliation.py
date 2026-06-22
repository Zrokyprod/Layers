from __future__ import annotations

from pathlib import Path
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.db.base import Base
from app.db.models import Project
from app.db.session import get_db_session, get_db_session_read
from app.main import app
from app.core.config import get_settings
from app.services.detectors.outcome_mismatch import detect_outcome_mismatch
from app.services.outcome_reconciliation import (
    ApiRecordConnector,
    SourceRecord,
    compare_claim_to_actual,
    get_reconciliation_summary,
    reconcile_outcome,
)
from app.services.system_of_record_connectors import (
    ConnectorConfigError,
    CustomerRecordApiConnector,
    LedgerRefundApiConnector,
)
from app.services.system_of_record_connector_config import (
    upsert_customer_record_connector_config,
    upsert_ledger_refund_connector_config,
)


def _seed_project(session_factory, project_id: str) -> None:
    with session_factory() as session:
        session.add(Project(id=project_id, name=project_id))
        session.commit()


def test_compare_claim_to_actual_has_honest_verdicts() -> None:
    matched = compare_claim_to_actual(
        claimed={"refund_id": "rf_123", "amount_usd": "42.50", "currency": "usd"},
        actual={"refund_id": "rf_123", "amount_usd": 42.5, "currency": "USD"},
    )
    assert matched.verdict == "matched"
    assert matched.reason == "all_compared_fields_matched"

    mismatched = compare_claim_to_actual(
        claimed={"refund_id": "rf_123", "amount_usd": 42.5, "currency": "USD"},
        actual={"refund_id": "rf_123", "amount_usd": 99.0, "currency": "USD"},
    )
    assert mismatched.verdict == "mismatched"
    assert mismatched.reason == "field_mismatch"
    assert mismatched.mismatches[0]["field"] == "amount_usd"

    missing_record = compare_claim_to_actual(
        claimed={"refund_id": "rf_missing", "amount_usd": 42.5},
        actual=None,
        actual_record_found=False,
    )
    assert missing_record.verdict == "mismatched"
    assert missing_record.reason == "system_of_record_record_missing"

    not_verified = compare_claim_to_actual(
        claimed={"refund_id": "rf_123", "amount_usd": 42.5},
        actual=None,
    )
    assert not_verified.verdict == "not_verified"
    assert not_verified.reason == "system_of_record_missing"


def test_ledger_refund_connector_fetches_and_normalizes_record_without_storing_secret() -> (
    None
):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "data": {
                    "id": "rf_123",
                    "amount": "42.50",
                    "currency": "usd",
                    "status": "posted",
                }
            },
        )

    connector = LedgerRefundApiConnector(
        base_url="https://ledger.example/api",
        refund_id="rf_123",
        bearer_token="ledger-secret-token",
        record_path="data",
        transport=httpx.MockTransport(handler),
    )

    source = connector.fetch()

    assert requests[0].url == "https://ledger.example/api/refunds/rf_123"
    assert requests[0].headers["authorization"] == "Bearer ledger-secret-token"
    assert source.record_found is True
    assert source.record == {
        "id": "rf_123",
        "amount": "42.50",
        "currency": "USD",
        "status": "posted",
        "refund_id": "rf_123",
        "amount_usd": "42.50",
    }
    assert source.metadata is not None
    assert source.metadata["http_status"] == 200
    assert "ledger-secret-token" not in json.dumps(source.metadata)


def test_ledger_refund_connector_handles_real_ledger_array_and_alias_shapes() -> None:
    connector = LedgerRefundApiConnector(
        base_url="https://ledger.example/api",
        refund_id="rf_array",
        record_path="data.0",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "refundId": "rf_array",
                            "order_id": "ord_1",
                            "amount_cents": "4218",
                            "currency": "usd",
                            "state": "posted",
                        }
                    ]
                },
            )
        ),
    )

    source = connector.fetch()

    assert source.record_found is True
    assert source.record is not None
    assert source.record["refund_id"] == "rf_array"
    assert source.record["amount_usd"] == 42.18
    assert source.record["currency"] == "USD"
    assert source.record["status"] == "posted"


def test_ledger_refund_connector_retries_transient_failure_and_records_metadata() -> (
    None
):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            raise httpx.ConnectError("temporary outage", request=request)
        return httpx.Response(
            200,
            json={
                "refund_id": "rf_retry",
                "amount_usd": "42.50",
                "currency": "usd",
            },
        )

    connector = LedgerRefundApiConnector(
        base_url="https://ledger.example/api",
        refund_id="rf_retry",
        bearer_token="ledger-secret-token",
        timeout_seconds=1.25,
        max_attempts=3,
        transport=httpx.MockTransport(handler),
    )

    source = connector.fetch()

    assert len(requests) == 2
    assert source.record_found is True
    assert source.record is not None
    assert source.record["refund_id"] == "rf_retry"
    assert source.metadata is not None
    assert source.metadata["attempts"] == 2
    assert source.metadata["retry_count"] == 1
    assert source.metadata["max_attempts"] == 3
    assert source.metadata["timeout_seconds"] == 1.25
    assert source.metadata["transient_errors"] == ["ConnectError"]
    assert "ledger-secret-token" not in json.dumps(source.metadata)


def test_ledger_refund_connector_exhausts_retryable_status_without_false_pass() -> None:
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, json={"error": "temporarily_unavailable"})

    source = LedgerRefundApiConnector(
        base_url="https://ledger.example/api",
        refund_id="rf_retry_exhausted",
        max_attempts=2,
        transport=httpx.MockTransport(handler),
    ).fetch()

    assert attempts == 2
    assert source.record is None
    assert source.record_found is None
    assert source.metadata is not None
    assert source.metadata["http_status"] == 503
    assert source.metadata["error"] == "http_error"
    assert source.metadata["attempts"] == 2
    assert source.metadata["retry_count"] == 1
    assert source.metadata["retryable"] is True
    assert source.metadata["transient_errors"] == ["http_503", "http_503"]


def test_ledger_refund_connector_ignores_malformed_cents_without_false_pass() -> None:
    for malformed in ("not-a-number", "NaN"):
        source = LedgerRefundApiConnector(
            base_url="https://ledger.example/api",
            refund_id=f"rf_bad_amount_{malformed}",
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    200,
                    json={
                        "refund_id": f"rf_bad_amount_{malformed}",
                        "amount_cents": malformed,
                        "currency": "usd",
                    },
                )
            ),
        ).fetch()

        assert source.record_found is True
        assert source.record is not None
        assert source.record["refund_id"] == f"rf_bad_amount_{malformed}"
        assert "amount_usd" not in source.record


def test_ledger_refund_connector_missing_record_and_unavailable_source_are_honest() -> (
    None
):
    missing = LedgerRefundApiConnector(
        base_url="https://ledger.example",
        refund_id="rf_missing",
        transport=httpx.MockTransport(lambda _request: httpx.Response(404)),
    ).fetch()
    assert missing.record is None
    assert missing.record_found is False
    assert missing.metadata is not None
    assert missing.metadata["http_status"] == 404

    unavailable = LedgerRefundApiConnector(
        base_url="https://ledger.example",
        refund_id="rf_unknown",
        transport=httpx.MockTransport(lambda _request: httpx.Response(503)),
    ).fetch()
    assert unavailable.record is None
    assert unavailable.record_found is None
    assert unavailable.metadata is not None
    assert unavailable.metadata["error"] == "http_error"


def test_ledger_refund_connector_rejects_private_hosts_by_default() -> None:
    with pytest.raises(ConnectorConfigError):
        LedgerRefundApiConnector(
            base_url="https://127.0.0.1", refund_id="rf_123"
        ).fetch()


def test_ledger_refund_connector_rejects_unsafe_url_shapes() -> None:
    for kwargs in (
        {"base_url": "https://ledger.example/api?token=hidden"},
        {"base_url": "https://ledger.example/api#fragment"},
        {
            "base_url": "https://ledger.example/api",
            "path_template": "/../refunds/{refund_id}",
        },
        {
            "base_url": "https://ledger.example/api",
            "path_template": "/refunds/{refund_id}?expand=all",
        },
        {
            "base_url": "https://ledger.example/api",
            "path_template": "/refunds/%2e%2e/secret/{refund_id}",
        },
        {
            "base_url": "https://ledger.example/api",
            "path_template": "/refunds\\{refund_id}",
        },
    ):
        with pytest.raises(ConnectorConfigError):
            LedgerRefundApiConnector(refund_id="rf_123", **kwargs).fetch()


def test_ledger_refund_connector_rejects_traversal_in_refund_id() -> None:
    with pytest.raises(ConnectorConfigError):
        LedgerRefundApiConnector(
            base_url="https://ledger.example/api",
            refund_id="../secret",
        ).fetch()


def test_reconcile_outcome_persists_match_and_is_idempotent(tmp_path: Path) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'reconcile.db'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )

    try:
        with session_factory() as session:
            first = reconcile_outcome(
                session,
                project_id="proj_reconcile",
                call_id="call_refund_1",
                trace_id="trace_refund_1",
                action_type="refund",
                system_ref="ledger:rf_123",
                claimed={"refund_id": "rf_123", "amount_usd": 42.5, "currency": "USD"},
                connector=ApiRecordConnector(
                    record={
                        "refund_id": "rf_123",
                        "amount_usd": "42.50",
                        "currency": "usd",
                    },
                    record_found=True,
                    connector_type="ledger_api",
                ),
                amount_usd=42.5,
                currency="USD",
                idempotency_key="call_refund_1:rf_123",
            )
            second = reconcile_outcome(
                session,
                project_id="proj_reconcile",
                claimed={"refund_id": "rf_123", "amount_usd": 42.5, "currency": "USD"},
                connector=ApiRecordConnector(record={"refund_id": "different"}),
                idempotency_key="call_refund_1:rf_123",
            )
            summary = get_reconciliation_summary(
                session, project_id="proj_reconcile", days=30
            )

        assert first.id == second.id
        assert first.verdict == "matched"
        assert first.connector_type == "ledger_api"
        assert summary.total == 1
        assert summary.matched == 1
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_reconciliation_api_creates_mismatch_and_lists_by_call(tmp_path: Path) -> None:
    db_path = tmp_path / "reconcile_api.db"
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

    def override_tenant():
        return TenantContext(
            tenant_id="proj_reconcile_api", role="admin", subject="user-reconcile"
        )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_db_session_read] = override_db
    app.dependency_overrides[require_tenant_context] = override_tenant

    try:
        with TestClient(app) as client:
            created = client.post(
                "/v1/outcomes/reconciliation",
                json={
                    "call_id": "call_refund_api",
                    "trace_id": "trace_refund_api",
                    "action_type": "refund",
                    "connector_type": "ledger_api",
                    "system_ref": "ledger:rf_999",
                    "claimed": {
                        "refund_id": "rf_999",
                        "amount_usd": 42.5,
                        "currency": "USD",
                    },
                    "actual": {
                        "refund_id": "rf_999",
                        "amount_usd": 41.5,
                        "currency": "USD",
                    },
                    "actual_record_found": True,
                    "idempotency_key": "call_refund_api:rf_999",
                },
            )
            assert created.status_code == 201
            body = created.json()
            assert body["verdict"] == "mismatched"
            assert body["reason"] == "field_mismatch"
            assert body["comparison"]["mismatches"][0]["field"] == "amount_usd"

            by_call = client.get("/v1/outcomes/reconciliation/by-call/call_refund_api")
            assert by_call.status_code == 200
            assert by_call.json()["items"][0]["id"] == body["id"]

            summary = client.get("/v1/outcomes/reconciliation/summary")
            assert summary.status_code == 200
            assert summary.json()["mismatched"] == 1
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_ledger_refund_reconciliation_api_fetches_system_record_and_redacts_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "ledger_refund_api.db"
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

    def override_tenant():
        return TenantContext(
            tenant_id="proj_ledger_refund", role="admin", subject="user-ledger"
        )

    def fake_fetch(self: LedgerRefundApiConnector) -> SourceRecord:
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
                "request_url": "https://ledger.example/refunds/rf_live",
                "http_status": 200,
                "refund_id": self.refund_id,
            },
        )

    monkeypatch.setattr(LedgerRefundApiConnector, "fetch", fake_fetch)
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_db_session_read] = override_db
    app.dependency_overrides[require_tenant_context] = override_tenant

    try:
        with TestClient(app) as client:
            created = client.post(
                "/v1/outcomes/reconciliation/ledger-refund",
                json={
                    "call_id": "call_live_refund",
                    "trace_id": "trace_live_refund",
                    "claimed": {
                        "refund_id": "rf_live",
                        "amount_usd": 42.5,
                        "currency": "USD",
                    },
                    "connector": {
                        "base_url": "https://ledger.example",
                        "bearer_token": "ledger-secret-token",
                    },
                },
            )

            assert created.status_code == 201
            body = created.json()
            assert body["verdict"] == "matched"
            assert body["connector_type"] == "ledger_refund_api"
            assert body["system_ref"] == "ledger:rf_live"
            assert body["reason"] == "all_compared_fields_matched"
            assert body["metadata"]["connector"]["http_status"] == 200
            assert body["metadata"]["match_fields"] == [
                "refund_id",
                "amount_usd",
                "currency",
            ]
            assert "ledger-secret-token" not in json.dumps(body)
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_customer_record_reconciliation_api_fetches_crm_record_and_redacts_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "customer_record_api.db"
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

    def override_tenant():
        return TenantContext(
            tenant_id="proj_customer_record", role="admin", subject="user-crm"
        )

    def fake_fetch(self: CustomerRecordApiConnector) -> SourceRecord:
        assert self.bearer_token == "crm-secret-token"
        return SourceRecord(
            record={
                "customer_id": self.customer_id,
                "email": "OWNER@EXAMPLE.COM",
                "status": "active",
                "account_id": "acct_1001",
            },
            record_found=True,
            metadata={
                "connector_type": "customer_record_api",
                "request_url": "https://crm.example/customers/cus_1001",
                "http_status": 200,
                "customer_id": self.customer_id,
            },
        )

    monkeypatch.setattr(CustomerRecordApiConnector, "fetch", fake_fetch)
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_db_session_read] = override_db
    app.dependency_overrides[require_tenant_context] = override_tenant

    try:
        with TestClient(app) as client:
            created = client.post(
                "/v1/outcomes/reconciliation/customer-record",
                json={
                    "call_id": "call_crm_update",
                    "trace_id": "trace_crm_update",
                    "customer_id": "cus_1001",
                    "claimed": {
                        "customer_id": "cus_1001",
                        "email": "owner@example.com",
                        "status": "ACTIVE",
                        "account_id": "acct_1001",
                    },
                    "connector": {
                        "base_url": "https://crm.example",
                        "bearer_token": "crm-secret-token",
                    },
                },
            )

            assert created.status_code == 201
            body = created.json()
            assert body["verdict"] == "matched"
            assert body["connector_type"] == "customer_record_api"
            assert body["system_ref"] == "crm:cus_1001"
            assert body["reason"] == "all_compared_fields_matched"
            assert body["metadata"]["connector"]["http_status"] == 200
            assert body["metadata"]["match_fields"] == [
                "customer_id",
                "email",
                "account_id",
                "status",
            ]
            assert "crm-secret-token" not in json.dumps(body)
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_ledger_refund_reconciliation_api_marks_missing_ledger_record_mismatched(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "ledger_refund_missing.db"
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

    def override_tenant():
        return TenantContext(
            tenant_id="proj_ledger_missing", role="admin", subject="user-ledger"
        )

    monkeypatch.setattr(
        LedgerRefundApiConnector,
        "fetch",
        lambda self: SourceRecord(
            record=None,
            record_found=False,
            metadata={
                "connector_type": "ledger_refund_api",
                "request_url": "https://ledger.example/refunds/rf_missing",
                "http_status": 404,
                "refund_id": self.refund_id,
            },
        ),
    )
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_db_session_read] = override_db
    app.dependency_overrides[require_tenant_context] = override_tenant

    try:
        with TestClient(app) as client:
            created = client.post(
                "/v1/outcomes/reconciliation/ledger-refund",
                json={
                    "call_id": "call_missing_refund",
                    "claimed": {"refund_id": "rf_missing", "amount_usd": 42.5},
                    "connector": {"base_url": "https://ledger.example"},
                },
            )

            assert created.status_code == 201
            body = created.json()
            assert body["verdict"] == "mismatched"
            assert body["reason"] == "system_of_record_record_missing"
            assert body["metadata"]["connector"]["http_status"] == 404
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_saved_ledger_refund_reconciliation_uses_stored_connector_for_member_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "PROVIDER_KEY_VAULT_KEK", "test-kek-for-saved-sor-connectors-123456"
    )
    get_settings.cache_clear()
    db_path = tmp_path / "saved_ledger_runtime.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )
    _seed_project(session_factory, "proj_saved_ledger")
    with session_factory() as session:
        upsert_ledger_refund_connector_config(
            session,
            project_id="proj_saved_ledger",
            base_url="https://ledger.example.com/api",
            path_template="/refunds/{refund_id}",
            record_path="data",
            bearer_token="stored-ledger-secret",
            updated_by_subject="admin@example.com",
        )

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def override_tenant():
        return TenantContext(
            tenant_id="proj_saved_ledger", role="member", subject=None
        )

    def fake_fetch(self: LedgerRefundApiConnector) -> SourceRecord:
        assert self.base_url == "https://ledger.example.com/api"
        assert self.record_path == "data"
        assert self.bearer_token == "stored-ledger-secret"
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
                "attempts": 1,
                "retryable": False,
            },
        )

    monkeypatch.setattr(LedgerRefundApiConnector, "fetch", fake_fetch)
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_db_session_read] = override_db
    app.dependency_overrides[require_tenant_context] = override_tenant

    try:
        with TestClient(app) as client:
            created = client.post(
                "/v1/outcomes/reconciliation/ledger-refund/saved",
                json={
                    "call_id": "call_saved_refund",
                    "trace_id": "trace_saved_refund",
                    "runtime_policy_decision_id": "decision_saved_refund",
                    "claimed": {
                        "refund_id": "rf_saved",
                        "amount_usd": 42.5,
                        "currency": "USD",
                        "status": "posted",
                    },
                    "metadata": {"partner_run_id": "pilot_1"},
                },
            )

            assert created.status_code == 201
            body = created.json()
            assert body["verdict"] == "matched"
            assert body["connector_type"] == "ledger_refund_api"
            assert body["system_ref"] == "ledger:rf_saved"
            assert body["runtime_policy_decision_id"] == "decision_saved_refund"
            assert body["idempotency_key"] == (
                "saved_ledger_refund:decision_saved_refund:rf_saved"
            )
            assert body["metadata"]["source"] == "saved_connector_runtime"
            assert body["metadata"]["partner_run_id"] == "pilot_1"
            assert body["metadata"]["connector_config_id"]
            assert body["metadata"]["connector"]["http_status"] == 200
            assert "stored-ledger-secret" not in json.dumps(body)
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        get_settings.cache_clear()


def test_saved_customer_record_reconciliation_uses_stored_connector(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "PROVIDER_KEY_VAULT_KEK", "test-kek-for-saved-crm-connectors-123456"
    )
    get_settings.cache_clear()
    db_path = tmp_path / "saved_customer_runtime.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )
    _seed_project(session_factory, "proj_saved_customer")
    with session_factory() as session:
        upsert_customer_record_connector_config(
            session,
            project_id="proj_saved_customer",
            base_url="https://crm.example.com/api",
            path_template="/customers/{customer_id}",
            record_path="data",
            bearer_token="stored-crm-secret",
            updated_by_subject="admin@example.com",
        )

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def override_tenant():
        return TenantContext(
            tenant_id="proj_saved_customer", role="member", subject=None
        )

    def fake_fetch(self: CustomerRecordApiConnector) -> SourceRecord:
        assert self.base_url == "https://crm.example.com/api"
        assert self.record_path == "data"
        assert self.bearer_token == "stored-crm-secret"
        return SourceRecord(
            record={
                "customer_id": self.customer_id,
                "email": "OWNER@EXAMPLE.COM",
                "status": "active",
                "account_id": "acct_1001",
            },
            record_found=True,
            metadata={
                "connector_type": "customer_record_api",
                "request_url": f"https://crm.example.com/api/customers/{self.customer_id}",
                "http_status": 200,
                "attempts": 1,
                "retryable": False,
            },
        )

    monkeypatch.setattr(CustomerRecordApiConnector, "fetch", fake_fetch)
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_db_session_read] = override_db
    app.dependency_overrides[require_tenant_context] = override_tenant

    try:
        with TestClient(app) as client:
            created = client.post(
                "/v1/outcomes/reconciliation/customer-record/saved",
                json={
                    "call_id": "call_saved_crm",
                    "trace_id": "trace_saved_crm",
                    "runtime_policy_decision_id": "decision_saved_crm",
                    "customer_id": "cus_saved",
                    "claimed": {
                        "customer_id": "cus_saved",
                        "email": "owner@example.com",
                        "status": "ACTIVE",
                        "account_id": "acct_1001",
                    },
                },
            )

            assert created.status_code == 201
            body = created.json()
            assert body["verdict"] == "matched"
            assert body["connector_type"] == "customer_record_api"
            assert body["system_ref"] == "crm:cus_saved"
            assert body["idempotency_key"] == (
                "saved_customer_record:decision_saved_crm:cus_saved"
            )
            assert body["metadata"]["source"] == "saved_connector_runtime"
            assert body["metadata"]["connector_config_id"]
            assert body["metadata"]["connector"]["http_status"] == 200
            assert "stored-crm-secret" not in json.dumps(body)
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        get_settings.cache_clear()


def test_saved_connector_reconciliation_fails_closed_when_config_missing(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "saved_connector_missing.db"
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

    def override_tenant():
        return TenantContext(
            tenant_id="proj_missing_saved_connector", role="member", subject=None
        )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_db_session_read] = override_db
    app.dependency_overrides[require_tenant_context] = override_tenant

    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/outcomes/reconciliation/ledger-refund/saved",
                json={
                    "claimed": {"refund_id": "rf_missing"},
                },
            )

            assert response.status_code == 404
            assert response.json()["detail"] == (
                "Ledger refund connector is not configured."
            )
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_outcome_mismatch_detector_fires_only_on_mismatched_reconciliation() -> None:
    result = detect_outcome_mismatch(
        {
            "outcome_reconciliation": {
                "verdict": "mismatched",
                "action_type": "refund",
                "system_ref": "ledger:rf_999",
                "reason": "field_mismatch",
                "comparison": {"mismatches": [{"field": "amount_usd"}]},
            }
        }
    )
    assert result is not None
    assert result["category"] == "OUTCOME_MISMATCH"
    assert result["severity_hint"] == "critical"

    assert (
        detect_outcome_mismatch({"outcome_reconciliation": {"verdict": "not_verified"}})
        is None
    )
