from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "run_admin_deployment_smoke.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("run_admin_deployment_smoke", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_authenticated_smoke_uses_owner_session_cookie(monkeypatch) -> None:
    module = _load_script()
    calls: list[tuple[str, str, dict[str, str], bytes | None]] = []

    def fake_request(
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: float,
    ) -> Any:
        request_headers = dict(headers or {})
        calls.append((method, url, request_headers, body))
        if url.endswith("/api/owner/session"):
            return module.HttpResult(
                status=200,
                text='{"ok":true}',
                body={"ok": True},
                headers={"set-cookie": "zroky_owner_token=session-value; HttpOnly; Secure; Path=/"},
                final_url=url,
            )
        response_bodies = {
            "/api/zroky/v1/owner/stats": {"total_users": 1, "total_projects": 1},
            "/api/zroky/v1/owner/health": {"overall": "healthy", "services": []},
            "/api/zroky/v1/owner/money-path-health": {"platform": {}, "tenants": []},
            "/api/zroky/v1/owner/pricing/plans": {"plans": [], "drift": {}},
        }
        response = response_bodies[next(path for path in response_bodies if url.endswith(path))]
        return module.HttpResult(status=200, text=json.dumps(response), body=response, headers={}, final_url=url)

    monkeypatch.setattr(module, "_request", fake_request)

    module._check_proxy_with_owner_token("https://ops.example.test", "owner-secret", 3.0)

    assert json.loads(calls[0][3] or b"{}") == {"token": "owner-secret"}
    assert calls[0][2] == {"content-type": "application/json"}
    assert all(headers == {"cookie": "zroky_owner_token=session-value"} for _, _, headers, _ in calls[1:])
