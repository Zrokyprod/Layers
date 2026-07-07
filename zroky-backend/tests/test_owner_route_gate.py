from __future__ import annotations

import importlib
import sys

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


def _reload_api_router(monkeypatch, **env: str):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    sys.modules.pop("app.api.router", None)
    return importlib.import_module("app.api.router")


def _router_tags(router_module) -> set[str]:
    tags: set[str] = set()
    for route in router_module.api_router.routes:
        tags.update(getattr(route, "tags", []) or [])
    return tags


def _owner_headers(monkeypatch, token: str = "owner-secret") -> dict[str, str]:
    monkeypatch.setenv("REQUIRE_PROVISIONING_TOKEN", "false")
    monkeypatch.setenv("PROVISIONING_TOKEN", token)
    get_settings.cache_clear()
    return {"x-zroky-admin-token": token}


def test_owner_router_not_mounted_when_legacy_owner_disabled(monkeypatch) -> None:
    router_module = _reload_api_router(monkeypatch, FEATURE_LEGACY_OWNER="false")
    paths = sorted({getattr(route, "path", "") for route in router_module.api_router.routes})

    assert not any(path.startswith("/v1/owner") for path in paths)

    sys.modules.pop("app.api.router", None)
    get_settings.cache_clear()


def test_launch_legacy_surfaces_are_hidden_but_control_dependencies_stay_mounted(monkeypatch) -> None:
    router_module = _reload_api_router(
        monkeypatch,
        FEATURE_LEGACY_OBSERVABILITY_API="false",
        FEATURE_LEGACY_REPLAY_API="false",
        FEATURE_LEGACY_DIAGNOSIS_API="false",
        FEATURE_LEGACY_ISSUES_API="false",
        FEATURE_LEGACY_DIAGNOSIS_ALIAS="false",
    )
    tags = _router_tags(router_module)

    hidden_tags = {
        "ablation",
        "analytics",
        "ask",
        "contracts",
        "detectors",
        "diagnoses",
        "diagnosis",
        "digest",
        "fix-events",
        "goldens",
        "intel",
        "issues",
        "judge-calibration",
        "judge-health",
        "live",
        "provider-drift",
        "recommendations",
        "regression-ci",
        "reliability",
        "replay",
        "replay-dispatch",
        "replay-runs",
    }
    assert tags.isdisjoint(hidden_tags)

    assert {"calls", "traces", "alerts", "notifications"}.issubset(tags)
    assert {"home", "outcomes", "verified-actions", "integrations"}.issubset(tags)

    sys.modules.pop("app.api.router", None)
    get_settings.cache_clear()


def test_owner_route_requires_token_even_when_global_provisioning_is_disabled(monkeypatch) -> None:
    monkeypatch.setenv("REQUIRE_PROVISIONING_TOKEN", "false")
    monkeypatch.setenv("PROVISIONING_TOKEN", "owner-secret")
    get_settings.cache_clear()

    client = TestClient(app)

    missing = client.get("/v1/owner/health")
    assert missing.status_code == 401
    assert missing.json()["detail"] == "Invalid owner credentials."

    wrong = client.get("/v1/owner/health", headers={"x-zroky-admin-token": "wrong"})
    assert wrong.status_code == 401
    assert wrong.json()["detail"] == "Invalid owner credentials."

    get_settings.cache_clear()


def test_owner_route_accepts_valid_owner_token(monkeypatch) -> None:
    monkeypatch.setenv("REQUIRE_PROVISIONING_TOKEN", "false")
    monkeypatch.setenv("PROVISIONING_TOKEN", "owner-secret")
    get_settings.cache_clear()

    client = TestClient(app)

    response = client.get("/v1/owner/health", headers={"x-zroky-admin-token": "owner-secret"})
    assert response.status_code == 200
    assert "services" in response.json()

    get_settings.cache_clear()


def test_owner_production_readiness_blocks_default_local_config(monkeypatch) -> None:
    headers = _owner_headers(monkeypatch)
    client = TestClient(app)

    response = client.get("/v1/owner/production-readiness", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["overall_status"] == "blocked"
    codes = {check["code"]: check for check in payload["checks"]}
    assert codes["app_env"]["status"] == "fail"
    assert codes["database_url"]["status"] == "fail"
    assert codes["redis_url"]["status"] == "fail"
    assert any(blocker.startswith("app_env:") for blocker in payload["hard_blockers"])

    get_settings.cache_clear()


def test_owner_production_readiness_passes_with_required_launch_config(monkeypatch) -> None:
    secret_values = {
        "PROVISIONING_TOKEN": "owner-secret-production",
        "AUTH_JWT_SECRET": "production-auth-jwt-secret",
        "OAUTH_STATE_SECRET": "production-oauth-state-secret",
        "GITHUB_WEBHOOK_SECRET": "production-github-webhook-secret",
        "PROVIDER_KEY_VAULT_KEK": "x" * 40,
        "OPENROUTER_API_KEY": "openrouter-production-key",
        "REPLAY_WORKER_TOKEN": "replay-worker-production-token",
        "RAZORPAY_KEY_SECRET": "razorpay-production-secret",
        "RAZORPAY_WEBHOOK_SECRET": "razorpay-webhook-production-secret",
        "PII_ENCRYPTION_KEY": "pii-production-secret",
        "METRICS_TOKEN": "metrics-production-secret",
    }
    config_values = {
        "APP_ENV": "production",
        "DATABASE_URL": "postgresql://zroky:secret@db.example.com/zroky",
        "REDIS_URL": "redis://redis.example.com:6379/0",
        "ALLOWED_ORIGINS": "https://zroky.com,https://admin.zroky.com",
        "TRUSTED_HOSTS": "api.zroky.com",
        "FEATURE_LEGACY_OWNER": "true",
        "ALLOW_PROJECT_HEADER_CONTEXT": "false",
        "REQUIRE_PROVISIONING_TOKEN": "true",
        "REPLAY_REAL_LLM_ENABLED": "true",
        "BILLING_ENFORCE_QUOTA": "true",
        "BILLING_QUOTA_FAILURE_POLICY": "strict",
        "BILLING_ENABLED": "true",
        "BILLING_PROVIDER": "razorpay",
        "RAZORPAY_KEY_ID": "rzp_live_123456789",
        "ENABLE_METRICS_ENDPOINT": "true",
        **secret_values,
    }
    for key, value in config_values.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()

    client = TestClient(app)
    response = client.get(
        "/v1/owner/production-readiness",
        headers={"x-zroky-admin-token": secret_values["PROVISIONING_TOKEN"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["overall_status"] == "pass"
    assert payload["hard_blockers"] == []
    assert all(
        check["status"] == "pass"
        for check in payload["checks"]
        if check["required_for_launch"]
    )

    response_text = response.text
    assert all(secret not in response_text for secret in secret_values.values())

    get_settings.cache_clear()
