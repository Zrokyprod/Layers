from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


FINAL_API_PROTECTED_PATHS = (
    "/v1/action-intents",
    "/v1/action-execution-attempts",
    "/v1/incidents",
    "/v1/outcomes/reconciliation",
    "/v1/policy/approval-requirements",
    "/v1/assurance-packs",
    "/v1/integrations/system-of-record/ledger-refund/status",
)

FINAL_DASHBOARD_PATHS = (
    "/operations",
    "/workflows",
    "/integrations",
    "/evidence",
    "/policies",
    "/approvals",
    "/outcomes",
)


@dataclass
class HttpResult:
    status: int
    text: str
    body: Any
    final_url: str
    set_cookies: list[str]


class SmokeFailure(RuntimeError):
    pass


def _parse_json(text: str) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _url(base_url: str, path: str) -> str:
    return urllib.parse.urljoin(f"{base_url.rstrip('/')}/", path.lstrip("/"))


def _request(
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: float,
    headers: dict[str, str] | None = None,
) -> HttpResult:
    request_headers: dict[str, str] = dict(headers or {})
    data: bytes | None = None
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(url=url, method=method, headers=request_headers, data=data)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8", errors="replace")
            return HttpResult(
                status=response.status,
                text=text,
                body=_parse_json(text),
                final_url=response.geturl(),
                set_cookies=response.headers.get_all("Set-Cookie") or [],
            )
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        return HttpResult(
            status=exc.code,
            text=text,
            body=_parse_json(text),
            final_url=url,
            set_cookies=exc.headers.get_all("Set-Cookie") or [],
        )


def _pass(label: str, detail: str = "") -> None:
    suffix = f" - {detail}" if detail else ""
    print(f"[PASS] {label}{suffix}")


def _fail(label: str, detail: str) -> None:
    raise SmokeFailure(f"{label}: {detail}")


def _require_status(result: HttpResult, expected: set[int], label: str) -> None:
    if result.status not in expected:
        _fail(label, f"expected HTTP {sorted(expected)}, got {result.status}: {result.text[:500]}")


def _check_backend(api_base_url: str, *, timeout: float, allow_skipped_ready_checks: bool) -> None:
    live = _request("GET", _url(api_base_url, "/health/live"), timeout=timeout)
    _require_status(live, {200}, "backend live health")
    if not isinstance(live.body, dict) or live.body.get("status") != "ok":
        _fail("backend live health", f"unexpected body: {live.text[:500]}")
    _pass("backend live health", "status=ok")

    ready = _request("GET", _url(api_base_url, "/health/ready"), timeout=timeout)
    _require_status(ready, {200}, "backend ready health")
    ready_body = ready.body if isinstance(ready.body, dict) else {}
    checks = ready_body.get("checks") if isinstance(ready_body.get("checks"), dict) else {}
    accepted = {"ok", "skipped"} if allow_skipped_ready_checks else {"ok"}
    if ready_body.get("status") != "ok" or checks.get("database") not in accepted or checks.get("redis") not in accepted:
        _fail("backend ready health", f"expected status=ok database/redis={sorted(accepted)}, got {ready.text[:500]}")
    _pass("backend ready health", "database/redis ready")

    for path in FINAL_API_PROTECTED_PATHS:
        result = _request("GET", _url(api_base_url, path), timeout=timeout)
        _require_status(result, {401, 403, 405}, f"final API protected route {path}")
        _pass(f"final API protected route {path}", f"guarded with HTTP {result.status}")


def _load_cookie_header(auth_state_path: str | None) -> str:
    if not auth_state_path:
        return ""
    state = json.loads(Path(auth_state_path).read_text(encoding="utf-8"))
    cookies = state.get("cookies") if isinstance(state, dict) else None
    if not isinstance(cookies, list):
        return ""
    pairs = []
    for cookie in cookies:
        if isinstance(cookie, dict) and cookie.get("name") and cookie.get("value"):
            pairs.append(f"{cookie['name']}={cookie['value']}")
    return "; ".join(pairs)


def _check_dashboard(
    dashboard_url: str,
    *,
    timeout: float,
    auth_state_path: str | None,
    check_protected_routes: bool,
) -> None:
    login = _request("GET", _url(dashboard_url, "/login"), timeout=timeout)
    _require_status(login, {200}, "dashboard login render")
    if "__next_f" not in login.text and "auth-shell" not in login.text:
        _fail("dashboard login render", "missing Next/auth render markers")
    _pass("dashboard login render", login.final_url)

    proxy = _request("GET", _url(dashboard_url, "/api/zroky/health/live"), timeout=timeout)
    _require_status(proxy, {200}, "dashboard API proxy")
    if not isinstance(proxy.body, dict) or proxy.body.get("status") != "ok":
        _fail("dashboard API proxy", f"unexpected body: {proxy.text[:500]}")
    _pass("dashboard API proxy", "backend health proxied")

    session = _request(
        "POST",
        _url(dashboard_url, "/api/auth/set-session"),
        payload={
            "access_token": "final-smoke-access-token",
            "refresh_token": "final-smoke-refresh-token",
            "access_max_age_seconds": 60,
            "refresh_max_age_seconds": 120,
        },
        timeout=timeout,
    )
    _require_status(session, {200}, "dashboard secure session cookie")
    cookies = ",".join(session.set_cookies)
    if "zroky_access_token=" not in cookies or "HttpOnly" not in cookies:
        _fail("dashboard secure session cookie", "access cookie was not HttpOnly")
    _pass("dashboard secure session cookie", "HttpOnly access cookie emitted")

    if not check_protected_routes:
        print("[SKIP] final dashboard protected routes skipped (covered by authenticated browser E2E)")
        return

    cookie_header = _load_cookie_header(auth_state_path)
    if not cookie_header:
        print("[SKIP] final dashboard protected routes skipped (no dashboard auth state provided)")
        return
    for path in FINAL_DASHBOARD_PATHS:
        result = _request(
            "GET",
            _url(dashboard_url, path),
            timeout=timeout,
            headers={"Cookie": cookie_header},
        )
        _require_status(result, {200}, f"final dashboard route {path}")
        if "This page could not be found" in result.text or "Requested resource was not found" in result.text:
            _fail(f"final dashboard route {path}", "route returned not-found content")
        _pass(f"final dashboard route {path}", result.final_url)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run final Zroky API and dashboard deployment smoke checks.")
    parser.add_argument("--api-base-url", required=True)
    parser.add_argument("--dashboard-url", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--allow-skipped-ready-checks", action="store_true")
    parser.add_argument("--dashboard-auth-state", default="", help="Optional Playwright auth state JSON for protected route smoke.")
    parser.add_argument("--check-protected-dashboard-routes", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        _check_backend(
            args.api_base_url,
            timeout=args.timeout_seconds,
            allow_skipped_ready_checks=args.allow_skipped_ready_checks,
        )
        _check_dashboard(
            args.dashboard_url,
            timeout=args.timeout_seconds,
            auth_state_path=args.dashboard_auth_state or None,
            check_protected_routes=args.check_protected_dashboard_routes,
        )
    except SmokeFailure as exc:
        print(f"[FAIL] {exc}")
        return 1
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return 2

    print("[final-product-smoke] passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
