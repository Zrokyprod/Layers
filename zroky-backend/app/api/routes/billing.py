"""
/v1/billing/* — billing routes.

Two routers coexist in this file. `api/router.py` mounts them under
separate feature flags so the legacy surface can be retired without
disturbing the §11.3 contract.

  Hosted billing (Module 5 / 12; plan section 11.3) always mounted:
    POST /v1/billing/checkout         Skydo payment request URL
    POST /v1/billing/portal           Skydo dashboard URL
    POST /v1/billing/webhook          signed billing webhook receiver
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
    Response,
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
    Call,
    Subscription,
    SubscriptionPlan,
    TenantSubscription,
)
from app.db.session import get_db_session
from app.schemas.billing import (
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
from app.services.entitlement_catalog import load_pricing_contract
from app.services import entitlements_resolver
from app.services.entitlements import seed_plan_entitlements
from app.services.skydo_gateway import (
    BillingWebhookSignatureError,
    SkydoError,
    SkydoGateway,
    get_skydo_gateway,
    verify_webhook_signature,
)
from app.services.skydo_sync import dispatch_event

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
# Module 5 - hosted Skydo billing surface
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
        payment_provider="skydo",
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


def _parse_stored_razorpay_request(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    order_id, _, plan_code = value.partition(":")
    return order_id.strip() or None, plan_code.strip().lower() or None


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
        description="Optional billing contact email for Skydo reconciliation.",
    )


class CheckoutResponse(BaseModel):
    session_id: str
    checkout_url: str
    plan_code: str
    org_id: str
    payment_provider: str = "skydo"
    payment_request_id: str
    manual_confirmation_required: bool = True
    instructions: str
    amount_usd: int | None = None
    currency: str = "USD"


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
    payment_provider: str = "skydo"


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
    payment_provider: str = "skydo"
    payment_customer_ref: str | None = None
    payment_subscription_ref: str | None = None
    payment_request_ref: str | None = None
    stripe_customer_id: str | None = None
    stripe_sub_id: str | None = None
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
    gateway: SkydoGateway = Depends(get_skydo_gateway),
) -> CheckoutResponse:
    """Start a Skydo payment request for a self-serve plan.

    Errors:
      422 — bad plan_code (out-of-vocab OR not self-serve, e.g. 'free' or 'enterprise')
      503 — BILLING_ENABLED=false
      502 — Skydo payment request configuration error
    """
    _require_billing_enabled()
    org_id = _resolve_org_id(tenant_id)

    try:
        plan_norm = assert_self_serve_plan(body.plan_code)
    except (InvalidPlanCodeError, PlanNotSelfServeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    sub = _get_or_create_org_subscription(db, org_id=org_id)
    amount_usd = _monthly_plan_amount_usd(plan_norm)
    try:
        result = gateway.create_payment_request(
            org_id=org_id,
            plan_code=plan_norm,
            amount_usd=amount_usd,
            customer_email=body.customer_email,
        )
    except SkydoError as exc:
        logger.exception("billing.checkout_failed org=%s plan=%s", org_id, plan_norm)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Skydo payment request failed: {exc}",
        ) from exc

    sub.payment_provider = "skydo"
    sub.payment_request_ref = result.id
    if body.customer_email:
        sub.payment_customer_ref = body.customer_email
    db.add(sub)
    db.commit()

    return CheckoutResponse(
        session_id=result.id,
        checkout_url=result.url,
        plan_code=plan_norm,
        org_id=org_id,
        payment_provider=result.provider,
        payment_request_id=result.id,
        manual_confirmation_required=result.manual_confirmation_required,
        instructions=result.instructions,
        amount_usd=amount_usd,
        currency="USD",
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
            plan_norm = assert_self_serve_plan(body.plan_code)
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
            plan_norm = assert_self_serve_plan(plan_norm)
        except (InvalidPlanCodeError, PlanNotSelfServeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Stored Razorpay plan is not valid for self-serve checkout.",
            ) from exc
        sub.plan_code = plan_norm
        sub.status = "active"
        sub.trial_end = None
        sub.current_period_end = datetime.now(timezone.utc) + timedelta(days=30)
        seed_plan_entitlements(db, org_id=org_id, plan_code=plan_norm, commit=False)

    sub.payment_provider = "razorpay"
    sub.payment_request_ref = body.razorpay_order_id
    sub.payment_subscription_ref = body.razorpay_payment_id
    db.add(sub)
    db.commit()
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
    gateway: SkydoGateway = Depends(get_skydo_gateway),
) -> PortalResponse:
    """Return a Skydo billing dashboard URL.

    Errors:
      503 — BILLING_ENABLED=false
      502 — Skydo portal configuration error
    """
    _require_billing_enabled()
    org_id = _resolve_org_id(tenant_id)

    try:
        result = gateway.create_portal_session(org_id=org_id)
    except SkydoError as exc:
        logger.exception("billing.portal_failed org=%s", org_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Skydo portal failed: {exc}",
        ) from exc

    return PortalResponse(
        session_id=result.id,
        portal_url=result.url,
        org_id=org_id,
        payment_provider=result.provider,
    )


@router.post("/webhook", response_model=WebhookResponse)
@limiter.limit("600/minute")
async def receive_billing_webhook(
    request: Request,
    response: Response,
    billing_signature: str | None = Header(
        default=None, alias="X-Zroky-Billing-Signature"
    ),
    skydo_signature: str | None = Header(default=None, alias="X-Skydo-Signature"),
    legacy_stripe_signature: str | None = Header(
        default=None, alias="Stripe-Signature"
    ),
    db: Session = Depends(get_db_session),
) -> WebhookResponse:
    """Signed Skydo/manual billing webhook receiver.

    Auth: HMAC-SHA256 via `X-Zroky-Billing-Signature` or
    `X-Skydo-Signature`. A legacy `Stripe-Signature` header is still accepted
    for old internal tooling during migration.

    Behaviour:
      - Verifies signature against SKYDO_WEBHOOK_SECRET.
      - Idempotent claim via `billing_events(provider, provider_event_id)`.
      - Dispatches to `services.skydo_sync.dispatch_event`.
      - Records every event (handled or skipped) in `billing_events`.
    """
    settings = get_settings()
    if not settings.BILLING_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing is disabled.",
        )
    webhook_secret = (
        settings.SKYDO_WEBHOOK_SECRET or settings.STRIPE_WEBHOOK_SECRET or ""
    ).strip()
    if not webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SKYDO_WEBHOOK_SECRET is not configured.",
        )

    raw_body = await request.body()
    signature = billing_signature or skydo_signature or legacy_stripe_signature
    try:
        event = verify_webhook_signature(
            payload=raw_body,
            header=signature,
            secret=webhook_secret,
            tolerance=settings.SKYDO_WEBHOOK_TOLERANCE_SECONDS,
        )
    except BillingWebhookSignatureError as exc:
        # Signature failures are deterministic; retries would fail too.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    try:
        result = dispatch_event(db, event)
    except ValueError as exc:
        # Malformed event envelope (missing id/type) — 400.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    return WebhookResponse(
        received=True,
        duplicate=result.duplicate,
        event_type=result.event_type,
        result=result.result,
        affected_org_id=result.affected_org_id,
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
        stripe_customer_id=sub.stripe_customer_id,
        stripe_sub_id=sub.stripe_sub_id,
        current_period_end=(
            sub.current_period_end.isoformat() if sub.current_period_end else None
        ),
        trial_end=sub.trial_end.isoformat() if sub.trial_end else None,
        sla_tier=sub.sla_tier,
        plan_template=template,
    )
