"""Plan-code vocabulary and billing-compatible entitlement templates.

The canonical plan catalog lives in ``services.entitlement_catalog``. This
module preserves the existing billing import surface used by entitlement
seeding, resolver fallbacks, and route schemas.
"""
from __future__ import annotations

from typing import Any

from app.services.entitlement_catalog import (
    DEFAULT_PLAN_CODE,
    DIGEST_AUDIENCE_VALUES,
    PLAN_ENTITLEMENTS,
    PLAN_KEYS_BINDING,
    VALID_PLAN_CODES,
    InvalidPlanCodeError,
)

SELF_SERVE_PLAN_CODES: tuple[str, ...] = ("pilot", "pro", "plus")
ENTERPRISE_PLAN_CODE: str = "enterprise"


class PlanNotSelfServeError(ValueError):
    """Plan is valid but cannot be purchased through self-serve checkout."""


def normalize_plan_code(value: str | None) -> str:
    """Lower/strip a plan code and reject unknown values."""
    if value is None:
        raise InvalidPlanCodeError("plan_code is required")
    norm = str(value).strip().lower()
    if norm not in VALID_PLAN_CODES:
        raise InvalidPlanCodeError(
            f"plan_code {value!r} must be one of: {sorted(VALID_PLAN_CODES)}"
        )
    return norm


def assert_self_serve_plan(plan_code: str) -> str:
    """Validate and require a self-serve paid plan."""
    norm = normalize_plan_code(plan_code)
    if norm not in SELF_SERVE_PLAN_CODES:
        raise PlanNotSelfServeError(
            f"plan_code {norm!r} is not self-serve checkoutable; "
            f"valid self-serve codes: {sorted(SELF_SERVE_PLAN_CODES)}"
        )
    return norm


def get_plan_entitlements(plan_code: str) -> dict[str, Any]:
    """Return a defensive copy of the entitlement template for a plan."""
    norm = normalize_plan_code(plan_code)
    return dict(PLAN_ENTITLEMENTS[norm])


__all__ = [
    "DEFAULT_PLAN_CODE",
    "SELF_SERVE_PLAN_CODES",
    "ENTERPRISE_PLAN_CODE",
    "VALID_PLAN_CODES",
    "PLAN_ENTITLEMENTS",
    "PLAN_KEYS_BINDING",
    "DIGEST_AUDIENCE_VALUES",
    "InvalidPlanCodeError",
    "PlanNotSelfServeError",
    "normalize_plan_code",
    "assert_self_serve_plan",
    "get_plan_entitlements",
]
