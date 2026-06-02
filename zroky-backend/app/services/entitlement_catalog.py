"""Centralized plan entitlement catalog.

This module is the canonical source for Zroky plan capabilities and
numeric limits. ``services.billing_plans`` keeps the legacy export surface
for billing, Stripe sync, and resolver code, but derives its templates from
this catalog.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
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


def _entitlements(
    *,
    watch: bool,
    pilot: bool,
    real_llm: bool,
    pro: bool,
    enterprise: bool,
) -> dict[str, bool]:
    return {
        "watch.cloud_capture": watch,
        "watch.basic_trace_view": watch,
        "pilot.failure_inbox": pilot,
        "pilot.issue_grouping": pilot,
        "pilot.root_cause_diagnosis": pilot,
        "pilot.replay_stub": pilot,
        "pilot.replay_real_llm": real_llm,
        "pilot.replay_mocked_tool": pilot,
        "pilot.goldens_basic": pilot,
        "pilot.alerts_basic": pilot,
        "pro.replay_live_sandbox": pro,
        "pro.replay_shadow": pro,
        "pro.ci_gate_nonblocking": pro,
        "pro.ci_gate_blocking": pro,
        "pro.outcome_attribution": pro,
        "pro.team_workflow": pro,
        "pro.advanced_goldens": pro,
        "enterprise.private_replay_worker": enterprise,
        "enterprise.sso": enterprise,
        "enterprise.audit_logs": enterprise,
        "enterprise.custom_retention": enterprise,
        "enterprise.provider_key_vault": enterprise,
        "enterprise.custom_detectors": enterprise,
    }


def _limits(
    *,
    max_projects: int,
    max_members: int,
    max_calls_per_month: int,
    max_diagnosis_jobs_per_month: int,
    max_real_replay_runs_per_month: int,
    max_mocked_tool_replay_runs_per_month: int,
    max_live_sandbox_replay_runs_per_month: int,
    max_golden_traces: int,
    retention_days: int,
) -> dict[str, int]:
    return {
        "max_projects": max_projects,
        "max_members": max_members,
        "max_calls_per_month": max_calls_per_month,
        "max_diagnosis_jobs_per_month": max_diagnosis_jobs_per_month,
        "max_real_replay_runs_per_month": max_real_replay_runs_per_month,
        "max_mocked_tool_replay_runs_per_month": max_mocked_tool_replay_runs_per_month,
        "max_live_sandbox_replay_runs_per_month": max_live_sandbox_replay_runs_per_month,
        "max_golden_traces": max_golden_traces,
        "retention_days": retention_days,
    }


def _compatibility(
    *,
    limits: Mapping[str, int],
    entitlements: Mapping[str, bool],
    goldens_max_sets: int,
    replay_monthly_runs: int,
    tier2_pr_enabled: bool,
    autofix_pr_enabled: bool,
    judge_ensemble_enabled: bool,
    digest_audience: str,
    compliance_export_enabled: bool,
) -> dict[str, Any]:
    return {
        "events.monthly_quota": limits["max_calls_per_month"],
        "retention.days": limits["retention_days"],
        "goldens.max_sets": goldens_max_sets,
        "replay.monthly_runs": replay_monthly_runs,
        "pilot.autopilot_enabled": entitlements["pilot.failure_inbox"],
        "pilot.tier2_pr_enabled": tier2_pr_enabled,
        "pilot.real_llm_replay_enabled": entitlements["pilot.replay_real_llm"],
        "pilot.autofix_pr_enabled": autofix_pr_enabled,
        "judge.ensemble_enabled": judge_ensemble_enabled,
        "digest.audience": digest_audience,
        "compliance.export_enabled": compliance_export_enabled,
        "selfhost.enabled": entitlements["enterprise.private_replay_worker"],
        "sso.enabled": entitlements["enterprise.sso"],
        "seats.included": limits["max_members"],
    }


def _entry(
    plan_code: str,
    *,
    entitlements: dict[str, bool],
    limits: dict[str, int],
    goldens_max_sets: int,
    replay_monthly_runs: int,
    tier2_pr_enabled: bool,
    autofix_pr_enabled: bool,
    judge_ensemble_enabled: bool,
    digest_audience: str,
    compliance_export_enabled: bool,
) -> PlanCatalogEntry:
    return PlanCatalogEntry(
        plan_code=plan_code,
        entitlements=entitlements,
        limits=limits,
        compatibility=_compatibility(
            limits=limits,
            entitlements=entitlements,
            goldens_max_sets=goldens_max_sets,
            replay_monthly_runs=replay_monthly_runs,
            tier2_pr_enabled=tier2_pr_enabled,
            autofix_pr_enabled=autofix_pr_enabled,
            judge_ensemble_enabled=judge_ensemble_enabled,
            digest_audience=digest_audience,
            compliance_export_enabled=compliance_export_enabled,
        ),
    )


_FREE_ENTITLEMENTS = _entitlements(
    watch=True, pilot=False, real_llm=False, pro=False, enterprise=False
)
_FREE_LIMITS = _limits(
    max_projects=1,
    max_members=2,
    max_calls_per_month=50_000,
    max_diagnosis_jobs_per_month=0,
    max_real_replay_runs_per_month=0,
    max_mocked_tool_replay_runs_per_month=0,
    max_live_sandbox_replay_runs_per_month=0,
    max_golden_traces=0,
    retention_days=7,
)

_PILOT_ENTITLEMENTS = _entitlements(
    watch=True, pilot=True, real_llm=False, pro=False, enterprise=False
)
_PILOT_LIMITS = _limits(
    max_projects=3,
    max_members=5,
    max_calls_per_month=500_000,
    max_diagnosis_jobs_per_month=100,
    max_real_replay_runs_per_month=0,
    max_mocked_tool_replay_runs_per_month=100,
    max_live_sandbox_replay_runs_per_month=0,
    max_golden_traces=100,
    retention_days=30,
)

_PRO_ENTITLEMENTS = _entitlements(
    watch=True, pilot=True, real_llm=True, pro=True, enterprise=False
)
_PRO_LIMITS = _limits(
    max_projects=10,
    max_members=10,
    max_calls_per_month=3_000_000,
    max_diagnosis_jobs_per_month=1_000,
    max_real_replay_runs_per_month=100,
    max_mocked_tool_replay_runs_per_month=1_000,
    max_live_sandbox_replay_runs_per_month=100,
    max_golden_traces=1_000,
    retention_days=90,
)

_ENTERPRISE_ENTITLEMENTS = _entitlements(
    watch=True, pilot=True, real_llm=True, pro=True, enterprise=True
)
_ENTERPRISE_LIMITS = _limits(
    max_projects=UNLIMITED,
    max_members=UNLIMITED,
    max_calls_per_month=UNLIMITED,
    max_diagnosis_jobs_per_month=UNLIMITED,
    max_real_replay_runs_per_month=UNLIMITED,
    max_mocked_tool_replay_runs_per_month=UNLIMITED,
    max_live_sandbox_replay_runs_per_month=UNLIMITED,
    max_golden_traces=UNLIMITED,
    retention_days=UNLIMITED,
)


PLAN_CATALOG: dict[str, PlanCatalogEntry] = {
    "free": _entry(
        "free",
        entitlements=_FREE_ENTITLEMENTS,
        limits=_FREE_LIMITS,
        goldens_max_sets=0,
        replay_monthly_runs=0,
        tier2_pr_enabled=False,
        autofix_pr_enabled=False,
        judge_ensemble_enabled=False,
        digest_audience="engineer",
        compliance_export_enabled=False,
    ),
    "pilot": _entry(
        "pilot",
        entitlements=_PILOT_ENTITLEMENTS,
        limits=_PILOT_LIMITS,
        goldens_max_sets=5,
        replay_monthly_runs=100,
        tier2_pr_enabled=False,
        autofix_pr_enabled=False,
        judge_ensemble_enabled=False,
        digest_audience="manager",
        compliance_export_enabled=False,
    ),
    "pro": _entry(
        "pro",
        entitlements=_PRO_ENTITLEMENTS,
        limits=_PRO_LIMITS,
        goldens_max_sets=50,
        replay_monthly_runs=1_000,
        tier2_pr_enabled=True,
        autofix_pr_enabled=False,
        judge_ensemble_enabled=True,
        digest_audience="executive",
        compliance_export_enabled=True,
    ),
    "enterprise": _entry(
        "enterprise",
        entitlements=_ENTERPRISE_ENTITLEMENTS,
        limits=_ENTERPRISE_LIMITS,
        goldens_max_sets=UNLIMITED,
        replay_monthly_runs=UNLIMITED,
        tier2_pr_enabled=True,
        autofix_pr_enabled=True,
        judge_ensemble_enabled=True,
        digest_audience="executive",
        compliance_export_enabled=True,
    ),
}


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
    "PLAN_CATALOG",
    "PLAN_ENTITLEMENTS",
    "PLAN_KEYS_BINDING",
    "DIGEST_AUDIENCE_VALUES",
    "InvalidPlanCodeError",
    "PlanCatalogEntry",
    "canonical_plan_code",
    "get_catalog_entry",
    "resolve_plan_template",
    "resolve_plan_entitlements",
    "resolve_plan_limits",
    "build_plan_entitlement_templates",
]
