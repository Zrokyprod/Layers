"""
Plan-code vocabulary + entitlement templates (Module 5; plan §11.1 + §11.2).

Single source of truth for:
  - VALID_PLAN_CODES — what plan codes the system understands.
  - PLAN_ENTITLEMENTS — for each plan, the canonical entitlement
    key/value pairs that get written to `entitlements` (source='plan')
    when a subscription becomes active under that plan.
  - resolve_stripe_price_id(plan_code) — looks up the configured Stripe
    Price ID for a plan from `Settings.STRIPE_PRICE_IDS_JSON`.

The values in `PLAN_ENTITLEMENTS` mirror the §11.1 tier matrix:
  | Plan       | events_quota | retention_days | seats | pilot |  judge | replay/mo |
  |------------|--------------|----------------|-------|-------|--------|-----------|
  | free       | 100,000      | 7              | 3     | -     | -      | 0         |
  | starter    | 1,000,000    | 30             | 5     | -     | -      | 100       |
  | pro        | 10,000,000   | 90             | 10    | ✓     | ✓      | 5,000     |
  | team       | 50,000,000   | 180            | 25    | ✓     | ✓      | 50,000    |
  | enterprise | unlimited    | unlimited      | -1    | ✓     | ✓      | -1        |

Encoding conventions:
  - Numeric quotas: int. -1 sentinel means "unlimited".
  - Boolean capabilities: bool.
  - The resolver in Module 6 will load these as the `plan` source
    layer, with `trial` and `override` overlays on top.

Module 5 itself does not enforce entitlement gates on routes; that is
Module 6's job. We only ensure the rows EXIST so Module 6 can read them.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)


# ── plan vocabulary ─────────────────────────────────────────────────────────


# Free is the default landing tier (no Stripe subscription needed).
# 'enterprise' is sales-led — checkout DOES NOT cover it; founder console
# creates the subscription manually after contract.
DEFAULT_PLAN_CODE: str = "free"
SELF_SERVE_PLAN_CODES: tuple[str, ...] = ("starter", "pro", "team")
ENTERPRISE_PLAN_CODE: str = "enterprise"
VALID_PLAN_CODES: frozenset[str] = frozenset(
    {DEFAULT_PLAN_CODE, *SELF_SERVE_PLAN_CODES, ENTERPRISE_PLAN_CODE}
)


# ── entitlement template (plan §11.2 + §11.1 tier matrix) ───────────────────


_UNLIMITED = -1  # sentinel; resolver in Module 6 treats <0 as "no cap"


PLAN_ENTITLEMENTS: dict[str, dict[str, Any]] = {
    # Key set is locked by plan §11.2 (10 keys) PLUS `seats.included` as
    # an extension — plan §11.1 binds per-tier seat caps but §11.2's
    # example list omits the key. Resolver-driven enforcement on the
    # invite path needs it, so it lives here. Module 6's resolver
    # asserts every plan declares the SAME key set so the dict shape is
    # stable across tiers.
    "free": {
        "events.monthly_quota": 100_000,
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
        "seats.included": 3,
    },
    "starter": {
        "events.monthly_quota": 1_000_000,
        "retention.days": 30,
        "goldens.max_sets": 5,
        "replay.monthly_runs": 100,
        "pilot.autopilot_enabled": False,
        "pilot.tier2_pr_enabled": False,
        "pilot.real_llm_replay_enabled": False,
        "pilot.autofix_pr_enabled": False,
        "judge.ensemble_enabled": False,
        "digest.audience": "engineer",
        "compliance.export_enabled": False,
        "selfhost.enabled": False,
        "sso.enabled": False,
        "seats.included": 5,
    },
    "pro": {
        "events.monthly_quota": 10_000_000,
        "retention.days": 90,
        "goldens.max_sets": 50,
        "replay.monthly_runs": 5_000,
        "pilot.autopilot_enabled": True,
        # Pro has tier-2 capability; pilot_policies.tier2_enabled
        # gates whether it's actually active (off by default per §6.3).
        "pilot.tier2_pr_enabled": True,
        # Pro tier MUST have real-LLM replay or the Pre-deploy CI Gate
        # silently passes every run (default_resolver echoes baseline).
        # Customer outcome at $299/mo is "did this PR actually break
        # production?" — that requires real re-execution. Spend is
        # capped per-run by ReplayBudgetTracker (REPLAY_REAL_LLM_BUDGET_USD)
        # AND by replay.monthly_runs=5000.
        "pilot.real_llm_replay_enabled": True,
        # Auto-fix PR generation is Enterprise-only.
        "pilot.autofix_pr_enabled": False,
        # Pro uses the single-judge (claude-haiku-4) per locked decision #4.
        "judge.ensemble_enabled": False,
        "digest.audience": "manager",
        "compliance.export_enabled": False,
        "selfhost.enabled": False,
        "sso.enabled": False,
        "seats.included": 10,
    },
    "team": {
        "events.monthly_quota": 50_000_000,
        "retention.days": 180,
        "goldens.max_sets": 500,
        "replay.monthly_runs": 50_000,
        "pilot.autopilot_enabled": True,
        "pilot.tier2_pr_enabled": True,
        # Team+ unlock real-LLM replay (Option B) with budget caps.
        "pilot.real_llm_replay_enabled": True,
        # Auto-fix PR generation is Enterprise-only.
        "pilot.autofix_pr_enabled": False,
        # Team+ get the ensemble (Haiku-4 + GPT-4.5-mini median vote)
        # per locked decision #4 — 'higher-stakes plans buy more judges'.
        "judge.ensemble_enabled": True,
        "digest.audience": "executive",
        "compliance.export_enabled": True,
        "selfhost.enabled": False,
        "sso.enabled": True,
        "seats.included": 25,
    },
    "enterprise": {
        "events.monthly_quota": _UNLIMITED,
        "retention.days": _UNLIMITED,
        "goldens.max_sets": _UNLIMITED,
        "replay.monthly_runs": _UNLIMITED,
        "pilot.autopilot_enabled": True,
        "pilot.tier2_pr_enabled": True,
        "pilot.real_llm_replay_enabled": True,
        # Most advanced feature: LLM-powered auto-fix PR generation from replay
        "pilot.autofix_pr_enabled": True,
        "judge.ensemble_enabled": True,
        "digest.audience": "executive",
        "compliance.export_enabled": True,
        "selfhost.enabled": True,
        "sso.enabled": True,
        "seats.included": _UNLIMITED,
    },
}


# Plan §11.2 binding key list — the resolver type-checks against this.
# `seats.included` is omitted: plan §11.2 example list doesn't include it.
# `judge.ensemble_enabled` is a Module 7 additive extension (plan §17.2
# decision #4); kept in the binding so the gate dependency can validate
# it at import time.
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


# `digest.audience` is an enum, not a numeric/bool — used by the resolver
# when validating override writes from the Founder Console.
DIGEST_AUDIENCE_VALUES: frozenset[str] = frozenset(
    {"engineer", "manager", "executive"}
)


# Sanity assertion: every plan declares the same key set so the
# Module 6 resolver can rely on a stable schema.
_REFERENCE_KEYS = frozenset(PLAN_ENTITLEMENTS["free"].keys())
for _plan, _values in PLAN_ENTITLEMENTS.items():
    assert frozenset(_values.keys()) == _REFERENCE_KEYS, (
        f"plan {_plan!r} has divergent entitlement keys; expected "
        f"{sorted(_REFERENCE_KEYS)}"
    )


# ── exceptions ──────────────────────────────────────────────────────────────


class InvalidPlanCodeError(ValueError):
    """Plan code not in VALID_PLAN_CODES — route maps to 422."""


class PlanNotSelfServeError(ValueError):
    """Plan code is valid but not self-serve checkoutable.
    `enterprise` falls here (sales-led); `free` falls here (no checkout
    needed). Route maps to 422."""


class StripePriceNotConfiguredError(RuntimeError):
    """Plan code is self-serve but `STRIPE_PRICE_IDS_JSON` is missing
    its entry. Route maps to 503 — this is a config bug, not a user error."""


# ── helpers ─────────────────────────────────────────────────────────────────


def normalize_plan_code(value: str | None) -> str:
    """Lower/strip; raise InvalidPlanCodeError on out-of-vocab."""
    if value is None:
        raise InvalidPlanCodeError("plan_code is required")
    norm = str(value).strip().lower()
    if norm not in VALID_PLAN_CODES:
        raise InvalidPlanCodeError(
            f"plan_code {value!r} must be one of: {sorted(VALID_PLAN_CODES)}"
        )
    return norm


def assert_self_serve_plan(plan_code: str) -> str:
    """Validate AND require self-serve. Used by /v1/billing/checkout
    so the route doesn't try to start a Stripe session for free or
    enterprise plans (which have no Price ID)."""
    norm = normalize_plan_code(plan_code)
    if norm not in SELF_SERVE_PLAN_CODES:
        raise PlanNotSelfServeError(
            f"plan_code {norm!r} is not self-serve checkoutable; "
            f"valid self-serve codes: {sorted(SELF_SERVE_PLAN_CODES)}"
        )
    return norm


def get_plan_entitlements(plan_code: str) -> dict[str, Any]:
    """Return a fresh copy of the entitlement template for a plan."""
    norm = normalize_plan_code(plan_code)
    # Defensive copy so callers can't mutate the module-level constant.
    return dict(PLAN_ENTITLEMENTS[norm])


def parse_price_map() -> dict[str, str]:
    """Load `Settings.STRIPE_PRICE_IDS_JSON` into a dict[plan_code, price_id].

    Returns {} on any parse error or wrong shape — the route layer
    surfaces a clear 503 via `resolve_stripe_price_id`.
    """
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
    for k, v in parsed.items():
        if isinstance(k, str) and isinstance(v, str) and v.strip():
            out[k.strip().lower()] = v.strip()
    return out


def resolve_stripe_price_id(plan_code: str) -> str:
    """Return the Stripe Price ID for a self-serve plan. Raises
    StripePriceNotConfiguredError if missing — this is a config bug.

    Raises PlanNotSelfServeError if the plan is not self-serve."""
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
