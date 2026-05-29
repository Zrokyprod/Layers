"""Plan-code vocabulary and billing-compatible entitlement templates.

The canonical plan catalog lives in ``services.entitlement_catalog``. This
module preserves the existing billing import surface used by Stripe sync,
entitlement seeding, resolver fallbacks, and route schemas.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.core.config import get_settings
from app.services.entitlement_catalog import (
    DEFAULT_PLAN_CODE,
    DIGEST_AUDIENCE_VALUES,
    PLAN_ENTITLEMENTS,
    PLAN_KEYS_BINDING,
    VALID_PLAN_CODES,
    InvalidPlanCodeError,
)

logger = logging.getLogger(__name__)


SELF_SERVE_PLAN_CODES: tuple[str, ...] = ("pilot", "pro", "plus")
ENTERPRISE_PLAN_CODE: str = "enterprise"


class PlanNotSelfServeError(ValueError):
    """Plan is valid but cannot be purchased through self-serve checkout."""


class StripePriceNotConfiguredError(RuntimeError):
    """Self-serve plan is missing from STRIPE_PRICE_IDS_JSON."""


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


def parse_price_map() -> dict[str, str]:
    """Load STRIPE_PRICE_IDS_JSON into a dict[plan_code, price_id]."""
    raw = (get_settings().STRIPE_PRICE_IDS_JSON or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        logger.warning("STRIPE_PRICE_IDS_JSON is not valid JSON; treating as empty")
        return {}
    if not isinstance(parsed, dict):
        logger.warning(
            "STRIPE_PRICE_IDS_JSON must be a JSON object {plan: price_id}"
        )
        return {}
    out: dict[str, str] = {}
    for key, value in parsed.items():
        if isinstance(key, str) and isinstance(value, str) and value.strip():
            out[key.strip().lower()] = value.strip()
    return out


def resolve_stripe_price_id(plan_code: str) -> str:
    """Return the Stripe Price ID for a self-serve plan."""
    norm = assert_self_serve_plan(plan_code)
    price_map = parse_price_map()
    price_id = price_map.get(norm)
    if not price_id:
        raise StripePriceNotConfiguredError(
            f"No Stripe Price ID configured for plan {norm!r}; "
            "add it to STRIPE_PRICE_IDS_JSON"
        )
    return price_id


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
    "StripePriceNotConfiguredError",
    "normalize_plan_code",
    "assert_self_serve_plan",
    "get_plan_entitlements",
    "parse_price_map",
    "resolve_stripe_price_id",
]
