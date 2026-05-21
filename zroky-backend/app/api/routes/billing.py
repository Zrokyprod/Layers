"""
/v1/billing/* — billing routes.

Two routers coexist in this file. `api/router.py` mounts them under
separate feature flags so the legacy surface can be retired without
disturbing the §11.3 contract.

  Stripe-aligned (Module 5 / 12; plan §11.3) — always mounted:
    POST /v1/billing/checkout         Stripe Checkout session URL
    POST /v1/billing/portal           Stripe Customer Portal URL
    POST /v1/billing/webhook          Stripe webhook receiver
    GET  /v1/billing/me               current org plan + SLA tier + entitlements baseline

  Legacy (Module 12 default-off; gated by FEATURE_LEGACY_BILLING):
    GET  /v1/billing/plans
    GET  /v1/billing/subscription
    PUT  /v1/billing/subscription
    GET  /v1/billing/usage

The legacy surface reads from the deprecated `tenant_subscriptions`
table. New code paths read `subscriptions` (org-scoped, Stripe-aligned)
via `services.entitlements_resolver`. The legacy file will be deleted
in a follow-up cleanup once the dashboard migrates off `/plans` and
`/usage` (tracked separately from Module 12).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Header,
    Request,
    Response,
    status,
)
from pydantic import BaseModel, Field
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
    StripePriceNotConfiguredError,
    assert_self_serve_plan,
    resolve_stripe_price_id,
)
from app.services.billing_quota import get_usage as _quota_get_usage
from app.services.stripe_gateway import (
    StripeError,
    StripeGateway,
    WebhookSignatureError,
    get_stripe_gateway,
    verify_webhook_signature,
)
from app.services.stripe_sync import dispatch_event

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
# Module 5 — Stripe-aligned billing surface (plan §11.3)
# ════════════════════════════════════════════════════════════════════════════


def _require_billing_enabled() -> None:
    s = get_settings()
    if not s.BILLING_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Billing is disabled (BILLING_ENABLED=false). "
                "Self-host instances skip Stripe by design."
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
    before any Stripe interaction has happened."""
    row = db.execute(
        select(Subscription).where(Subscription.org_id == org_id)
    ).scalar_one_or_none()
    if row is not None:
        return row

    row = Subscription(
        org_id=org_id,
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


class CheckoutRequest(BaseModel):
    plan_code: str = Field(
        description=(
            "Self-serve plan code: 'starter' | 'pro' | 'team'. "
            "'enterprise' is sales-led; 'free' has no checkout."
        ),
        examples=["pro"],
    )
    customer_email: str | None = Field(
        default=None,
        max_length=320,
        description=(
            "Optional email for Stripe Customer creation when the org has "
            "no existing customer_id. Ignored if a customer already exists."
        ),
    )


class CheckoutResponse(BaseModel):
    session_id: str
    checkout_url: str
    plan_code: str
    org_id: str


class PortalResponse(BaseModel):
    session_id: str
    portal_url: str
    org_id: str


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
    stripe_customer_id: str | None = None
    stripe_sub_id: str | None = None
    current_period_end: str | None = None
    trial_end: str | None = None
    # Module 12 — Reliability SLA tier (plan §11.4). 'none' for
    # Free/Starter/Pro; 'team'/'enterprise' for tiers carrying the
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
            "Canonical entitlement template for the current plan_code. "
            "Module 6's resolver may override individual values; this is "
            "the baseline."
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
    body: CheckoutRequest,
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
    gateway: StripeGateway = Depends(get_stripe_gateway),
) -> CheckoutResponse:
    """Start a Stripe Checkout session for a self-serve plan.

    Errors:
      422 — bad plan_code (out-of-vocab OR not self-serve, e.g. 'free' or 'enterprise')
      503 — BILLING_ENABLED=false OR Stripe Price ID missing for the plan
      502 — Stripe API error (live gateway only)
    """
    _require_billing_enabled()
    org_id = _resolve_org_id(tenant_id)

    try:
        plan_norm = assert_self_serve_plan(body.plan_code)
    except (InvalidPlanCodeError, PlanNotSelfServeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    try:
        price_id = resolve_stripe_price_id(plan_norm)
    except StripePriceNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    sub = _get_or_create_org_subscription(db, org_id=org_id)
    settings = get_settings()
    try:
        result = gateway.create_checkout_session(
            org_id=org_id,
            plan_code=plan_norm,
            price_id=price_id,
            success_url=settings.BILLING_CHECKOUT_SUCCESS_URL,
            cancel_url=settings.BILLING_CHECKOUT_CANCEL_URL,
            customer_id=sub.stripe_customer_id,
            customer_email=body.customer_email,
        )
    except StripeError as exc:
        logger.exception("billing.checkout_failed org=%s plan=%s", org_id, plan_norm)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Stripe checkout failed: {exc}",
        ) from exc

    return CheckoutResponse(
        session_id=result.id,
        checkout_url=result.url,
        plan_code=plan_norm,
        org_id=org_id,
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
    gateway: StripeGateway = Depends(get_stripe_gateway),
) -> PortalResponse:
    """Return a Stripe Customer Portal session URL.

    Errors:
      404 — org has no Stripe customer yet (must hit /checkout first)
      503 — BILLING_ENABLED=false
      502 — Stripe API error
    """
    _require_billing_enabled()
    org_id = _resolve_org_id(tenant_id)

    sub = _get_or_create_org_subscription(db, org_id=org_id)
    if not sub.stripe_customer_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "Org has no Stripe customer. Run /v1/billing/checkout first "
                "to create a subscription."
            ),
        )

    settings = get_settings()
    try:
        result = gateway.create_portal_session(
            customer_id=sub.stripe_customer_id,
            return_url=settings.BILLING_PORTAL_RETURN_URL,
        )
    except StripeError as exc:
        logger.exception("billing.portal_failed org=%s", org_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Stripe portal failed: {exc}",
        ) from exc

    return PortalResponse(
        session_id=result.id, portal_url=result.url, org_id=org_id,
    )


@router.post("/webhook", response_model=WebhookResponse)
@limiter.limit("600/minute")  # Stripe can burst on backfill
async def receive_stripe_webhook(
    request: Request,
    response: Response,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    db: Session = Depends(get_db_session),
) -> WebhookResponse:
    """Stripe webhook receiver.

    Auth: HMAC-SHA256 via the `Stripe-Signature` header (NOT a tenant
    header). Stripe expects HTTP 200 on success; we return 400 only for
    signature failures (Stripe will retry on 5xx, which is what we want
    for transient handler errors).

    Behaviour:
      - Verifies signature against STRIPE_WEBHOOK_SECRET.
      - Idempotent claim via `stripe_events.stripe_event_id` UNIQUE.
      - Dispatches to `services.stripe_sync.dispatch_event`.
      - Records every event (handled or skipped) in `stripe_events`
        for audit.
    """
    settings = get_settings()
    if not settings.BILLING_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing is disabled.",
        )
    if not (settings.STRIPE_WEBHOOK_SECRET or "").strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="STRIPE_WEBHOOK_SECRET is not configured.",
        )

    raw_body = await request.body()
    try:
        event = verify_webhook_signature(
            payload=raw_body,
            header=stripe_signature,
            secret=settings.STRIPE_WEBHOOK_SECRET,
            tolerance=settings.STRIPE_WEBHOOK_TOLERANCE_SECONDS,
        )
    except WebhookSignatureError as exc:
        # 400 — Stripe will not retry. This is the correct response for
        # signature failures; replays would also fail.
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
    """Return the calling org's current plan + Stripe identifiers.

    Auto-creates a free-tier shell `subscriptions` row on first call so
    the dashboard never sees a 404 here. The plan_template field is the
    canonical baseline for the current plan; Module 6's resolver may
    override individual values via override/trial rows.
    """
    org_id = _resolve_org_id(tenant_id)
    sub = _get_or_create_org_subscription(db, org_id=org_id)
    template = dict(PLAN_ENTITLEMENTS.get(sub.plan_code, {}))

    return BillingMeResponse(
        org_id=org_id,
        plan_code=sub.plan_code,
        status=sub.status,
        seats=sub.seats,
        stripe_customer_id=sub.stripe_customer_id,
        stripe_sub_id=sub.stripe_sub_id,
        current_period_end=(
            sub.current_period_end.isoformat() if sub.current_period_end else None
        ),
        trial_end=sub.trial_end.isoformat() if sub.trial_end else None,
        sla_tier=sub.sla_tier,
        plan_template=template,
    )
