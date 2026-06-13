"""
/v1/billing/* — billing routes.

Two routers coexist in this file. `api/router.py` mounts them under
separate feature flags so the legacy surface can be retired without
disturbing the §11.3 contract.

  Hosted billing (Module 5 / 12; plan section 11.3) always mounted:
    POST /v1/billing/razorpay/order   Razorpay Standard Checkout order
    POST /v1/billing/razorpay/verify  Razorpay client callback verification
    POST /v1/billing/webhook          signed Razorpay webhook receiver
    GET  /v1/billing/me               current org plan + SLA tier + entitlements baseline

  Legacy (Module 12 default-off; gated by FEATURE_LEGACY_BILLING):
    GET  /v1/billing/plans
    GET  /v1/billing/subscription
    PUT  /v1/billing/subscription
    GET  /v1/billing/usage

The legacy surface reads from the deprecated `tenant_subscriptions`
table. New code paths read `subscriptions` (org-scoped, provider-neutral)
via `services.entitlements_resolver`. The legacy file will be deleted
in a follow-up cleanup once the dashboard migrates off `/plans` and
`/usage` (tracked separately from Module 12).
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from razorpay.errors import BadRequestError, GatewayError, ServerError
from fastapi import (
    APIRouter,
    Body,
    Depends,
    HTTPException,
    Header,
    Request,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import require_tenant_id, require_tenant_role
from app.api.routes._internal.billing_schemas import (
    BillingMeResponse,
    CheckoutRequest,
    CheckoutResponse,
    PortalResponse,
    RazorpayOrderRequest,
    RazorpayOrderResponse,
    RazorpayVerifyRequest,
    RazorpayVerifyResponse,
    WebhookResponse,
)
from app.core.config import get_settings
from app.core.limiter import limiter
from app.db.models import (
    BillingEvent,
    GoldenSet,
    GoldenTrace,
    Subscription,
)
from app.db.session import get_db_session
from app.schemas.billing import (
    BillingMeteringHealthResponse,
    BillingUsageMeter,
    BillingUsageResponse,
)
from app.services.billing_plans import (
    DEFAULT_PLAN_CODE,
    InvalidPlanCodeError,
    PLAN_ENTITLEMENTS,
    PlanNotSelfServeError,
)
from app.services.billing_quota import get_usage as _quota_get_usage
from app.services.billing_metering import get_metering_health
from app.services import entitlements_resolver
from app.services.entitlements import seed_plan_entitlements
from app.services.replay_runs import check_replay_monthly_quota
from app.api.routes.billing_legacy import router as _legacy_router
from app.api.routes._internal.billing_razorpay import (
    _normalize_razorpay_plan_code,
    _parse_stored_razorpay_request,
    _razorpay_amount_for_plan,
    _razorpay_auth_failure,
    _razorpay_client,
    _razorpay_receipt,
    _razorpay_webhook_confirms_paid,
    _razorpay_webhook_event_id,
    _require_razorpay_paid_checkout as _internal_require_razorpay_paid_checkout,
    _verify_razorpay_signature,
    _verify_razorpay_webhook_signature,
)

logger = logging.getLogger(__name__)

# §11.3 surface (always mounted by api/router.py).
router = APIRouter(prefix="/v1/billing")

# Legacy surface (gated by FEATURE_LEGACY_BILLING; default-off as of
# Module 12). Mounted under the same /v1/billing prefix so existing
# clients see no path change while the flag is on.
legacy_router = _legacy_router


def _require_razorpay_paid_checkout(
    *,
    payment_id: str,
    order_id: str,
    org_id: str,
    plan_code: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    return _internal_require_razorpay_paid_checkout(
        payment_id=payment_id,
        order_id=order_id,
        org_id=org_id,
        plan_code=plan_code,
        client_factory=_razorpay_client,
    )


# ════════════════════════════════════════════════════════════════════════════
# Module 5 - hosted Razorpay billing surface
# ════════════════════════════════════════════════════════════════════════════


def _require_billing_enabled() -> None:
    s = get_settings()
    if not s.BILLING_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Billing is disabled (BILLING_ENABLED=false). "
                "Self-host instances skip hosted billing by design."
            ),
        )


def _resolve_org_id(tenant_id: str) -> str:
    """`subscriptions.org_id` is the billing entity. Until the `orgs`
    table ships (Module 6/8), org_id == project_id (the tenant_id from
    the auth dependency). This helper centralises the indirection so the
    later org rewire only touches one place.
    """
    return tenant_id


def _get_or_create_org_subscription(
    db: Session, *, org_id: str
) -> Subscription:
    """Return the new-style `Subscription` row for an org, creating a
    free-tier shell when missing. The shell is needed by GET /me even
    before any paid billing interaction has happened."""
    row = db.execute(
        select(Subscription).where(Subscription.org_id == org_id)
    ).scalar_one_or_none()
    if row is not None:
        return row

    row = Subscription(
        org_id=org_id,
        payment_provider="razorpay",
        plan_code=DEFAULT_PLAN_CODE,
        status="active",
        seats=1,
    )
    db.add(row)
    try:
        db.commit()
        db.refresh(row)
    except IntegrityError:
        db.rollback()
        row = db.execute(
            select(Subscription).where(Subscription.org_id == org_id)
        ).scalar_one()
    return row


# ── schemas ──────────────────────────────────────────────────────────────────


def _usage_meter(*, used: int, limit: int | None, resets_at: str | None = None) -> BillingUsageMeter:
    if limit is None or limit < 0:
        return BillingUsageMeter(
            used=used,
            limit=None,
            unlimited=True,
            overage=None,
            state="ok",
            resets_at=resets_at,
        )
    overage = max(0, used - limit)
    if limit <= 0:
        state = "blocked" if used == 0 else "exceeded"
    elif used >= limit:
        state = "exceeded"
    elif used / limit >= 0.8:
        state = "near_limit"
    else:
        state = "ok"
    return BillingUsageMeter(
        used=used,
        limit=limit,
        unlimited=False,
        overage=overage or None,
        state=state,
        resets_at=resets_at,
    )


def _month_bounds() -> tuple[datetime, datetime, str]:
    now = datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end, start.strftime("%Y-%m")


def _resolved_int_entitlement(
    db: Session,
    org_id: str,
    key: str,
    *,
    default: int = 0,
) -> int:
    try:
        raw = entitlements_resolver.get(db, org_id, key, default=default)
        return int(raw) if raw is not None else default
    except (TypeError, ValueError):
        return default


# ── routes ───────────────────────────────────────────────────────────────────


@router.post(
    "/checkout",
    response_model=CheckoutResponse,
    status_code=status.HTTP_200_OK,
)
@limiter.limit("12/minute")
def create_checkout_session(
    request: Request,
    body: CheckoutRequest = Body(...),
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> CheckoutResponse:
    """Legacy compatibility endpoint.

    Razorpay Standard Checkout needs an order id, so new clients must call
    `/v1/billing/razorpay/order` and then open Razorpay Checkout in-browser.
    """
    _require_billing_enabled()
    try:
        _normalize_razorpay_plan_code(body.plan_code)
    except (InvalidPlanCodeError, PlanNotSelfServeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Use /v1/billing/razorpay/order for Razorpay Standard Checkout.",
    )


@router.post(
    "/razorpay/order",
    response_model=RazorpayOrderResponse,
    status_code=status.HTTP_200_OK,
)
@limiter.limit("12/minute")
def create_razorpay_order(
    request: Request,
    body: RazorpayOrderRequest = Body(...),
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> RazorpayOrderResponse:
    """Create a Razorpay Standard Checkout order for a tenant-scoped plan."""
    _require_billing_enabled()
    org_id = _resolve_org_id(tenant_id)
    currency = body.currency.strip().upper()
    plan_norm: str | None = None
    amount_usd: int | None = None
    amount = body.amount

    if body.plan_code:
        try:
            plan_norm = _normalize_razorpay_plan_code(body.plan_code)
        except (InvalidPlanCodeError, PlanNotSelfServeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
        if currency != "INR":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Self-serve Razorpay plan checkout uses INR.",
            )
        amount, amount_usd = _razorpay_amount_for_plan(plan_norm)
        if body.amount is not None and body.amount != amount:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="amount does not match the selected plan.",
            )

    if amount is None or amount < 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="amount must be at least 100 in the smallest currency unit.",
        )

    receipt = body.receipt or _razorpay_receipt(org_id, plan_norm)
    payload: dict[str, Any] = {
        "amount": amount,
        "currency": currency,
        "receipt": receipt,
        "notes": {
            "org_id": org_id,
            "plan_code": plan_norm or "",
            "product": "zroky",
        },
    }
    if body.customer_email:
        payload["notes"]["customer_email"] = body.customer_email

    try:
        order = _razorpay_client().order.create(data=payload)
    except BadRequestError as exc:
        logger.exception("billing.razorpay_order_bad_request org=%s", org_id)
        status_code = (
            status.HTTP_401_UNAUTHORIZED
            if _razorpay_auth_failure(exc)
            else status.HTTP_500_INTERNAL_SERVER_ERROR
        )
        detail = (
            "Razorpay authentication failed."
            if status_code == status.HTTP_401_UNAUTHORIZED
            else "Razorpay order creation failed."
        )
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except (GatewayError, ServerError) as exc:
        logger.exception("billing.razorpay_order_gateway_error org=%s", org_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Razorpay order creation failed.",
        ) from exc
    except Exception as exc:
        logger.exception("billing.razorpay_order_failed org=%s", org_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Razorpay order creation failed.",
        ) from exc

    order_id = str(order.get("id") or "")
    if not order_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Razorpay order response did not include an order id.",
        )

    sub = _get_or_create_org_subscription(db, org_id=org_id)
    sub.payment_provider = "razorpay"
    sub.payment_request_ref = f"{order_id}:{plan_norm}" if plan_norm else order_id
    if body.customer_email:
        sub.payment_customer_ref = body.customer_email
    db.add(sub)
    db.commit()

    return RazorpayOrderResponse(
        order_id=order_id,
        amount=int(order.get("amount") or amount),
        currency=str(order.get("currency") or currency),
        receipt=str(order.get("receipt") or receipt),
        plan_code=plan_norm,
        org_id=org_id,
        amount_usd=amount_usd,
    )


@router.post(
    "/razorpay/verify",
    response_model=RazorpayVerifyResponse,
    status_code=status.HTTP_200_OK,
)
@limiter.limit("30/minute")
def verify_razorpay_payment(
    request: Request,
    body: RazorpayVerifyRequest = Body(...),
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> RazorpayVerifyResponse:
    """Verify Razorpay checkout success signature and activate the paid plan."""
    _require_billing_enabled()
    org_id = _resolve_org_id(tenant_id)

    if not _verify_razorpay_signature(
        order_id=body.razorpay_order_id,
        payment_id=body.razorpay_payment_id,
        signature=body.razorpay_signature,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Razorpay signature mismatch.",
        )

    sub = _get_or_create_org_subscription(db, org_id=org_id)
    stored_order_id, plan_norm = _parse_stored_razorpay_request(
        sub.payment_request_ref
    )
    if stored_order_id != body.razorpay_order_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Razorpay order is not pending for this org.",
        )

    if plan_norm:
        try:
            plan_norm = _normalize_razorpay_plan_code(plan_norm)
        except (InvalidPlanCodeError, PlanNotSelfServeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Stored Razorpay plan is not valid for self-serve checkout.",
            ) from exc

    _require_razorpay_paid_checkout(
        payment_id=body.razorpay_payment_id,
        order_id=body.razorpay_order_id,
        org_id=org_id,
        plan_code=plan_norm,
    )

    if plan_norm:
        sub.plan_code = plan_norm
        sub.status = "active"
        sub.trial_end = None
        sub.current_period_end = datetime.now(timezone.utc) + timedelta(days=30)
        seed_plan_entitlements(db, org_id=org_id, plan_code=plan_norm, commit=False)

    sub.payment_provider = "razorpay"
    sub.payment_request_ref = body.razorpay_order_id
    sub.payment_subscription_ref = body.razorpay_payment_id
    provider_event_id = f"razorpay_verify:{body.razorpay_payment_id}"
    existing_event = db.execute(
        select(BillingEvent).where(
            BillingEvent.provider == "razorpay",
            BillingEvent.provider_event_id == provider_event_id,
        )
    ).scalar_one_or_none()
    if existing_event is None:
        db.add(
            BillingEvent(
                provider="razorpay",
                provider_event_id=provider_event_id,
                event_type="payment.succeeded",
                provider_created_at=datetime.now(timezone.utc),
                processed_at=datetime.now(timezone.utc),
                result="applied",
                affected_org_id=org_id,
                payload_json=json.dumps(
                    {
                        "provider": "razorpay",
                        "payment_id": body.razorpay_payment_id,
                        "order_id": body.razorpay_order_id,
                        "plan_code": plan_norm,
                        "org_id": org_id,
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
        existing_event = db.execute(
            select(BillingEvent).where(
                BillingEvent.provider == "razorpay",
                BillingEvent.provider_event_id == provider_event_id,
            )
        ).scalar_one_or_none()
        if existing_event is None:
            raise
    entitlements_resolver.invalidate(org_id)

    return RazorpayVerifyResponse(
        success=True,
        order_id=body.razorpay_order_id,
        payment_id=body.razorpay_payment_id,
        org_id=org_id,
        plan_code=plan_norm,
    )


@router.post(
    "/portal",
    response_model=PortalResponse,
    status_code=status.HTTP_200_OK,
)
@limiter.limit("12/minute")
def create_portal_session(
    request: Request,
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> PortalResponse:
    """Return the configured Razorpay dashboard URL for billing operations."""
    _require_billing_enabled()
    org_id = _resolve_org_id(tenant_id)
    portal_url = (get_settings().RAZORPAY_DASHBOARD_URL or "").strip()
    if not portal_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RAZORPAY_DASHBOARD_URL is not configured.",
        )

    return PortalResponse(
        session_id="razorpay_dashboard",
        portal_url=portal_url,
        org_id=org_id,
        payment_provider="razorpay",
    )


@router.post("/webhook", response_model=WebhookResponse)
@limiter.limit("600/minute")
async def receive_billing_webhook(
    request: Request,
    razorpay_signature: str | None = Header(default=None, alias="X-Razorpay-Signature"),
    db: Session = Depends(get_db_session),
) -> WebhookResponse:
    """Signed Razorpay webhook receiver."""
    settings = get_settings()
    if not settings.BILLING_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing is disabled.",
        )

    raw_body = await request.body()
    _verify_razorpay_webhook_signature(
        payload=raw_body,
        signature=razorpay_signature,
    )
    try:
        event = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Razorpay webhook JSON.",
        ) from exc
    if not isinstance(event, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Razorpay webhook payload.",
        )

    event_type = str(event.get("event") or event.get("type") or "unknown").strip()
    event_id = _razorpay_webhook_event_id(event, raw_body)
    existing_event = db.execute(
        select(BillingEvent).where(
            BillingEvent.provider == "razorpay",
            BillingEvent.provider_event_id == event_id,
        )
    ).scalar_one_or_none()
    if existing_event is not None:
        return WebhookResponse(
            received=True,
            duplicate=True,
            event_type=event_type,
            result=existing_event.result or "skipped",
            affected_org_id=existing_event.affected_org_id,
        )

    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    payment = payload.get("payment", {}).get("entity", {}) if isinstance(payload, dict) else {}
    order = payload.get("order", {}).get("entity", {}) if isinstance(payload, dict) else {}
    data_object = event.get("data", {}).get("object", {}) if isinstance(event.get("data"), dict) else {}
    if not isinstance(payment, dict):
        payment = {}
    if not isinstance(order, dict):
        order = {}
    if not isinstance(data_object, dict):
        data_object = {}
    notes = payment.get("notes") or order.get("notes") or data_object.get("notes") or data_object or {}
    if not isinstance(notes, dict):
        notes = {}

    org_id = str(event.get("org_id") or notes.get("org_id") or "").strip() or None
    plan_code = str(event.get("plan_code") or notes.get("plan_code") or "").strip().lower() or None
    payment_id = str(payment.get("id") or data_object.get("payment_ref") or event.get("payment_id") or "").strip() or None
    order_id = str(order.get("id") or payment.get("order_id") or data_object.get("payment_request_id") or event.get("order_id") or "").strip() or None
    result = "skipped"
    invalidate_org_id: str | None = None
    if org_id and _razorpay_webhook_confirms_paid(
        event_type=event_type,
        payment=payment,
        order=order,
    ):
        sub = _get_or_create_org_subscription(db, org_id=org_id)
        sub.payment_provider = "razorpay"
        sub.payment_request_ref = order_id or sub.payment_request_ref
        sub.payment_subscription_ref = payment_id or sub.payment_subscription_ref
        if plan_code:
            try:
                normalized_plan = _normalize_razorpay_plan_code(plan_code)
            except (InvalidPlanCodeError, PlanNotSelfServeError):
                normalized_plan = None
            if normalized_plan:
                sub.plan_code = normalized_plan
                sub.status = "active"
                sub.trial_end = None
                sub.current_period_end = datetime.now(timezone.utc) + timedelta(days=30)
                seed_plan_entitlements(db, org_id=org_id, plan_code=normalized_plan, commit=False)
                invalidate_org_id = org_id
        db.add(sub)
        result = "applied"

    db.add(
        BillingEvent(
            provider="razorpay",
            provider_event_id=event_id,
            event_type=event_type,
            provider_created_at=datetime.now(timezone.utc),
            processed_at=datetime.now(timezone.utc),
            result=result,
            affected_org_id=org_id,
            payload_json=json.dumps(event, separators=(",", ":"), sort_keys=True),
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        duplicate_event = db.execute(
            select(BillingEvent).where(
                BillingEvent.provider == "razorpay",
                BillingEvent.provider_event_id == event_id,
            )
        ).scalar_one_or_none()
        if duplicate_event is not None:
            return WebhookResponse(
                received=True,
                duplicate=True,
                event_type=event_type,
                result=duplicate_event.result or "skipped",
                affected_org_id=duplicate_event.affected_org_id,
            )
        raise
    if invalidate_org_id:
        entitlements_resolver.invalidate(invalidate_org_id)
    return WebhookResponse(
        received=True,
        duplicate=False,
        event_type=event_type,
        result=result,
        affected_org_id=org_id,
    )


@router.get("/me", response_model=BillingMeResponse)
@limiter.limit("60/minute")
def get_billing_me(
    request: Request,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> BillingMeResponse:
    """Return the calling org's current plan and payment identifiers.

    Auto-creates a free-tier shell `subscriptions` row on first call so
    the dashboard never sees a 404 here. The plan_template field is the
    effective resolved entitlement view used by dashboard plan gates.
    """
    org_id = _resolve_org_id(tenant_id)
    sub = _get_or_create_org_subscription(db, org_id=org_id)
    template = entitlements_resolver.resolve_all(db, org_id)

    return BillingMeResponse(
        org_id=org_id,
        plan_code=sub.plan_code,
        status=sub.status,
        seats=sub.seats,
        payment_provider=sub.payment_provider,
        payment_customer_ref=sub.payment_customer_ref,
        payment_subscription_ref=sub.payment_subscription_ref,
        payment_request_ref=sub.payment_request_ref,
        current_period_end=(
            sub.current_period_end.isoformat() if sub.current_period_end else None
        ),
        trial_end=sub.trial_end.isoformat() if sub.trial_end else None,
        sla_tier=sub.sla_tier,
        plan_template=template,
    )


@router.get("/usage", response_model=BillingUsageResponse)
@limiter.limit("60/minute")
def get_billing_usage(
    request: Request,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> BillingUsageResponse:
    """Return hosted billing usage from current org-scoped meters."""
    org_id = _resolve_org_id(tenant_id)
    sub = _get_or_create_org_subscription(db, org_id=org_id)
    period_start, period_end, period_month = _month_bounds()
    quota_usage = _quota_get_usage(db, tenant_id)
    replay_quota = check_replay_monthly_quota(db, tenant_id)

    golden_trace_used = int(
        db.execute(
            select(func.count(GoldenTrace.id)).where(
                GoldenTrace.project_id == tenant_id,
                GoldenTrace.status == "active",
            )
        ).scalar_one()
        or 0
    )
    golden_set_used = int(
        db.execute(
            select(func.count(GoldenSet.id)).where(GoldenSet.project_id == tenant_id)
        ).scalar_one()
        or 0
    )
    golden_trace_limit = _resolved_int_entitlement(
        db, org_id, "max_golden_traces", default=0
    )
    golden_set_limit = _resolved_int_entitlement(
        db, org_id, "goldens.max_sets", default=0
    )
    metering = get_metering_health(db, tenant_id)

    return BillingUsageResponse(
        tenant_id=tenant_id,
        org_id=org_id,
        period_month=period_month,
        period_start=period_start,
        period_end=period_end,
        plan_code=quota_usage.plan_slug or sub.plan_code,
        plan_name=quota_usage.plan_name,
        subscription_status=sub.status,
        calls=_usage_meter(
            used=quota_usage.current_count,
            limit=quota_usage.plan_limit_calls,
            resets_at=period_end.date().isoformat(),
        ),
        replay=_usage_meter(
            used=replay_quota.used,
            limit=replay_quota.limit,
            resets_at=replay_quota.resets_at,
        ),
        goldens=_usage_meter(
            used=golden_trace_used,
            limit=golden_trace_limit,
            resets_at=None,
        ),
        golden_sets=_usage_meter(
            used=golden_set_used,
            limit=golden_set_limit,
            resets_at=None,
        ),
        metering_health=BillingMeteringHealthResponse(
            state=metering.state,
            failure_count=metering.failure_count,
            last_failure_at=metering.last_failure_at,
            last_failure_type=metering.last_failure_type,
            failure_policy=metering.failure_policy,
            detail=metering.detail,
        ),
    )
