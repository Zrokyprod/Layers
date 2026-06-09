"""Skydo billing gateway helpers.

Skydo is payment-link/invoice oriented for this use case. Their public FAQs say
website checkout and recurring InstaLinks are not available, so Zroky keeps the
subscription state internally and uses Skydo only as the payment collection
rail. A successful Skydo payment is applied through the signed billing webhook
or the owner confirmation endpoint.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlencode, urlsplit, urlunsplit
from uuid import uuid4

from app.core.config import get_settings


class SkydoError(RuntimeError):
    """Skydo payment request setup failed."""


class BillingWebhookSignatureError(ValueError):
    """Billing webhook signature missing, malformed, expired, or invalid."""


@dataclass(frozen=True)
class SkydoPaymentRequestResult:
    id: str
    url: str
    provider: str = "skydo"
    manual_confirmation_required: bool = True
    instructions: str = (
        "Complete the Skydo payment link or invoice, then confirm the payment "
        "from the owner panel or signed billing webhook."
    )


@dataclass(frozen=True)
class SkydoPortalResult:
    id: str
    url: str
    provider: str = "skydo"


class SkydoGateway(Protocol):
    def create_payment_request(
        self,
        *,
        org_id: str,
        plan_code: str,
        amount_usd: int | None,
        customer_email: str | None = None,
    ) -> SkydoPaymentRequestResult: ...

    def create_portal_session(self, *, org_id: str) -> SkydoPortalResult: ...


def _append_query(url: str, params: dict[str, str]) -> str:
    parts = urlsplit(url)
    existing = parts.query
    extra = urlencode(params)
    query = f"{existing}&{extra}" if existing else extra
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


class ConfiguredSkydoGateway:
    """Config-backed Skydo payment-link gateway.

    `SKYDO_PAYMENT_LINK_TEMPLATE` can include `{payment_request_id}`,
    `{org_id}`, `{plan_code}`, `{amount_usd}`, and `{customer_email}` tokens.
    If no template is configured, we return `SKYDO_PAYMENT_INSTRUCTIONS_URL`
    with Zroky reference query params for support/reconciliation.
    """

    def create_payment_request(
        self,
        *,
        org_id: str,
        plan_code: str,
        amount_usd: int | None,
        customer_email: str | None = None,
    ) -> SkydoPaymentRequestResult:
        settings = get_settings()
        payment_request_id = f"skydo_req_{uuid4().hex}"
        amount_token = "" if amount_usd is None else str(amount_usd)
        email_token = customer_email or ""
        values = {
            "payment_request_id": payment_request_id,
            "org_id": org_id,
            "plan_code": plan_code,
            "amount_usd": amount_token,
            "customer_email": email_token,
        }

        template = (settings.SKYDO_PAYMENT_LINK_TEMPLATE or "").strip()
        if template:
            try:
                url = template.format(**values)
            except KeyError as exc:
                raise SkydoError(
                    f"SKYDO_PAYMENT_LINK_TEMPLATE contains unknown token: {exc}"
                ) from exc
        else:
            base = (settings.SKYDO_PAYMENT_INSTRUCTIONS_URL or "").strip()
            if not base:
                raise SkydoError(
                    "SKYDO_PAYMENT_INSTRUCTIONS_URL or SKYDO_PAYMENT_LINK_TEMPLATE "
                    "must be configured when billing is enabled."
                )
            url = _append_query(
                base,
                {
                    "zroky_payment_request_id": payment_request_id,
                    "org_id": org_id,
                    "plan": plan_code,
                    **({"amount_usd": amount_token} if amount_token else {}),
                },
            )

        return SkydoPaymentRequestResult(id=payment_request_id, url=url)

    def create_portal_session(self, *, org_id: str) -> SkydoPortalResult:
        settings = get_settings()
        portal_url = (settings.SKYDO_PORTAL_URL or "").strip()
        if not portal_url:
            raise SkydoError("SKYDO_PORTAL_URL is not configured.")
        portal_id = f"skydo_portal_{uuid4().hex[:12]}"
        return SkydoPortalResult(
            id=portal_id,
            url=_append_query(portal_url, {"org_id": org_id}),
        )


def sign_webhook_payload(
    *, payload: bytes, secret: str, timestamp: int | None = None
) -> str:
    ts = timestamp if timestamp is not None else int(time.time())
    signed_payload = f"{ts}.".encode("utf-8") + payload
    sig = hmac.new(
        secret.encode("utf-8"), signed_payload, hashlib.sha256
    ).hexdigest()
    return f"t={ts},v1={sig}"


def verify_webhook_signature(
    *,
    payload: bytes,
    header: str | None,
    secret: str,
    tolerance: int = 300,
    now: float | None = None,
) -> dict[str, Any]:
    if not header or not isinstance(header, str):
        raise BillingWebhookSignatureError("billing signature header is missing")
    if not secret:
        raise BillingWebhookSignatureError("billing webhook secret is not configured")

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
        raise BillingWebhookSignatureError(
            "billing signature header is missing required `t=` or `v1=` parts"
        )
    try:
        ts_int = int(timestamp)
    except (TypeError, ValueError) as exc:
        raise BillingWebhookSignatureError(
            f"billing signature timestamp {timestamp!r} is not an integer"
        ) from exc

    current = now if now is not None else time.time()
    if abs(current - ts_int) > tolerance:
        raise BillingWebhookSignatureError(
            f"billing signature timestamp is outside tolerance window "
            f"({tolerance}s); replay rejected"
        )

    signed_payload = f"{timestamp}.".encode("utf-8") + payload
    expected = hmac.new(
        secret.encode("utf-8"), signed_payload, hashlib.sha256
    ).hexdigest()
    if not any(hmac.compare_digest(expected, sig) for sig in v1_signatures):
        raise BillingWebhookSignatureError("billing signature HMAC does not match")

    try:
        event = json.loads(payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise BillingWebhookSignatureError(
            "billing webhook payload is not valid UTF-8 JSON"
        ) from exc
    if not isinstance(event, dict):
        raise BillingWebhookSignatureError(
            "billing webhook payload top-level must be a JSON object"
        )
    return event


def get_skydo_gateway() -> SkydoGateway:
    return ConfiguredSkydoGateway()


__all__ = [
    "BillingWebhookSignatureError",
    "ConfiguredSkydoGateway",
    "SkydoError",
    "SkydoGateway",
    "SkydoPaymentRequestResult",
    "SkydoPortalResult",
    "get_skydo_gateway",
    "sign_webhook_payload",
    "verify_webhook_signature",
]
