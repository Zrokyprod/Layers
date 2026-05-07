import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app

client = TestClient(app)


def test_internal_exchange_rate_endpoint_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENABLE_INTERNAL_DEBUG_ENDPOINT", raising=False)
    monkeypatch.delenv("INTERNAL_DEBUG_TOKEN", raising=False)
    get_settings.cache_clear()

    try:
        response = client.get("/internal/exchange-rate")
        assert response.status_code == 404
    finally:
        get_settings.cache_clear()


def test_internal_exchange_rate_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENABLE_INTERNAL_DEBUG_ENDPOINT", "true")
    monkeypatch.setenv("INTERNAL_DEBUG_TOKEN", "internal-secret")
    monkeypatch.setenv("INTERNAL_DEBUG_TOKEN_HEADER_NAME", "x-zroky-internal-token")
    monkeypatch.setenv("ZROKY_EXCHANGE_RATE_USD_TO_INR", "84.125")
    monkeypatch.setenv("ZROKY_EXCHANGE_RATE_SOURCE", "configured_static")
    get_settings.cache_clear()

    try:
        unauthorized = client.get("/internal/exchange-rate")
        assert unauthorized.status_code == 401

        authorized = client.get(
            "/internal/exchange-rate",
            headers={"X-Zroky-Internal-Token": "internal-secret"},
        )
        assert authorized.status_code == 200
        payload = authorized.json()
        assert set(payload.keys()) == {
            "checked_at",
            "live_fetch",
            "cache",
            "configured_fallback",
            "resolved_default",
        }

        assert set(payload["live_fetch"].keys()) == {
            "enabled",
            "provider_url",
            "provider_source",
            "refresh_interval_minutes",
            "cache_ttl_seconds",
            "failure_cache_ttl_seconds",
            "max_stale_seconds",
        }
        assert set(payload["cache"].keys()) == {
            "status",
            "exchange_rate_usd_to_inr",
            "exchange_rate_timestamp",
            "fetched_at",
            "exchange_rate_source",
            "cache_age_seconds",
            "is_stale",
            "is_usable",
            "error",
        }
        assert set(payload["configured_fallback"].keys()) == {
            "is_available",
            "exchange_rate_usd_to_inr",
            "exchange_rate_source",
        }
        assert set(payload["resolved_default"].keys()) == {
            "mode",
            "exchange_rate_usd_to_inr",
            "exchange_rate_timestamp",
            "exchange_rate_source",
        }

        assert payload["configured_fallback"]["is_available"] is True
        assert payload["configured_fallback"]["exchange_rate_usd_to_inr"] == pytest.approx(84.125)
        assert payload["resolved_default"]["mode"] in {"configured_static", "live_cached"}
    finally:
        get_settings.cache_clear()


def test_internal_exchange_rate_returns_503_for_misconfigured_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENABLE_INTERNAL_DEBUG_ENDPOINT", "true")
    monkeypatch.delenv("INTERNAL_DEBUG_TOKEN", raising=False)
    get_settings.cache_clear()

    try:
        response = client.get("/internal/exchange-rate")
        assert response.status_code == 503
    finally:
        get_settings.cache_clear()
