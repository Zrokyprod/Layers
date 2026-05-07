from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import get_settings
from app.services import currency


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_resolve_ingest_exchange_rate_prefers_payload_rate(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_at = datetime(2026, 4, 28, 12, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(
        currency,
        "_cached_live_usd_to_inr_rate",
        lambda *, now: (83.12345678, now - timedelta(minutes=5), "live_exchangerate_host_cached"),
    )

    result = currency.resolve_ingest_exchange_rate(
        {
            "exchange_rate_usd_to_inr": 81.333333333,
            "exchange_rate_timestamp": "2026-04-28T10:00:00+00:00",
            "exchange_rate_source": "sdk_payload",
        },
        captured_at=captured_at,
    )

    assert result["exchange_rate_usd_to_inr"] == pytest.approx(81.33333333)
    assert result["exchange_rate_source"] == "sdk_payload"
    assert result["exchange_rate_timestamp"] == datetime(2026, 4, 28, 10, 0, tzinfo=timezone.utc)


def test_resolve_ingest_exchange_rate_uses_cached_live_rate(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_at = datetime(2026, 4, 28, 12, 0, tzinfo=timezone.utc)

    monkeypatch.delenv("ZROKY_EXCHANGE_RATE_USD_TO_INR", raising=False)
    monkeypatch.setattr(
        currency,
        "_cached_live_usd_to_inr_rate",
        lambda *, now: (83.987654321, now - timedelta(minutes=3), "live_exchangerate_host_cached"),
    )

    result = currency.resolve_ingest_exchange_rate({}, captured_at=captured_at)

    assert result["exchange_rate_usd_to_inr"] == pytest.approx(83.98765432)
    assert result["exchange_rate_source"] == "live_exchangerate_host_cached"
    assert result["exchange_rate_timestamp"] == captured_at - timedelta(minutes=3)


def test_resolve_ingest_exchange_rate_falls_back_to_configured_static(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_at = datetime(2026, 4, 28, 12, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(currency, "_cached_live_usd_to_inr_rate", lambda *, now: (None, None, None))
    monkeypatch.setenv("ZROKY_EXCHANGE_RATE_USD_TO_INR", "84.75")
    monkeypatch.setenv("ZROKY_EXCHANGE_RATE_SOURCE", "configured_static")

    result = currency.resolve_ingest_exchange_rate({}, captured_at=captured_at)

    assert result["exchange_rate_usd_to_inr"] == pytest.approx(84.75)
    assert result["exchange_rate_source"] == "configured_static"
    assert result["exchange_rate_timestamp"] == captured_at


def test_cached_live_rate_is_rejected_when_stale(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime(2026, 4, 28, 12, 0, tzinfo=timezone.utc)
    stale_at = now - timedelta(hours=2)

    monkeypatch.setenv("EXCHANGE_RATE_ENABLE_LIVE_FETCH", "true")
    monkeypatch.setenv("EXCHANGE_RATE_MAX_STALE_SECONDS", "60")
    monkeypatch.setattr(
        currency,
        "_cache_get",
        lambda: {
            "status": "ok",
            "exchange_rate_usd_to_inr": 83.42,
            "exchange_rate_timestamp": stale_at.isoformat(),
            "exchange_rate_source": "live_exchangerate_host",
            "fetched_at": stale_at.isoformat(),
        },
    )

    rate, timestamp, source = currency._cached_live_usd_to_inr_rate(now=now)

    assert rate is None
    assert timestamp is None
    assert source is None


def test_refresh_live_exchange_rate_success_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXCHANGE_RATE_ENABLE_LIVE_FETCH", "true")
    monkeypatch.setenv("EXCHANGE_RATE_CACHE_TTL_SECONDS", "1200")
    monkeypatch.setenv("EXCHANGE_RATE_PROVIDER_SOURCE", "live_exchangerate_host")

    captured_cache: dict[str, object] = {}

    def _capture_cache(payload: dict, ttl_seconds: int) -> None:
        captured_cache["payload"] = payload
        captured_cache["ttl"] = ttl_seconds

    monkeypatch.setattr(currency, "_cache_get", lambda: None)
    monkeypatch.setattr(
        currency,
        "_fetch_live_exchange_rate_payload",
        lambda: {
            "base": "USD",
            "date": "2026-04-28",
            "rates": {"INR": 83.556677889},
        },
    )
    monkeypatch.setattr(currency, "_cache_set", _capture_cache)

    result = currency.refresh_live_usd_to_inr_rate(force=True)

    assert result["status"] == "ok"
    assert result["exchange_rate_source"] == "live_exchangerate_host"
    assert result["exchange_rate_usd_to_inr"] == pytest.approx(83.55667789)
    assert captured_cache["ttl"] == 1200
    payload = captured_cache["payload"]
    assert isinstance(payload, dict)
    assert payload["status"] == "ok"


def test_refresh_live_exchange_rate_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXCHANGE_RATE_ENABLE_LIVE_FETCH", "false")

    result = currency.refresh_live_usd_to_inr_rate(force=True)

    assert result["status"] == "disabled"
    assert result["exchange_rate_usd_to_inr"] is None
