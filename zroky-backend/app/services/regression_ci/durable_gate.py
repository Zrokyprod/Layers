from __future__ import annotations

import json
import logging
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Mapping

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models import Call, GoldenSet, GoldenTrace, ReplayRun, ReplayRunTrace
from app.db.session import SessionLocal
from app.services.regression_ci.blast_radius import ChangedFile
from app.services.regression_ci.models import (
    BlastRadius,
    BlastRadiusSource,
    RegressionCIReport,
)
from app.services.regression_ci.orchestrator import (
    DEFAULT_REGRESSION_THRESHOLD,
    CandidateOutput,
    RegressionCIInputs,
    run_regression_ci,
)

logger = logging.getLogger(__name__)


def run_regression_ci_background(
    *,
    tenant_id: str,
    run_id: str,
    request_payload: dict[str, Any],
) -> None:
    """Durable worker entry point for a persisted regression-CI run."""
    session: Session = SessionLocal()
    try:
        from app.services.embedding_service import get_embedding_service
        from app.services.entitlements_resolver import (
            get_plan_code,
            has,
            resolve_all,
        )
        from app.services.judge_engine import get_evaluator
        from app.services.replay_executor import (
            ReplayBudgetTracker,
            default_resolver,
            make_live_llm_resolver,
        )

        try:
            ents = resolve_all(session, tenant_id)
            plan = get_plan_code(session, tenant_id)
            real_llm_entitled = has(
                session, tenant_id, "pilot.real_llm_replay_enabled",
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "regression_ci.worker.entitlements_lookup_failed tenant=%s",
                tenant_id,
                exc_info=True,
            )
            ents, plan, real_llm_entitled = None, None, False

        evaluator = get_evaluator(plan_code=plan, entitlements_dict=ents)

        budget_tracker: ReplayBudgetTracker | None = None
        if real_llm_entitled:
            from app.core.config import get_settings

            budget_tracker = ReplayBudgetTracker(
                budget_usd=float(get_settings().REPLAY_REAL_LLM_BUDGET_USD)
            )
            inner_resolver = make_live_llm_resolver(
                candidate_prompt_override=None,
                candidate_model_override=None,
                budget_tracker=budget_tracker,
            )
        else:
            inner_resolver = default_resolver

        def _adapter(call: Call) -> CandidateOutput:
            synthetic_trace = GoldenTrace(
                id=f"regression-ci-syn-{call.id}",
                golden_set_id=_synthetic_golden_set_id(call.project_id),
                project_id=call.project_id,
                expected_output_text="",
                source_evidence_json="{}",
            )
            actual = inner_resolver(synthetic_trace, call)
            return CandidateOutput(
                text=actual.text,
                error_message=actual.reason,
                cost_usd=actual.cost_total,
                latency_ms=actual.latency_ms,
            )

        op_override = _operator_override_from_payload(request_payload)
        inputs = RegressionCIInputs(
            project_id=tenant_id,
            git_sha=request_payload.get("git_sha"),
            pr_body=request_payload.get("pr_body"),
            zroky_yaml=request_payload.get("zroky_yaml"),
            changed_files=[
                ChangedFile(path=cf["path"], hunks=cf.get("hunks", ""))
                for cf in request_payload.get("changed_files") or []
            ],
            threshold=float(
                request_payload.get("threshold", DEFAULT_REGRESSION_THRESHOLD)
            ),
            target_total_cap=request_payload.get("target_total_cap"),
            sample_window_days=int(request_payload.get("sample_window_days", 30)),
        )

        embedder = None
        try:
            embedder = get_embedding_service()
        except Exception:  # noqa: BLE001
            logger.warning(
                "regression_ci.worker.embedder_unavailable tenant=%s",
                tenant_id,
                exc_info=True,
            )

        report = run_regression_ci(
            inputs,
            db=session,
            candidate_resolver=_adapter,
            embedder=embedder,
            judge=evaluator,
            operator_override=op_override,
            run_id_override=run_id,
        )
        report = apply_golden_gate_policy(session, report)
        _persist_report(session, tenant_id=tenant_id, run_id=run_id, report=report)

        if report.verdict in {"fail", "not_verified", "error"}:
            _dispatch_failed_ci_alert(
                session=session,
                tenant_id=tenant_id,
                run_id=run_id,
                status=report.verdict,
                git_sha=request_payload.get("git_sha"),
                report=report.to_dict(),
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "regression_ci.worker.failed tenant=%s run=%s",
            tenant_id,
            run_id,
        )
        _persist_error(
            session,
            tenant_id=tenant_id,
            run_id=run_id,
            request_payload=request_payload,
            exc=exc,
        )
    finally:
        session.close()


def apply_golden_gate_policy(
    db: Session,
    report: RegressionCIReport,
) -> RegressionCIReport:
    """Overlay the product gate policy on top of the trace-sampling report."""
    evidence = _collect_golden_gate_evidence(db, report.project_id)
    failed = evidence["failed"]
    warned = evidence["warned"]
    reasons = list(evidence["not_verified_reasons"])
    notes = list(report.notes)

    verdict = report.verdict
    if verdict != "error":
        if failed:
            verdict = "fail"
        elif reasons:
            verdict = "not_verified"
        elif warned and verdict == "pass":
            verdict = "warn"

    if reasons:
        notes.append("golden gate not verified: " + "; ".join(reasons[:3]))
    if failed:
        notes.append(f"{len(failed)} blocking Golden(s) failed")
    if warned:
        notes.append(f"{len(warned)} warning Golden(s) failed or lacked proof")

    return replace(
        report,
        verdict=verdict,
        failed_goldens=tuple(failed),
        warn_goldens=tuple(warned),
        not_verified_reasons=tuple(reasons),
        notes=tuple(dict.fromkeys(notes)),
    )


def _collect_golden_gate_evidence(
    db: Session,
    project_id: str,
) -> dict[str, list[dict[str, Any]] | list[str]]:
    rows = list(
        db.execute(
            select(GoldenSet, GoldenTrace)
            .join(GoldenTrace, GoldenTrace.golden_set_id == GoldenSet.id)
            .where(
                GoldenSet.project_id == project_id,
                GoldenTrace.project_id == project_id,
                GoldenTrace.status == "active",
            )
            .order_by(GoldenSet.created_at.asc(), GoldenTrace.created_at.asc())
        ).all()
    )

    blocking_total = 0
    trusted_blocking_total = 0
    failed: list[dict[str, Any]] = []
    warned: list[dict[str, Any]] = []
    reasons: list[str] = []

    for golden_set, trace in rows:
        blocking = bool(golden_set.blocks_ci) and not bool(golden_set.is_flaky)
        trusted = _trace_has_trusted_proof(trace)
        latest = _latest_trace_result(db, project_id=project_id, trace_id=trace.id)
        item = _golden_item(golden_set, trace, latest)

        if blocking:
            blocking_total += 1
            if not trusted:
                reasons.append(
                    f"blocking Golden {trace.id} is active but not backed by trusted replay proof"
                )
                continue
            trusted_blocking_total += 1
            if latest is None:
                reasons.append(f"blocking Golden {trace.id} has no replay evidence")
            elif latest["status"] == "fail":
                failed.append(item)
            elif latest["status"] in {"not_verified", "error"}:
                reasons.append(
                    f"blocking Golden {trace.id} replay status is {latest['status']}"
                )
            continue

        if latest and latest["status"] in {"fail", "not_verified", "error"}:
            warned.append(item)

    if blocking_total == 0:
        reasons.append("no active blocking Goldens exist for this project")
    elif trusted_blocking_total == 0:
        reasons.append("no active blocking Goldens have trusted replay proof")

    return {
        "failed": failed,
        "warned": warned,
        "not_verified_reasons": _dedupe(reasons),
    }


def _trace_has_trusted_proof(trace: GoldenTrace) -> bool:
    try:
        criteria = json.loads(trace.criteria_json or "{}")
    except json.JSONDecodeError:
        return False
    if not isinstance(criteria, dict):
        return False
    contract = criteria.get("golden_contract_v1")
    if not isinstance(contract, dict):
        return False
    linked_proof = contract.get("linked_proof")
    if not isinstance(linked_proof, dict):
        return False
    return (
        linked_proof.get("proof_status") == "verified_fix"
        or linked_proof.get("verified_fix") is True
    )


def _latest_trace_result(
    db: Session,
    *,
    project_id: str,
    trace_id: str,
) -> dict[str, Any] | None:
    row = db.execute(
        select(ReplayRunTrace, ReplayRun)
        .join(ReplayRun, ReplayRun.id == ReplayRunTrace.replay_run_id)
        .where(
            ReplayRunTrace.project_id == project_id,
            ReplayRunTrace.golden_trace_id == trace_id,
            ReplayRun.project_id == project_id,
        )
        .order_by(desc(ReplayRunTrace.created_at), desc(ReplayRunTrace.id))
        .limit(1)
    ).first()
    if row is None:
        return None
    trace, run = row
    summary = _json_object(run.summary_json)
    return {
        "status": trace.status,
        "replay_run_id": run.id,
        "replay_mode": summary.get("requested_replay_mode")
        or summary.get("executor_replay_mode")
        or summary.get("replay_mode")
        or "unknown",
        "verification_status": summary.get("verification_status"),
        "verified_fix": bool(summary.get("verified_fix")),
    }


def _golden_item(
    golden_set: GoldenSet,
    trace: GoldenTrace,
    latest: Mapping[str, Any] | None,
) -> dict[str, Any]:
    status_value = str(latest.get("status")) if latest else "missing_replay"
    return {
        "golden_set_id": golden_set.id,
        "golden_trace_id": trace.id,
        "golden_name": golden_set.name,
        "status": status_value,
        "assertion": f"replay_trace_status:{status_value}",
        "replay_run_id": latest.get("replay_run_id") if latest else None,
        "replay_mode": latest.get("replay_mode") if latest else "unknown",
        "recommended_fix": "Replay the fix with trusted evidence, then update the Golden contract.",
    }


def _persist_report(
    db: Session,
    *,
    tenant_id: str,
    run_id: str,
    report: RegressionCIReport,
) -> None:
    row = db.execute(
        select(ReplayRun).where(
            ReplayRun.id == run_id,
            ReplayRun.project_id == tenant_id,
        )
    ).scalar_one_or_none()
    if row is None:
        return
    row.status = report.verdict
    row.completed_at = row.completed_at or datetime.now(timezone.utc)
    row.summary_json = json.dumps(report.to_dict())
    db.add(row)
    db.commit()


def _persist_error(
    session: Session,
    *,
    tenant_id: str,
    run_id: str,
    request_payload: dict[str, Any],
    exc: Exception,
) -> None:
    try:
        session.rollback()
        row = session.execute(
            select(ReplayRun).where(
                ReplayRun.id == run_id,
                ReplayRun.project_id == tenant_id,
            )
        ).scalar_one_or_none()
        if row is not None:
            error_summary = {
                "schema_version": "v1",
                "run_id": run_id,
                "project_id": tenant_id,
                "git_sha": request_payload.get("git_sha"),
                "verdict": "error",
                "failed_goldens": [],
                "warn_goldens": [],
                "not_verified_reasons": [],
                "notes": [f"worker_failed:{type(exc).__name__}"],
            }
            row.status = "error"
            row.completed_at = datetime.now(timezone.utc)
            row.summary_json = json.dumps(error_summary)
            session.add(row)
            session.commit()
            _dispatch_failed_ci_alert(
                session=session,
                tenant_id=tenant_id,
                run_id=run_id,
                status="error",
                git_sha=request_payload.get("git_sha"),
                report=error_summary,
            )
    except Exception:  # noqa: BLE001
        logger.exception("regression_ci.worker.finalize_error_failed run=%s", run_id)


def _operator_override_from_payload(payload: Mapping[str, Any]) -> BlastRadius | None:
    raw = payload.get("operator_override")
    if not raw:
        return None
    return BlastRadius(
        category=raw["category"],
        source=BlastRadiusSource.OVERRIDE,
        target=raw.get("target"),
        confidence=1.0,
    )


def _dispatch_failed_ci_alert(
    *,
    session: Session,
    tenant_id: str,
    run_id: str,
    status: str,
    git_sha: str | None,
    report: Mapping[str, Any],
) -> None:
    try:
        from app.services.notification_dispatch import dispatch_ci_gate_failed_slack_alert

        dispatch_ci_gate_failed_slack_alert(
            db=session,
            tenant_id=tenant_id,
            run_id=run_id,
            status=status,
            git_sha=git_sha,
            report=dict(report),
        )
    except Exception:  # noqa: BLE001
        logger.debug("regression_ci.worker.slack_alert_failed", exc_info=True)


def _json_object(raw: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _synthetic_golden_set_id(project_id: str) -> str:
    return f"regression-ci:{project_id}"
