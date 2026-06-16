from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

class CheckoutRequest(BaseModel):
    plan_code: str = Field(
        description=(
            "Self-serve plan code: 'starter' | 'pro'. "
            "Legacy 'pilot' maps to 'starter' and 'plus' maps to 'pro'. "
            "'enterprise' is sales-led; 'free' has no checkout."
        ),
        examples=["starter"],
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
            "Effective resolved entitlement template for the current org. "
            "Falls back to free when billing is incomplete, canceled, or "
            "unpaid, and includes active trial or override rows."
        ),
    )
