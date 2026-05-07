from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app

client = TestClient(app)


def test_liveness() -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"


def test_readiness_default_skips_checks() -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"ok", "degraded"}
    assert "database" in payload["checks"]
    assert "redis" in payload["checks"]


def test_request_id_header_is_returned() -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert "X-Request-Id" in response.headers
    assert response.headers["X-Request-Id"].strip()


def test_metrics_endpoint_returns_prometheus_payload() -> None:
    warmup = client.get("/health/live")
    assert warmup.status_code == 200

    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")
    assert "zroky_http_requests_total" in response.text


def test_metrics_endpoint_requires_token_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("METRICS_TOKEN", "metrics-secret")
    get_settings.cache_clear()

    try:
        unauthorized = client.get("/metrics")
        assert unauthorized.status_code == 401

        authorized = client.get("/metrics", headers={"X-Zroky-Metrics-Token": "metrics-secret"})
        assert authorized.status_code == 200
    finally:
        get_settings.cache_clear()
