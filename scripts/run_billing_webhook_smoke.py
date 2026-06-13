from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any
from uuid import uuid4


DEFAULT_API_BASE_URL = "https://api.zroky.com"


class SmokeFailure(RuntimeError):
    pass


def _url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}/{path.lstrip('/')}"


def _request_json(method: str, url: str, *, body: bytes, headers: dict[str, str], timeout: float) -> tuple[int, Any, str]:
    request = urllib.request.Request(url=url, method=method, headers=headers, data=body)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8", errors="replace")
            return response.status, json.loads(text), text
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        return exc.code, parsed, text


def _compact_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _sign(payload: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _expect(condition: bool, label: str, detail: str) -> None:
    if not condition:
        raise SmokeFailure(f"{label}: {detail}")


def _post_webhook(api_base_url: str, *, secret: str, event: dict[str, Any], timeout: float) -> dict[str, Any]:
    body = _compact_json_bytes(event)
    status, parsed, text = _request_json(
        "POST",
        _url(api_base_url, "/v1/billing/webhook"),
        body=body,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": _sign(body, secret),
        },
        timeout=timeout,
    )
    _expect(status == 200, "billing webhook", f"expected HTTP 200, got {status}: {text[:600]}")
    _expect(isinstance(parsed, dict), "billing webhook", f"expected JSON object, got: {text[:600]}")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify deployed Razorpay billing webhook signature handling with a synthetic skipped event.",
    )
    parser.add_argument("--api-base-url", default=os.getenv("ZROKY_DEPLOY_API_URL", DEFAULT_API_BASE_URL))
    parser.add_argument(
        "--webhook-secret",
        default=os.getenv("RAZORPAY_WEBHOOK_SECRET") or os.getenv("ZROKY_RAZORPAY_WEBHOOK_SECRET") or "",
        help="Webhook signing secret. Prefer passing via env; the value is never printed.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    secret = str(args.webhook_secret or "").strip()
    if not secret:
        print("[ERROR] RAZORPAY_WEBHOOK_SECRET or ZROKY_RAZORPAY_WEBHOOK_SECRET is required.")
        return 2
    if len(secret) < 16:
        print("[ERROR] Webhook secret is too short for production smoke.")
        return 2

    event_id = f"evt_zroky_billing_smoke_{int(time.time())}_{uuid4().hex[:12]}"
    event = {
        "id": event_id,
        "event": "customer.created",
        "created_at": int(time.time()),
        "payload": {
            "customer": {
                "entity": {
                    "id": f"cust_zroky_smoke_{uuid4().hex[:10]}",
                    "notes": {"source": "zroky_billing_webhook_smoke"},
                }
            }
        },
    }

    try:
        first = _post_webhook(args.api_base_url, secret=secret, event=event, timeout=args.timeout_seconds)
        _expect(first.get("event_type") == "customer.created", "billing webhook first delivery", f"body={first}")
        _expect(first.get("result") == "skipped", "billing webhook first delivery", f"body={first}")
        print(f"[PASS] billing webhook signed delivery - event_id={event_id} result=skipped")

        duplicate = _post_webhook(args.api_base_url, secret=secret, event=event, timeout=args.timeout_seconds)
        _expect(duplicate.get("result") == "skipped", "billing webhook duplicate delivery", f"body={duplicate}")
        print(f"[PASS] billing webhook duplicate delivery - event_id={event_id} result=skipped")
    except SmokeFailure as exc:
        print(f"[FAIL] {exc}")
        return 1

    print("[billing-webhook-smoke] passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
