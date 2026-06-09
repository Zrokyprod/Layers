"""Backend entitlement catalog derived from the shared pricing contract.

``api-contracts/pricing-plans.json`` is the source of truth for Zroky plan
capabilities and numeric limits. This module validates that contract and keeps
the legacy export surface used by billing, Stripe sync, and resolver code.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


UNLIMITED = -1
DEFAULT_PLAN_CODE = "free"
CANONICAL_PLAN_CODES: tuple[str, ...] = ("free", "pilot", "pro", "enterprise")
PLAN_ALIASES: dict[str, str] = {"plus": "pro"}
VALID_PLAN_CODES: frozenset[str] = frozenset(
    {*CANONICAL_PLAN_CODES, *PLAN_ALIASES.keys()}
)

ENTITLEMENT_KEYS: frozenset[str] = frozenset(
    {
        "watch.cloud_capture",
        "watch.basic_trace_view",
        "pilot.failure_inbox",
        "pilot.issue_grouping",
        "pilot.root_cause_diagnosis",
        "pilot.replay_stub",
        "pilot.replay_real_llm",
        "pilot.replay_mocked_tool",
        "pilot.goldens_basic",
        "pilot.alerts_basic",
        "pro.replay_live_sandbox",
        "pro.replay_shadow",
        "pro.ci_gate_nonblocking",
        "pro.ci_gate_blocking",
        "pro.outcome_attribution",
        "pro.team_workflow",
        "pro.advanced_goldens",
        "enterprise.private_replay_worker",
        "enterprise.sso",
        "enterprise.audit_logs",
        "enterprise.custom_retention",
        "enterprise.provider_key_vault",
        "enterprise.custom_detectors",
    }
)

LIMIT_KEYS: frozenset[str] = frozenset(
    {
        "max_projects",
        "max_members",
        "max_calls_per_month",
        "max_diagnosis_jobs_per_month",
        "max_real_replay_runs_per_month",
        "max_mocked_tool_replay_runs_per_month",
        "max_live_sandbox_replay_runs_per_month",
        "max_golden_traces",
        "retention_days",
    }
)


class InvalidPlanCodeError(ValueError):
    """Plan code not in the catalog vocabulary."""


@dataclass(frozen=True)
class PlanCatalogEntry:
    plan_code: str
    entitlements: Mapping[str, bool]
    limits: Mapping[str, int]
    compatibility: Mapping[str, Any]

    def template(self) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        merged.update(self.entitlements)
        merged.update(self.limits)
        merged.update(self.compatibility)
        return merged


PRICING_CONTRACT_PATH = (
    Path(__file__).resolve().parents[3] / "api-contracts" / "pricing-plans.json"
)


def load_pricing_contract(path: Path | None = None) -> dict[str, Any]:
    """Load the shared backend/landing pricing contract JSON."""
    source = path or PRICING_CONTRACT_PATH
    with source.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, dict) or not isinstance(raw.get("plans"), list):
        raise ValueError(f"Pricing contract at {source} must contain a plans list")
    return raw


def _as_bool_map(raw: Any, *, plan_code: str) -> dict[str, bool]:
    if not isinstance(raw, dict):
        raise ValueError(f"plan {plan_code!r} entitlements must be an object")
    values = {str(key): bool(value) for key, value in raw.items()}
    if set(values) != ENTITLEMENT_KEYS:
        raise ValueError(
            f"plan {plan_code!r} entitlement keys drifted; expected "
            f"{sorted(ENTITLEMENT_KEYS)}"
        )
    return values


def _as_int_map(raw: Any, *, plan_code: str) -> dict[str, int]:
    if not isinstance(raw, dict):
        raise ValueError(f"plan {plan_code!r} limits must be an object")
    values = {str(key): int(value) for key, value in raw.items()}
    if set(values) != LIMIT_KEYS:
        raise ValueError(
            f"plan {plan_code!r} limit keys drifted; expected {sorted(LIMIT_KEYS)}"
        )
    return values


def _as_compatibility_map(raw: Any, *, plan_code: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"plan {plan_code!r} compatibility must be an object")
    values = {str(key): value for key, value in raw.items()}
    required = {
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
        "seats.included",
    }
    if set(values) != required:
        raise ValueError(
            f"plan {plan_code!r} compatibility keys drifted; expected "
            f"{sorted(required)}"
        )
    return values


def _validate_public_pricing(
    *,
    plan_code: str,
    pricing: Mapping[str, Any],
    entitlements: Mapping[str, bool],
    limits: Mapping[str, int],
    compatibility: Mapping[str, Any],
) -> None:
    checks = {
        "calls_per_month": limits["max_calls_per_month"],
        "retention_days": limits["retention_days"],
        "replay_credits": compatibility["replay.monthly_runs"],
        "golden_traces": limits["max_golden_traces"],
        "golden_sets": compatibility["goldens.max_sets"],
        "non_blocking_ci": entitlements["pro.ci_gate_nonblocking"],
        "blocking_ci": entitlements["pro.ci_gate_blocking"],
        "provider_key_vault": entitlements["enterprise.provider_key_vault"],
    }
    for key, expected in checks.items():
        if pricing.get(key) != expected:
            raise ValueError(
                f"plan {plan_code!r} public pricing {key!r}={pricing.get(key)!r} "
                f"does not match enforcement value {expected!r}"
            )


def _build_plan_catalog_from_contract() -> dict[str, PlanCatalogEntry]:
    contract = load_pricing_contract()
    aliases = contract.get("aliases")
    if aliases != PLAN_ALIASES:
        raise ValueError("pricing contract aliases do not match PLAN_ALIASES")
    order = tuple(contract.get("canonical_plan_order", ()))
    if order != CANONICAL_PLAN_CODES:
        raise ValueError(
            "pricing contract canonical_plan_order does not match "
            "CANONICAL_PLAN_CODES"
        )

    entries: dict[str, PlanCatalogEntry] = {}
    for raw_plan in contract["plans"]:
        if not isinstance(raw_plan, dict):
            raise ValueError("pricing contract plan entries must be objects")
        plan_code = str(raw_plan.get("code") or "").strip().lower()
        if plan_code not in CANONICAL_PLAN_CODES:
            raise ValueError(f"pricing contract has unknown plan code: {plan_code!r}")
        enforcement = raw_plan.get("enforcement")
        if not isinstance(enforcement, dict):
            raise ValueError(f"plan {plan_code!r} missing enforcement object")
        entitlements = _as_bool_map(
            enforcement.get("entitlements"), plan_code=plan_code
        )
        limits = _as_int_map(enforcement.get("limits"), plan_code=plan_code)
        compatibility = _as_compatibility_map(
            enforcement.get("compatibility"), plan_code=plan_code
        )
        pricing = raw_plan.get("pricing")
        if not isinstance(pricing, dict):
            raise ValueError(f"plan {plan_code!r} missing public pricing object")
        _validate_public_pricing(
            plan_code=plan_code,
            pricing=pricing,
            entitlements=entitlements,
            limits=limits,
            compatibility=compatibility,
        )
        entries[plan_code] = PlanCatalogEntry(
            plan_code=plan_code,
            entitlements=entitlements,
            limits=limits,
            compatibility=compatibility,
        )

    if tuple(entries) != CANONICAL_PLAN_CODES:
        raise ValueError("pricing contract plans are not in canonical order")
    return entries


PLAN_CATALOG: dict[str, PlanCatalogEntry] = _build_plan_catalog_from_contract()


def canonical_plan_code(plan_code: str | None) -> str:
    """Return the canonical catalog code, resolving legacy aliases."""
    if plan_code is None:
        raise InvalidPlanCodeError("plan_code is required")
    norm = str(plan_code).strip().lower()
    canonical = PLAN_ALIASES.get(norm, norm)
    if canonical not in PLAN_CATALOG:
        raise InvalidPlanCodeError(
            f"plan_code {plan_code!r} must be one of: {sorted(VALID_PLAN_CODES)}"
        )
    return canonical


def get_catalog_entry(plan_code: str | None) -> PlanCatalogEntry:
    """Return the canonical catalog entry for a plan or legacy alias."""
    return PLAN_CATALOG[canonical_plan_code(plan_code)]


def _plan_code_from_args(
    plan_code: str | None, subscription_plan: Any | None
) -> str:
    if plan_code is not None:
        return plan_code
    if subscription_plan is not None:
        slug = getattr(subscription_plan, "slug", None)
        if slug is not None:
            return str(slug)
    raise InvalidPlanCodeError("plan_code is required")


def _parse_features_overlay(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    text = raw.strip() if isinstance(raw, str) else ""
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
    if isinstance(parsed, list):
        return {
            str(item).strip(): True
            for item in parsed
            if isinstance(item, str) and item.strip()
        }
    if isinstance(parsed, dict):
        return {str(key).strip(): value for key, value in parsed.items() if str(key).strip()}
    return {}


def _subscription_plan_overlays(subscription_plan: Any | None) -> dict[str, Any]:
    if subscription_plan is None:
        return {}
    overlays = _parse_features_overlay(getattr(subscription_plan, "features_json", None))

    max_projects = getattr(subscription_plan, "max_projects", None)
    if max_projects is not None:
        overlays["max_projects"] = int(max_projects)

    max_members = getattr(subscription_plan, "max_members_per_project", None)
    if max_members is not None:
        overlays["max_members"] = int(max_members)
        overlays["seats.included"] = int(max_members)

    max_calls = getattr(subscription_plan, "max_calls_per_month", None)
    if max_calls is not None:
        overlays["max_calls_per_month"] = int(max_calls)
        overlays["events.monthly_quota"] = int(max_calls)

    return overlays


def resolve_plan_template(
    plan_code: str | None,
    subscription_plan: Any | None = None,
) -> dict[str, Any]:
    """Resolve the full entitlement template for a plan.

    Legacy ``SubscriptionPlan`` rows can overlay capabilities via
    ``features_json`` and numeric caps via their existing columns. For
    legacy ``TenantSubscription`` callers, pass ``tenant_subscription.plan``.
    """
    selected_plan_code = _plan_code_from_args(plan_code, subscription_plan)
    template = get_catalog_entry(selected_plan_code).template()
    template.update(_subscription_plan_overlays(subscription_plan))
    return template


def resolve_plan_entitlements(
    plan_code: str | None,
    subscription_plan: Any | None = None,
) -> dict[str, bool]:
    """Resolve boolean capability flags for a plan."""
    template = resolve_plan_template(plan_code, subscription_plan)
    return {key: value for key, value in template.items() if isinstance(value, bool)}


def resolve_plan_limits(
    plan_code: str | None,
    subscription_plan: Any | None = None,
) -> dict[str, int]:
    """Resolve required numeric limits for a plan."""
    template = resolve_plan_template(plan_code, subscription_plan)
    return {key: int(template[key]) for key in LIMIT_KEYS}


def build_plan_entitlement_templates() -> dict[str, dict[str, Any]]:
    """Build billing-compatible templates for canonical plans and aliases."""
    templates = {code: entry.template() for code, entry in PLAN_CATALOG.items()}
    for alias, canonical in PLAN_ALIASES.items():
        templates[alias] = dict(templates[canonical])
    return templates


PLAN_ENTITLEMENTS: dict[str, dict[str, Any]] = build_plan_entitlement_templates()
PLAN_KEYS_BINDING: frozenset[str] = frozenset(
    key for values in PLAN_ENTITLEMENTS.values() for key in values
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


__all__ = [
    "UNLIMITED",
    "DEFAULT_PLAN_CODE",
    "CANONICAL_PLAN_CODES",
    "PLAN_ALIASES",
    "VALID_PLAN_CODES",
    "ENTITLEMENT_KEYS",
    "LIMIT_KEYS",
    "PRICING_CONTRACT_PATH",
    "PLAN_CATALOG",
    "PLAN_ENTITLEMENTS",
    "PLAN_KEYS_BINDING",
    "DIGEST_AUDIENCE_VALUES",
    "InvalidPlanCodeError",
    "PlanCatalogEntry",
    "load_pricing_contract",
    "canonical_plan_code",
    "get_catalog_entry",
    "resolve_plan_template",
    "resolve_plan_entitlements",
    "resolve_plan_limits",
    "build_plan_entitlement_templates",
]
