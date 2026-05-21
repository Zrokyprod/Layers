import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import Call
from app.db.session import get_db_session, get_db_session_read
from app.main import app


@pytest.fixture()
def client(tmp_path: Path):
    get_settings.cache_clear()
    db_path = tmp_path / "test_cost_trust.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)

    def override_get_db_session():
        session = testing_session_local()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_db_session_read] = override_get_db_session

    with TestClient(app) as test_client:
        yield test_client, testing_session_local

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    get_settings.cache_clear()


def _add_call(
    session_local,
    *,
    project_id: str,
    call_id: str,
    created_at: datetime,
    cost_total: float,
    input_tokens: int = 100,
    output_tokens: int = 40,
    provider: str = "openai",
    model: str = "gpt-4o",
    pricing_last_updated_at: datetime | None = None,
    pricing_source: str = "cached_rate_card",
    cost_confidence: str = "high",
    confidence_reason: str | None = "fresh_pricing_full_baseline",
    exchange_rate_usd_to_inr: float | None = 83.0,
    exchange_rate_timestamp: datetime | None = None,
    exchange_rate_source: str | None = "test_rate_card",
    agent_name: str | None = None,
    user_id: str | None = None,
    call_type: str | None = None,
    metadata: dict | None = None,
) -> None:
    pricing_last_updated_at = pricing_last_updated_at or datetime.now(timezone.utc) - timedelta(days=1)
    exchange_rate_timestamp = exchange_rate_timestamp or created_at
    total_tokens = input_tokens + output_tokens
    with session_local() as session:
        session.add(
            Call(
                id=call_id,
                project_id=project_id,
                event_id=f"event-{call_id}",
                created_at=created_at,
                agent_name=agent_name,
                user_id=user_id,
                call_type=call_type,
                provider=provider,
                model=model,
                status="success",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                reasoning_tokens=0,
                total_tokens=total_tokens,
                cost_total=cost_total,
                reasoning_cost_total=0.0,
                cache_savings_total=0.0,
                pricing_version="test-pricing-v1",
                pricing_source=pricing_source,
                pricing_last_updated_at=pricing_last_updated_at,
                cost_currency="USD",
                token_unit="tokens",
                exchange_rate_usd_to_inr=exchange_rate_usd_to_inr,
                exchange_rate_timestamp=exchange_rate_timestamp if exchange_rate_usd_to_inr is not None else None,
                exchange_rate_source=exchange_rate_source if exchange_rate_usd_to_inr is not None else None,
                cost_confidence=cost_confidence,
                confidence_reason=confidence_reason,
                payload_json=json.dumps({"provider": provider, "model": model}, separators=(",", ":")),
                metadata_json=json.dumps(metadata or {"user_id": "prod-user"}, separators=(",", ":")),
            )
        )
        session.commit()


def _headers(project_id: str) -> dict[str, str]:
    return {"X-Project-Id": project_id}


def _sum_daily_trend(payload: dict) -> float:
    return round(sum(float(point["total_cost_usd"]) for point in payload["points"]), 6)


def test_cost_breakdowns_prefer_first_class_call_attribution_columns(client) -> None:
    test_client, session_local = client
    project_id = "proj-cost-attribution-columns"
    now = datetime.now(timezone.utc)
    _add_call(
        session_local,
        project_id=project_id,
        call_id="baseline-old",
        created_at=now - timedelta(days=14, minutes=5),
        cost_total=0.01,
    )
    _add_call(
        session_local,
        project_id=project_id,
        call_id="expensive-attributed-call",
        created_at=now - timedelta(hours=1),
        cost_total=2.5,
        agent_name="column-agent",
        user_id="column-user",
        call_type="chat",
        metadata={"agent_name": "metadata-agent", "user_id": "metadata-user"},
    )

    by_agent = test_client.get("/v1/analytics/cost/by-agent", headers=_headers(project_id))
    by_user = test_client.get("/v1/analytics/cost/by-user", headers=_headers(project_id))
    top_calls = test_client.get("/v1/analytics/cost/top-calls", headers=_headers(project_id))

    assert by_agent.status_code == 200
    assert by_user.status_code == 200
    assert top_calls.status_code == 200
    assert by_agent.json()["items"][0]["key"] == "column-agent"
    assert by_user.json()["items"][0]["key"] == "column-user"
    top_item = top_calls.json()["items"][0]
    assert top_item["call_id"] == "expensive-attributed-call"
    assert top_item["agent_name"] == "column-agent"
    assert top_item["user_id"] == "column-user"
    assert top_item["call_type"] == "chat"
    assert top_item["cost_confidence"] == "high"
    assert top_item["pricing_source"] == "cached_rate_card"


def test_synthetic_calls_are_excluded_from_cost_totals(client) -> None:
    test_client, session_local = client
    project_id = "proj-cost-synthetic"
    now = datetime.now(timezone.utc)
    _add_call(
        session_local,
        project_id=project_id,
        call_id="baseline-old",
        created_at=now - timedelta(days=14, minutes=5),
        cost_total=0.01,
    )
    _add_call(
        session_local,
        project_id=project_id,
        call_id="prod-call",
        created_at=now - timedelta(hours=1),
        cost_total=0.5,
    )
    _add_call(
        session_local,
        project_id=project_id,
        call_id="synthetic-call",
        created_at=now - timedelta(minutes=30),
        cost_total=9.0,
        metadata={"is_synthetic": True, "user_id": "demo"},
    )

    response = test_client.get("/v1/analytics/cost/daily-trend", headers=_headers(project_id))

    assert response.status_code == 200
    assert _sum_daily_trend(response.json()) == 0.5


def test_less_than_14_days_data_degrades_confidence(client) -> None:
    test_client, session_local = client
    project_id = "proj-cost-short-baseline"
    now = datetime.now(timezone.utc)
    _add_call(
        session_local,
        project_id=project_id,
        call_id="recent-only",
        created_at=now - timedelta(hours=2),
        cost_total=0.25,
    )

    response = test_client.get("/v1/analytics/cost/by-model", headers=_headers(project_id))

    assert response.status_code == 200
    payload = response.json()
    assert payload["cost_confidence"] == "degraded"
    assert payload["confidence_reason"] == "insufficient_data"


def test_stale_pricing_marks_cost_confidence_stale(client) -> None:
    test_client, session_local = client
    project_id = "proj-cost-stale-pricing"
    now = datetime.now(timezone.utc)
    stale_pricing_at = now - timedelta(days=30)
    _add_call(
        session_local,
        project_id=project_id,
        call_id="baseline-old",
        created_at=now - timedelta(days=14, minutes=5),
        cost_total=0.01,
        pricing_last_updated_at=stale_pricing_at,
        cost_confidence="stale",
        confidence_reason="pricing_catalog_stale",
    )
    _add_call(
        session_local,
        project_id=project_id,
        call_id="recent-stale",
        created_at=now - timedelta(hours=1),
        cost_total=0.3,
        pricing_last_updated_at=stale_pricing_at,
        cost_confidence="stale",
        confidence_reason="pricing_catalog_stale",
    )

    response = test_client.get("/v1/analytics/cost/by-user", headers=_headers(project_id))

    assert response.status_code == 200
    payload = response.json()
    assert payload["cost_confidence"] == "stale"
    assert payload["confidence_reason"] == "pricing_catalog_stale"


def test_missing_tokens_degrades_confidence(client) -> None:
    test_client, session_local = client
    project_id = "proj-cost-missing-tokens"
    now = datetime.now(timezone.utc)
    _add_call(
        session_local,
        project_id=project_id,
        call_id="baseline-old",
        created_at=now - timedelta(days=14, minutes=5),
        cost_total=0.01,
    )
    _add_call(
        session_local,
        project_id=project_id,
        call_id="missing-token-call",
        created_at=now - timedelta(hours=1),
        cost_total=0.3,
        input_tokens=0,
        output_tokens=0,
    )

    response = test_client.get("/v1/analytics/cost/reasoning-share", headers=_headers(project_id))

    assert response.status_code == 200
    payload = response.json()
    assert payload["cost_confidence"] == "degraded"
    assert payload["confidence_reason"] == "missing_tokens"


def test_dashboard_cost_total_matches_sum_of_production_calls(client) -> None:
    test_client, session_local = client
    project_id = "proj-cost-dashboard-total"
    now = datetime.now(timezone.utc)
    _add_call(
        session_local,
        project_id=project_id,
        call_id="baseline-old",
        created_at=now - timedelta(days=14, minutes=5),
        cost_total=0.01,
    )
    _add_call(
        session_local,
        project_id=project_id,
        call_id="today-1",
        created_at=now - timedelta(minutes=20),
        cost_total=0.1,
    )
    _add_call(
        session_local,
        project_id=project_id,
        call_id="today-2",
        created_at=now - timedelta(minutes=10),
        cost_total=0.2,
    )
    _add_call(
        session_local,
        project_id=project_id,
        call_id="today-synthetic",
        created_at=now - timedelta(minutes=30),
        cost_total=10.0,
        metadata={"is_synthetic": True},
    )

    summary = test_client.get("/v1/analytics/summary", headers=_headers(project_id)).json()
    trend = test_client.get("/v1/analytics/cost/daily-trend", headers=_headers(project_id)).json()

    assert summary["cost_today_usd"] == pytest.approx(0.3)
    assert _sum_daily_trend(trend) == pytest.approx(0.3)


def test_cost_query_is_deterministic(client) -> None:
    test_client, session_local = client
    project_id = "proj-cost-deterministic"
    now = datetime.now(timezone.utc)
    _add_call(
        session_local,
        project_id=project_id,
        call_id="baseline-old",
        created_at=now - timedelta(days=14, minutes=5),
        cost_total=0.01,
    )
    _add_call(
        session_local,
        project_id=project_id,
        call_id="deterministic-call",
        created_at=now - timedelta(hours=1),
        cost_total=0.42,
    )

    first = test_client.get("/v1/analytics/cost/by-model", headers=_headers(project_id)).json()
    second = test_client.get("/v1/analytics/cost/by-model", headers=_headers(project_id)).json()

    assert first == second


def test_same_call_returns_same_inr_value_across_repeated_queries(client) -> None:
    test_client, session_local = client
    project_id = "proj-cost-inr-deterministic"
    now = datetime.now(timezone.utc)
    _add_call(
        session_local,
        project_id=project_id,
        call_id="audited-call",
        created_at=now - timedelta(minutes=5),
        cost_total=1.25,
        exchange_rate_usd_to_inr=80.0,
        exchange_rate_timestamp=now - timedelta(minutes=5),
        exchange_rate_source="test_static_rate",
    )

    first = test_client.get(
        "/v1/calls/audited-call?display_currency=INR",
        headers=_headers(project_id),
    ).json()
    second = test_client.get(
        "/v1/calls/audited-call?display_currency=INR",
        headers=_headers(project_id),
    ).json()

    assert first["cost_audit"]["cost_total_usd"] == pytest.approx(1.25)
    assert first["cost_audit"]["cost_total_display"] == pytest.approx(100.0)
    assert first["cost_audit"]["display_currency_code"] == "INR"
    assert first["cost_audit"]["display_currency_symbol"] == "₹"
    assert first["cost_audit"]["display_rounding_mode"] == "HALF_UP"
    assert first["cost_audit"]["display_decimal_places"] == 2
    assert first["cost_audit"] == second["cost_audit"]


def test_inr_display_uses_half_up_two_decimal_rounding(client) -> None:
    test_client, session_local = client
    project_id = "proj-cost-inr-rounding"
    now = datetime.now(timezone.utc)
    _add_call(
        session_local,
        project_id=project_id,
        call_id="rounding-call",
        created_at=now - timedelta(minutes=5),
        cost_total=1.0,
        exchange_rate_usd_to_inr=1.005,
        exchange_rate_timestamp=now - timedelta(minutes=5),
    )

    payload = test_client.get(
        "/v1/calls/rounding-call?display_currency=INR",
        headers=_headers(project_id),
    ).json()

    assert payload["cost_audit"]["cost_total_display"] == pytest.approx(1.01)
    assert payload["cost_audit"]["exchange_rate_decimal_places"] == 8


def test_exchange_rate_is_returned_at_eight_decimal_precision(client) -> None:
    test_client, session_local = client
    project_id = "proj-cost-rate-precision"
    now = datetime.now(timezone.utc)
    _add_call(
        session_local,
        project_id=project_id,
        call_id="precision-call",
        created_at=now - timedelta(minutes=5),
        cost_total=1.0,
        exchange_rate_usd_to_inr=83.123456789,
        exchange_rate_timestamp=now - timedelta(minutes=5),
    )

    payload = test_client.get(
        "/v1/calls/precision-call?display_currency=INR",
        headers=_headers(project_id),
    ).json()

    assert payload["cost_audit"]["exchange_rate_used"] == pytest.approx(83.12345679)
    assert payload["cost_audit"]["cost_total_display"] == pytest.approx(83.12)


def test_new_exchange_rate_does_not_reprice_historical_calls(client) -> None:
    test_client, session_local = client
    project_id = "proj-cost-historical-rate"
    now = datetime.now(timezone.utc)
    _add_call(
        session_local,
        project_id=project_id,
        call_id="historical-call",
        created_at=now - timedelta(days=2),
        cost_total=2.0,
        exchange_rate_usd_to_inr=80.0,
        exchange_rate_timestamp=now - timedelta(days=2),
        exchange_rate_source="test_static_rate",
    )
    _add_call(
        session_local,
        project_id=project_id,
        call_id="new-rate-call",
        created_at=now - timedelta(minutes=5),
        cost_total=2.0,
        exchange_rate_usd_to_inr=90.0,
        exchange_rate_timestamp=now - timedelta(minutes=5),
        exchange_rate_source="test_static_rate",
    )

    response = test_client.get(
        "/v1/calls/historical-call?display_currency=INR",
        headers=_headers(project_id),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["cost_audit"]["cost_total_display"] == pytest.approx(160.0)
    assert payload["cost_audit"]["exchange_rate_used"] == pytest.approx(80.0)


def test_missing_exchange_rate_falls_back_to_usd_and_degrades_confidence(client) -> None:
    test_client, session_local = client
    project_id = "proj-cost-missing-exchange-rate"
    now = datetime.now(timezone.utc)
    _add_call(
        session_local,
        project_id=project_id,
        call_id="baseline-old",
        created_at=now - timedelta(days=14, minutes=5),
        cost_total=0.01,
        exchange_rate_usd_to_inr=None,
        exchange_rate_timestamp=None,
        exchange_rate_source=None,
    )
    _add_call(
        session_local,
        project_id=project_id,
        call_id="missing-rate-call",
        created_at=now - timedelta(hours=1),
        cost_total=0.3,
        exchange_rate_usd_to_inr=None,
        exchange_rate_timestamp=None,
        exchange_rate_source=None,
    )

    response = test_client.get(
        "/v1/analytics/cost/by-model?display_currency=INR",
        headers=_headers(project_id),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["display_currency"] == "USD"
    assert payload["cost_total_display"] == pytest.approx(payload["cost_total_usd"])
    assert payload["cost_confidence"] == "degraded"
    assert "missing_exchange_rate" in payload["confidence_reason"]


def test_dashboard_total_in_inr_matches_usd_total_times_stored_rate(client) -> None:
    test_client, session_local = client
    project_id = "proj-cost-inr-dashboard-total"
    now = datetime.now(timezone.utc)
    _add_call(
        session_local,
        project_id=project_id,
        call_id="baseline-old",
        created_at=now - timedelta(days=14, minutes=5),
        cost_total=0.01,
        exchange_rate_usd_to_inr=80.0,
        exchange_rate_timestamp=now - timedelta(days=14, minutes=5),
    )
    _add_call(
        session_local,
        project_id=project_id,
        call_id="today-1",
        created_at=now - timedelta(minutes=20),
        cost_total=0.1,
        exchange_rate_usd_to_inr=80.0,
        exchange_rate_timestamp=now - timedelta(minutes=20),
    )
    _add_call(
        session_local,
        project_id=project_id,
        call_id="today-2",
        created_at=now - timedelta(minutes=10),
        cost_total=0.2,
        exchange_rate_usd_to_inr=80.0,
        exchange_rate_timestamp=now - timedelta(minutes=10),
    )

    payload = test_client.get(
        "/v1/analytics/summary?display_currency=INR",
        headers=_headers(project_id),
    ).json()

    assert payload["cost_total_usd"] == pytest.approx(0.3)
    assert payload["cost_total_display"] == pytest.approx(24.0)
    assert payload["exchange_rate_used"] == pytest.approx(80.0)


def test_synthetic_calls_are_excluded_from_inr_totals(client) -> None:
    test_client, session_local = client
    project_id = "proj-cost-inr-synthetic"
    now = datetime.now(timezone.utc)
    _add_call(
        session_local,
        project_id=project_id,
        call_id="baseline-old",
        created_at=now - timedelta(days=14, minutes=5),
        cost_total=0.01,
        exchange_rate_usd_to_inr=80.0,
    )
    _add_call(
        session_local,
        project_id=project_id,
        call_id="prod-call",
        created_at=now - timedelta(hours=1),
        cost_total=0.5,
        exchange_rate_usd_to_inr=80.0,
    )
    _add_call(
        session_local,
        project_id=project_id,
        call_id="synthetic-call",
        created_at=now - timedelta(minutes=30),
        cost_total=9.0,
        exchange_rate_usd_to_inr=80.0,
        metadata={"is_synthetic": True, "user_id": "demo"},
    )

    payload = test_client.get(
        "/v1/analytics/cost/daily-trend?display_currency=INR",
        headers=_headers(project_id),
    ).json()

    assert payload["cost_total_usd"] == pytest.approx(0.5)
    assert payload["cost_total_display"] == pytest.approx(40.0)
