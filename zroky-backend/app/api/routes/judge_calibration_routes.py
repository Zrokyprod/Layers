"""Calibrated Judge API — public scoreboard + label CRUD.

Surface:
  GET    /v1/judge/calibration/latest        — latest run (all models or filter)
  GET    /v1/judge/calibration/history        — per-model time-series
  POST   /v1/judge/calibration/run-now        — manual trigger (tenant admin)
  GET    /v1/judge/calibration/mode/{model}   — current mode + accuracy snapshot
  GET    /v1/judge/calibration/labels         — list labels for a trace
  POST   /v1/judge/calibration/labels         — create / upsert a label
  DELETE /v1/judge/calibration/labels/{id}   — soft-delete (deactivate)

Every verdict in the system now includes:
  { verdict: ..., confidence: ..., judge_accuracy_on_your_data: 0.91, mode: "blocking" }
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import require_tenant_id, require_tenant_role
from app.core.config import get_settings
from app.core.limiter import limiter
from app.db.models import (
    GoldenLabel,
    GoldenTrace,
    JudgeCalibrationRun,
    JudgeModeOverride,
)
from app.db.session import get_db_session
from app.services.judge_calibration_metrics import (
    build_confusion_matrix,
    per_class_metrics,
    accuracy,
    cohens_kappa,
)
from app.services.judge_calibration_runner import run_calibration
from app.services.judge_mode_resolver import resolve_mode

router = APIRouter(prefix="/v1/judge/calibration", tags=["judge-calibration"])
logger = logging.getLogger(__name__)


# ── Schemas ────────────────────────────────────────────────────────────────────


class LabelCreate(BaseModel):
    golden_trace_id: str
    verdict: str = Field(pattern=r"^(pass|fail|inconclusive)$")
    rationale: str | None = None


class LabelView(BaseModel):
    id: str
    golden_trace_id: str
    labeler_user_id: str | None
    verdict: str
    rationale: str | None
    version: int
    active: bool
    created_at: datetime


class CalibrationRunView(BaseModel):
    id: str
    project_id: str
    judge_model: str
    run_date: date
    status: str
    sample_count: int
    agreement_count: int
    accuracy: float
    kappa: float
    low_confidence_pct: float
    per_class_metrics: list[dict[str, Any]]
    confusion_matrix: dict[str, dict[str, int]]
    cost_usd: float
    completed_at: datetime | None


class ModeView(BaseModel):
    project_id: str
    judge_model: str
    mode: str
    reason: str | None
    accuracy: float | None
    sample_count: int | None
    last_run_date: str | None


class RunNowResponse(BaseModel):
    run_id: str
    status: str
    message: str


# ── Helpers ────────────────────────────────────────────────────────────────────


def _serialize_run(run: JudgeCalibrationRun) -> CalibrationRunView:
    per_class: list[dict] = []
    if run.per_class_metrics_json:
        try:
            per_class = json.loads(run.per_class_metrics_json)
        except json.JSONDecodeError:
            pass
    matrix: dict[str, dict[str, int]] = {}
    if run.confusion_matrix_json:
        try:
            matrix = json.loads(run.confusion_matrix_json)
        except json.JSONDecodeError:
            pass
    return CalibrationRunView(
        id=run.id,
        project_id=run.project_id,
        judge_model=run.judge_model,
        run_date=run.run_date,
        status=run.status,
        sample_count=run.sample_count,
        agreement_count=run.agreement_count,
        accuracy=run.accuracy,
        kappa=run.kappa,
        low_confidence_pct=run.low_confidence_pct,
        per_class_metrics=per_class,
        confusion_matrix=matrix,
        cost_usd=float(run.cost_usd),
        completed_at=run.completed_at,
    )


def _serialize_label(label: GoldenLabel) -> LabelView:
    return LabelView(
        id=label.id,
        golden_trace_id=label.golden_trace_id,
        labeler_user_id=label.labeler_user_id,
        verdict=label.verdict,
        rationale=label.rationale,
        version=label.version,
        active=label.active,
        created_at=label.created_at,
    )


# ── Latest run ────────────────────────────────────────────────────────────────


@router.get("/latest", response_model=list[CalibrationRunView])
@limiter.limit("30/minute")
def get_latest(
    request: Request,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
    judge_model: str | None = Query(None),
) -> list[CalibrationRunView]:
    """Latest completed calibration run(s). Filter by judge_model if given."""
    q = (
        select(JudgeCalibrationRun)
        .where(
            JudgeCalibrationRun.project_id == tenant_id,
            JudgeCalibrationRun.status == "complete",
        )
        .order_by(desc(JudgeCalibrationRun.run_date))
    )
    if judge_model:
        q = q.where(JudgeCalibrationRun.judge_model == judge_model)
    # Return the most recent row per judge_model
    rows = db.execute(q.limit(20)).scalars().all()
    # Dedupe by model (keep first = latest date)
    seen: set[str] = set()
    out: list[CalibrationRunView] = []
    for r in rows:
        if r.judge_model not in seen:
            seen.add(r.judge_model)
            out.append(_serialize_run(r))
    return out


# ── History ────────────────────────────────────────────────────────────────────


@router.get("/history", response_model=list[CalibrationRunView])
@limiter.limit("30/minute")
def get_history(
    request: Request,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
    judge_model: str = Query(..., description="Judge model slug"),
    days: int = Query(default=30, ge=1, le=365),
) -> list[CalibrationRunView]:
    """Time-series of calibration runs for a specific judge model."""
    since = datetime.now(timezone.utc).date() - timedelta(days=days)
    rows = db.execute(
        select(JudgeCalibrationRun)
        .where(
            JudgeCalibrationRun.project_id == tenant_id,
            JudgeCalibrationRun.judge_model == judge_model,
            JudgeCalibrationRun.status == "complete",
            JudgeCalibrationRun.run_date >= since,
        )
        .order_by(JudgeCalibrationRun.run_date)
    ).scalars().all()
    return [_serialize_run(r) for r in rows]


# ── Mode snapshot ─────────────────────────────────────────────────────────────


@router.get("/mode/{judge_model}", response_model=ModeView)
@limiter.limit("60/minute")
def get_mode(
    request: Request,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
    judge_model: str = "...",
) -> ModeView:
    """Current mode + latest accuracy for a judge model."""
    view = resolve_mode(db, project_id=tenant_id, judge_model=judge_model)
    return ModeView(
        project_id=view.project_id,
        judge_model=view.judge_model,
        mode=view.mode,
        reason=view.reason,
        accuracy=view.accuracy,
        sample_count=view.sample_count,
        last_run_date=view.last_run_date,
    )


# ── Run now ────────────────────────────────────────────────────────────────────


@router.post("/run-now", response_model=RunNowResponse)
@limiter.limit("5/minute")
def run_now(
    request: Request,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
    _role: None = Depends(require_tenant_role("admin")),
    judge_model: str | None = Query(None),
) -> RunNowResponse:
    """Trigger a calibration run manually. Admin-only."""
    settings = get_settings()
    model = judge_model or settings.JUDGE_SINGLE_MODEL or "anthropic/claude-haiku-4"
    run = run_calibration(
        db,
        project_id=tenant_id,
        judge_model=model,
    )
    return RunNowResponse(
        run_id=run.id,
        status=run.status,
        message=f"Calibration run complete: {run.sample_count} samples, accuracy={run.accuracy:.4f}",
    )


# ── Labels ─────────────────────────────────────────────────────────────────────


@router.get("/labels", response_model=list[LabelView])
@limiter.limit("30/minute")
def list_labels(
    request: Request,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
    trace_id: str | None = Query(None, description="Filter by golden_trace_id"),
) -> list[LabelView]:
    """List human labels. Optionally filter by trace_id. Returns all versions
    (active and inactive) so the caller sees history."""
    q = select(GoldenLabel).where(GoldenLabel.project_id == tenant_id)
    if trace_id:
        q = q.where(GoldenLabel.golden_trace_id == trace_id)
    q = q.order_by(GoldenLabel.golden_trace_id, desc(GoldenLabel.version))
    rows = db.execute(q).scalars().all()
    return [_serialize_label(l) for l in rows]


@router.post("/labels", response_model=LabelView)
@limiter.limit("30/minute")
def create_or_update_label(
    request: Request,
    body: LabelCreate,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
    user_id: str = Depends(lambda r: r.state.user_id if hasattr(r.state, "user_id") else None),
) -> LabelView:
    """Create or update a human label on a golden trace.

    Upsert semantics:
      - If an active label exists for this trace → deactivate it and insert
        a new row with version = max(existing) + 1.
      - If no active label exists → insert version=1.
    """
    # Verify trace exists and belongs to tenant
    trace = db.execute(
        select(GoldenTrace).where(
            GoldenTrace.id == body.golden_trace_id,
            GoldenTrace.project_id == tenant_id,
        )
    ).scalar_one_or_none()
    if trace is None:
        raise HTTPException(status_code=404, detail="Golden trace not found")

    # Deactivate existing active label for this trace
    existing = db.execute(
        select(GoldenLabel).where(
            GoldenLabel.golden_trace_id == body.golden_trace_id,
            GoldenLabel.active.is_(True),
        )
    ).scalars().all()

    max_version = 0
    for old in existing:
        old.active = False
        if old.version > max_version:
            max_version = old.version

    label = GoldenLabel(
        id=str(__import__("uuid").uuid4()),
        golden_trace_id=body.golden_trace_id,
        project_id=tenant_id,
        labeler_user_id=user_id,
        verdict=body.verdict,
        rationale=body.rationale,
        version=max_version + 1,
        active=True,
    )
    db.add(label)
    db.commit()
    db.refresh(label)
    return _serialize_label(label)


@router.delete("/labels/{label_id}")
@limiter.limit("30/minute")
def delete_label(
    request: Request,
    label_id: str,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> dict[str, str]:
    """Soft-delete: deactivate the label (set active=false)."""
    label = db.execute(
        select(GoldenLabel).where(
            GoldenLabel.id == label_id,
            GoldenLabel.project_id == tenant_id,
        )
    ).scalar_one_or_none()
    if label is None:
        raise HTTPException(status_code=404, detail="Label not found")
    label.active = False
    db.commit()
    return {"message": "Label deactivated", "label_id": label_id}
