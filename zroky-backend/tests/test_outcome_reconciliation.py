from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.db.base import Base
from app.db.session import get_db_session, get_db_session_read
from app.main import app
from app.services.detectors.outcome_mismatch import detect_outcome_mismatch
from app.services.outcome_reconciliation import (
    ApiRecordConnector,
    compare_claim_to_actual,
    get_reconciliation_summary,
    reconcile_outcome,
)


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


def test_reconcile_outcome_persists_match_and_is_idempotent(tmp_path: Path) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'reconcile.db'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

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
                    record={"refund_id": "rf_123", "amount_usd": "42.50", "currency": "usd"},
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
            summary = get_reconciliation_summary(session, project_id="proj_reconcile", days=30)

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
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def override_tenant():
        return TenantContext(tenant_id="proj_reconcile_api", role="admin", subject="user-reconcile")

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

    assert detect_outcome_mismatch({"outcome_reconciliation": {"verdict": "not_verified"}}) is None
