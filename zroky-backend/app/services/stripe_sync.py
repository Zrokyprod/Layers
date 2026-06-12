"""
Stripe → DB reconciliation (Module 5; plan §3.3 + §11.3 + §17.1 risk #3).

Single entry point:
  `dispatch_event(db, event) -> EventDispatchResult`

The webhook route hands us a verified Stripe event payload (already
through `verify_webhook_signature`). We:

  1. INSERT-or-conflict on `stripe_events.stripe_event_id` to claim
     the event idempotently. A duplicate delivery short-circuits with
     `duplicate=True`; the route returns 200 so Stripe stops retrying.
  2. Dispatch to a per-event-type handler:
        checkout.session.completed         → `_apply_checkout_completed`
        customer.subscription.updated      → `_apply_subscription_updated`
        customer.subscription.deleted      → `_apply_subscription_deleted`
        invoice.paid                       → `_apply_invoice_paid`
        invoice.payment_failed             → `_apply_invoice_payment_failed`
        (anything else)                    → `_apply_skipped`
  3. Each handler upserts the matching `subscriptions` row AND seeds
     `entitlements` rows (via `services.entitlements`).
  4. We update the `stripe_events` row with `processed_at`, `result`,
     `affected_org_id`, and (on failure) `error_message`. The row is
     committed even if the handler raised — this is the audit trail.

Out-of-order arrivals (plan §17.1 risk #3): the
`subscriptions.current_period_end` field acts as a causal token.
A handler refuses to apply an UPDATE event whose Stripe-side timestamp
is older than what's already on the row. Implementation detail: we use
`stripe_created_at` from the event envelope as the causal clock.

What this module does NOT do:
  - Verify the webhook signature (the route does that).
  - Parse plan_code from Stripe Price IDs (we read it from
    `subscription.metadata.plan_code` which the checkout session sets,
    falling back to a price-id lookup).
  - Issue refunds, send dunning emails, or anything user-facing.
    Module 5 is data-plane only.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Subscription, StripeEvent
from app.services.billing_plans import (
    PLAN_ENTITLEMENTS,
    VALID_PLAN_CODES,
    parse_price_map,
)
from app.services.entitlements import (
    clear_plan_entitlements,
    clear_trial_entitlements,
    seed_plan_entitlements,
    set_trial_entitlements,
)

logger = logging.getLogger(__name__)
_STALE_EVENT_CLOCK_SKEW = timedelta(seconds=10)


# ── handled vocab ───────────────────────────────────────────────────────────


HANDLED_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "checkout.session.completed",
        "customer.subscription.updated",
        "customer.subscription.created",  # treat same as updated
        "customer.subscription.deleted",
        "invoice.paid",
        "invoice.payment_failed",
    }
)


# ── result envelope ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EventDispatchResult:
    stripe_event_id: str
    event_type: str
    duplicate: bool
    result: str  # 'applied' | 'skipped' | 'failed'
    affected_org_id: str | None = None
    error_message: str | None = None


# ── helpers ─────────────────────────────────────────────────────────────────


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ts_to_dt(value: Any) -> datetime | None:
    """Stripe sends unix-epoch seconds for `created`, `current_period_end`,
    `trial_end`, etc. NULL when absent."""
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _normalize_status(stripe_status: str | None) -> str:
    """Map Stripe subscription status → our status enum (also includes
    `trialing` etc.)."""
    if not stripe_status:
        return "incomplete"
    norm = str(stripe_status).strip().lower()
    if norm not in {
        "trialing", "active", "past_due", "canceled", "unpaid", "incomplete",
        "incomplete_expired",
    }:
        return "incomplete"
    if norm == "incomplete_expired":
        return "incomplete"
    return norm


def _extract_org_id(obj: dict[str, Any]) -> str | None:
    """org_id is wired into Stripe via `metadata.org_id` on the
    Checkout Session AND on the Subscription (set via
    `subscription_data.metadata.org_id` at checkout time). We also
    fall back to `client_reference_id` on the checkout session."""
    if not isinstance(obj, dict):
        return None
    metadata = obj.get("metadata") or {}
    if isinstance(metadata, dict):
        candidate = metadata.get("org_id")
        if candidate and isinstance(candidate, str):
            return candidate.strip() or None
    cri = obj.get("client_reference_id")
    if cri and isinstance(cri, str):
        return cri.strip() or None
    return None


def _extract_plan_code(obj: dict[str, Any]) -> str | None:
    """Resolve plan_code from (in priority order):
      1) `metadata.plan_code` on the Subscription/Session
      2) Stripe price id lookup against STRIPE_PRICE_IDS_JSON
    Returns None if both fail."""
    if not isinstance(obj, dict):
        return None
    metadata = obj.get("metadata") or {}
    if isinstance(metadata, dict):
        cand = metadata.get("plan_code")
        if isinstance(cand, str):
            norm = cand.strip().lower()
            if norm in VALID_PLAN_CODES:
                return norm

    # Subscription has `items.data[0].price.id`; Checkout Session
    # has `display_items` (legacy) or we already passed plan_code via
    # metadata so this is the fallback.
    items = obj.get("items") or {}
    if isinstance(items, dict):
        data = items.get("data") or []
        if isinstance(data, list) and data:
            price = (data[0] or {}).get("price") or {}
            price_id = price.get("id") if isinstance(price, dict) else None
            if isinstance(price_id, str) and price_id.strip():
                inverse = {v: k for k, v in parse_price_map().items()}
                hit = inverse.get(price_id.strip())
                if hit and hit in VALID_PLAN_CODES:
                    return hit
    return None


def _get_or_create_subscription(
    db: Session, *, org_id: str, plan_code: str
) -> Subscription:
    row = db.execute(
        select(Subscription).where(Subscription.org_id == org_id)
    ).scalar_one_or_none()
    if row is not None:
        return row
    row = Subscription(
        id=str(uuid4()),
        org_id=org_id,
        plan_code=plan_code,
        status="incomplete",
        seats=1,
    )
    db.add(row)
    db.flush()  # populate defaults; commit happens later
    return row


def _is_stale_event(
    sub: Subscription, event_created_at: datetime | None
) -> bool:
    """Out-of-order delivery defence: refuse to apply an event whose
    Stripe-side timestamp is older than `subscription.updated_at`.

    NULL timestamps are treated as "current" so first-write goes
    through (the alternative — refusing — would deadlock initial
    setup).
    """
    if event_created_at is None or sub.updated_at is None:
        return False
    if not sub.stripe_sub_id and sub.status == "incomplete":
        return False
    # Only block clearly older events. Same-second is allowed (Stripe
    # can emit two events with identical `created` for related ops), and
    # Stripe timestamps are second-granularity while local DB timestamps
    # may be slightly later due to processing latency.
    return event_created_at < (sub.updated_at - _STALE_EVENT_CLOCK_SKEW)


# ── per-event handlers ──────────────────────────────────────────────────────


def _apply_checkout_completed(
    db: Session, *, event_obj: dict[str, Any]
) -> tuple[str, str | None]:
    """checkout.session.completed → seed Subscription + plan entitlements."""
    org_id = _extract_org_id(event_obj)
    if not org_id:
        return "skipped", None
    plan_code = _extract_plan_code(event_obj) or "pro"  # safe default
    if plan_code not in VALID_PLAN_CODES:
        return "skipped", org_id

    customer_id = event_obj.get("customer") if isinstance(event_obj, dict) else None
    sub_id = event_obj.get("subscription") if isinstance(event_obj, dict) else None

    sub = _get_or_create_subscription(db, org_id=org_id, plan_code=plan_code)
    sub.plan_code = plan_code
    sub.status = "active"
    if isinstance(customer_id, str) and customer_id.strip():
        sub.stripe_customer_id = customer_id.strip()
    if isinstance(sub_id, str) and sub_id.strip():
        sub.stripe_sub_id = sub_id.strip()
    db.add(sub)

    seed_plan_entitlements(db, org_id=org_id, plan_code=plan_code, commit=False)
    return "applied", org_id


def _apply_subscription_event(
    db: Session,
    *,
    event_obj: dict[str, Any],
    event_created_at: datetime | None,
    is_delete: bool,
) -> tuple[str, str | None]:
    """Shared logic for customer.subscription.{created,updated,deleted}."""
    org_id = _extract_org_id(event_obj)
    if not org_id:
        return "skipped", None
    plan_code = _extract_plan_code(event_obj)
    stripe_sub_id = event_obj.get("id") if isinstance(event_obj, dict) else None
    customer_id = event_obj.get("customer") if isinstance(event_obj, dict) else None
    status_norm = _normalize_status(event_obj.get("status"))
    cpe = _ts_to_dt(event_obj.get("current_period_end"))
    trial_end = _ts_to_dt(event_obj.get("trial_end"))

    sub = _get_or_create_subscription(
        db, org_id=org_id, plan_code=plan_code or "free"
    )
    if _is_stale_event(sub, event_created_at):
        logger.info(
            "stripe_sync.stale_event_dropped org=%s sub=%s event_ts=%s sub_updated=%s",
            org_id, stripe_sub_id, event_created_at, sub.updated_at,
        )
        return "skipped", org_id

    if isinstance(stripe_sub_id, str) and stripe_sub_id.strip():
        sub.stripe_sub_id = stripe_sub_id.strip()
    if isinstance(customer_id, str) and customer_id.strip():
        sub.stripe_customer_id = customer_id.strip()
    if cpe is not None:
        sub.current_period_end = cpe
    if trial_end is not None:
        sub.trial_end = trial_end
    if plan_code:
        sub.plan_code = plan_code

    if is_delete:
        sub.status = "canceled"
        clear_plan_entitlements(db, org_id=org_id, commit=False)
        clear_trial_entitlements(db, org_id=org_id, commit=False)
    else:
        sub.status = status_norm
        # Refresh entitlement layers based on status:
        #   trialing  → trial overlay (plan still seeded for fallback when trial expires)
        #   active    → plan rows; clear trial rows
        #   past_due  → keep existing plan rows; banner only
        #   canceled  → cleared above
        #   unpaid    → grace period; do NOT clear yet
        if plan_code:
            seed_plan_entitlements(db, org_id=org_id, plan_code=plan_code, commit=False)
        if status_norm == "trialing" and plan_code and trial_end:
            set_trial_entitlements(
                db, org_id=org_id, plan_code=plan_code,
                expires_at=trial_end, commit=False,
            )
        elif status_norm == "active":
            clear_trial_entitlements(db, org_id=org_id, commit=False)

    db.add(sub)
    return "applied", org_id


def _apply_invoice_paid(
    db: Session,
    *,
    event_obj: dict[str, Any],
    event_created_at: datetime | None,  # noqa: ARG001 - reserved for stale-check parity
) -> tuple[str, str | None]:
    """invoice.paid → bump subscription back to 'active' if it was past_due,
    refresh current_period_end if newer."""
    org_id = _extract_org_id(event_obj)
    sub_stripe_id = (
        event_obj.get("subscription") if isinstance(event_obj, dict) else None
    )
    if not isinstance(sub_stripe_id, str) or not sub_stripe_id.strip():
        return "skipped", org_id

    sub = db.execute(
        select(Subscription).where(
            Subscription.stripe_sub_id == sub_stripe_id.strip()
        )
    ).scalar_one_or_none()
    if sub is None:
        return "skipped", org_id

    # invoice.paid restores the customer from `past_due` → `active`.
    # If status was `canceled` we leave it (a paid invoice for a
    # canceled sub is a closing/refund event, not a re-activation).
    if sub.status == "past_due":
        sub.status = "active"
    cpe = _ts_to_dt(
        (event_obj.get("lines") or {}).get("data", [{}])[0].get("period", {}).get("end")
        if isinstance(event_obj.get("lines"), dict) else None
    )
    # Fallback: invoice.period_end on top-level invoice
    if cpe is None:
        cpe = _ts_to_dt(event_obj.get("period_end"))
    if cpe is not None and (sub.current_period_end is None or cpe > sub.current_period_end):
        sub.current_period_end = cpe
    db.add(sub)
    return "applied", sub.org_id


def _apply_invoice_payment_failed(
    db: Session,
    *,
    event_obj: dict[str, Any],
    event_created_at: datetime | None,  # noqa: ARG001
) -> tuple[str, str | None]:
    """invoice.payment_failed → flip subscription to past_due (banner state).
    Plan rows stay so the customer keeps using their tier during grace."""
    org_id = _extract_org_id(event_obj)
    sub_stripe_id = (
        event_obj.get("subscription") if isinstance(event_obj, dict) else None
    )
    if not isinstance(sub_stripe_id, str) or not sub_stripe_id.strip():
        return "skipped", org_id

    sub = db.execute(
        select(Subscription).where(
            Subscription.stripe_sub_id == sub_stripe_id.strip()
        )
    ).scalar_one_or_none()
    if sub is None:
        return "skipped", org_id

    if sub.status not in {"canceled", "incomplete"}:
        sub.status = "past_due"
    db.add(sub)
    return "applied", sub.org_id


# ── public dispatcher ───────────────────────────────────────────────────────


def dispatch_event(
    db: Session, event: dict[str, Any]
) -> EventDispatchResult:
    """Idempotent webhook event handler.

    Args:
      db:    request-scoped Session (route owns the lifecycle)
      event: parsed Stripe event payload (top-level dict)

    Returns: EventDispatchResult with `duplicate`, `result`, etc.
    """
    if not isinstance(event, dict):
        raise ValueError("event payload must be a dict")
    event_id = str(event.get("id") or "").strip()
    event_type = str(event.get("type") or "").strip()
    if not event_id or not event_type:
        raise ValueError("event missing id or type")

    payload_json = json.dumps(event, separators=(",", ":"), sort_keys=True)
    stripe_created_at = _ts_to_dt(event.get("created"))

    # 1. Idempotent claim. If the row already exists, this is a duplicate
    #    delivery — return early without re-running the handler.
    log_row = StripeEvent(
        id=str(uuid4()),
        stripe_event_id=event_id,
        event_type=event_type,
        stripe_created_at=stripe_created_at,
        payload_json=payload_json,
        result="pending",
    )
    db.add(log_row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.execute(
            select(StripeEvent).where(StripeEvent.stripe_event_id == event_id)
        ).scalar_one_or_none()
        return EventDispatchResult(
            stripe_event_id=event_id,
            event_type=event_type,
            duplicate=True,
            result=existing.result if existing else "applied",
            affected_org_id=existing.affected_org_id if existing else None,
        )

    # 2. Dispatch.
    data = event.get("data") or {}
    obj = data.get("object") if isinstance(data, dict) else {}
    if not isinstance(obj, dict):
        obj = {}

    result_kind: str
    org_id: str | None = None
    error: str | None = None

    try:
        if event_type == "checkout.session.completed":
            result_kind, org_id = _apply_checkout_completed(db, event_obj=obj)
        elif event_type in {
            "customer.subscription.created",
            "customer.subscription.updated",
        }:
            result_kind, org_id = _apply_subscription_event(
                db, event_obj=obj, event_created_at=stripe_created_at,
                is_delete=False,
            )
        elif event_type == "customer.subscription.deleted":
            result_kind, org_id = _apply_subscription_event(
                db, event_obj=obj, event_created_at=stripe_created_at,
                is_delete=True,
            )
        elif event_type == "invoice.paid":
            result_kind, org_id = _apply_invoice_paid(
                db, event_obj=obj, event_created_at=stripe_created_at,
            )
        elif event_type == "invoice.payment_failed":
            result_kind, org_id = _apply_invoice_payment_failed(
                db, event_obj=obj, event_created_at=stripe_created_at,
            )
        else:
            result_kind, org_id = "skipped", _extract_org_id(obj)
    except Exception as exc:  # noqa: BLE001 — we record AND re-raise
        db.rollback()
        # Re-fetch the log row (rollback wiped session state)
        log_row = db.execute(
            select(StripeEvent).where(StripeEvent.stripe_event_id == event_id)
        ).scalar_one_or_none()
        if log_row is not None:
            log_row.result = "failed"
            log_row.processed_at = _now()
            log_row.error_message = str(exc)[:1000]
            db.add(log_row)
            db.commit()
        logger.exception(
            "stripe_sync.handler_failed event_id=%s type=%s",
            event_id, event_type,
        )
        return EventDispatchResult(
            stripe_event_id=event_id,
            event_type=event_type,
            duplicate=False,
            result="failed",
            affected_org_id=None,
            error_message=str(exc)[:1000],
        )

    log_row.result = result_kind
    log_row.processed_at = _now()
    log_row.affected_org_id = org_id
    db.add(log_row)
    db.commit()

    # Cache invalidation: handlers wrote entitlements with commit=False
    # so the resolver-cache hook in services/entitlements.py was skipped.
    # Now that the dispatcher has committed, drop the cached merged dict
    # so the next has()/get() call sees the fresh state immediately
    # (otherwise the 60s TTL is the only freshness bound).
    if result_kind == "applied" and org_id:
        try:
            from app.services.entitlements_resolver import invalidate
            invalidate(org_id)
        except Exception:  # noqa: BLE001 — never propagate from cache hook
            logger.exception(
                "stripe_sync.cache_invalidate_failed event_id=%s org=%s",
                event_id, org_id,
            )

    logger.info(
        "stripe_sync.dispatched event_id=%s type=%s result=%s org=%s",
        event_id, event_type, result_kind, org_id,
    )
    return EventDispatchResult(
        stripe_event_id=event_id,
        event_type=event_type,
        duplicate=False,
        result=result_kind,
        affected_org_id=org_id,
    )


__all__ = [
    "EventDispatchResult",
    "HANDLED_EVENT_TYPES",
    "dispatch_event",
]
