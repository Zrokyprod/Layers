from __future__ import annotations

import importlib
import sys

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


def test_owner_router_not_mounted_when_legacy_owner_disabled(monkeypatch) -> None:
    monkeypatch.setenv("FEATURE_LEGACY_OWNER", "false")

    from app.core.config import get_settings

    get_settings.cache_clear()
    sys.modules.pop("app.api.router", None)

    router_module = importlib.import_module("app.api.router")
    paths = sorted({getattr(route, "path", "") for route in router_module.api_router.routes})

    assert not any(path.startswith("/v1/owner") for path in paths)

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
