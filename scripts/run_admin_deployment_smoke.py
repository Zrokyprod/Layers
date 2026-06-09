from __future__ import annotations

import argparse
import http.client
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


DEFAULT_ADMIN_URL = "https://ops.zroky.com"


@dataclass
class HttpResult:
    status: int
    text: str
    body: Any
    headers: dict[str, str]
    final_url: str


class SmokeFailure(RuntimeError):
    pass


def _json_or_none(text: str) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}/{path.lstrip('/')}"


def _request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 20.0,
) -> HttpResult:
    attempts = 3 if method.upper() in {"GET", "HEAD"} else 1
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(url=url, method=method, headers=dict(headers or {}))
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                text = response.read().decode("utf-8", errors="replace")
                return HttpResult(
                    status=response.status,
                    text=text,
                    body=_json_or_none(text),
                    headers={k.lower(): v for k, v in response.headers.items()},
                    final_url=response.geturl(),
                )
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            return HttpResult(
                status=exc.code,
                text=text,
                body=_json_or_none(text),
                headers={k.lower(): v for k, v in exc.headers.items()},
                final_url=url,
            )
        except (http.client.IncompleteRead, urllib.error.URLError) as exc:
            if attempt >= attempts:
                reason = getattr(exc, "reason", None) or str(exc)
                raise SmokeFailure(f"{method} {url} failed: {reason}") from exc
            time.sleep(0.75 * attempt)

    raise SmokeFailure(f"{method} {url} failed after {attempts} attempts")


def _pass(label: str, detail: str = "") -> None:
    suffix = f" - {detail}" if detail else ""
    print(f"[PASS] {label}{suffix}")


def _skip(label: str, detail: str) -> None:
    print(f"[SKIP] {label} - {detail}")


def _fail(label: str, detail: str) -> None:
    raise SmokeFailure(f"{label}: {detail}")


def _expect_status(result: HttpResult, expected: int | set[int], label: str) -> None:
    expected_set = {expected} if isinstance(expected, int) else expected
    if result.status not in expected_set:
        _fail(label, f"expected HTTP {sorted(expected_set)}, got {result.status}: {result.text[:600]}")


def _require_json_object(result: HttpResult, label: str) -> dict[str, Any]:
    if not isinstance(result.body, dict):
        _fail(label, f"expected JSON object, got: {result.text[:600]}")
    return result.body


def _check_owner_routes(admin_url: str, timeout: float) -> None:
    routes = [
        "/",
        "/owner",
        "/owner/money-path",
        "/owner/projects",
        "/owner/pricing",
        "/owner/ops",
        "/owner/infrastructure",
        "/owner/support",
        "/owner/audit",
        "/owner/settings",
    ]
    for route in routes:
        result = _request("GET", _url(admin_url, route), timeout=timeout)
        _expect_status(result, 200, f"admin route {route}")
        if "Zroky" not in result.text and "__next" not in result.text:
            _fail(f"admin route {route}", "response did not look like a Next.js page")
        _pass(f"admin route {route}", f"status=200 final={urllib.parse.urlparse(result.final_url).path or '/'}")


def _check_security_headers(admin_url: str, timeout: float) -> None:
    result = _request("GET", _url(admin_url, "/owner"), timeout=timeout)
    _expect_status(result, 200, "admin security headers")
    expected = {
        "x-frame-options": "DENY",
        "x-content-type-options": "nosniff",
        "referrer-policy": "strict-origin-when-cross-origin",
    }
    for key, value in expected.items():
        actual = result.headers.get(key)
        if actual != value:
            _fail("admin security headers", f"{key} expected {value!r}, got {actual!r}")
    csp = result.headers.get("content-security-policy", "")
    if "frame-ancestors 'none'" not in csp:
        _fail("admin security headers", "CSP missing frame-ancestors 'none'")
    _pass("admin security headers", "CSP and clickjacking headers present")


def _check_proxy_without_owner_token(admin_url: str, timeout: float) -> None:
    result = _request("GET", _url(admin_url, "/api/zroky/v1/owner/stats"), timeout=timeout)
    if result.status == 200:
        _fail("admin proxy no-token guard", "owner stats returned 200 without x-zroky-admin-token")
    if result.status == 404:
        _fail(
            "admin proxy owner route availability",
            "owner stats returned 404; backend likely has FEATURE_LEGACY_OWNER=false",
        )
    if result.status >= 500:
        _fail("admin proxy backend configuration", f"expected auth rejection, got {result.status}: {result.text[:600]}")
    _expect_status(result, {401, 403}, "admin proxy no-token guard")
    _pass("admin proxy no-token guard", f"status={result.status}")


def _check_owner_json_fields(body: dict[str, Any], fields: list[str], label: str) -> None:
    missing = [field for field in fields if field not in body]
    if missing:
        _fail(label, f"missing fields: {', '.join(missing)}")


def _check_proxy_with_owner_token(admin_url: str, owner_token: str, timeout: float) -> None:
    headers = {"x-zroky-admin-token": owner_token}
    checks = [
        ("/api/zroky/v1/owner/stats", ["total_users", "total_projects"], "owner stats"),
        ("/api/zroky/v1/owner/health", ["overall", "services"], "owner health"),
        ("/api/zroky/v1/owner/money-path-health", ["platform", "tenants"], "owner money-path health"),
        ("/api/zroky/v1/owner/pricing/plans", ["plans", "drift"], "owner pricing plans"),
    ]
    for path, fields, label in checks:
        result = _request("GET", _url(admin_url, path), headers=headers, timeout=timeout)
        _expect_status(result, 200, f"admin proxy {label}")
        body = _require_json_object(result, f"admin proxy {label}")
        _check_owner_json_fields(body, fields, f"admin proxy {label}")
        _pass(f"admin proxy {label}", "status=200")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 10.10 smoke checks against the deployed owner dashboard.")
    parser.add_argument("--admin-url", default=os.environ.get("ZROKY_ADMIN_URL", DEFAULT_ADMIN_URL))
    parser.add_argument("--owner-token", default=os.environ.get("ZROKY_OWNER_TOKEN") or os.environ.get("ZROKY_ADMIN_TOKEN"))
    parser.add_argument("--require-owner-token", action="store_true")
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()

    admin_url = args.admin_url.rstrip("/")
    owner_token = str(args.owner_token or "")

    try:
        _check_owner_routes(admin_url, args.timeout)
        _check_security_headers(admin_url, args.timeout)
        _check_proxy_without_owner_token(admin_url, args.timeout)
        if owner_token:
            _check_proxy_with_owner_token(admin_url, owner_token, args.timeout)
        elif args.require_owner_token:
            _fail("admin proxy authenticated owner smoke", "ZROKY_OWNER_TOKEN or --owner-token is required")
        else:
            _skip("admin proxy authenticated owner smoke", "set ZROKY_OWNER_TOKEN to verify live owner API data")
    except SmokeFailure as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    print(f"[DONE] admin deployment smoke admin_url={admin_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
