"""
Stripe gateway abstraction (Module 5; plan §11.3).

Why a wrapper, not the official `stripe` package:
  - The four Stripe operations we need (create checkout session, create
    portal session, retrieve subscription/customer, verify webhook
    signature) are all simple form-encoded POSTs / HMAC checks. The
    `stripe` package adds ~1 MB of dependency and stateful client
    semantics for negligible code-size win.
  - A thin abstraction lets us inject a `StubStripeGateway` in tests
    without monkeypatching deep into the official lib's internals.
  - We can swap in the official package later by changing only this
    file — every caller goes through `StripeGateway.*`.

This module exposes:
  - `StripeError`             generic exception
  - `WebhookSignatureError`   raised by `verify_webhook_signature`
  - `StripeGateway`           abstract protocol (Live + Stub honour it)
  - `LiveStripeGateway`       httpx-backed; only constructed when
                              BILLING_ENABLED=true and STRIPE_API_KEY set
  - `StubStripeGateway`       in-memory; used by tests AND by the
                              non-billing dev path so /v1/billing/* still
                              returns sensible responses
  - `verify_webhook_signature(payload, header, secret, tolerance)`
                              standalone HMAC-SHA256 verifier
                              (Stripe's documented algorithm)
  - `get_stripe_gateway()`    DI factory; returns Live or Stub based on
                              settings

The gateway returns plain dict[str, Any] payloads — same shape as the
Stripe API responses so call-sites are wire-compatible if we ever swap
in `stripe` proper.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


# ── exceptions ──────────────────────────────────────────────────────────────


class StripeError(RuntimeError):
    """Generic Stripe API failure (HTTP non-2xx, network, parse)."""


class WebhookSignatureError(ValueError):
    """`Stripe-Signature` header missing, malformed, expired, or HMAC
    mismatch. The webhook route maps this to 400."""


# ── webhook signature verifier (used by the route directly) ─────────────────


def verify_webhook_signature(
    *,
    payload: bytes,
    header: str | None,
    secret: str,
    tolerance: int = 300,
    now: float | None = None,
) -> dict[str, Any]:
    """Stripe's documented HMAC-SHA256 webhook verifier.

    Header format (https://stripe.com/docs/webhooks/signatures):
      `t=1492774577,v1=5257a869e7ec...`

    Args:
      payload:   raw request body (bytes — DO NOT decode/re-encode)
      header:    contents of the `Stripe-Signature` request header
      secret:    `whsec_...` value from STRIPE_WEBHOOK_SECRET
      tolerance: max age in seconds; rows older than this are rejected
                 to defend against replay attacks
      now:       unix-epoch seconds; injectable for tests

    Returns the parsed JSON event payload on success.
    Raises WebhookSignatureError on any failure mode.
    """
    if not header or not isinstance(header, str):
        raise WebhookSignatureError("Stripe-Signature header is missing")
    if not secret:
        raise WebhookSignatureError("webhook secret is not configured")

    # Parse the comma-separated key=value pairs. We tolerate unknown
    # versions (Stripe may add v2 etc.) but require at least one v1.
    timestamp: str | None = None
    v1_signatures: list[str] = []
    for part in header.split(","):
        if "=" not in part:
            continue
        scheme, _, value = part.strip().partition("=")
        if scheme == "t":
            timestamp = value
        elif scheme == "v1":
            v1_signatures.append(value)

    if timestamp is None or not v1_signatures:
        raise WebhookSignatureError(
            "Stripe-Signature header is missing required `t=` or `v1=` parts"
        )

    try:
        ts_int = int(timestamp)
    except (TypeError, ValueError) as exc:
        raise WebhookSignatureError(
            f"Stripe-Signature timestamp {timestamp!r} is not an integer"
        ) from exc

    current = now if now is not None else time.time()
    if abs(current - ts_int) > tolerance:
        raise WebhookSignatureError(
            f"Stripe-Signature timestamp is outside tolerance window "
            f"({tolerance}s); replay rejected"
        )

    signed_payload = f"{timestamp}.".encode("utf-8") + payload
    expected = hmac.new(
        secret.encode("utf-8"), signed_payload, hashlib.sha256
    ).hexdigest()

    if not any(hmac.compare_digest(expected, sig) for sig in v1_signatures):
        raise WebhookSignatureError("Stripe-Signature HMAC does not match")

    try:
        event = json.loads(payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise WebhookSignatureError(
            "webhook payload is not valid UTF-8 JSON"
        ) from exc
    if not isinstance(event, dict):
        raise WebhookSignatureError(
            "webhook payload top-level must be a JSON object"
        )
    return event


def sign_webhook_payload(
    *, payload: bytes, secret: str, timestamp: int | None = None
) -> str:
    """Produce a valid `Stripe-Signature` header for `payload`.

    Used exclusively by tests to construct fixtures that round-trip
    through `verify_webhook_signature` — we keep this tightly scoped
    to the gateway so test code doesn't reimplement HMAC.
    """
    ts = timestamp if timestamp is not None else int(time.time())
    signed_payload = f"{ts}.".encode("utf-8") + payload
    sig = hmac.new(
        secret.encode("utf-8"), signed_payload, hashlib.sha256
    ).hexdigest()
    return f"t={ts},v1={sig}"


# ── gateway protocol + implementations ──────────────────────────────────────


@dataclass(frozen=True)
class CheckoutSessionResult:
    id: str
    url: str
    customer_id: str | None = None


@dataclass(frozen=True)
class PortalSessionResult:
    id: str
    url: str


class StripeGateway(Protocol):
    """Method surface used by routes/billing.py + services/stripe_sync.py."""

    is_live: bool

    def create_checkout_session(
        self,
        *,
        org_id: str,
        plan_code: str,
        price_id: str,
        success_url: str,
        cancel_url: str,
        customer_id: str | None = None,
        customer_email: str | None = None,
    ) -> CheckoutSessionResult: ...

    def create_portal_session(
        self,
        *,
        customer_id: str,
        return_url: str,
    ) -> PortalSessionResult: ...


class StubStripeGateway:
    """In-memory implementation. Returns deterministic stub URLs that
    look like Stripe-hosted Checkout / Portal links so tests can match
    on shape without hitting the network.

    Recorded calls are exposed via `last_*` attributes for assertions.
    """

    is_live = False

    def __init__(self) -> None:
        self.last_checkout: dict[str, Any] | None = None
        self.last_portal: dict[str, Any] | None = None
        self._counter = 0

    def _next_id(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}_stub_{self._counter:04d}_{uuid4().hex[:6]}"

    def create_checkout_session(
        self,
        *,
        org_id: str,
        plan_code: str,
        price_id: str,
        success_url: str,
        cancel_url: str,
        customer_id: str | None = None,
        customer_email: str | None = None,
    ) -> CheckoutSessionResult:
        session_id = self._next_id("cs")
        url = (
            f"https://stub.stripe.local/checkout/{session_id}"
            f"?plan={plan_code}&org={org_id}"
        )
        self.last_checkout = {
            "org_id": org_id,
            "plan_code": plan_code,
            "price_id": price_id,
            "customer_id": customer_id,
            "customer_email": customer_email,
            "success_url": success_url,
            "cancel_url": cancel_url,
            "session_id": session_id,
        }
        return CheckoutSessionResult(
            id=session_id, url=url, customer_id=customer_id
        )

    def create_portal_session(
        self, *, customer_id: str, return_url: str,
    ) -> PortalSessionResult:
        session_id = self._next_id("bps")
        url = f"https://stub.stripe.local/portal/{session_id}?return_to={return_url}"
        self.last_portal = {
            "customer_id": customer_id,
            "return_url": return_url,
            "session_id": session_id,
        }
        return PortalSessionResult(id=session_id, url=url)


class LiveStripeGateway:
    """httpx-backed implementation. Only constructed when BILLING_ENABLED
    AND STRIPE_API_KEY is set. We use form-encoded POSTs (Stripe's
    canonical wire format) and Bearer auth.

    Errors map to `StripeError` with the Stripe-returned message
    preserved so the route can pass an actionable detail to the
    operator (NOT to the customer — the customer sees a generic 503)."""

    is_live = True

    def __init__(self, api_key: str, base_url: str, timeout: float = 10.0) -> None:
        if not api_key.strip():
            raise ValueError("STRIPE_API_KEY must be non-empty")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def _post(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        # Stripe expects form-encoded — flatten nested dicts via
        # `parent[child]=value` per their convention.
        flat: list[tuple[str, str]] = []
        for k, v in data.items():
            if v is None:
                continue
            if isinstance(v, bool):
                flat.append((k, "true" if v else "false"))
            elif isinstance(v, (int, float)):
                flat.append((k, str(v)))
            elif isinstance(v, dict):
                for sk, sv in v.items():
                    if sv is None:
                        continue
                    flat.append((f"{k}[{sk}]", str(sv)))
            elif isinstance(v, list):
                for idx, item in enumerate(v):
                    if isinstance(item, dict):
                        for sk, sv in item.items():
                            if sv is None:
                                continue
                            flat.append((f"{k}[{idx}][{sk}]", str(sv)))
                    else:
                        flat.append((f"{k}[{idx}]", str(item)))
            else:
                flat.append((k, str(v)))

        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(
                    url,
                    data=flat,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Stripe-Version": "2024-04-10",
                    },
                )
        except httpx.HTTPError as exc:
            logger.exception("stripe_gateway.http_error path=%s", path)
            raise StripeError(f"Stripe HTTP error: {exc}") from exc

        if response.status_code >= 400:
            try:
                body = response.json()
            except Exception:  # pragma: no cover — non-JSON error
                body = {}
            err = (body.get("error") or {}) if isinstance(body, dict) else {}
            msg = err.get("message") or response.text[:500]
            logger.error(
                "stripe_gateway.api_error path=%s status=%d msg=%s",
                path, response.status_code, msg,
            )
            raise StripeError(
                f"Stripe API error {response.status_code}: {msg}"
            )

        try:
            return response.json()
        except Exception as exc:  # pragma: no cover — Stripe always returns JSON
            raise StripeError(f"Stripe response is not valid JSON: {exc}") from exc

    def create_checkout_session(
        self,
        *,
        org_id: str,
        plan_code: str,
        price_id: str,
        success_url: str,
        cancel_url: str,
        customer_id: str | None = None,
        customer_email: str | None = None,
    ) -> CheckoutSessionResult:
        data: dict[str, Any] = {
            "mode": "subscription",
            "success_url": success_url,
            "cancel_url": cancel_url,
            "line_items[0][price]": price_id,
            "line_items[0][quantity]": 1,
            "client_reference_id": org_id,
            "metadata[org_id]": org_id,
            "metadata[plan_code]": plan_code,
            "subscription_data[metadata][org_id]": org_id,
            "subscription_data[metadata][plan_code]": plan_code,
        }
        if customer_id:
            data["customer"] = customer_id
        elif customer_email:
            data["customer_email"] = customer_email

        body = self._post("/v1/checkout/sessions", data)
        sid = str(body.get("id") or "")
        url = str(body.get("url") or "")
        if not sid or not url:
            raise StripeError(
                "Stripe checkout response missing id or url"
            )
        return CheckoutSessionResult(
            id=sid, url=url, customer_id=body.get("customer")
        )

    def create_portal_session(
        self, *, customer_id: str, return_url: str,
    ) -> PortalSessionResult:
        if not customer_id.strip():
            raise StripeError("customer_id is required for portal session")
        body = self._post(
            "/v1/billing_portal/sessions",
            {"customer": customer_id, "return_url": return_url},
        )
        sid = str(body.get("id") or "")
        url = str(body.get("url") or "")
        if not sid or not url:
            raise StripeError("Stripe portal response missing id or url")
        return PortalSessionResult(id=sid, url=url)


# ── DI factory ──────────────────────────────────────────────────────────────


def get_stripe_gateway() -> StripeGateway:
    """Decide which gateway to hand to the route.

    Live  → BILLING_ENABLED=true AND STRIPE_API_KEY non-empty.
    Stub  → otherwise. The stub lets local dev / self-host run the
            checkout flow end-to-end with deterministic URLs.
    """
    s = get_settings()
    if s.BILLING_ENABLED and (s.STRIPE_API_KEY or "").strip():
        return LiveStripeGateway(
            api_key=s.STRIPE_API_KEY.strip(),  # type: ignore[union-attr]
            base_url=s.STRIPE_API_BASE_URL,
        )
    return StubStripeGateway()


__all__ = [
    "StripeError",
    "WebhookSignatureError",
    "CheckoutSessionResult",
    "PortalSessionResult",
    "StripeGateway",
    "StubStripeGateway",
    "LiveStripeGateway",
    "verify_webhook_signature",
    "sign_webhook_payload",
    "get_stripe_gateway",
]
