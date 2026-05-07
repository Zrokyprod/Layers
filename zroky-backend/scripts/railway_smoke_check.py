#!/usr/bin/env python3
"""Railway go-live smoke checks for API liveness, readiness, and provisioning guards."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass
class HttpResponse:
    status: int
    body: Any
    text: str


def _parse_json(text: str) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _request_json(
    method: str,
    url: str,
    timeout_seconds: float,
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
) -> HttpResponse:
    headers = dict(headers or {})
    data: bytes | None = None

    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(url=url, method=method, headers=headers, data=data)

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            text = response.read().decode("utf-8")
            return HttpResponse(status=response.status, body=_parse_json(text), text=text)
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8")
        return HttpResponse(status=exc.code, body=_parse_json(text), text=text)
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Request failed for {method} {url}: {exc.reason}") from exc


def _print_result(ok: bool, success_message: str, failure_message: str, failures: list[str]) -> None:
    if ok:
        print(f"[PASS] {success_message}")
    else:
        print(f"[FAIL] {failure_message}")
        failures.append(failure_message)


def _normalize_base_url(url: str) -> str:
    return url.rstrip("/")


def run_smoke_checks(args: argparse.Namespace) -> int:
    base_url = _normalize_base_url(args.base_url)
    failures: list[str] = []

    # 1) Liveness check
    live = _request_json(
        method="GET",
        url=f"{base_url}/health/live",
        timeout_seconds=args.timeout_seconds,
    )
    live_status = isinstance(live.body, dict) and live.body.get("status") == "ok"
    _print_result(
        ok=live.status == 200 and live_status,
        success_message="GET /health/live returned 200 and status=ok",
        failure_message=f"GET /health/live expected 200/status=ok but got status={live.status} body={live.text}",
        failures=failures,
    )

    # 2) Readiness check
    ready = _request_json(
        method="GET",
        url=f"{base_url}/health/ready",
        timeout_seconds=args.timeout_seconds,
    )
    ready_body = ready.body if isinstance(ready.body, dict) else {}
    checks = ready_body.get("checks") if isinstance(ready_body.get("checks"), dict) else {}

    expected_check_values = {"ok"}
    if args.allow_skipped_ready_checks:
        expected_check_values.add("skipped")

    db_check_ok = checks.get("database") in expected_check_values
    redis_check_ok = checks.get("redis") in expected_check_values
    ready_ok = ready.status == 200 and ready_body.get("status") == "ok" and db_check_ok and redis_check_ok

    _print_result(
        ok=ready_ok,
        success_message=(
            "GET /health/ready returned 200/status=ok with database and redis readiness checks passing"
        ),
        failure_message=(
            "GET /health/ready expected status=ok with database/redis checks passing "
            f"but got status={ready.status} body={ready.text}"
        ),
        failures=failures,
    )

    timestamp = int(time.time())

    # 3) Provisioning guard without admin token
    no_token_response = _request_json(
        method="POST",
        url=f"{base_url}/v1/projects",
        timeout_seconds=args.timeout_seconds,
        payload={"name": f"{args.project_name_prefix}-no-token-{timestamp}"},
    )
    _print_result(
        ok=no_token_response.status == args.expected_unauthorized_status,
        success_message=(
            f"POST /v1/projects without admin token returned {args.expected_unauthorized_status} as expected"
        ),
        failure_message=(
            "POST /v1/projects without admin token expected "
            f"{args.expected_unauthorized_status} but got status={no_token_response.status} body={no_token_response.text}"
        ),
        failures=failures,
    )

    # 4) Provisioning flow with admin token (optional)
    if args.provisioning_token:
        headers = {args.provisioning_token_header: args.provisioning_token}

        auth_project_response = _request_json(
            method="POST",
            url=f"{base_url}/v1/projects",
            timeout_seconds=args.timeout_seconds,
            headers=headers,
            payload={"name": f"{args.project_name_prefix}-with-token-{timestamp}"},
        )

        auth_body = auth_project_response.body if isinstance(auth_project_response.body, dict) else {}
        project_id = auth_body.get("project_id")
        create_ok = (
            auth_project_response.status == 201
            and isinstance(project_id, str)
            and project_id.startswith("proj_")
        )

        _print_result(
            ok=create_ok,
            success_message="POST /v1/projects with admin token returned 201 and created project_id",
            failure_message=(
                "POST /v1/projects with admin token expected 201/project_id but got "
                f"status={auth_project_response.status} body={auth_project_response.text}"
            ),
            failures=failures,
        )

        if create_ok:
            projects_response = _request_json(
                method="GET",
                url=f"{base_url}/v1/projects?limit=50",
                timeout_seconds=args.timeout_seconds,
                headers=headers,
            )

            projects_body = projects_response.body if isinstance(projects_response.body, list) else []
            found_project = any(
                isinstance(item, dict) and item.get("project_id") == project_id for item in projects_body
            )

            _print_result(
                ok=projects_response.status == 200 and found_project,
                success_message="GET /v1/projects with admin token returned 200 and includes created project",
                failure_message=(
                    "GET /v1/projects with admin token expected 200 and created project presence but got "
                    f"status={projects_response.status} body={projects_response.text}"
                ),
                failures=failures,
            )
    else:
        print("[SKIP] Provisioning success check with admin token skipped (no token provided)")

    passed = 3 + (2 if args.provisioning_token else 0) - len(failures)
    total = 5 if args.provisioning_token else 3
    print(f"Summary: passed={passed} failed={len(failures)} total={total}")

    if failures:
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Railway production smoke checks for Zroky backend")
    parser.add_argument("--base-url", required=True, help="API base URL, for example https://api.example.com")
    parser.add_argument(
        "--provisioning-token",
        default="",
        help="Admin provisioning token for authenticated project creation checks",
    )
    parser.add_argument(
        "--provisioning-token-header",
        default="X-Zroky-Admin-Token",
        help="Header name for provisioning token",
    )
    parser.add_argument(
        "--expected-unauthorized-status",
        type=int,
        default=401,
        help="Expected status for unauthenticated POST /v1/projects",
    )
    parser.add_argument(
        "--project-name-prefix",
        default="RailwaySmoke",
        help="Prefix for synthetic projects created during smoke validation",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=20.0,
        help="HTTP timeout per request in seconds",
    )
    parser.add_argument(
        "--allow-skipped-ready-checks",
        action="store_true",
        help="Allow readiness checks to report 'skipped' instead of strict 'ok'",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return run_smoke_checks(args)
    except Exception as exc:  # pragma: no cover - operator-facing guard
        print(f"[ERROR] {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
