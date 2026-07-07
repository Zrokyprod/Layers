from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.db.models import SubscriptionPlan, TenantSubscription
from app.services.entitlement_catalog import (
    CANONICAL_PLAN_CODES,
    ENTITLEMENT_KEYS,
    LIMIT_KEYS,
    PLAN_CATALOG,
    PLAN_ENTITLEMENTS,
    PLAN_KEYS_BINDING,
    InvalidPlanCodeError,
    canonical_plan_code,
    get_catalog_entry,
    load_pricing_contract,
    resolve_plan_entitlements,
    resolve_plan_limits,
    resolve_plan_template,
)


EXPECTED_LIMITS = {
    "free": {
        "max_projects": 1,
        "max_members": 2,
        "max_calls_per_month": 5_000,
        "max_diagnosis_jobs_per_month": 0,
        "max_real_replay_runs_per_month": 0,
        "max_mocked_tool_replay_runs_per_month": 0,
        "max_live_sandbox_replay_runs_per_month": 0,
        "max_golden_traces": 0,
        "retention_days": 7,
    },
    "starter": {
        "max_projects": 3,
        "max_members": -1,
        "max_calls_per_month": 50_000,
        "max_diagnosis_jobs_per_month": 100,
        "max_real_replay_runs_per_month": 0,
        "max_mocked_tool_replay_runs_per_month": 50,
        "max_live_sandbox_replay_runs_per_month": 0,
        "max_golden_traces": 500,
        "retention_days": 30,
    },
    "team": {
        "max_projects": 10,
        "max_members": -1,
        "max_calls_per_month": 250_000,
        "max_diagnosis_jobs_per_month": 1_000,
        "max_real_replay_runs_per_month": 500,
        "max_mocked_tool_replay_runs_per_month": 500,
        "max_live_sandbox_replay_runs_per_month": 500,
        "max_golden_traces": 2_500,
        "retention_days": 90,
    },
    "scale": {
        "max_projects": -1,
        "max_members": -1,
        "max_calls_per_month": 1_000_000,
        "max_diagnosis_jobs_per_month": -1,
        "max_real_replay_runs_per_month": 2_000,
        "max_mocked_tool_replay_runs_per_month": 2_000,
        "max_live_sandbox_replay_runs_per_month": 2_000,
        "max_golden_traces": 10_000,
        "retention_days": 180,
    },
    "enterprise": {
        "max_projects": -1,
        "max_members": -1,
        "max_calls_per_month": -1,
        "max_diagnosis_jobs_per_month": -1,
        "max_real_replay_runs_per_month": -1,
        "max_mocked_tool_replay_runs_per_month": -1,
        "max_live_sandbox_replay_runs_per_month": -1,
        "max_golden_traces": -1,
        "retention_days": -1,
    },
}


LEGACY_COMPATIBILITY_KEYS = {
    "events.monthly_quota",
    "actions.protected.monthly_quota",
    "actions.policy_checks.monthly_quota",
    "actions.runner_executions.monthly_quota",
    "actions.receipts.monthly_quota",
    "actions.verifications.monthly_quota",
    "actions.source_mutations.monthly_quota",
    "connectors.system_of_record.max",
    "agents.max",
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


@pytest.mark.parametrize("plan_code", CANONICAL_PLAN_CODES)
def test_required_keys_present_for_every_canonical_plan(plan_code: str) -> None:
    template = resolve_plan_template(plan_code)
    assert ENTITLEMENT_KEYS.issubset(template)
    assert LIMIT_KEYS.issubset(template)
    assert LEGACY_COMPATIBILITY_KEYS.issubset(template)
    assert set(template).issubset(PLAN_KEYS_BINDING)


@pytest.mark.parametrize("plan_code", CANONICAL_PLAN_CODES)
def test_catalog_entries_have_exact_required_key_sets(plan_code: str) -> None:
    entry = PLAN_CATALOG[plan_code]
    assert set(entry.entitlements) == ENTITLEMENT_KEYS
    assert set(entry.limits) == LIMIT_KEYS


@pytest.mark.parametrize("plan_code", CANONICAL_PLAN_CODES)
def test_default_limits(plan_code: str) -> None:
    assert resolve_plan_limits(plan_code) == EXPECTED_LIMITS[plan_code]


def test_agent_profile_limits_by_tier() -> None:
    assert resolve_plan_template("free")["agents.max"] == 1
    assert resolve_plan_template("starter")["agents.max"] == 3
    assert resolve_plan_template("team")["agents.max"] == 10
    assert resolve_plan_template("pro")["agents.max"] == 10
    assert resolve_plan_template("scale")["agents.max"] == -1
    assert resolve_plan_template("enterprise")["agents.max"] == -1


def test_pricing_contract_matches_backend_enforcement() -> None:
    contract = load_pricing_contract()
    plans = {plan["code"]: plan for plan in contract["plans"]}

    assert tuple(plans) == CANONICAL_PLAN_CODES

    for plan_code in CANONICAL_PLAN_CODES:
        plan = plans[plan_code]
        entry = get_catalog_entry(plan_code)
        pricing = plan["pricing"]
        enforcement = plan["enforcement"]

        assert enforcement["limits"] == entry.limits
        assert enforcement["entitlements"] == entry.entitlements
        assert enforcement["compatibility"] == entry.compatibility
        assert pricing["protected_actions_per_month"] == entry.compatibility[
            "actions.protected.monthly_quota"
        ]
        assert pricing["managed_agents"] == entry.compatibility["agents.max"]
        assert pricing["connectors"] == entry.compatibility[
            "connectors.system_of_record.max"
        ]
        assert pricing["approver_seats"] == entry.compatibility["seats.included"]
        assert pricing["evidence_retention_days"] == entry.compatibility[
            "retention.days"
        ]
        assert pricing["slack_approvals"] is True
        assert pricing["scoped_policy_rules_dry_run"] == entry.entitlements[
            "pro.ci_gate_nonblocking"
        ]
        assert pricing["audit_manifest_export"] == entry.compatibility[
            "compliance.export_enabled"
        ]

    assert plans["free"]["pricing"]["bypass_detection"] == "none"
    assert plans["starter"]["pricing"]["bypass_detection"] == "basic"
    assert plans["team"]["pricing"]["bypass_detection"] == "full"
    assert plans["scale"]["pricing"]["bypass_detection"] == "full"
    assert plans["enterprise"]["pricing"]["bypass_detection"] == "custom"
    assert plans["free"]["pricing"]["overage_policy"] == "hard_cap"
    assert plans["starter"]["pricing"]["overage_per_action_usd"] == 0.03
    assert plans["team"]["pricing"]["overage_per_action_usd"] == 0.025
    assert plans["scale"]["pricing"]["overage_per_action_usd"] == 0.015
    assert plans["enterprise"]["pricing"]["overage_policy"] == "custom"


def test_packaged_pricing_contract_matches_shared_source() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    repo_root = backend_root.parent
    shared = repo_root / "api-contracts" / "pricing-plans.json"
    packaged = backend_root / "api-contracts" / "pricing-plans.json"

    assert json.loads(packaged.read_text(encoding="utf-8")) == json.loads(
        shared.read_text(encoding="utf-8")
    )


def test_default_boolean_entitlements_by_tier() -> None:
    free = resolve_plan_entitlements("free")
    starter = resolve_plan_entitlements("starter")
    team = resolve_plan_entitlements("team")
    scale = resolve_plan_entitlements("scale")
    enterprise = resolve_plan_entitlements("enterprise")

    assert free["watch.cloud_capture"] is True
    assert free["watch.basic_trace_view"] is True
    assert free["pilot.failure_inbox"] is True
    assert free["pilot.replay_stub"] is False
    assert free["pro.ci_gate_blocking"] is False

    assert starter["pilot.failure_inbox"] is True
    assert starter["pilot.replay_mocked_tool"] is True
    assert starter["pilot.replay_real_llm"] is False
    assert starter["pro.ci_gate_nonblocking"] is True
    assert starter["pro.ci_gate_blocking"] is False

    assert team["pilot.replay_real_llm"] is True
    assert team["pro.ci_gate_nonblocking"] is True
    assert team["pro.ci_gate_blocking"] is True
    assert team["enterprise.sso"] is False

    assert scale["enterprise.audit_logs"] is True
    assert scale["enterprise.custom_retention"] is True
    assert scale["enterprise.sso"] is False

    assert enterprise["enterprise.sso"] is True
    assert all(enterprise[key] is True for key in ENTITLEMENT_KEYS)


def test_legacy_aliases_resolve_to_launch_plans() -> None:
    assert canonical_plan_code("pilot") == "starter"
    assert get_catalog_entry("pilot").plan_code == "starter"
    assert PLAN_ENTITLEMENTS["pilot"] == PLAN_ENTITLEMENTS["starter"]
    assert resolve_plan_template("pilot") == resolve_plan_template("starter")
    assert canonical_plan_code("pro") == "team"
    assert get_catalog_entry("pro").plan_code == "team"
    assert PLAN_ENTITLEMENTS["pro"] == PLAN_ENTITLEMENTS["team"]
    assert resolve_plan_template("pro") == resolve_plan_template("team")
    assert canonical_plan_code("plus") == "scale"
    assert get_catalog_entry("plus").plan_code == "scale"
    assert PLAN_ENTITLEMENTS["plus"] == PLAN_ENTITLEMENTS["scale"]
    assert resolve_plan_template("plus") == resolve_plan_template("scale")


def test_invalid_plan_code_raises() -> None:
    with pytest.raises(InvalidPlanCodeError):
        canonical_plan_code("ultra")


def test_features_json_list_sets_feature_keys_true() -> None:
    plan = SubscriptionPlan(
        slug="pilot",
        name="Pilot Override",
        monthly_cost_usd=0,
        annual_cost_usd=0,
        max_projects=3,
        max_members_per_project=5,
        max_calls_per_month=500_000,
        features_json=json.dumps(["pilot.replay_real_llm", "pro.replay_shadow"]),
    )

    entitlements = resolve_plan_entitlements("pilot", subscription_plan=plan)

    assert entitlements["pilot.replay_real_llm"] is True
    assert entitlements["pro.replay_shadow"] is True


def test_features_json_object_and_legacy_columns_overlay_template() -> None:
    plan = SubscriptionPlan(
        slug="pilot",
        name="Pilot Override",
        monthly_cost_usd=0,
        annual_cost_usd=0,
        max_projects=9,
        max_members_per_project=8,
        max_calls_per_month=123_456,
        features_json=json.dumps(
            {
                "pilot.replay_real_llm": True,
                "max_real_replay_runs_per_month": 25,
                "replay.monthly_runs": 250,
            }
        ),
    )

    template = resolve_plan_template("pilot", subscription_plan=plan)
    limits = resolve_plan_limits("pilot", subscription_plan=plan)

    assert template["pilot.replay_real_llm"] is True
    assert template["replay.monthly_runs"] == 250
    assert limits["max_projects"] == 9
    assert limits["max_members"] == 8
    assert limits["max_calls_per_month"] == 123_456
    assert limits["max_real_replay_runs_per_month"] == 25
    assert template["seats.included"] == 8
    assert template["events.monthly_quota"] == 123_456


def test_subscription_plan_slug_can_select_plan_code() -> None:
    plan = SubscriptionPlan(
        slug="plus",
        name="Legacy Plus",
        monthly_cost_usd=0,
        annual_cost_usd=0,
        max_projects=10,
        max_members_per_project=10,
        max_calls_per_month=3_000_000,
        features_json="[]",
    )

    assert resolve_plan_template(None, subscription_plan=plan) == resolve_plan_template(
        "plus",
        subscription_plan=plan,
    )


def test_tenant_subscription_plan_relationship_can_feed_resolver() -> None:
    plan = SubscriptionPlan(
        id="plan-pilot",
        slug="pilot",
        name="Pilot",
        monthly_cost_usd=0,
        annual_cost_usd=0,
        max_projects=4,
        max_members_per_project=6,
        max_calls_per_month=600_000,
        features_json=json.dumps({"pilot.replay_real_llm": True}),
    )
    subscription = TenantSubscription(
        tenant_id="tenant-1",
        plan_id=plan.id,
        plan=plan,
    )

    template = resolve_plan_template(None, subscription_plan=subscription.plan)

    assert template["pilot.failure_inbox"] is True
    assert template["pilot.replay_real_llm"] is True
    assert template["max_projects"] == 4
    assert template["max_members"] == 6
    assert template["max_calls_per_month"] == 600_000
