import pytest

from app.core.config import get_settings
from app.services import provider_status


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_resolve_provider_status_prefers_payload_context(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fetch_unexpected(*_args, **_kwargs):
        raise AssertionError("fetch should not be called when payload already has provider status")

    monkeypatch.setattr(provider_status, "_fetch_status_from_endpoint", _fetch_unexpected)

    result = provider_status.resolve_provider_status_context(
        provider="openai",
        payload={
            "provider_status": {"status": "operational"},
            "provider_latency_trend_ms": {"p95": 120, "p99": 240},
        },
    )

    assert result["provider_status"] == "operational"
    assert result["provider_latency_p95_ms"] == 120
    assert result["provider_latency_p99_ms"] == 240
    assert result["status_fallback_used"] is False


def test_resolve_provider_status_uses_cache_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        provider_status,
        "_cache_get",
        lambda _provider: {
            "provider_status": "degraded",
            "provider_latency_p95_ms": 900,
            "provider_latency_p99_ms": 1800,
        },
    )

    result = provider_status.resolve_provider_status_context(
        provider="openai",
        payload={"provider_status": "unknown"},
    )

    assert result["provider_status"] == "degraded"
    assert result["provider_latency_p95_ms"] == 900
    assert result["provider_latency_p99_ms"] == 1800
    assert result["status_fallback_used"] is True


def test_resolve_provider_status_fetches_and_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "PROVIDER_STATUS_ENDPOINTS_JSON",
        '{"openai":"https://status.example/openai"}',
    )

    monkeypatch.setattr(provider_status, "_cache_get", lambda _provider: None)
    monkeypatch.setattr(
        provider_status,
        "_fetch_status_from_endpoint",
        lambda **_kwargs: {
            "provider_status": "operational",
            "provider_latency_p95_ms": 340,
            "provider_latency_p99_ms": 650,
        },
    )

    writes: list[tuple[str, dict, int]] = []

    def _cache_set(provider: str, payload: dict, ttl: int) -> None:
        writes.append((provider, payload, ttl))

    monkeypatch.setattr(provider_status, "_cache_set", _cache_set)

    result = provider_status.resolve_provider_status_context(
        provider="openai",
        payload={"provider_status": "unknown"},
    )

    assert result["provider_status"] == "operational"
    assert result["status_fallback_used"] is False
    assert writes
    assert writes[0][0] == "openai"


def test_resolve_provider_status_returns_unknown_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "PROVIDER_STATUS_ENDPOINTS_JSON",
        '{"openai":"https://status.example/openai"}',
    )
    monkeypatch.setattr(provider_status, "_cache_get", lambda _provider: None)
    monkeypatch.setattr(provider_status, "_fetch_status_from_endpoint", lambda **_kwargs: None)

    result = provider_status.resolve_provider_status_context(
        provider="openai",
        payload={"provider_latency_trend_ms": {"p95": 2200, "p99": 4300}},
    )

    assert result["provider_status"] == "unknown"
    assert result["provider_latency_p95_ms"] == 2200
    assert result["provider_latency_p99_ms"] == 4300
    assert result["status_fallback_used"] is True


def test_verify_provider_connection_success_from_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "PROVIDER_STATUS_ENDPOINTS_JSON",
        '{"openai":"https://status.example/openai"}',
    )
    monkeypatch.setattr(
        provider_status,
        "_fetch_status_from_endpoint",
        lambda **_kwargs: {
            "provider_status": "operational",
            "provider_latency_p95_ms": 250,
            "provider_latency_p99_ms": 480,
        },
    )
    monkeypatch.setattr(provider_status, "_cache_get", lambda _provider: None)

    cache_writes: list[tuple[str, dict, int]] = []

    def _cache_set(provider: str, payload: dict, ttl: int) -> None:
        cache_writes.append((provider, payload, ttl))

    monkeypatch.setattr(provider_status, "_cache_set", _cache_set)

    result = provider_status.verify_provider_connection("openai")

    assert result["verified"] is True
    assert result["provider_status"] == "operational"
    assert result["status_fallback_used"] is False
    assert cache_writes


def test_verify_provider_connection_prefers_credential_probe_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        provider_status,
        "_probe_provider_credentials",
        lambda **_kwargs: (True, None),
    )
    monkeypatch.setattr(
        provider_status,
        "_fetch_status_from_endpoint",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("status endpoint fetch should not run after credential probe success")
        ),
    )

    result = provider_status.verify_provider_connection("openai")

    assert result["verified"] is True
    assert result["provider_status"] == "operational"
    assert result["status_fallback_used"] is False
    assert "credentialed" in result["message"].lower()


def test_verify_provider_connection_returns_failed_on_credential_probe_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        provider_status,
        "_probe_provider_credentials",
        lambda **_kwargs: (False, "Provider rejected credentials."),
    )
    monkeypatch.setattr(
        provider_status,
        "_cache_get",
        lambda _provider: (_ for _ in ()).throw(
            AssertionError("cache should not be used after credential probe failure")
        ),
    )

    result = provider_status.verify_provider_connection("openai")

    assert result["verified"] is False
    assert result["provider_status"] == "unknown"
    assert result["status_fallback_used"] is False
    assert "rejected credentials" in result["message"].lower()


def test_verify_provider_connection_fails_when_endpoint_missing() -> None:
    result = provider_status.verify_provider_connection("openai")

    assert result["verified"] is False
    assert result["provider_status"] == "unknown"
    assert "not configured" in result["message"]


def test_verify_provider_connection_uses_cached_status_when_fetch_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "PROVIDER_STATUS_ENDPOINTS_JSON",
        '{"openai":"https://status.example/openai"}',
    )
    monkeypatch.setattr(provider_status, "_fetch_status_from_endpoint", lambda **_kwargs: None)
    monkeypatch.setattr(
        provider_status,
        "_cache_get",
        lambda _provider: {
            "provider_status": "degraded",
            "provider_latency_p95_ms": 910,
            "provider_latency_p99_ms": 1700,
        },
    )

    result = provider_status.verify_provider_connection("openai")

    assert result["verified"] is True
    assert result["provider_status"] == "degraded"
    assert result["status_fallback_used"] is True
    assert "cached" in result["message"].lower()
