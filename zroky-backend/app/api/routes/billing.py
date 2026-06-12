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
import logging
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import uuid4

import razorpay
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
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import require_project_role
from app.api.dependencies.tenant import require_tenant_id, require_tenant_role
from app.core.config import get_settings
from app.core.limiter import limiter
from app.db.models import (
    BillingEvent,
    Call,
    GoldenSet,
    GoldenTrace,
    Subscription,
    SubscriptionPlan,
    TenantSubscription,
)
from app.db.session import get_db_session
from app.schemas.billing import (
    BillingMeteringHealthResponse,
    BillingUsageMeter,
    BillingUsageResponse,
    BillingUsageSummaryResponse,
    SubscriptionPlanListResponse,
    SubscriptionPlanResponse,
    TenantSubscriptionResponse,
    TenantSubscriptionUpdateRequest,
)
from app.services.billing_plans import (
    DEFAULT_PLAN_CODE,
    InvalidPlanCodeError,
    PLAN_ENTITLEMENTS,
    PlanNotSelfServeError,
    assert_self_serve_plan,
)
from app.services.billing_quota import get_usage as _quota_get_usage
from app.services.billing_metering import get_metering_health
from app.services.entitlement_catalog import load_pricing_contract
from app.services import entitlements_resolver
from app.services.entitlements import seed_plan_entitlements
from app.services.replay_runs import check_replay_monthly_quota

logger = logging.getLogger(__name__)

# §11.3 surface (always mounted by api/router.py).
router = APIRouter(prefix="/v1/billing")

# Legacy surface (gated by FEATURE_LEGACY_BILLING; default-off as of
# Module 12). Mounted under the same /v1/billing prefix so existing
# clients see no path change while the flag is on.
legacy_router = APIRouter(prefix="/v1/billing")


def _get_or_create_subscription(
    db: Session, tenant_id: str
) -> TenantSubscription:
    """Return existing tenant subscription or create a free-tier one."""
    existing = db.execute(
        select(TenantSubscription).where(TenantSubscription.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if existing:
        return existing

    free_plan = db.execute(
        select(SubscriptionPlan).where(SubscriptionPlan.slug == "free").where(SubscriptionPlan.is_active.is_(True))
    ).scalar_one_or_none()
    if free_plan is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Default free plan is not configured.",
        )

    now = datetime.now(timezone.utc)
    sub = TenantSubscription(
        tenant_id=tenant_id,
        plan_id=free_plan.id,
        billing_interval="monthly",
        status="active",
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
        seats=1,
    )
    db.add(sub)
    try:
        db.commit()
        db.refresh(sub)
    except IntegrityError:
        db.rollback()
        sub = db.execute(
            select(TenantSubscription).where(TenantSubscription.tenant_id == tenant_id)
        ).scalar_one()
    return sub


@legacy_router.get("/plans", response_model=SubscriptionPlanListResponse)
def list_plans(
    db: Session = Depends(get_db_session),
) -> SubscriptionPlanListResponse:
    rows = db.execute(
        select(SubscriptionPlan)
        .where(SubscriptionPlan.is_active.is_(True))
        .order_by(SubscriptionPlan.sort_order.asc())
    ).scalars().all()
    return SubscriptionPlanListResponse(
        plans=[SubscriptionPlanResponse.model_validate(r) for r in rows]
    )


@legacy_router.get("/subscription", response_model=TenantSubscriptionResponse)
def get_subscription(
    tenant_id: str = Depends(require_project_role("viewer")),
    db: Session = Depends(get_db_session),
) -> TenantSubscriptionResponse:
    sub = _get_or_create_subscription(db, tenant_id)
    return TenantSubscriptionResponse.model_validate(sub)


@legacy_router.put("/subscription", response_model=TenantSubscriptionResponse)
def update_subscription(
    body: TenantSubscriptionUpdateRequest,
    tenant_id: str = Depends(require_project_role("admin")),
    db: Session = Depends(get_db_session),
) -> TenantSubscriptionResponse:
    sub = _get_or_create_subscription(db, tenant_id)

    if body.plan_id is not None:
        plan = db.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.id == body.plan_id).where(SubscriptionPlan.is_active.is_(True))
        ).scalar_one_or_none()
        if plan is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or inactive plan selected.",
            )
        sub.plan_id = plan.id

    if body.billing_interval is not None:
        if body.billing_interval not in {"monthly", "annual"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="billing_interval must be 'monthly' or 'annual'.",
            )
        sub.billing_interval = body.billing_interval

    if body.status is not None:
        if body.status not in {"active", "canceled", "past_due", "trialing"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid status value.",
            )
        sub.status = body.status
        if body.status == "canceled" and sub.canceled_at is None:
            sub.canceled_at = datetime.now(timezone.utc)

    if body.seats is not None:
        if body.seats < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="seats must be at least 1.",
            )
        sub.seats = body.seats

    db.commit()
    db.refresh(sub)
    return TenantSubscriptionResponse.model_validate(sub)


@legacy_router.get("/usage", response_model=BillingUsageSummaryResponse)
def get_usage_summary(
    tenant_id: str = Depends(require_project_role("viewer")),
    db: Session = Depends(get_db_session),
) -> BillingUsageSummaryResponse:
    sub = _get_or_create_subscription(db, tenant_id)
    period_start = sub.current_period_start
    period_end = sub.current_period_end
    current_month = datetime.now(timezone.utc).strftime("%Y-%m")

    # Use event_counts ledger for current-month call count (O(1) index seek).
    # Fall back to calls table query for historical billing periods.
    usage = _quota_get_usage(db, tenant_id)
    if usage.month == current_month:
        total_calls = usage.current_count
    else:
        total_calls = int(
            db.execute(
                select(func.count(Call.id))
                .where(Call.project_id == tenant_id)
                .where(Call.created_at >= period_start)
                .where(Call.created_at < period_end)
            ).scalar() or 0
        )

    result = db.execute(
        select(
            func.coalesce(func.sum(Call.total_tokens), 0).label("total_tokens"),
            func.coalesce(func.sum(Call.cost_total), 0).label("total_cost"),
        )
        .where(Call.project_id == tenant_id)
        .where(Call.created_at >= period_start)
        .where(Call.created_at < period_end)
    ).one()

    total_tokens = int(result.total_tokens or 0)
    total_cost = float(result.total_cost or 0)

    plan_limit_calls = sub.plan.max_calls_per_month
    plan_limit_tokens = sub.plan.max_tokens_per_month

    overage_calls = None
    overage_tokens = None
    if plan_limit_calls is not None and total_calls > plan_limit_calls:
        overage_calls = total_calls - plan_limit_calls
    if plan_limit_tokens is not None and total_tokens > plan_limit_tokens:
        overage_tokens = total_tokens - plan_limit_tokens

    return BillingUsageSummaryResponse(
        tenant_id=tenant_id,
        period_start=period_start,
        period_end=period_end,
        total_calls=total_calls,
        total_tokens=total_tokens,
        total_cost_usd=total_cost,
        plan_limit_calls=plan_limit_calls,
        plan_limit_tokens=plan_limit_tokens,
        overage_calls=overage_calls,
        overage_tokens=overage_tokens,
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


def _monthly_plan_amount_usd(plan_code: str) -> int | None:
    """Return the public monthly USD price from the shared pricing contract."""
    try:
        contract = load_pricing_contract()
    except Exception:
        logger.exception("billing.pricing_contract_load_failed")
        return None
    canonical = "pro" if plan_code == "plus" else plan_code
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
    *, payment_id: str, order_id: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    client = _razorpay_client()
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
) -> tuple[dict[str, Any], dict[str, Any]]:
    payment, order = _fetch_razorpay_payment_and_order(
        payment_id=payment_id,
        order_id=order_id,
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


# ── schemas ──────────────────────────────────────────────────────────────────


class CheckoutRequest(BaseModel):
    plan_code: str = Field(
        description=(
            "Self-serve plan code: 'pilot' | 'pro' | 'plus'. "
            "'enterprise' is sales-led; 'free' has no checkout."
        ),
        examples=["pro"],
    )
    customer_email: str | None = Field(
        default=None,
        max_length=320,
        description="Optional billing contact email for Razorpay reconciliation.",
    )


class CheckoutResponse(BaseModel):
    session_id: str
    checkout_url: str
    plan_code: str
    org_id: str
    payment_provider: str = "razorpay"
    payment_request_id: str
    manual_confirmation_required: bool = False
    instructions: str
    amount_usd: int | None = None
    currency: str = "INR"


class RazorpayOrderRequest(BaseModel):
    plan_code: str | None = Field(
        default=None,
        description=(
            "Optional self-serve plan code. When present, the backend computes "
            "the INR paise amount from the pricing contract."
        ),
        examples=["pro"],
    )
    amount: int | None = Field(
        default=None,
        ge=100,
        description="Custom order amount in the smallest currency unit; paise for INR.",
    )
    currency: str = Field(
        default="INR",
        min_length=3,
        max_length=3,
        description="ISO currency code. Plan checkout currently uses INR.",
    )
    receipt: str | None = Field(
        default=None,
        max_length=40,
        description="Optional Razorpay receipt id for reconciliation.",
    )
    customer_email: str | None = Field(default=None, max_length=320)

    @model_validator(mode="after")
    def require_plan_or_amount(self) -> "RazorpayOrderRequest":
        if not self.plan_code and self.amount is None:
            raise ValueError("Either plan_code or amount is required.")
        return self


class RazorpayOrderResponse(BaseModel):
    order_id: str
    amount: int
    currency: str
    receipt: str | None = None
    plan_code: str | None = None
    org_id: str
    payment_provider: str = "razorpay"
    amount_usd: int | None = None


class RazorpayVerifyRequest(BaseModel):
    razorpay_payment_id: str = Field(min_length=1)
    razorpay_order_id: str = Field(min_length=1)
    razorpay_signature: str = Field(min_length=1)


class RazorpayVerifyResponse(BaseModel):
    success: bool
    order_id: str
    payment_id: str
    org_id: str
    plan_code: str | None = None


class PortalResponse(BaseModel):
    session_id: str
    portal_url: str
    org_id: str
    payment_provider: str = "razorpay"


class WebhookResponse(BaseModel):
    received: bool
    duplicate: bool
    event_type: str
    result: str  # 'applied' | 'skipped' | 'failed'
    affected_org_id: str | None = None


class BillingMeResponse(BaseModel):
    org_id: str
    plan_code: str
    status: str
    seats: int
    payment_provider: str = "razorpay"
    payment_customer_ref: str | None = None
    payment_subscription_ref: str | None = None
    payment_request_ref: str | None = None
    current_period_end: str | None = None
    trial_end: str | None = None
    # Module 12 — Reliability SLA tier (plan §11.4). 'none' for
    # Free/Pro/Plus; 'team'/'enterprise' for tiers carrying the
    # refund-on-miss SLA contract. Read-only here; mutations happen
    # exclusively in the Founder Console (Module 13).
    sla_tier: str = Field(
        default="none",
        description=(
            "Reliability SLA tier: 'none' | 'team' | 'enterprise'. "
            "Mutated only by the Founder Console — the lifecycle "
            "sweep does NOT reset this on auto-downgrade so refund "
            "eligibility audits remain reconstructable."
        ),
    )
    plan_template: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Effective resolved entitlement template for the current org. "
            "Falls back to free when billing is incomplete, canceled, or "
            "unpaid, and includes active trial or override rows."
        ),
    )


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
