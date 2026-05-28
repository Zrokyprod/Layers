"""Plan-code vocabulary and entitlement templates.

This module is the backend source of truth for launch pricing:

| Plan       | Price | Events/mo | Retention | Seats | Replay/mo | Real LLM |
|------------|-------|-----------|-----------|-------|-----------|----------|
| free       | $0    | 50,000    | 7 days    | 2     | 0         | no       |
| pro        | $29   | 500,000   | 30 days   | 5     | 100       | no       |
| plus       | $99   | 3,000,000 | 90 days   | 10    | 1,000     | yes      |
| enterprise | custom| unlimited | unlimited | -1    | -1        | yes      |

Encoding conventions:
- Numeric quotas are ints. -1 means unlimited.
- Boolean capabilities are bools.
- The resolver overlays override > trial > plan rows on top of this template.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)


DEFAULT_PLAN_CODE: str = "free"
SELF_SERVE_PLAN_CODES: tuple[str, ...] = ("pro", "plus")
ENTERPRISE_PLAN_CODE: str = "enterprise"
VALID_PLAN_CODES: frozenset[str] = frozenset(
    {DEFAULT_PLAN_CODE, *SELF_SERVE_PLAN_CODES, ENTERPRISE_PLAN_CODE}
)

_UNLIMITED = -1


PLAN_ENTITLEMENTS: dict[str, dict[str, Any]] = {
    "free": {
        "events.monthly_quota": 50_000,
        "retention.days": 7,
        "goldens.max_sets": 0,
        "replay.monthly_runs": 0,
        "pilot.autopilot_enabled": False,
        "pilot.tier2_pr_enabled": False,
        "pilot.real_llm_replay_enabled": False,
        "pilot.autofix_pr_enabled": False,
        "judge.ensemble_enabled": False,
        "digest.audience": "engineer",
        "compliance.export_enabled": False,
        "selfhost.enabled": False,
        "sso.enabled": False,
        "seats.included": 2,
    },
    "pro": {
        "events.monthly_quota": 500_000,
        "retention.days": 30,
        "goldens.max_sets": 5,
        "replay.monthly_runs": 100,
        "pilot.autopilot_enabled": True,
        "pilot.tier2_pr_enabled": False,
        "pilot.real_llm_replay_enabled": False,
        "pilot.autofix_pr_enabled": False,
        "judge.ensemble_enabled": False,
        "digest.audience": "manager",
        "compliance.export_enabled": False,
        "selfhost.enabled": False,
        "sso.enabled": False,
        "seats.included": 5,
    },
    "plus": {
        "events.monthly_quota": 3_000_000,
        "retention.days": 90,
        "goldens.max_sets": 50,
        "replay.monthly_runs": 1_000,
        "pilot.autopilot_enabled": True,
        "pilot.tier2_pr_enabled": True,
        "pilot.real_llm_replay_enabled": True,
        "pilot.autofix_pr_enabled": False,
        "judge.ensemble_enabled": True,
        "digest.audience": "executive",
        "compliance.export_enabled": True,
        "selfhost.enabled": False,
        "sso.enabled": False,
        "seats.included": 10,
    },
    "enterprise": {
        "events.monthly_quota": _UNLIMITED,
        "retention.days": _UNLIMITED,
        "goldens.max_sets": _UNLIMITED,
        "replay.monthly_runs": _UNLIMITED,
        "pilot.autopilot_enabled": True,
        "pilot.tier2_pr_enabled": True,
        "pilot.real_llm_replay_enabled": True,
        "pilot.autofix_pr_enabled": True,
        "judge.ensemble_enabled": True,
        "digest.audience": "executive",
        "compliance.export_enabled": True,
        "selfhost.enabled": True,
        "sso.enabled": True,
        "seats.included": _UNLIMITED,
    },
}


PLAN_KEYS_BINDING: frozenset[str] = frozenset(
    {
        "events.monthly_quota",
        "retention.days",
        "goldens.max_sets",
        "replay.monthly_runs",
        "pilot.autopilot_enabled",
        "pilot.tier2_pr_enabled",
        "pilot.real_llm_replay_enabled",
        "pilot.autofix_pr_enabled",
        "judge.ensemble_enabled",
        "digest.audience",
        "compliance.export_enabled",
        "selfhost.enabled",
        "sso.enabled",
    }
)

DIGEST_AUDIENCE_VALUES: frozenset[str] = frozenset(
    {"engineer", "manager", "executive"}
)


_REFERENCE_KEYS = frozenset(PLAN_ENTITLEMENTS[DEFAULT_PLAN_CODE].keys())
for _plan, _values in PLAN_ENTITLEMENTS.items():
    assert frozenset(_values.keys()) == _REFERENCE_KEYS, (
        f"plan {_plan!r} has divergent entitlement keys; expected "
        f"{sorted(_REFERENCE_KEYS)}"
    )


class InvalidPlanCodeError(ValueError):
    """Plan code not in VALID_PLAN_CODES."""


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
