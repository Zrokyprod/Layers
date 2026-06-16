from __future__ import annotations

import hashlib
import hmac
import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Callable
from uuid import uuid4

import razorpay
from fastapi import HTTPException, status
from razorpay.errors import BadRequestError, GatewayError, ServerError

from app.core.config import get_settings
from app.services.billing_plans import (
    InvalidPlanCodeError,
    PlanNotSelfServeError,
    assert_self_serve_plan,
)
from app.services.entitlement_catalog import canonical_plan_code, load_pricing_contract

logger = logging.getLogger(__name__)


def _monthly_plan_amount_usd(plan_code: str) -> int | None:
    """Return the public monthly USD price from the shared pricing contract."""
    try:
        contract = load_pricing_contract()
    except Exception:
        logger.exception("billing.pricing_contract_load_failed")
        return None
    try:
        canonical = canonical_plan_code(plan_code)
    except InvalidPlanCodeError:
        canonical = plan_code
    for raw_plan in contract.get("plans", []):
        if not isinstance(raw_plan, dict):
            continue
        if str(raw_plan.get("code") or "").strip().lower() != canonical:
            continue
        price = raw_plan.get("price")
        if not isinstance(price, dict):
            return None
        amount = price.get("monthly_usd")
        return int(amount) if isinstance(amount, (int, float)) else None
    return None


def _razorpay_credentials() -> tuple[str, str]:
    settings = get_settings()
    key_id = (settings.RAZORPAY_KEY_ID or "").strip()
    key_secret = (settings.RAZORPAY_KEY_SECRET or "").strip()
    if not key_id or not key_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Razorpay credentials are not configured.",
        )
    return key_id, key_secret


def _razorpay_client() -> razorpay.Client:
    key_id, key_secret = _razorpay_credentials()
    return razorpay.Client(auth=(key_id, key_secret))


def _razorpay_auth_failure(exc: Exception) -> bool:
    message = str(exc).lower()
    return "auth" in message or "key" in message or "credential" in message


def _razorpay_receipt(org_id: str, plan_code: str | None) -> str:
    plan_part = (plan_code or "custom").strip().lower()[:10] or "custom"
    org_part = org_id.replace(":", "_").replace("/", "_")[:12] or "org"
    return f"zroky_{org_part}_{plan_part}_{uuid4().hex[:8]}"[:40]


def _razorpay_amount_for_plan(plan_code: str) -> tuple[int, int]:
    """Return (amount_paise, monthly_amount_usd) for a self-serve plan."""
    amount_usd = _monthly_plan_amount_usd(plan_code)
    if amount_usd is None or amount_usd <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Plan {plan_code!r} is not configured with a billable monthly amount.",
        )

    settings = get_settings()
    rate = Decimal(str(settings.ZROKY_EXCHANGE_RATE_USD_TO_INR))
    if rate <= 0:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ZROKY_EXCHANGE_RATE_USD_TO_INR must be greater than zero.",
        )
    amount = (Decimal(str(amount_usd)) * rate * Decimal("100")).quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    )
    return max(100, int(amount)), amount_usd


def _verify_razorpay_signature(
    *,
    order_id: str,
    payment_id: str,
    signature: str,
) -> bool:
    _, key_secret = _razorpay_credentials()
    payload = f"{order_id}|{payment_id}".encode("utf-8")
    expected = hmac.new(
        key_secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def _razorpay_status(entity: dict[str, Any]) -> str:
    return str(entity.get("status") or "").strip().lower()


def _razorpay_payment_is_captured(payment: dict[str, Any]) -> bool:
    return _razorpay_status(payment) == "captured" or payment.get("captured") is True


def _razorpay_order_is_paid(order: dict[str, Any]) -> bool:
    return _razorpay_status(order) == "paid"


def _razorpay_webhook_confirms_paid(
    *, event_type: str, payment: dict[str, Any], order: dict[str, Any]
) -> bool:
    if event_type in {"payment.captured", "payment.succeeded"}:
        return _razorpay_payment_is_captured(payment)
    if event_type == "order.paid":
        return _razorpay_order_is_paid(order)
    return False


def _razorpay_notes(*entities: dict[str, Any]) -> dict[str, Any]:
    for entity in entities:
        raw = entity.get("notes")
        if isinstance(raw, dict):
            return raw
    return {}


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _fetch_razorpay_payment_and_order(
    *,
    payment_id: str,
    order_id: str,
    client_factory: Callable[[], Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    client = (client_factory or _razorpay_client)()
    try:
        payment = client.payment.fetch(payment_id)
        order = client.order.fetch(order_id)
    except BadRequestError as exc:
        logger.exception("billing.razorpay_payment_verify_bad_request")
        status_code = (
            status.HTTP_401_UNAUTHORIZED
            if _razorpay_auth_failure(exc)
            else status.HTTP_400_BAD_REQUEST
        )
        detail = (
            "Razorpay authentication failed."
            if status_code == status.HTTP_401_UNAUTHORIZED
            else "Razorpay payment or order could not be verified."
        )
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except (GatewayError, ServerError) as exc:
        logger.exception("billing.razorpay_payment_verify_gateway_error")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Razorpay payment verification is temporarily unavailable.",
        ) from exc
    except Exception as exc:
        logger.exception("billing.razorpay_payment_verify_failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Razorpay payment verification failed.",
        ) from exc

    if not isinstance(payment, dict) or not isinstance(order, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Razorpay payment verification returned an invalid response.",
        )
    return payment, order


def _require_razorpay_paid_checkout(
    *,
    payment_id: str,
    order_id: str,
    org_id: str,
    plan_code: str | None,
    client_factory: Callable[[], Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    payment, order = _fetch_razorpay_payment_and_order(
        payment_id=payment_id,
        order_id=order_id,
        client_factory=client_factory,
    )

    payment_order_id = str(payment.get("order_id") or "").strip()
    fetched_order_id = str(order.get("id") or "").strip()
    if payment_order_id and payment_order_id != order_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Razorpay payment does not belong to the verified order.",
        )
    if fetched_order_id and fetched_order_id != order_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Razorpay order response does not match the verified order.",
        )
    if not (
        _razorpay_payment_is_captured(payment)
        or _razorpay_order_is_paid(order)
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Razorpay payment is not captured or order is not paid yet.",
        )

    notes = _razorpay_notes(payment, order)
    note_org_id = str(notes.get("org_id") or "").strip()
    if note_org_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Razorpay order metadata does not match this org.",
        )

    provider_currency = str(
        payment.get("currency") or order.get("currency") or ""
    ).strip().upper()
    if provider_currency and provider_currency != "INR":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Razorpay payment currency does not match checkout currency.",
        )

    if plan_code:
        try:
            expected_plan = _normalize_razorpay_plan_code(plan_code)
        except (InvalidPlanCodeError, PlanNotSelfServeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Stored Razorpay plan is not valid for self-serve checkout.",
            ) from exc

        note_plan_code = str(notes.get("plan_code") or "").strip().lower()
        try:
            note_plan_code = _normalize_razorpay_plan_code(note_plan_code)
        except (InvalidPlanCodeError, PlanNotSelfServeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Razorpay order metadata does not match the selected plan.",
            ) from exc
        if note_plan_code != expected_plan:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Razorpay order metadata does not match the selected plan.",
            )

        expected_amount, _ = _razorpay_amount_for_plan(expected_plan)
        for provider_amount in (
            _int_or_none(payment.get("amount")),
            _int_or_none(order.get("amount")),
        ):
            if provider_amount is not None and provider_amount != expected_amount:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Razorpay payment amount does not match the selected plan.",
                )

    return payment, order


def _parse_stored_razorpay_request(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    order_id, _, plan_code = value.partition(":")
    return order_id.strip() or None, plan_code.strip().lower() or None


_RAZORPAY_PLAN_ALIASES: dict[str, str] = {
    "pilot": "starter",
    "plus": "pro",
}


def _normalize_razorpay_plan_code(plan_code: str) -> str:
    raw = (plan_code or "").strip().lower()
    return assert_self_serve_plan(_RAZORPAY_PLAN_ALIASES.get(raw, raw))


def _razorpay_webhook_event_id(event: dict[str, Any], raw_body: bytes) -> str:
    explicit = event.get("id") or event.get("event_id")
    if explicit:
        return str(explicit)
    payment = (
        event.get("payload", {})
        .get("payment", {})
        .get("entity", {})
    )
    if isinstance(payment, dict) and payment.get("id"):
        return f"{event.get('event') or 'razorpay'}:{payment['id']}"
    digest = hashlib.sha256(raw_body).hexdigest()[:32]
    return f"razorpay:{digest}"


def _verify_razorpay_webhook_signature(*, payload: bytes, signature: str | None) -> None:
    secret = (get_settings().RAZORPAY_WEBHOOK_SECRET or "").strip()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RAZORPAY_WEBHOOK_SECRET is not configured.",
        )
    if not signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing Razorpay webhook signature.",
        )
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Razorpay webhook signature mismatch.",
        )
