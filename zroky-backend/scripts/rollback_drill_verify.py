#!/usr/bin/env python3
"""Run automated rollback drill verification via backend settings API."""

from __future__ import annotations

import argparse
import json
import sys
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


def _normalize_base_url(url: str) -> str:
    return url.rstrip("/")


def run_verification(args: argparse.Namespace) -> int:
    base_url = _normalize_base_url(args.base_url)
    payload: dict[str, Any] = {"phase": args.phase}

    if args.phase == "deploy":
        payload["deploy_revision"] = args.deploy_revision
    else:
        payload["rollback_revision"] = args.rollback_revision

    headers: dict[str, str] = {
        "X-Project-Id": args.project_id,
    }
    if args.access_token:
        token = args.access_token.strip()
        headers["Authorization"] = token if token.lower().startswith("bearer ") else f"Bearer {token}"

    response = _request_json(
        method="POST",
        url=f"{base_url}/v1/settings/rollback-drill/verify",
        timeout_seconds=args.timeout_seconds,
        headers=headers,
        payload=payload,
    )

    print(response.text)

    if response.status != 200:
        return 2

    body = response.body if isinstance(response.body, dict) else {}
    return 0 if bool(body.get("passed")) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run automated rollback drill verification against Zroky backend")
    parser.add_argument("--base-url", required=True, help="API base URL, for example https://api.example.com")
    parser.add_argument("--project-id", required=True, help="Target project id sent via X-Project-Id")
    parser.add_argument("--phase", required=True, choices=["deploy", "rollback"], help="Verification phase to run")
    parser.add_argument("--deploy-revision", default="", help="Deploy revision id (required for deploy phase)")
    parser.add_argument("--rollback-revision", default="", help="Rollback revision id (required for rollback phase)")
    parser.add_argument(
        "--access-token",
        default="",
        help="Bearer token for admin-auth environments (optional in local header-context mode)",
    )
    parser.add_argument("--timeout-seconds", type=float, default=20.0, help="HTTP timeout per request in seconds")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.phase == "deploy" and not args.deploy_revision.strip():
        print("[ERROR] --deploy-revision is required when --phase deploy")
        return 2
    if args.phase == "rollback" and not args.rollback_revision.strip():
        print("[ERROR] --rollback-revision is required when --phase rollback")
        return 2

    try:
        return run_verification(args)
    except Exception as exc:  # pragma: no cover - operator-facing guard
        print(f"[ERROR] {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
