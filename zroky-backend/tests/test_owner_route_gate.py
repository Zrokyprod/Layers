from __future__ import annotations

import importlib
import sys


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
