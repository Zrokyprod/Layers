from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.routes._internal.owner_money_path_schemas import (
    OwnerLaunchGateEvidence,
    OwnerLaunchReadinessGate,
    OwnerLaunchReadinessResponse,
    OwnerMoneyPathHealthResponse,
)
from app.api.routes._internal.owner_money_path import (
    BLOCKING_CI_STATUSES,
    FINAL_READINESS_COMMANDS,
    PRODUCT_STANDARD,
    VERIFIED_REPLAY_STATUSES,
    _json_object,
)
from app.db.models import (
    GoldenSet,
    GoldenTrace,
    OutcomeReconciliationCheck,
    ReplayRun,
    RuntimePolicyDecision,
)


STALE_PRODUCT_DOC_PATHS = (
    ".devin/workflows/replay.md",
    ".kiro/specs/replay-worker-real-llm-execution/bugfix.md",
    ".kiro/specs/unknown-failure-discovery/design.md",
    ".kiro/specs/unknown-failure-discovery/requirements.md",
    ".kiro/specs/unknown-failure-discovery/tasks.md",
)


def _evidence(
    label: str,
    value: str | int | float | bool | None,
    *,
    status: str | None = None,
    detail: str | None = None,
) -> OwnerLaunchGateEvidence:
    return OwnerLaunchGateEvidence(
        label=label,
        value=value,
        status=status,
        detail=detail,
    )


def _gate(
    *,
    code: str,
    title: str,
    status: str,
    summary: str,
    blockers: list[str] | None = None,
    evidence: list[OwnerLaunchGateEvidence] | None = None,
    verification_commands: list[str] | None = None,
) -> OwnerLaunchReadinessGate:
    return OwnerLaunchReadinessGate(
        code=code,
        title=title,
        status=status,
        summary=summary,
        blockers=blockers or [],
        evidence=evidence or [],
        verification_commands=verification_commands or [],
    )


def _status_for(*, blockers: list[str], missing: list[str]) -> str:
    if blockers:
        return "fail"
    if missing:
        return "not_verified"
    return "pass"


def _replay_trust_counts(
    db: Session,
    *,
    project_ids: list[str],
    since: datetime,
) -> dict[str, int]:
    counts = {
        "trusted_verified": 0,
        "stub_marked_verified": 0,
        "not_verified": 0,
        "errors": 0,
    }
    if not project_ids:
        return counts

    runs = (
        db.execute(
            select(ReplayRun).where(
                ReplayRun.project_id.in_(project_ids),
                ReplayRun.created_at >= since,
            )
        )
        .scalars()
        .all()
    )
    for run in runs:
        summary = _json_object(run.summary_json)
        replay_mode = str(
            summary.get("requested_replay_mode")
            or summary.get("executor_replay_mode")
            or summary.get("replay_mode")
            or ""
        )
        verified = (
            summary.get("verified_fix") is True
            or str(summary.get("verification_status") or "") in VERIFIED_REPLAY_STATUSES
        )
        if run.status == "not_verified":
            counts["not_verified"] += 1
        if run.status == "error":
            counts["errors"] += 1
        if verified and replay_mode == "stub":
            counts["stub_marked_verified"] += 1
        elif verified:
            counts["trusted_verified"] += 1
    return counts


def _ci_run_counts(
    db: Session,
    *,
    project_ids: list[str],
    since: datetime,
) -> dict[str, int]:
    counts = {
        "total": 0,
        "pass": 0,
        "warn": 0,
        "fail": 0,
        "not_verified": 0,
        "error": 0,
    }
    if not project_ids:
        return counts
    rows = db.execute(
        select(ReplayRun.status, func.count(ReplayRun.id))
        .where(
            ReplayRun.project_id.in_(project_ids),
            ReplayRun.trigger == "github",
            ReplayRun.created_at >= since,
        )
        .group_by(ReplayRun.status)
    ).all()
    for status, count in rows:
        key = str(status or "unknown")
        if key in counts:
            counts[key] = int(count or 0)
        counts["total"] += int(count or 0)
    return counts


def _behavioral_golden_counts(
    db: Session,
    *,
    project_ids: list[str],
) -> dict[str, int]:
    counts = {
        "active": 0,
        "blocking": 0,
        "blocking_behavioral": 0,
        "blocking_text_only": 0,
    }
    if not project_ids:
        return counts
    rows = db.execute(
        select(GoldenTrace, GoldenSet)
        .join(GoldenSet, GoldenTrace.golden_set_id == GoldenSet.id)
        .where(
            GoldenTrace.project_id.in_(project_ids),
            GoldenTrace.status == "active",
        )
    ).all()
    for trace, golden_set in rows:
        counts["active"] += 1
        if not bool(golden_set.blocks_ci) or bool(golden_set.is_flaky):
            continue
        counts["blocking"] += 1
        criteria = _json_object(trace.criteria_json)
        contract = criteria.get("golden_contract_v1")
        if isinstance(contract, dict) and contract:
            counts["blocking_behavioral"] += 1
        else:
            counts["blocking_text_only"] += 1
    return counts


def _runtime_policy_counts(
    db: Session,
    *,
    project_ids: list[str],
    since: datetime,
) -> dict[str, int]:
    counts = {
        "blocked": 0,
        "pending_approval": 0,
        "approved": 0,
        "rejected": 0,
        "risk_stopped": 0,
    }
    if not project_ids:
        return counts
    rows = (
        db.execute(
            select(RuntimePolicyDecision).where(
                RuntimePolicyDecision.project_id.in_(project_ids),
                RuntimePolicyDecision.created_at >= since,
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        if row.status in counts:
            counts[row.status] += 1
        if row.decision in {"block", "requires_approval"} or row.status in {
            "blocked",
            "pending_approval",
            "approved",
            "rejected",
        }:
            counts["risk_stopped"] += 1
    return counts


def _outcome_reconciliation_counts(
    db: Session,
    *,
    project_ids: list[str],
    since: datetime,
) -> dict[str, int]:
    counts = {
        "total": 0,
        "matched": 0,
        "mismatched": 0,
        "not_verified": 0,
        "linked_calls": 0,
        "linked_runtime_policy": 0,
    }
    if not project_ids:
        return counts

    rows = (
        db.execute(
            select(OutcomeReconciliationCheck).where(
                OutcomeReconciliationCheck.project_id.in_(project_ids),
                OutcomeReconciliationCheck.checked_at >= since,
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        counts["total"] += 1
        if row.verdict in {"matched", "mismatched", "not_verified"}:
            counts[row.verdict] += 1
        if row.call_id:
            counts["linked_calls"] += 1
        if row.runtime_policy_decision_id:
            counts["linked_runtime_policy"] += 1
    return counts


def _repo_root_for_source_truth() -> Path | None:
    candidates = [
        Path.cwd(),
        Path.cwd().parent,
        Path(__file__).resolve().parents[5],
    ]
    for candidate in candidates:
        if (candidate / "README.md").exists() and (
            candidate / "zroky-backend"
        ).exists():
            return candidate
    return None


def _source_truth_status() -> tuple[str, list[str], list[OwnerLaunchGateEvidence]]:
    root = _repo_root_for_source_truth()
    if root is None:
        return (
            "not_verified",
            ["repo_root_not_found"],
            [
                _evidence(
                    "README marker",
                    "missing",
                    status="not_verified",
                    detail="Backend could not locate the repository root to verify product source of truth.",
                )
            ],
        )

    readme = root / "README.md"
    text = readme.read_text(encoding="utf-8", errors="replace")
    has_marker = "single product and implementation source of truth" in text
    stale_docs = [rel for rel in STALE_PRODUCT_DOC_PATHS if (root / rel).exists()]
    evidence = [
        _evidence(
            "README.md", "present", status="pass" if has_marker else "not_verified"
        ),
        _evidence(
            "stale planning docs",
            len(stale_docs),
            status="fail" if stale_docs else "pass",
        ),
    ]
    if stale_docs:
        return "fail", [f"stale_doc:{rel}" for rel in stale_docs], evidence
    if not has_marker:
        return "not_verified", ["readme_source_marker_missing"], evidence
    return "pass", [], evidence


def build_launch_readiness(
    db: Session,
    *,
    money_path: OwnerMoneyPathHealthResponse,
) -> OwnerLaunchReadinessResponse:
    now = datetime.now(UTC)
    since_7d = now - timedelta(days=7)
    platform = money_path.platform
    tenants = money_path.tenants
    project_ids = [row.project_id for row in tenants]

    replay_counts = _replay_trust_counts(db, project_ids=project_ids, since=since_7d)
    ci_counts = _ci_run_counts(db, project_ids=project_ids, since=since_7d)
    golden_counts = _behavioral_golden_counts(db, project_ids=project_ids)
    runtime_counts = _runtime_policy_counts(db, project_ids=project_ids, since=since_7d)
    reconciliation_counts = _outcome_reconciliation_counts(
        db, project_ids=project_ids, since=since_7d
    )
    source_status, source_blockers, source_evidence = _source_truth_status()

    gates: list[OwnerLaunchReadinessGate] = []

    capture_blockers = [
        code
        for code in platform.launch_blockers
        if code
        in {
            "capture_loss_detected",
            "gateway_backpressure",
            "gateway_spool_stale",
        }
    ]
    capture_missing = []
    if platform.captures_24h <= 0:
        capture_missing.append("no_capture_24h")
    if platform.tenants_without_recent_capture > 0:
        capture_missing.append("tenant_capture_gap")
    gates.append(
        _gate(
            code="durable_capture",
            title="Durable Capture",
            status=_status_for(blockers=capture_blockers, missing=capture_missing),
            summary="SDK, gateway, and direct ingest must preserve masked production events with visible loss/backpressure.",
            blockers=capture_blockers + capture_missing,
            evidence=[
                _evidence("captures_24h", platform.captures_24h),
                _evidence(
                    "tenants_without_recent_capture",
                    platform.tenants_without_recent_capture,
                ),
                _evidence(
                    "gateway_unhealthy_tenants", platform.gateway_unhealthy_tenants
                ),
                _evidence("gateway_loss_tenants", platform.gateway_loss_tenants),
                _evidence(
                    "gateway_backpressure_tenants",
                    platform.gateway_backpressure_tenants,
                ),
            ],
            verification_commands=[
                "python -m pytest tests/test_ingest.py tests/test_capture_health.py",
                "go test ./...",
            ],
        )
    )

    duplicate_project_ids = len(set(project_ids)) != len(project_ids)
    tenant_missing = [] if tenants else ["no_active_tenants"]
    tenant_blockers = ["duplicate_tenant_rows"] if duplicate_project_ids else []
    gates.append(
        _gate(
            code="tenant_isolation",
            title="Tenant Isolation",
            status=_status_for(blockers=tenant_blockers, missing=tenant_missing),
            summary="Every tenant-scoped flow must use the selected project and reject cross-project access.",
            blockers=tenant_blockers + tenant_missing,
            evidence=[
                _evidence("tenant_rows", len(tenants)),
                _evidence("unique_project_rows", len(set(project_ids))),
                _evidence("money_path_scoped_rows", bool(tenants)),
            ],
            verification_commands=[
                "python -m pytest tests/test_tenant_session_project_selection.py tests/test_tenant_project_route_scoping.py",
            ],
        )
    )

    failure_missing = []
    if platform.issues_open <= 0:
        failure_missing.append("no_grouped_failures")
    gates.append(
        _gate(
            code="failure_intelligence",
            title="Failure Intelligence",
            status=_status_for(blockers=[], missing=failure_missing),
            summary="Production failures must group into actionable issues with root cause, blast radius, next action, and proof status.",
            blockers=failure_missing,
            evidence=[
                _evidence("open_grouped_failures", platform.issues_open),
                _evidence(
                    "tenants_with_failures",
                    sum(1 for row in tenants if row.open_issue_count > 0),
                ),
            ],
            verification_commands=[
                "python -m pytest tests/test_failure_intelligence.py tests/test_issues.py",
            ],
        )
    )

    replay_blockers: list[str] = []
    if replay_counts["stub_marked_verified"] > 0:
        replay_blockers.append("stub_replay_marked_verified")
    if platform.replay_jobs_stale > 0:
        replay_blockers.append("replay_worker_stale_jobs")
    if replay_counts["errors"] > 0:
        replay_blockers.append("replay_executor_errors")
    replay_missing = []
    if replay_counts["trusted_verified"] <= 0:
        replay_missing.append("trusted_replay_proof_missing")
    if replay_counts["not_verified"] > 0:
        replay_missing.append("recent_replay_not_verified")
    gates.append(
        _gate(
            code="honest_replay_proof",
            title="Honest Replay Proof",
            status=_status_for(blockers=replay_blockers, missing=replay_missing),
            summary="Replay must report pass/fail/not_verified/error honestly; stub replay can never be trusted proof.",
            blockers=replay_blockers + replay_missing,
            evidence=[
                _evidence(
                    "trusted_verified_replays_7d", replay_counts["trusted_verified"]
                ),
                _evidence(
                    "stub_marked_verified", replay_counts["stub_marked_verified"]
                ),
                _evidence("not_verified_replays_7d", replay_counts["not_verified"]),
                _evidence("replay_errors_7d", replay_counts["errors"]),
                _evidence("stale_replay_jobs", platform.replay_jobs_stale),
            ],
            verification_commands=[
                "python -m pytest tests/test_replay_runs.py tests/test_replay_executor.py tests/test_replay_worker_claiming.py",
                "python -m pytest",
            ],
        )
    )

    golden_blockers = []
    if golden_counts["blocking_text_only"] > 0:
        golden_blockers.append("blocking_text_only_goldens")
    golden_missing = []
    if golden_counts["blocking_behavioral"] <= 0:
        golden_missing.append("behavioral_blocking_goldens_missing")
    gates.append(
        _gate(
            code="behavioral_goldens",
            title="Behavioral Goldens",
            status=_status_for(blockers=golden_blockers, missing=golden_missing),
            summary="Blocking Goldens must verify behavior contracts, not only final text.",
            blockers=golden_blockers + golden_missing,
            evidence=[
                _evidence("active_goldens", golden_counts["active"]),
                _evidence("blocking_goldens", golden_counts["blocking"]),
                _evidence(
                    "blocking_behavioral_goldens", golden_counts["blocking_behavioral"]
                ),
                _evidence(
                    "blocking_text_only_goldens", golden_counts["blocking_text_only"]
                ),
            ],
            verification_commands=[
                "python -m pytest tests/test_goldens.py",
            ],
        )
    )

    ci_blockers = []
    if ci_counts["fail"] > 0:
        ci_blockers.append("blocking_ci_failures")
    if ci_counts["error"] > 0:
        ci_blockers.append("ci_executor_errors")
    ci_missing = []
    if ci_counts["total"] <= 0:
        ci_missing.append("ci_gate_run_missing")
    if ci_counts["not_verified"] > 0:
        ci_missing.append("ci_not_verified")
    gates.append(
        _gate(
            code="durable_ci_gate",
            title="Durable CI Gate",
            status=_status_for(blockers=ci_blockers, missing=ci_missing),
            summary="CI must run durable Golden gates and fail repeat regressions or not_verified safety checks.",
            blockers=ci_blockers + ci_missing,
            evidence=[
                _evidence("ci_runs_7d", ci_counts["total"]),
                _evidence("ci_pass_7d", ci_counts["pass"]),
                _evidence("ci_warn_7d", ci_counts["warn"]),
                _evidence("ci_fail_7d", ci_counts["fail"]),
                _evidence("ci_not_verified_7d", ci_counts["not_verified"]),
                _evidence("ci_error_7d", ci_counts["error"]),
            ],
            verification_commands=[
                "python -m pytest tests/test_regression_ci_routes.py tests/test_regression_ci_orchestrator.py",
                "npm test",
            ],
        )
    )

    runtime_missing = []
    if runtime_counts["risk_stopped"] <= 0:
        runtime_missing.append("runtime_risk_stop_evidence_missing")
    gates.append(
        _gate(
            code="runtime_risk_stop",
            title="Runtime Risk Stop",
            status=_status_for(blockers=[], missing=runtime_missing),
            summary="Risky autonomous actions must be blocked or paused before side effects execute.",
            blockers=runtime_missing,
            evidence=[
                _evidence("risk_stopped_7d", runtime_counts["risk_stopped"]),
                _evidence("blocked_7d", runtime_counts["blocked"]),
                _evidence("pending_approvals_7d", runtime_counts["pending_approval"]),
                _evidence("approved_7d", runtime_counts["approved"]),
                _evidence("rejected_7d", runtime_counts["rejected"]),
            ],
            verification_commands=[
                "python -m pytest tests/test_runtime_policy_gate.py",
            ],
        )
    )

    outcome_blockers: list[str] = []
    if reconciliation_counts["mismatched"] > 0:
        outcome_blockers.append("outcome_mismatch_detected")
    outcome_missing: list[str] = []
    if reconciliation_counts["total"] <= 0:
        outcome_missing.append("outcome_reconciliation_missing")
    if reconciliation_counts["not_verified"] > 0:
        outcome_missing.append("outcome_not_verified")
    if reconciliation_counts["matched"] <= 0:
        outcome_missing.append("matched_outcome_proof_missing")
    gates.append(
        _gate(
            code="outcome_verification",
            title="Outcome Verification",
            status=_status_for(blockers=outcome_blockers, missing=outcome_missing),
            summary="Money-touching actions must be reconciled against the system of record; green output alone is not proof.",
            blockers=outcome_blockers + outcome_missing,
            evidence=[
                _evidence("reconciliation_checks_7d", reconciliation_counts["total"]),
                _evidence("matched_7d", reconciliation_counts["matched"]),
                _evidence("mismatched_7d", reconciliation_counts["mismatched"]),
                _evidence("not_verified_7d", reconciliation_counts["not_verified"]),
                _evidence(
                    "checks_linked_to_calls_7d", reconciliation_counts["linked_calls"]
                ),
                _evidence(
                    "checks_linked_to_runtime_policy_7d",
                    reconciliation_counts["linked_runtime_policy"],
                ),
            ],
            verification_commands=[
                "python -m pytest tests/test_outcome_reconciliation.py",
                "npm test -- src/app/(dashboard)/outcomes/page.test.tsx",
            ],
        )
    )

    billing_blockers = list(platform.billing_launch_blockers or [])
    gates.append(
        _gate(
            code="billing_quota",
            title="Billing + Quota",
            status=_status_for(blockers=billing_blockers, missing=[]),
            summary="Plan entitlements, usage, metering, payment lifecycle, and provider proof must be reliable and owner-visible.",
            blockers=billing_blockers,
            evidence=[
                _evidence("billing_launch_blockers", len(billing_blockers)),
                _evidence(
                    "metering_failure_tenants", platform.metering_failure_tenants
                ),
                _evidence(
                    "event_counter_failure_count", platform.event_counter_failure_count
                ),
                _evidence(
                    "billing_provider_verification",
                    platform.billing_provider_verification.state,
                    detail=platform.billing_provider_verification.detail,
                ),
                _evidence("tenants_with_quota_risk", platform.tenants_with_quota_risk),
                _evidence(
                    "tenants_with_billing_risk", platform.tenants_with_billing_risk
                ),
            ],
            verification_commands=[
                "python -m pytest tests/test_billing_v2.py tests/test_owner_money_path_health.py",
            ],
        )
    )

    getting_value_tenants = sum(
        1 for row in tenants if row.value_status == "getting_value"
    )
    owner_value_blockers = [
        code
        for code in platform.launch_blockers
        if code
        in {
            "deployment_smoke_not_passing",
            "billing_provider_unverified",
            "pricing_contract_drift",
        }
    ]
    owner_value_missing = []
    if getting_value_tenants <= 0:
        owner_value_missing.append("no_tenant_getting_value")
    gates.append(
        _gate(
            code="owner_value_proof",
            title="Owner Value Proof",
            status=_status_for(
                blockers=owner_value_blockers, missing=owner_value_missing
            ),
            summary="Owner must see who is getting reliability value and where money path is blocked.",
            blockers=owner_value_blockers + owner_value_missing,
            evidence=[
                _evidence("getting_value_tenants", getting_value_tenants),
                _evidence("blocked_regressions_7d", platform.blocked_regressions_7d),
                _evidence("verified_fixes_7d", platform.verified_fixes_7d),
                _evidence(
                    "deployment_smoke",
                    platform.last_deployed_smoke.status,
                    detail=platform.last_deployed_smoke.detail,
                ),
                _evidence("launch_blockers", len(platform.launch_blockers)),
            ],
            verification_commands=[
                "python -m pytest tests/test_owner_money_path_health.py",
                "python scripts/run_money_path_demo.py --json",
                "npm test -- --run src/app/owner/page.test.tsx src/app/owner/money-path/page.test.tsx",
            ],
        )
    )

    gates.append(
        _gate(
            code="single_source_of_truth",
            title="Single Source Of Truth",
            status=source_status,
            summary="Only root README.md may guide product direction; stale planning Markdown must not steer implementation.",
            blockers=source_blockers,
            evidence=source_evidence,
            verification_commands=[
                'git ls-files "*.md"',
                "python scripts/check_docs_drift.py",
            ],
        )
    )

    paid_launch_allowed = all(gate.status == "pass" for gate in gates)
    hard_blockers = [
        f"{gate.code}:{blocker}"
        for gate in gates
        for blocker in gate.blockers
        if gate.status != "pass"
    ]
    if paid_launch_allowed:
        overall_status = "pass"
    elif any(gate.status == "fail" for gate in gates):
        overall_status = "blocked"
    else:
        overall_status = "not_verified"

    return OwnerLaunchReadinessResponse(
        generated_at=now,
        product_standard=PRODUCT_STANDARD,
        overall_status=overall_status,
        paid_launch_allowed=paid_launch_allowed,
        gates=gates,
        hard_blockers=hard_blockers,
        verification_commands=FINAL_READINESS_COMMANDS,
    )
