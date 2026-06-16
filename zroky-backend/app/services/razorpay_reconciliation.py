"""Recover paid Razorpay orders when browser callbacks or webhooks are missed."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from razorpay.errors import BadRequestError, GatewayError, ServerError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.routes._internal.billing_razorpay import (
    _normalize_razorpay_plan_code,
    _parse_stored_razorpay_request,
    _razorpay_amount_for_plan,
    _razorpay_client,
    _razorpay_order_is_paid,
    _razorpay_payment_is_captured,
)
from app.db.models import BillingEvent, Subscription
from app.services import entitlements_resolver
from app.services.billing_plans import InvalidPlanCodeError, PlanNotSelfServeError
from app.services.entitlements import seed_plan_entitlements

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RazorpayReconciliationRecord:
    org_id: str
    order_id: str | None
    plan_code: str | None
    result: str
    detail: str


@dataclass
class RazorpayReconciliationResult:
    examined: int = 0
    activated: int = 0
    skipped: int = 0
    failed: int = 0
    records: list[RazorpayReconciliationRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "examined": self.examined,
            "activated": self.activated,
            "skipped": self.skipped,
            "failed": self.failed,
            "records": [
                {
                    "org_id": record.org_id,
                    "order_id": record.order_id,
                    "plan_code": record.plan_code,
                    "result": record.result,
                    "detail": record.detail,
                }
                for record in self.records
            ],
        }


def reconcile_pending_razorpay_orders(
    db: Session,
    *,
    limit: int = 100,
    client_factory: Callable[[], Any] | None = None,
) -> RazorpayReconciliationResult:
    """Activate paid Razorpay orders that are still pending locally.

    Browser callbacks provide fast activation and webhooks are the primary
    provider-driven path. This sweep is the final fallback for cases where the
    browser closes and the webhook delivery never reaches us.
    """
    if limit <= 0:
        raise ValueError("limit must be positive")

    result = RazorpayReconciliationResult()
    rows = (
        db.execute(
            select(Subscription)
            .where(
                Subscription.payment_provider == "razorpay",
                Subscription.payment_request_ref.is_not(None),
                Subscription.payment_subscription_ref.is_(None),
            )
            .order_by(Subscription.updated_at.asc(), Subscription.created_at.asc())
            .limit(limit)
        )
        .scalars()
        .all()
    )

    client = None
    for sub in rows:
        result.examined += 1
        order_id, stored_plan = _parse_stored_razorpay_request(sub.payment_request_ref)
        if not order_id or not stored_plan:
            _record(result, sub, order_id, stored_plan, "skipped", "missing_order_or_plan")
            continue

        try:
            plan_code = _normalize_razorpay_plan_code(stored_plan)
            client = client or (client_factory or _razorpay_client)()
            order = client.order.fetch(order_id)
            payments_payload = client.order.payments(order_id)
            payment = _captured_payment(payments_payload)

            _require_order_metadata(
                sub=sub,
                order=order,
                plan_code=plan_code,
                order_id=order_id,
            )
            _require_order_amount(order=order, plan_code=plan_code)

            order_paid = isinstance(order, dict) and _razorpay_order_is_paid(order)
            payment_captured = payment is not None and _razorpay_payment_is_captured(payment)
            if not (order_paid or payment_captured):
                _record(result, sub, order_id, plan_code, "skipped", "order_not_paid")
                continue
            if payment is None or not str(payment.get("id") or "").strip():
                _record(result, sub, order_id, plan_code, "skipped", "missing_captured_payment")
                continue

            _activate_subscription_from_order(
                db,
                sub=sub,
                order_id=order_id,
                payment=payment,
                plan_code=plan_code,
            )
            result.activated += 1
            result.records.append(
                RazorpayReconciliationRecord(
                    org_id=sub.org_id,
                    order_id=order_id,
                    plan_code=plan_code,
                    result="activated",
                    detail="paid_order_reconciled",
                )
            )
        except (InvalidPlanCodeError, PlanNotSelfServeError, ValueError) as exc:
            db.rollback()
            _record(result, sub, order_id, stored_plan, "skipped", str(exc))
        except (BadRequestError, GatewayError, ServerError) as exc:
            db.rollback()
            result.failed += 1
            result.records.append(
                RazorpayReconciliationRecord(
                    org_id=sub.org_id,
                    order_id=order_id,
                    plan_code=stored_plan,
                    result="failed",
                    detail=exc.__class__.__name__,
                )
            )
            logger.exception(
                "razorpay_reconciliation.provider_error org=%s order=%s",
                sub.org_id,
                order_id,
            )
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            result.failed += 1
            result.records.append(
                RazorpayReconciliationRecord(
                    org_id=sub.org_id,
                    order_id=order_id,
                    plan_code=stored_plan,
                    result="failed",
                    detail=exc.__class__.__name__,
                )
            )
            logger.exception(
                "razorpay_reconciliation.failed org=%s order=%s",
                sub.org_id,
                order_id,
            )

    return result


def _captured_payment(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    items = payload.get("items")
    if not isinstance(items, list):
        return None
    first_payment: dict[str, Any] | None = None
    for item in items:
        if not isinstance(item, dict):
            continue
        if first_payment is None:
            first_payment = item
        if _razorpay_payment_is_captured(item):
            return item
    return first_payment


def _require_order_metadata(
    *,
    sub: Subscription,
    order: Any,
    plan_code: str,
    order_id: str,
) -> None:
    if not isinstance(order, dict):
        raise ValueError("order_response_invalid")
    if str(order.get("id") or "").strip() not in {"", order_id}:
        raise ValueError("order_id_mismatch")
    notes = order.get("notes") if isinstance(order.get("notes"), dict) else {}
    note_org = str(notes.get("org_id") or "").strip()
    if note_org and note_org != sub.org_id:
        raise ValueError("order_org_mismatch")
    note_plan = str(notes.get("plan_code") or "").strip().lower()
    if note_plan and _normalize_razorpay_plan_code(note_plan) != plan_code:
        raise ValueError("order_plan_mismatch")


def _require_order_amount(*, order: dict[str, Any], plan_code: str) -> None:
    expected_amount, _ = _razorpay_amount_for_plan(plan_code)
    try:
        actual_amount = int(order.get("amount") or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("order_amount_invalid") from exc
    currency = str(order.get("currency") or "").strip().upper()
    if actual_amount != expected_amount:
        raise ValueError("order_amount_mismatch")
    if currency != "INR":
        raise ValueError("order_currency_mismatch")


def _activate_subscription_from_order(
    db: Session,
    *,
    sub: Subscription,
    order_id: str,
    payment: dict[str, Any],
    plan_code: str,
) -> None:
    payment_id = str(payment.get("id") or "").strip()
    provider_event_id = f"razorpay_reconcile:{payment_id}"
    existing_event = db.execute(
        select(BillingEvent).where(
            BillingEvent.provider == "razorpay",
            BillingEvent.provider_event_id == provider_event_id,
        )
    ).scalar_one_or_none()

    sub.plan_code = plan_code
    sub.status = "active"
    sub.trial_end = None
    sub.current_period_end = datetime.now(timezone.utc) + timedelta(days=30)
    sub.payment_provider = "razorpay"
    sub.payment_request_ref = order_id
    sub.payment_subscription_ref = payment_id
    seed_plan_entitlements(db, org_id=sub.org_id, plan_code=plan_code, commit=False)
    if existing_event is None:
        db.add(
            BillingEvent(
                provider="razorpay",
                provider_event_id=provider_event_id,
                event_type="payment.reconciled",
                provider_created_at=datetime.now(timezone.utc),
                processed_at=datetime.now(timezone.utc),
                result="applied",
                affected_org_id=sub.org_id,
                payload_json=json.dumps(
                    {
                        "provider": "razorpay",
                        "payment_id": payment_id,
                        "order_id": order_id,
                        "plan_code": plan_code,
                        "org_id": sub.org_id,
                        "source": "reconciliation",
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            )
        )
    db.add(sub)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise
    entitlements_resolver.invalidate(sub.org_id)


def _record(
    result: RazorpayReconciliationResult,
    sub: Subscription,
    order_id: str | None,
    plan_code: str | None,
    outcome: str,
    detail: str,
) -> None:
    if outcome == "skipped":
        result.skipped += 1
    elif outcome == "failed":
        result.failed += 1
    result.records.append(
        RazorpayReconciliationRecord(
            org_id=sub.org_id,
            order_id=order_id,
            plan_code=plan_code,
            result=outcome,
            detail=detail,
        )
    )


__all__ = [
    "RazorpayReconciliationRecord",
    "RazorpayReconciliationResult",
    "reconcile_pending_razorpay_orders",
]
