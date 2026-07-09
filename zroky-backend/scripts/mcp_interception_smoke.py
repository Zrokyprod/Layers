#!/usr/bin/env python3
"""Smoke-test the MCP interception ingress after deployment.

The script is intentionally HTTP-only so it can run against Railway/prod
without direct DB access.

Common safe rollout usage:

  # Before enabling MCP_INTERCEPTION_ENABLED, prove the route is inert.
  python scripts/mcp_interception_smoke.py \
    --base-url https://api.example.com \
    --project-id proj_x \
    --expect-disabled

  # After enabling the flag and configuring project bindings/upstream, run a
  # known-safe canary tool call and require a signed receipt.
  python scripts/mcp_interception_smoke.py \
    --base-url https://api.example.com \
    --project-id proj_x \
    --tool-name safe_canary_tool \
    --arguments '{"record_ref":"canary_1","status":"completed"}' \
    --expect-decision allow \
    --require-receipt \
    --expect-proof-status matched
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
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
    *,
    method: str,
    url: str,
    timeout_seconds: float,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> HttpResponse:
    request = urllib.request.Request(
        url=url,
        method=method,
        headers={**headers, "Content-Type": "application/json"},
        data=json.dumps(payload).encode("utf-8"),
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            text = response.read().decode("utf-8")
            return HttpResponse(status=response.status, body=_parse_json(text), text=text)
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8")
        return HttpResponse(status=exc.code, body=_parse_json(text), text=text)
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Request failed for {method} {url}: {exc.reason}") from exc


def _headers(args: argparse.Namespace) -> dict[str, str]:
    headers = {"X-Project-Id": args.auth_project_id or args.project_id}
    if args.access_token:
        token = args.access_token.strip()
        headers["Authorization"] = token if token.lower().startswith("bearer ") else f"Bearer {token}"
    if args.idempotency_key:
        headers["Idempotency-Key"] = args.idempotency_key
    return headers


def _json_object(value: str, *, name: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{name} must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{name} must decode to a JSON object")
    return parsed


def _zroky_meta(response: HttpResponse) -> dict[str, Any]:
    body = response.body if isinstance(response.body, dict) else {}
    result = body.get("result") if isinstance(body.get("result"), dict) else {}
    meta = result.get("_meta") if isinstance(result.get("_meta"), dict) else {}
    zroky = meta.get("zroky") if isinstance(meta.get("zroky"), dict) else {}
    return zroky


def _print_pass(message: str) -> None:
    print(f"[PASS] {message}")


def _fail(message: str) -> int:
    print(f"[FAIL] {message}")
    return 1


def _mcp_payload(method: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        payload["params"] = params
    return payload


def run_smoke(args: argparse.Namespace) -> int:
    base_url = args.base_url.rstrip("/")
    url = f"{base_url}/v1/mcp/{args.project_id}"
    headers = _headers(args)

    if args.expect_disabled:
        response = _request_json(
            method="POST",
            url=url,
            timeout_seconds=args.timeout_seconds,
            headers=headers,
            payload=_mcp_payload("tools/list"),
        )
        if response.status == 404:
            _print_pass("MCP route is inert while feature flag is disabled")
            return 0
        return _fail(f"Expected disabled MCP route to return 404, got {response.status}: {response.text}")

    list_response = _request_json(
        method="POST",
        url=url,
        timeout_seconds=args.timeout_seconds,
        headers=headers,
        payload=_mcp_payload("tools/list"),
    )
    if list_response.status != 200:
        return _fail(f"tools/list expected HTTP 200, got {list_response.status}: {list_response.text}")
    _print_pass("tools/list returned HTTP 200")

    if not args.tool_name:
        print("[SKIP] tools/call skipped because --tool-name was not provided")
        return 0

    arguments = _json_object(args.arguments, name="--arguments")
    call_response = _request_json(
        method="POST",
        url=url,
        timeout_seconds=args.timeout_seconds,
        headers=headers,
        payload=_mcp_payload(
            "tools/call",
            params={"name": args.tool_name, "arguments": arguments},
        ),
    )
    if call_response.status != 200:
        return _fail(f"tools/call expected HTTP 200, got {call_response.status}: {call_response.text}")

    meta = _zroky_meta(call_response)
    decision = meta.get("decision")
    if decision != args.expect_decision:
        return _fail(
            f"Expected decision={args.expect_decision!r}, got {decision!r}. "
            f"body={call_response.text}"
        )
    _print_pass(f"tools/call decision={decision}")

    result = call_response.body.get("result") if isinstance(call_response.body, dict) else {}
    is_error = result.get("isError") if isinstance(result, dict) else None
    if args.expect_error and is_error is not True:
        return _fail(f"Expected MCP tool result isError=true, got {is_error!r}: {call_response.text}")
    if not args.expect_error and args.expect_decision == "allow" and is_error is True:
        return _fail(f"Expected allowed canary not to be an MCP error: {call_response.text}")

    if args.require_receipt:
        missing = [
            key
            for key in ("receipt_id", "receipt_digest", "signature_valid", "proof_status")
            if key not in meta
        ]
        if missing:
            return _fail(f"Receipt metadata missing keys {missing}: {call_response.text}")
        if meta.get("signature_valid") is not True:
            return _fail(f"Expected signature_valid=true, got {meta.get('signature_valid')!r}")
        if not str(meta.get("receipt_digest") or "").startswith("sha256:"):
            return _fail(f"Expected sha256 receipt digest, got {meta.get('receipt_digest')!r}")
        _print_pass(
            f"signed receipt present id={meta.get('receipt_id')} proof_status={meta.get('proof_status')}"
        )

    if args.expect_proof_status and meta.get("proof_status") != args.expect_proof_status:
        return _fail(
            f"Expected proof_status={args.expect_proof_status!r}, got {meta.get('proof_status')!r}"
        )
    if args.expect_proof_status:
        _print_pass(f"proof_status={args.expect_proof_status}")

    print("[PASS] MCP interception smoke completed")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run MCP interception smoke checks against Zroky backend")
    parser.add_argument("--base-url", required=True, help="API base URL, for example https://api.example.com")
    parser.add_argument("--project-id", required=True, help="Target project id")
    parser.add_argument("--auth-project-id", default="", help="Override X-Project-Id header value")
    parser.add_argument("--access-token", default="", help="Bearer token for auth environments")
    parser.add_argument(
        "--idempotency-key",
        default=f"mcp-smoke-{int(time.time())}",
        help="Explicit idempotency key for the canary tools/call",
    )
    parser.add_argument("--expect-disabled", action="store_true", help="Assert route returns 404")
    parser.add_argument("--tool-name", default="", help="Tool name for tools/call canary")
    parser.add_argument("--arguments", default="{}", help="JSON object passed as MCP tool arguments")
    parser.add_argument(
        "--expect-decision",
        default="allow",
        choices=["allow", "deny", "hold", "observe"],
        help="Expected Zroky decision for tools/call",
    )
    parser.add_argument("--expect-error", action="store_true", help="Expect result.isError=true")
    parser.add_argument("--require-receipt", action="store_true", help="Require signed receipt metadata")
    parser.add_argument(
        "--expect-proof-status",
        default="",
        choices=["", "matched", "mismatched", "not_verified"],
        help="Expected proof_status in receipt metadata",
    )
    parser.add_argument("--timeout-seconds", type=float, default=30.0, help="HTTP timeout per request")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return run_smoke(args)
    except Exception as exc:  # pragma: no cover - operator-facing guard
        print(f"[ERROR] {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
