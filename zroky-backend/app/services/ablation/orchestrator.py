"""Ablation orchestrator — public entry point for the root-cause attribution pipeline.

run_ablation_job()
    Full pipeline: determinism probe → control group → axis scoring → synthesis → persist.
    Designed to run in a background thread (called from the API route via threading.Thread).

get_ablation_job()
    Fetch a completed/in-progress job by id.

get_ablation_jobs_for_call()
    Fetch all jobs for a given call_id.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AblationAxis, AblationJob, Call, DiagnosisJob
from app.services.ablation.axis_extractor import extract_axes
from app.services.ablation.confidence_scorer import score_axes
from app.services.ablation.control_group import select_control_group
from app.services.ablation.determinism_classifier import classify_determinism
from app.services.ablation.synthesis import synthesise_root_cause

logger = logging.getLogger(__name__)

INSUFFICIENT_DATA_STATUSES = frozenset({"unknown"})


# ── Public API ─────────────────────────────────────────────────────────────────


def run_ablation_job(
    db: Session,
    *,
    project_id: str,
    call_id: str,
    diagnosis_job_id: str | None = None,
) -> AblationJob:
    """Create and execute a full ablation job.

    Returns the completed (or error-status) AblationJob row.
    Safe to call from a background thread — creates its own transaction
    segments and commits after each phase.
    """
    job = _create_job(db, project_id=project_id, call_id=call_id, diagnosis_job_id=diagnosis_job_id)

    try:
        call = _load_call(db, project_id=project_id, call_id=call_id)
        if call is None:
            return _finish_error(db, job, f"Call {call_id} not found for project {project_id}")

        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        db.commit()

        # ── Phase 0: Determinism probe ─────────────────────────────────────────
        det_result = classify_determinism(db, project_id=project_id, call=call)
        job.determinism_class = det_result.determinism_class
        job.determinism_probe_json = json.dumps(det_result.probe_detail, separators=(",", ":"))
        db.commit()

        if det_result.determinism_class == "unknown":
            return _finish_insufficient(db, job, "insufficient history for determinism probe")

        # ── Phase 1: Control group ─────────────────────────────────────────────
        control_group = select_control_group(db, project_id=project_id, failing_call=call)
        job.control_group_size = len(control_group)
        db.commit()

        if not control_group:
            return _finish_insufficient(db, job, "no similar successful calls found for control group")

        # ── Phase 2: Axis extraction + scoring ────────────────────────────────
        axes = extract_axes(call)
        scored = score_axes(axes, control_group)

        # ── Phase 3: Persist axes ─────────────────────────────────────────────
        diag_categories = _get_diagnosis_categories(db, project_id=project_id, call_id=call_id)

        for sa in scored:
            ax_row = AblationAxis(
                id=str(uuid4()),
                ablation_job_id=job.id,
                project_id=project_id,
                axis_type=sa.axis.axis_type,
                axis_label=sa.axis.axis_label,
                failing_value=sa.axis.failing_value,
                confidence=float(sa.confidence),
                evidence_json=json.dumps(sa.evidence, separators=(",", ":")),
            )
            db.add(ax_row)
        db.commit()

        # ── Phase 4: LLM Synthesis ─────────────────────────────────────────────
        scored_dicts = [
            {
                "axis_type": s.axis.axis_type,
                "axis_label": s.axis.axis_label,
                "confidence": float(s.confidence),
                "evidence": s.evidence,
            }
            for s in scored
        ]
        synthesis = synthesise_root_cause(
            determinism_class=det_result.determinism_class,
            agent_name=call.agent_name,
            diagnosis_categories=diag_categories,
            scored_axes=scored_dicts,
            control_group_size=len(control_group),
        )

        job.root_cause_narrative = synthesis.root_cause_narrative
        job.fix_suggestion = synthesis.fix_suggestion
        job.fix_difficulty = synthesis.fix_difficulty
        job.synthesis_confidence = float(synthesis.synthesis_confidence)
        job.status = "done"
        job.completed_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(
            "ablation job %s done: det=%s top_axis=%s conf=%.2f",
            job.id,
            det_result.determinism_class,
            scored[0].axis.axis_type if scored else "none",
            scored[0].confidence if scored else 0,
        )
        return job

    except Exception as exc:
        logger.exception("ablation job %s failed: %s", job.id, exc)
        return _finish_error(db, job, str(exc))


def get_ablation_job(
    db: Session,
    *,
    project_id: str,
    job_id: str,
) -> AblationJob | None:
    return db.execute(
        select(AblationJob).where(
            AblationJob.project_id == project_id,
            AblationJob.id == job_id,
        )
    ).scalar_one_or_none()


def get_ablation_jobs_for_call(
    db: Session,
    *,
    project_id: str,
    call_id: str,
    limit: int = 5,
) -> list[AblationJob]:
    rows = db.execute(
        select(AblationJob)
        .where(
            AblationJob.project_id == project_id,
            AblationJob.call_id == call_id,
        )
        .order_by(AblationJob.created_at.desc())
        .limit(limit)
    ).scalars().all()
    return list(rows)


def list_ablation_jobs(
    db: Session,
    *,
    project_id: str,
    limit: int = 20,
    status_filter: str | None = None,
) -> list[AblationJob]:
    q = (
        select(AblationJob)
        .where(AblationJob.project_id == project_id)
        .order_by(AblationJob.created_at.desc())
        .limit(limit)
    )
    if status_filter:
        q = q.where(AblationJob.status == status_filter)
    return list(db.execute(q).scalars().all())


# ── Internal helpers ───────────────────────────────────────────────────────────


def _create_job(
    db: Session,
    *,
    project_id: str,
    call_id: str,
    diagnosis_job_id: str | None,
) -> AblationJob:
    job = AblationJob(
        id=str(uuid4()),
        project_id=project_id,
        call_id=call_id,
        diagnosis_job_id=diagnosis_job_id,
        status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _load_call(db: Session, *, project_id: str, call_id: str) -> Call | None:
    return db.execute(
        select(Call).where(Call.project_id == project_id, Call.id == call_id)
    ).scalar_one_or_none()


def _get_diagnosis_categories(
    db: Session,
    *,
    project_id: str,
    call_id: str,
) -> list[str]:
    rows = db.execute(
        select(DiagnosisJob.diagnosis_type).where(
            DiagnosisJob.project_id == project_id,
            DiagnosisJob.call_id == call_id,
        )
    ).all()
    return [r[0] for r in rows if r[0]]


def _finish_error(db: Session, job: AblationJob, msg: str) -> AblationJob:
    job.status = "error"
    job.error_message = msg[:2000]
    job.completed_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except Exception:
        db.rollback()
    return job


def _finish_insufficient(db: Session, job: AblationJob, msg: str) -> AblationJob:
    job.status = "insufficient_data"
    job.error_message = msg
    job.completed_at = datetime.now(timezone.utc)
    db.commit()
    return job
