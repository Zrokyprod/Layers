from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "run_final_product_smoke.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("run_final_product_smoke", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_final_product_smoke_checks_final_api_and_dashboard_surfaces(monkeypatch, capsys) -> None:
    module = _load_script()
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    monkeypatch.setattr(module, "_load_cookie_header", lambda _auth_state_path: "zroky_access_token=token")

    def fake_request(
        method: str,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        timeout: float,
        headers: dict[str, str] | None = None,
    ):
        calls.append((method, url, payload))
        if url.endswith("/health/live") or url.endswith("/api/zroky/health/live"):
            return module.HttpResult(status=200, text='{"status":"ok"}', body={"status": "ok"}, final_url=url, set_cookies=[])
        if url.endswith("/health/ready"):
            return module.HttpResult(
                status=200,
                text='{"status":"ok","checks":{"database":"ok","redis":"ok"}}',
                body={"status": "ok", "checks": {"database": "ok", "redis": "ok"}},
                final_url=url,
                set_cookies=[],
            )
        if url.endswith("/api/auth/set-session"):
            return module.HttpResult(
                status=200,
                text='{"ok":true}',
                body={"ok": True},
                final_url=url,
                set_cookies=["zroky_access_token=final-smoke-access-token; HttpOnly; Secure"],
            )
        if url.startswith("https://api.example.test/"):
            return module.HttpResult(status=401, text='{"detail":"Not authenticated"}', body={}, final_url=url, set_cookies=[])
        return module.HttpResult(status=200, text="<html>__next_f</html>", body=None, final_url=url, set_cookies=[])

    monkeypatch.setattr(module, "_request", fake_request)

    assert (
        module.main(
            [
                "--api-base-url",
                "https://api.example.test",
                "--dashboard-url",
                "https://app.example.test",
                "--dashboard-auth-state",
                "auth-state.json",
                "--timeout-seconds",
                "3",
            ]
        )
        == 0
    )

    requested_urls = [url for _method, url, _payload in calls]
    for path in module.FINAL_API_PROTECTED_PATHS:
        assert f"https://api.example.test{path}" in requested_urls
    for path in module.FINAL_DASHBOARD_PATHS:
        assert f"https://app.example.test{path}" not in requested_urls
    assert "goldens" not in "\n".join(requested_urls)
    assert "replay" not in "\n".join(requested_urls)
    assert "[final-product-smoke] passed" in capsys.readouterr().out


def test_final_product_smoke_fails_when_final_dashboard_route_is_missing(monkeypatch) -> None:
    module = _load_script()

    monkeypatch.setattr(module, "_load_cookie_header", lambda _auth_state_path: "zroky_access_token=token")

    def fake_request(
        method: str,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        timeout: float,
        headers: dict[str, str] | None = None,
    ):
        if url.endswith("/health/live") or url.endswith("/api/zroky/health/live"):
            return module.HttpResult(status=200, text='{"status":"ok"}', body={"status": "ok"}, final_url=url, set_cookies=[])
        if url.endswith("/health/ready"):
            return module.HttpResult(
                status=200,
                text='{"status":"ok","checks":{"database":"ok","redis":"ok"}}',
                body={"status": "ok", "checks": {"database": "ok", "redis": "ok"}},
                final_url=url,
                set_cookies=[],
            )
        if url.endswith("/api/auth/set-session"):
            return module.HttpResult(
                status=200,
                text="ok",
                body=None,
                final_url=url,
                set_cookies=["zroky_access_token=value; HttpOnly"],
            )
        if url.startswith("https://api.example.test/"):
            return module.HttpResult(status=401, text="", body=None, final_url=url, set_cookies=[])
        if url.endswith("/operations"):
            return module.HttpResult(status=404, text="This page could not be found.", body=None, final_url=url, set_cookies=[])
        return module.HttpResult(status=200, text="<html>__next_f</html>", body=None, final_url=url, set_cookies=[])

    monkeypatch.setattr(module, "_request", fake_request)

    assert (
        module.main(
            [
                "--api-base-url",
                "https://api.example.test",
                "--dashboard-url",
                "https://app.example.test",
                "--dashboard-auth-state",
                "auth-state.json",
                "--check-protected-dashboard-routes",
            ]
        )
        == 1
    )
