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
import os
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
    headers: dict[str, str]


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
    payload: dict[str, Any] | None = None,
) -> HttpResponse:
    request_headers = dict(headers)
    data = None
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url=url,
        method=method,
        headers=request_headers,
        data=data,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            text = response.read().decode("utf-8")
            return HttpResponse(
                status=response.status,
                body=_parse_json(text),
                text=text,
                headers={key.lower(): value for key, value in response.headers.items()},
            )
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8")
        return HttpResponse(
            status=exc.code,
            body=_parse_json(text),
            text=text,
            headers={key.lower(): value for key, value in exc.headers.items()},
        )
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Request failed for {method} {url}: {exc.reason}") from exc


def _headers(args: argparse.Namespace) -> dict[str, str]:
    headers = {"X-Project-Id": args.auth_project_id or args.project_id}
    api_key = args.api_key or os.getenv(args.api_key_env, "")
    if api_key:
        headers["X-API-Key"] = api_key.strip()
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


def _receipt_proof_status(receipt: dict[str, Any]) -> str | None:
    payload = receipt.get("receipt") if isinstance(receipt.get("receipt"), dict) else {}
    verification = payload.get("verification") if isinstance(payload.get("verification"), dict) else {}
    status = verification.get("proof_status") or verification.get("status")
    if status == "verified":
        return "matched"
    if status == "unverifiable":
        return "not_verified"
    return str(status) if status else None


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

    initialize_response = _request_json(
        method="POST",
        url=url,
        timeout_seconds=args.timeout_seconds,
        headers=headers,
        payload=_mcp_payload(
            "initialize",
            params={
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "zroky-mcp-smoke", "version": "1.0"},
            },
        ),
    )
    if initialize_response.status != 200:
        return _fail(
            f"initialize expected HTTP 200, got {initialize_response.status}: "
            f"{initialize_response.text}"
        )
    session_id = initialize_response.headers.get("mcp-session-id")
    if session_id:
        headers["Mcp-Session-Id"] = session_id
        initialized_response = _request_json(
            method="POST",
            url=url,
            timeout_seconds=args.timeout_seconds,
            headers=headers,
            payload={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        )
        if initialized_response.status != 202:
            return _fail(
                "notifications/initialized expected HTTP 202, got "
                f"{initialized_response.status}: {initialized_response.text}"
            )
    _print_pass("MCP initialize/session handshake completed")

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
        try:
            immediate = _validate_inline_receipt_meta(meta)
        except RuntimeError as exc:
            return _fail(str(exc))
        if immediate is None:
            intent_id = meta.get("intent_id")
            if not intent_id:
                return _fail(f"Cannot poll async receipt without intent_id: {call_response.text}")
            polled = _poll_async_receipt(
                base_url=base_url,
                headers=headers,
                timeout_seconds=args.timeout_seconds,
                action_id=str(intent_id),
                expect_proof_status=args.expect_proof_status,
                poll_interval_seconds=args.receipt_poll_interval_seconds,
                max_wait_seconds=args.receipt_timeout_seconds,
            )
            if polled != 0:
                return polled
        else:
            proof_status = immediate
            if args.expect_proof_status and proof_status != args.expect_proof_status:
                return _fail(
                    f"Expected proof_status={args.expect_proof_status!r}, got {proof_status!r}"
                )

    if args.expect_proof_status and not args.require_receipt and meta.get("proof_status") != args.expect_proof_status:
        return _fail(
            f"Expected proof_status={args.expect_proof_status!r}, got {meta.get('proof_status')!r}"
        )
    if args.expect_proof_status:
        _print_pass(f"proof_status={args.expect_proof_status}")

    print("[PASS] MCP interception smoke completed")
    return 0


def _validate_inline_receipt_meta(meta: dict[str, Any]) -> str | None:
    receipt_identity_keys = ("receipt_id", "receipt_digest", "signature_valid")
    if not any(key in meta for key in receipt_identity_keys):
        return None
    missing = [key for key in (*receipt_identity_keys, "proof_status") if key not in meta]
    if missing:
        raise RuntimeError(f"Receipt metadata missing keys {missing}")
    if meta.get("signature_valid") is not True:
        raise RuntimeError(f"Expected signature_valid=true, got {meta.get('signature_valid')!r}")
    if not str(meta.get("receipt_digest") or "").startswith("sha256:"):
        raise RuntimeError(f"Expected sha256 receipt digest, got {meta.get('receipt_digest')!r}")
    _print_pass(f"signed receipt present id={meta.get('receipt_id')} proof_status={meta.get('proof_status')}")
    return str(meta.get("proof_status"))


def _poll_async_receipt(
    *,
    base_url: str,
    headers: dict[str, str],
    timeout_seconds: float,
    action_id: str,
    expect_proof_status: str,
    poll_interval_seconds: float,
    max_wait_seconds: float,
) -> int:
    deadline = time.time() + max_wait_seconds
    last_status = ""
    while time.time() < deadline:
        intent_response = _request_json(
            method="GET",
            url=f"{base_url}/v1/action-intents/{action_id}",
            timeout_seconds=timeout_seconds,
            headers=headers,
        )
        if intent_response.status != 200:
            return _fail(
                f"receipt poll expected action intent HTTP 200, got {intent_response.status}: "
                f"{intent_response.text}"
            )
        intent = intent_response.body if isinstance(intent_response.body, dict) else {}
        last_status = (
            f"proof_status={intent.get('proof_status')} receipt_status={intent.get('receipt_status')}"
        )
        if intent.get("receipt_status") == "generated":
            receipt_response = _request_json(
                method="GET",
                url=f"{base_url}/v1/action-intents/{action_id}/receipt",
                timeout_seconds=timeout_seconds,
                headers=headers,
            )
            if receipt_response.status != 200:
                return _fail(
                    f"receipt fetch expected HTTP 200, got {receipt_response.status}: "
                    f"{receipt_response.text}"
                )
            receipt = receipt_response.body if isinstance(receipt_response.body, dict) else {}
            if receipt.get("signature_valid") is not True:
                return _fail(f"Expected receipt signature_valid=true, got {receipt.get('signature_valid')!r}")
            if not str(receipt.get("receipt_digest") or "").startswith("sha256:"):
                return _fail(f"Expected sha256 receipt digest, got {receipt.get('receipt_digest')!r}")
            proof_status = str(intent.get("proof_status") or _receipt_proof_status(receipt) or "")
            if expect_proof_status and proof_status != expect_proof_status:
                return _fail(f"Expected proof_status={expect_proof_status!r}, got {proof_status!r}")
            _print_pass(
                f"async signed receipt generated id={receipt.get('receipt_id')} proof_status={proof_status}"
            )
            return 0
        time.sleep(poll_interval_seconds)
    return _fail(f"Timed out waiting for async receipt for {action_id}; last {last_status}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run MCP interception smoke checks against Zroky backend")
    parser.add_argument("--base-url", required=True, help="API base URL, for example https://api.example.com")
    parser.add_argument("--project-id", required=True, help="Target project id")
    parser.add_argument("--auth-project-id", default="", help="Override X-Project-Id header value")
    parser.add_argument("--api-key", default="", help="Project API key; defaults to --api-key-env")
    parser.add_argument("--api-key-env", default="MCP_CANARY_API_KEY", help="Environment variable containing API key")
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
    parser.add_argument("--receipt-timeout-seconds", type=float, default=90.0, help="Max wait for async receipt")
    parser.add_argument("--receipt-poll-interval-seconds", type=float, default=3.0, help="Async receipt poll interval")
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
