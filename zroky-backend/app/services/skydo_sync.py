"""Skydo payment events -> subscription and entitlement state.

The event shape is intentionally provider-neutral so we can accept:

{
  "id": "evt_or_manual_id",
  "type": "payment.succeeded",
  "provider": "skydo",
  "created": 1760000000,
  "data": {
    "object": {
      "org_id": "project/org id",
      "plan_code": "pro",
      "payment_request_id": "skydo_req_...",
      "payment_ref": "skydo payment or invoice ref",
      "customer_ref": "skydo client ref",
      "period_end": "2026-07-07T00:00:00Z"
    }
  }
}
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

from app.db.models import BillingEvent, Subscription
from app.services.billing_plans import VALID_PLAN_CODES
from app.services.entitlement_catalog import canonical_plan_code
from app.services.entitlements import (
    clear_plan_entitlements,
    clear_trial_entitlements,
    seed_plan_entitlements,
)

logger = logging.getLogger(__name__)


HANDLED_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "payment_request.created",
        "payment.succeeded",
        "payment.failed",
        "payment.canceled",
        "payment.refunded",
        "subscription.canceled",
    }
)


@dataclass(frozen=True)
class EventDispatchResult:
    provider_event_id: str
    provider: str
    event_type: str
    duplicate: bool
    result: str
    affected_org_id: str | None = None
    error_message: str | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ts_to_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(int(value), tz=timezone.utc)
        except (TypeError, ValueError, OverflowError):
            return None
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.isdigit():
            return _ts_to_dt(int(raw))
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _extract_object(event: dict[str, Any]) -> dict[str, Any]:
    data = event.get("data") or {}
    obj = data.get("object") if isinstance(data, dict) else None
    if isinstance(obj, dict):
        return obj
    return data if isinstance(data, dict) else {}


def _metadata(obj: dict[str, Any]) -> dict[str, Any]:
    metadata = obj.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _extract_org_id(obj: dict[str, Any]) -> str | None:
    for key in ("org_id", "project_id", "tenant_id", "client_reference_id"):
        value = obj.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    metadata = _metadata(obj)
    for key in ("org_id", "project_id", "tenant_id"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _extract_plan_code(obj: dict[str, Any]) -> str | None:
    value = obj.get("plan_code") or _metadata(obj).get("plan_code")
    if not isinstance(value, str):
        return None
    norm = value.strip().lower()
    if norm not in VALID_PLAN_CODES:
        return None
    return canonical_plan_code(norm)


def _first_text(obj: dict[str, Any], *keys: str) -> str | None:
    metadata = _metadata(obj)
    for key in keys:
        value = obj.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
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
        payment_provider="skydo",
    )
    db.add(row)
    db.flush()
    return row


def _sync_payment_refs(sub: Subscription, obj: dict[str, Any]) -> None:
    sub.payment_provider = "skydo"
    payment_request_ref = _first_text(
        obj, "payment_request_id", "payment_request_ref", "checkout_session_id"
    )
    payment_ref = _first_text(
        obj, "payment_ref", "payment_id", "invoice_id", "subscription_ref"
    )
    customer_ref = _first_text(obj, "customer_ref", "client_id", "customer_id")
    if payment_request_ref:
        sub.payment_request_ref = payment_request_ref
    if payment_ref:
        sub.payment_subscription_ref = payment_ref
    if customer_ref:
        sub.payment_customer_ref = customer_ref


def _apply_payment_request_created(
    db: Session, *, event_obj: dict[str, Any]
) -> tuple[str, str | None]:
    org_id = _extract_org_id(event_obj)
    plan_code = _extract_plan_code(event_obj)
    if not org_id or not plan_code:
        return "skipped", org_id
    sub = _get_or_create_subscription(db, org_id=org_id, plan_code=plan_code)
    sub.plan_code = plan_code
    sub.status = "incomplete"
    _sync_payment_refs(sub, event_obj)
    db.add(sub)
    return "applied", org_id


def _apply_payment_succeeded(
    db: Session,
    *,
    event_obj: dict[str, Any],
    event_created_at: datetime | None,
) -> tuple[str, str | None]:
    org_id = _extract_org_id(event_obj)
    plan_code = _extract_plan_code(event_obj)
    if not org_id or not plan_code:
        return "skipped", org_id

    sub = _get_or_create_subscription(db, org_id=org_id, plan_code=plan_code)
    sub.plan_code = plan_code
    sub.status = "active"
    sub.trial_end = None
    period_end = (
        _ts_to_dt(event_obj.get("period_end"))
        or _ts_to_dt(event_obj.get("current_period_end"))
        or ((event_created_at or _now()) + timedelta(days=30))
    )
    sub.current_period_end = period_end
    _sync_payment_refs(sub, event_obj)
    db.add(sub)
    seed_plan_entitlements(db, org_id=org_id, plan_code=plan_code, commit=False)
    clear_trial_entitlements(db, org_id=org_id, commit=False)
    return "applied", org_id


def _apply_payment_failed(
    db: Session, *, event_obj: dict[str, Any]
) -> tuple[str, str | None]:
    org_id = _extract_org_id(event_obj)
    if not org_id:
        return "skipped", None
    sub = db.execute(
        select(Subscription).where(Subscription.org_id == org_id)
    ).scalar_one_or_none()
    if sub is None:
        return "skipped", org_id
    if sub.status not in {"canceled", "incomplete"}:
        sub.status = "past_due"
    _sync_payment_refs(sub, event_obj)
    db.add(sub)
    return "applied", org_id


def _apply_canceled(
    db: Session, *, event_obj: dict[str, Any]
) -> tuple[str, str | None]:
    org_id = _extract_org_id(event_obj)
    if not org_id:
        return "skipped", None
    sub = db.execute(
        select(Subscription).where(Subscription.org_id == org_id)
    ).scalar_one_or_none()
    if sub is None:
        return "skipped", org_id
    sub.status = "canceled"
    _sync_payment_refs(sub, event_obj)
    db.add(sub)
    clear_plan_entitlements(db, org_id=org_id, commit=False)
    clear_trial_entitlements(db, org_id=org_id, commit=False)
    return "applied", org_id


def dispatch_event(db: Session, event: dict[str, Any]) -> EventDispatchResult:
    if not isinstance(event, dict):
        raise ValueError("event payload must be a dict")
    provider = str(event.get("provider") or "skydo").strip().lower()
    event_id = str(event.get("id") or event.get("event_id") or "").strip()
    event_type = str(event.get("type") or event.get("event_type") or "").strip()
    if not event_id or not event_type:
        raise ValueError("event missing id or type")

    payload_json = json.dumps(event, separators=(",", ":"), sort_keys=True)
    provider_created_at = _ts_to_dt(event.get("created") or event.get("created_at"))
    log_row = BillingEvent(
        id=str(uuid4()),
        provider=provider,
        provider_event_id=event_id,
        event_type=event_type,
        provider_created_at=provider_created_at,
        payload_json=payload_json,
        result="pending",
    )
    db.add(log_row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.execute(
            select(BillingEvent).where(
                BillingEvent.provider == provider,
                BillingEvent.provider_event_id == event_id,
            )
        ).scalar_one_or_none()
        return EventDispatchResult(
            provider_event_id=event_id,
            provider=provider,
            event_type=event_type,
            duplicate=True,
            result=existing.result if existing else "applied",
            affected_org_id=existing.affected_org_id if existing else None,
        )

    obj = _extract_object(event)
    result_kind: str
    org_id: str | None = None

    try:
        if event_type == "payment_request.created":
            result_kind, org_id = _apply_payment_request_created(
                db, event_obj=obj
            )
        elif event_type == "payment.succeeded":
            result_kind, org_id = _apply_payment_succeeded(
                db, event_obj=obj, event_created_at=provider_created_at
            )
        elif event_type == "payment.failed":
            result_kind, org_id = _apply_payment_failed(db, event_obj=obj)
        elif event_type in {
            "payment.canceled",
            "payment.refunded",
            "subscription.canceled",
        }:
            result_kind, org_id = _apply_canceled(db, event_obj=obj)
        else:
            result_kind, org_id = "skipped", _extract_org_id(obj)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        log_row = db.execute(
            select(BillingEvent).where(
                BillingEvent.provider == provider,
                BillingEvent.provider_event_id == event_id,
            )
        ).scalar_one_or_none()
        if log_row is None:
            log_row = BillingEvent(
                id=str(uuid4()),
                provider=provider,
                provider_event_id=event_id,
                event_type=event_type,
                provider_created_at=provider_created_at,
                payload_json=payload_json,
            )
        if log_row is not None:
            log_row.result = "failed"
            log_row.processed_at = _now()
            log_row.error_message = str(exc)[:1000]
            db.add(log_row)
            db.commit()
        logger.exception(
            "skydo_sync.handler_failed event_id=%s type=%s",
            event_id, event_type,
        )
        return EventDispatchResult(
            provider_event_id=event_id,
            provider=provider,
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

    if result_kind == "applied" and org_id:
        try:
            from app.services.entitlements_resolver import invalidate
            invalidate(org_id)
        except Exception:  # noqa: BLE001
            logger.exception(
                "skydo_sync.cache_invalidate_failed event_id=%s org=%s",
                event_id, org_id,
            )

    return EventDispatchResult(
        provider_event_id=event_id,
        provider=provider,
        event_type=event_type,
        duplicate=False,
        result=result_kind,
        affected_org_id=org_id,
    )


__all__ = ["EventDispatchResult", "HANDLED_EVENT_TYPES", "dispatch_event"]
