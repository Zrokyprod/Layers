from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete, or_
from sqlalchemy.orm import Session

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.models import (  # noqa: E402
    Anomaly,
    ApiKey,
    Call,
    DiagnosisJob,
    Entitlement,
    GoldenSet,
    GoldenTrace,
    Notification,
    Project,
    ProjectAlert,
    ProjectDashboardConfig,
    ProjectInvitation,
    ProjectMembership,
    ProviderKeyVault,
    ReplayRun,
    ReplayRunTrace,
    Subscription,
    User,
)
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services.anomalies import compute_fingerprint  # noqa: E402
from app.services.entitlements import seed_plan_entitlements  # noqa: E402
from app.services.issue_projection import legacy_issue_payload  # noqa: E402
from app.services.security import hash_api_key, hash_password  # noqa: E402

FIXTURE_PATH = REPO_ROOT / "demos" / "mvp-money-path" / "refund_money_path_fixture.json"


def _compact_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _load_fixture(path: Path = FIXTURE_PATH) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        parsed = json.load(handle)
    if not isinstance(parsed, dict):
        raise ValueError(f"fixture must be a JSON object: {path}")
    return parsed


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _delete_existing_demo_rows(
    db: Session,
    *,
    project_id: str,
    user_id: str,
    user_subject: str,
) -> None:
    db.execute(
        delete(ReplayRunTrace).where(ReplayRunTrace.project_id == project_id)
    )
    db.execute(delete(ReplayRun).where(ReplayRun.project_id == project_id))
    db.execute(delete(GoldenTrace).where(GoldenTrace.project_id == project_id))
    db.execute(delete(GoldenSet).where(GoldenSet.project_id == project_id))
    db.execute(delete(ProjectAlert).where(ProjectAlert.tenant_id == project_id))
    db.execute(delete(Anomaly).where(Anomaly.project_id == project_id))
    db.execute(delete(DiagnosisJob).where(DiagnosisJob.tenant_id == project_id))
    db.execute(delete(Call).where(Call.project_id == project_id))
    db.execute(delete(ProviderKeyVault).where(ProviderKeyVault.project_id == project_id))
    db.execute(delete(ApiKey).where(ApiKey.project_id == project_id))
    db.execute(delete(ProjectInvitation).where(ProjectInvitation.project_id == project_id))
    db.execute(delete(ProjectDashboardConfig).where(ProjectDashboardConfig.tenant_id == project_id))
    db.execute(delete(Notification).where(Notification.project_id == project_id))
    db.execute(delete(Notification).where(Notification.user_id == user_id))
    db.execute(delete(Entitlement).where(Entitlement.org_id == project_id))
    db.execute(delete(Subscription).where(Subscription.org_id == project_id))
    db.execute(delete(ProjectMembership).where(ProjectMembership.project_id == project_id))
    db.execute(delete(Project).where(Project.id == project_id))
    db.execute(delete(User).where(or_(User.id == user_id, User.subject == user_subject)))
    db.flush()


def seed_money_path_demo(db: Session, *, fixture_path: Path = FIXTURE_PATH) -> dict[str, str]:
    fixture = _load_fixture(fixture_path)
    demo = fixture["demo"]
    ids = fixture["ids"]
    scenario = fixture["scenario"]
    bad = fixture["fake_model_responses"]["bad_version"]
    fixed = fixture["fake_model_responses"]["fixed_version"]
    broken_pr = fixture["fake_model_responses"]["broken_pr"]
    fake_tool = fixture["fake_tools"]["get_refund_status"]
    timing = fixture["timing"]
    costs = fixture["costs"]

    project_id = str(demo["project_id"])
    # Keep deterministic fixture IDs/content, but make the demo recent so
    # dashboard routes with 7/30 day windows can exercise the seeded data.
    base_time = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=20)
    user_id = str(ids["user"])
    expected_tool = str(scenario["expected_tool"])
    bad_output = str(bad["output"])
    fixed_output = str(fixed["output"])
    broken_output = str(broken_pr["output"])

    user_subject = f"email:{demo['user_email']}"
    _delete_existing_demo_rows(
        db,
        project_id=project_id,
        user_id=user_id,
        user_subject=user_subject,
    )

    user = User(
        id=user_id,
        subject=user_subject,
        email=str(demo["user_email"]),
        password_hash=hash_password(str(demo["user_password"])),
        display_name="Zroky Demo User",
        email_verified_at=base_time,
        is_active=True,
        created_at=base_time,
        updated_at=base_time,
    )
    project = Project(
        id=project_id,
        name=str(demo["project_name"]),
        owner_ref=user.subject,
        is_active=True,
        default_golden_set_id=str(ids["golden_set"]),
        created_at=base_time,
        updated_at=base_time,
    )
    membership = ProjectMembership(
        id=str(ids["membership"]),
        project_id=project_id,
        user_id=user_id,
        role="owner",
        is_active=True,
        created_at=base_time,
        updated_at=base_time,
    )
    subscription = Subscription(
        id=str(ids["subscription"]),
        org_id=project_id,
        stripe_customer_id=None,
        stripe_sub_id=None,
        plan_code="pro",
        status="active",
        seats=3,
        current_period_end=base_time + timedelta(days=30),
        trial_end=None,
        sla_tier="none",
        created_at=base_time,
        updated_at=base_time,
    )
    api_key = ApiKey(
        id=str(ids.get("api_key", "demo-api-key-refund-money-path")),
        project_id=project_id,
        name="Demo ingest key",
        key_prefix="zk_live_demo",
        key_hash=hash_api_key("zk_live_demo_refund_money_path"),
        scopes_json=_compact_json(["project:member"]),
        expires_at=base_time + timedelta(days=90),
        created_at=base_time,
        updated_at=base_time,
    )
    invitation = ProjectInvitation(
        id=str(ids.get("invitation", "demo-invite-refund-money-path")),
        project_id=project_id,
        email="teammate@zroky.local",
        role="member",
        invited_by_subject=user_subject,
        token_hash=hash_api_key("demo-refund-money-path-invite-token"),
        expires_at=base_time + timedelta(days=7),
        created_at=base_time,
        updated_at=base_time,
    )
    dashboard_config = ProjectDashboardConfig(
        tenant_id=project_id,
        monthly_budget_usd=250.0,
        budget_threshold_percentage=80.0,
        retention_days=90,
        pii_custom_patterns_json=_compact_json(["RF-\\d{4}"]),
        notifications_json=_compact_json(
            {
                "email_enabled": True,
                "slack_enabled": False,
                "teams_enabled": False,
                "browser_enabled": True,
                "terminal_enabled": True,
            }
        ),
        provider_verifications_json=_compact_json(
            {
                "fake-provider": {
                    "status": "verified",
                    "last_checked_at": base_time.isoformat(),
                    "last_error": None,
                }
            }
        ),
        pricing_validation_json=_compact_json({}),
        rollback_drill_json=_compact_json({}),
        evaluation_settings_json=_compact_json(
            {
                "judge_mode": "standard",
                "default_judge_model": "auto",
                "minimum_confidence": 0.75,
                "auto_calibration_enabled": True,
                "record_replay_calibration": True,
            }
        ),
        created_at=base_time,
        updated_at=base_time,
    )
    db.add_all([user, project, membership, subscription, api_key, invitation, dashboard_config])
    db.flush()
    seed_plan_entitlements(db, org_id=project_id, plan_code="pro", commit=False)

    call_payload = {
        "trace_id": scenario["trace_id"],
        "provider": str(bad["provider"]),
        "agent_name": scenario["agent_name"],
        "workflow_name": scenario["workflow_name"],
        "prompt_fingerprint": scenario["prompt_fingerprint"],
        "prompt_version": scenario["prompt_version"],
        "messages": [{"role": "user", "content": scenario["user_input"]}],
        "input": scenario["user_input"],
        "output": bad_output,
        "response": bad_output,
        "failure_reason": "The refund-status tool was required but no tool call was made.",
        "tool_calls": [],
        "tools_available": [expected_tool],
        "expected_tool": expected_tool,
        "retrieval_context": [
            {
                "source": "support-policy/refunds.md",
                "text": "Refund policy pages explain timelines but do not contain account-specific status.",
            }
        ],
        "customer_id": scenario["customer_id"],
        "order_id": scenario["order_id"],
    }
    tool_summary = {
        "tools_available": [expected_tool],
        "expected_tool": expected_tool,
        "tool_calls": [],
        "tool_not_called": True,
    }
    bad_call = Call(
        id=str(ids["bad_call"]),
        project_id=project_id,
        event_id="evt-demo-refund-missed-tool",
        created_at=base_time,
        agent_name=str(scenario["agent_name"]),
        user_id=str(scenario["customer_id"]),
        call_type="chat",
        provider=str(bad["provider"]),
        model=str(bad["model"]),
        status="failed",
        error_code=str(scenario["failure_code"]),
        latency_ms=float(timing["bad_call_latency_ms"]),
        input_tokens=118,
        output_tokens=39,
        reasoning_tokens=0,
        total_tokens=157,
        cost_total=float(costs["bad_call_usd"]),
        reasoning_cost_total=0.0,
        cache_savings_total=0.0,
        pricing_version="demo-fixed",
        pricing_source="fixture",
        cost_confidence="high",
        confidence_reason=None,
        output_fingerprint="demo-generic-refund-policy",
        is_production=True,
        tool_lifecycle_summary_json=_compact_json(tool_summary),
        retry_metadata_json=None,
        payload_json=_compact_json(call_payload),
        metadata_json=_compact_json(call_payload),
    )
    db.add(bad_call)

    diagnosis_result = {
        "failure_code": scenario["failure_code"],
        "root_cause": "The agent treated a status lookup as a policy question and skipped get_refund_status.",
        "failure_reason": "TOOL_NOT_CALLED: refund status questions require get_refund_status before answering.",
        "expected_tool": expected_tool,
        "observed_tools": [],
        "confidence": 0.99,
        "suggested_fix": "Update the refund support prompt to call get_refund_status before answering refund status questions.",
    }
    diagnosis = DiagnosisJob(
        id=str(ids["diagnosis"]),
        tenant_id=project_id,
        diagnosis_id=str(ids["diagnosis"]),
        call_id=str(ids["bad_call"]),
        status="completed",
        agent_name=str(scenario["agent_name"]),
        prompt_fingerprint=str(scenario["prompt_fingerprint"]),
        payload_json=_compact_json(call_payload),
        result_json=_compact_json(diagnosis_result),
        error_message=None,
        created_at=base_time + timedelta(seconds=5),
        updated_at=base_time + timedelta(seconds=7),
    )
    db.add(diagnosis)

    issue_evidence = {
        "summary": "Refund status request got a generic refund policy answer.",
        "root_cause": diagnosis_result["root_cause"],
        "failure_reason": diagnosis_result["failure_reason"],
        "failure_code": scenario["failure_code"],
        "prompt_fingerprint": scenario["prompt_fingerprint"],
        "prompt_version": scenario["prompt_version"],
        "workflow_name": scenario["workflow_name"],
        "agent_name": scenario["agent_name"],
        "call_id": ids["bad_call"],
        "diagnosis_id": ids["diagnosis"],
        "trace_id": scenario["trace_id"],
        "expected_tool": expected_tool,
        "observed_tools": [],
        "blast_radius_usd": 1260.0,
        "recommended_next_action": diagnosis_result["suggested_fix"],
        "legacy_issue": legacy_issue_payload(
            failure_code=str(scenario["failure_code"]),
            prompt_fingerprint=str(scenario["prompt_fingerprint"]),
            agent_name=str(scenario["agent_name"]),
            call_id=str(ids["bad_call"]),
            diagnosis_id=str(ids["diagnosis"]),
            call_cost_usd=1260.0,
            sample_evidence_json=_compact_json(diagnosis_result),
        ),
        "issue_triage": {
            "assigned_to": "support-platform",
            "deploy_pr_url": "https://github.com/acme/refund-agent/pull/42",
            "updated_at": base_time.isoformat(),
        },
    }
    source_context = {
        "kind": "issue",
        "id": str(ids["issue"]),
        "issue_id": str(ids["issue"]),
        "call_id": str(ids["bad_call"]),
        "title": "Refund status tool skipped",
        "reason": diagnosis_result["failure_reason"],
        "failure_code": str(scenario["failure_code"]),
        "severity": "critical",
        "affected_agent": str(scenario["agent_name"]),
        "affected_workflow": str(scenario["workflow_name"]),
        "occurrence_count": 17,
        "last_seen_at": (base_time + timedelta(minutes=8)).isoformat(),
        "origin": "issue",
        "confidence": 0.99,
        "discovery_signature": str(scenario["prompt_fingerprint"]),
    }
    detector = "TOOL_SELECTION_FAILURE"
    anomaly = Anomaly(
        id=str(ids["issue"]),
        project_id=project_id,
        fingerprint=compute_fingerprint(
            detector=detector,
            prompt_fingerprint=str(scenario["prompt_fingerprint"]),
            agent_name=str(scenario["agent_name"]),
        ),
        detector=detector,
        severity="critical",
        status="open",
        first_seen_at=base_time,
        last_seen_at=base_time + timedelta(minutes=8),
        occurrence_count=17,
        sample_call_ids_json=_compact_json([ids["bad_call"]]),
        evidence_json=_compact_json(issue_evidence),
        created_at=base_time,
        updated_at=base_time + timedelta(minutes=8),
    )
    db.add(anomaly)
    db.add(
        ProjectAlert(
            id=str(ids.get("alert", "demo-alert-refund-tool-not-called")),
            tenant_id=project_id,
            diagnosis_id=str(ids["diagnosis"]),
            category="TOOL_SELECTION_FAILURE",
            severity="critical",
            status="OPEN",
            source="demo_seed",
            title="Refund status tool skipped",
            evidence_json=_compact_json(issue_evidence),
            created_at=base_time,
            updated_at=base_time + timedelta(minutes=8),
        )
    )
    db.add(
        Notification(
            id=str(ids.get("notification", "demo-notif-refund-tool")),
            user_id=user_id,
            project_id=project_id,
            title="Critical refund flow issue detected",
            body="The refund support agent skipped get_refund_status.",
            category="issue",
            is_read=False,
            action_url=f"/issues/{ids['issue']}",
            created_at=base_time + timedelta(minutes=8),
        )
    )

    golden_set = GoldenSet(
        id=str(ids["golden_set"]),
        project_id=project_id,
        name="Refund status protected flow",
        description="Protects refund status lookups from generic policy-only answers.",
        judge_config_json=_compact_json(
            {
                "owner": "support-platform",
                "owner_email": "support-platform@example.com",
                "ci_usage": "blocking",
            }
        ),
        is_flaky=False,
        blocks_ci=True,
        created_at=base_time + timedelta(minutes=11),
        updated_at=base_time + timedelta(minutes=16),
    )
    regression_ci_set = GoldenSet(
        id=str(ids["regression_ci_set"]),
        project_id=project_id,
        name="Regression CI synthetic gate - Refund Demo",
        description="Synthetic parent set for the demo Regression CI run.",
        judge_config_json=_compact_json({"owner": "support-platform", "ci_usage": "regression-ci"}),
        is_flaky=False,
        blocks_ci=True,
        created_at=base_time + timedelta(minutes=18),
        updated_at=base_time + timedelta(minutes=18),
    )
    db.add_all([golden_set, regression_ci_set])

    criteria = {
        "required_tool_behavior": {
            "tool": expected_tool,
            "arguments": fake_tool["arguments"],
            "response": fake_tool["response"],
        },
        "must_call_tools": [expected_tool],
        "must_not_contain": ["Refunds are usually processed within 5-10 business days."],
        "expected_semantics": [
            "Tell the customer refund id RF-1001.",
            "Say the refund was issued on 2026-01-14.",
            "Say the expected arrival date is 2026-01-19.",
        ],
        "max_latency_ms": 1200,
    }
    golden_trace = GoldenTrace(
        id=str(ids["golden_trace"]),
        golden_set_id=str(ids["golden_set"]),
        project_id=project_id,
        call_id=str(ids["bad_call"]),
        status="active",
        expected_output_text=fixed_output,
        source_output_text=bad_output,
        source_evidence_json=_compact_json(
            {
                "source_call_id": ids["bad_call"],
                "source_trace_id": scenario["trace_id"],
                "failure_code": scenario["failure_code"],
                "source_output_text": bad_output,
                "observed_tool_calls": [],
                "expected_tool": expected_tool,
            }
        ),
        expected_tokens=46,
        expected_cost_usd=0.0034,
        expected_latency_ms=int(timing["verified_replay_latency_ms"]),
        criteria_json=_compact_json(criteria),
        weight=1.0,
        created_at=base_time + timedelta(minutes=12),
        updated_at=base_time + timedelta(minutes=16),
    )
    db.add(golden_trace)

    output_diff = {
        "original": bad_output,
        "candidate": fixed_output,
        "summary": "Candidate answer replaces generic policy with account-specific refund status.",
    }
    tool_behavior_diff = {
        "original_tool_calls": [],
        "candidate_tool_calls": fixed["tool_calls"],
        "required_tool_called": True,
        "tool_result": fake_tool["response"],
    }
    verified_summary = {
        "trace_count_at_dispatch": 1,
        "trace_count_executed": 1,
        "pass_count": 1,
        "fail_count": 0,
        "error_count": 0,
        "reproduced_original_failure": True,
        "fix_passed": True,
        "verified_fix": True,
        "verification_status": "verified_fix",
        "requested_replay_mode": "mocked-tool",
        "replay_mode": "mocked-tool",
        "source_kind": "issue",
        "source_id": str(ids["issue"]),
        "source_issue_id": str(ids["issue"]),
        "source_call_id": str(ids["bad_call"]),
        "source_issue_failure_code": str(scenario["failure_code"]),
        "source_issue_severity": "critical",
        "source_context": source_context,
        "candidate_prompt_override": fixed["candidate_prompt"],
        "candidate_model_override": fixed["model"],
        "output_diff": output_diff,
        "tool_behavior_diff": tool_behavior_diff,
        "cost_delta_usd": round(float(costs["verified_replay_usd"]) - float(costs["bad_call_usd"]), 4),
        "latency_delta_ms": int(timing["verified_replay_latency_ms"]) - int(timing["bad_call_latency_ms"]),
        "replay_cost_usd": float(costs["verified_replay_usd"]),
    }
    verified_run = ReplayRun(
        id=str(ids["verified_replay"]),
        project_id=project_id,
        golden_set_id=str(ids["golden_set"]),
        trigger="manual",
        git_sha="demo-fixed-refund-tool",
        status="pass",
        started_at=base_time + timedelta(minutes=13),
        completed_at=base_time + timedelta(minutes=14),
        summary_json=_compact_json(verified_summary),
        created_at=base_time + timedelta(minutes=13),
    )
    verified_trace = ReplayRunTrace(
        id=str(ids["verified_replay_trace"]),
        replay_run_id=str(ids["verified_replay"]),
        golden_trace_id=str(ids["golden_trace"]),
        project_id=project_id,
        call_id_replayed=str(ids["bad_call"]),
        judge_scores_json=_compact_json(
            {
                "confidence": 0.97,
                "reason": "The candidate called get_refund_status and answered with the tool result.",
                "output_diff": output_diff,
                "tool_behavior_diff": tool_behavior_diff,
                "cost_delta_usd": verified_summary["cost_delta_usd"],
                "latency_delta_ms": verified_summary["latency_delta_ms"],
            }
        ),
        status="pass",
        diff_metric=0.04,
        output_text=fixed_output,
        completed_at=base_time + timedelta(minutes=14),
        created_at=base_time + timedelta(minutes=13),
    )
    db.add_all([verified_run, verified_trace])

    ci_report = {
        "schema_version": "v1",
        "run_id": ids["regression_ci_run"],
        "project_id": project_id,
        "git_sha": "demo-break-refund-tool",
        "pull_request_url": "https://github.com/acme/refund-agent/pull/43",
        "blast_radius": {
            "category": "system_prompt",
            "source": "declared",
            "files": ["agents/refund_support/prompt.md"],
            "target": "refund-support-agent",
            "confidence": 1.0,
        },
        "sample_spec": {
            "target_total": 1,
            "stratification": {
                "pass_history": 0.0,
                "fail_history": 1.0,
                "rare_cluster": 0.0,
                "recent_24h": 0.0,
            },
            "blast_radius": {
                "category": "system_prompt",
                "source": "declared",
                "files": ["agents/refund_support/prompt.md"],
                "target": "refund-support-agent",
                "confidence": 1.0,
            },
        },
        "stratification_realised": {
            "pass_history": 0,
            "fail_history": 1,
            "rare_cluster": 0,
            "recent_24h": 0,
            "realised_total": 1,
        },
        "trace_count": 1,
        "regressed_count": 1,
        "regression_rate": 1.0,
        "threshold": 0.02,
        "verdict": "fail",
        "error_count": 0,
        "error_rate": 0.0,
        "judge_used_count": 0,
        "cost_usd": float(costs["ci_replay_usd"]),
        "duration_seconds": 9,
        "clusters": [
            {
                "label": "refund status tool not called",
                "keywords": ["refund", "status", "tool"],
                "size": 1,
                "sample_trace_id": ids["golden_trace"],
                "sample_input": scenario["user_input"],
            }
        ],
        "notes": [
            "Demo PR removes get_refund_status behavior and returns generic refund policy text."
        ],
    }
    ci_summary = {
        **ci_report,
        "source_kind": "issue_ci_gate",
        "source_id": str(ids["issue"]),
        "source_issue_id": str(ids["issue"]),
        "source_call_id": str(ids["bad_call"]),
        "source_issue_failure_code": str(scenario["failure_code"]),
        "source_issue_severity": "critical",
        "source_context": {
            **source_context,
            "kind": "issue_ci_gate",
            "origin": "ci_gate",
        },
        "report": ci_report,
        "pr_comment_markdown": (
            "<!-- zroky-regression-ci -->\n\n"
            "## Regression CI blocked this PR\n\n"
            "1 of 1 protected refund flows regressed. The candidate skipped get_refund_status and returned generic policy text.\n"
        ),
    }
    ci_run = ReplayRun(
        id=str(ids["regression_ci_run"]),
        project_id=project_id,
        golden_set_id=str(ids["golden_set"]),
        trigger="github",
        git_sha=str(ci_report["git_sha"]),
        status="fail",
        started_at=base_time + timedelta(minutes=18),
        completed_at=base_time + timedelta(minutes=19),
        summary_json=_compact_json(ci_summary),
        created_at=base_time + timedelta(minutes=18),
    )
    ci_trace = ReplayRunTrace(
        id=str(ids["regression_ci_trace"]),
        replay_run_id=str(ids["regression_ci_run"]),
        golden_trace_id=str(ids["golden_trace"]),
        project_id=project_id,
        call_id_replayed=str(ids["bad_call"]),
        judge_scores_json=_compact_json(
            {
                "confidence": 0.96,
                "reason": "Regression: get_refund_status was not called.",
                "output_diff": {"original": fixed_output, "candidate": broken_output},
                "tool_behavior_diff": {
                    "expected_tool_calls": fixed["tool_calls"],
                    "candidate_tool_calls": broken_pr["tool_calls"],
                    "required_tool_called": False,
                },
                "cost_delta_usd": round(float(costs["ci_replay_usd"]) - float(costs["verified_replay_usd"]), 4),
                "latency_delta_ms": int(timing["ci_latency_ms"]) - int(timing["verified_replay_latency_ms"]),
            }
        ),
        status="fail",
        diff_metric=0.91,
        output_text=broken_output,
        completed_at=base_time + timedelta(minutes=19),
        created_at=base_time + timedelta(minutes=18),
    )
    db.add_all([ci_run, ci_trace])

    db.commit()

    return {
        "project_id": project_id,
        "email": str(demo["user_email"]),
        "password": str(demo["user_password"]),
        "user_id": user_id,
        "membership_id": str(ids["membership"]),
        "api_key_id": str(ids.get("api_key", "demo-api-key-refund-money-path")),
        "api_key_prefix": api_key.key_prefix,
        "invitation_id": str(ids.get("invitation", "demo-invite-refund-money-path")),
        "call_id": str(ids["bad_call"]),
        "diagnosis_id": str(ids["diagnosis"]),
        "issue_id": str(ids["issue"]),
        "golden_set_id": str(ids["golden_set"]),
        "golden_trace_id": str(ids["golden_trace"]),
        "replay_run_id": str(ids["verified_replay"]),
        "replay_trace_id": str(ids["verified_replay_trace"]),
        "ci_run_id": str(ids["regression_ci_run"]),
        "ci_trace_id": str(ids["regression_ci_trace"]),
        "trace_id": str(scenario["trace_id"]),
        "issue_url": f"http://localhost:3000/issues/{ids['issue']}",
        "call_url": f"http://localhost:3000/calls/{ids['bad_call']}",
        "replay_url": f"http://localhost:3000/replay/{ids['verified_replay']}",
        "golden_set_url": f"http://localhost:3000/goldens/{ids['golden_set']}",
        "ci_gate_url": f"http://localhost:3000/ci-gates/{ids['regression_ci_run']}",
        "trace_url": f"http://localhost:3000/trace/{scenario['trace_id']}",
        "goldens_url": "http://localhost:3000/goldens",
        "ci_gates_url": "http://localhost:3000/ci-gates",
        "failure_inbox_url": "http://localhost:3000/home",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the deterministic Zroky MVP money path demo.")
    parser.add_argument(
        "--fixture",
        type=Path,
        default=FIXTURE_PATH,
        help="Path to refund_money_path_fixture.json.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print only the machine-readable seed summary JSON.",
    )
    parser.add_argument(
        "--create-schema",
        action="store_true",
        help="Create all SQLAlchemy tables before seeding. Intended for isolated local E2E databases.",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        if args.create_schema:
            Base.metadata.create_all(bind=db.get_bind())
        summary = seed_money_path_demo(db, fixture_path=args.fixture)

    if args.json:
        print(json.dumps(summary, separators=(",", ":"), sort_keys=True))
        return

    print("Seeded deterministic Zroky MVP money path demo.")
    print(f"Project: {summary['project_id']}")
    print(f"Login: {summary['email']} / {summary['password']}")
    print("Walkthrough:")
    print(f"  Failure Inbox: {summary['failure_inbox_url']}")
    print(f"  Call Detail:    {summary['call_url']}")
    print(f"  Issue Detail:  {summary['issue_url']}")
    print(f"  Replay Lab:    {summary['replay_url']}")
    print(f"  Golden Set:    {summary['golden_set_url']}")
    print(f"  CI Gate:       {summary['ci_gate_url']}")
    print(f"  Trace:         {summary['trace_url']}")


if __name__ == "__main__":
    main()
