"""Judge Health surface — exposes calibration drift + per-dimension drift.

Until this route, judge-engine drift signals lived only in process logs
(`judge_calibration_drift_alert ...` WARNING entries) and the in-memory
alert callback registry. Operators had no UI surface to inspect calibration
health, so the entire Layer 3 self-monitoring story was invisible.

This route exposes two GET endpoints under `/v1/judge`:

  GET /v1/judge/health
      → verdict-level drift for every (judge_model) the project has used,
        AND per-dimension drift for the standard MultiDim + ReferenceFree
        dimensions (accuracy, faithfulness, relevance, coherence,
        groundedness, completeness). Designed to drive a "Judge Health"
        panel on the dashboard home page.

  GET /v1/judge/health/dimension/{dimension}
      → focused per-dimension snapshot (e.g. for a drill-down view).

Tenant scoping: project_id is derived from the JWT (`require_tenant_role`)
so the dashboard cannot peek at other tenants' calibration windows.

Read-only. Never mutates calibration state. Safe to call from polling UIs.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.dependencies.tenant import require_tenant_role
from app.core.config import get_settings
from app.services.judge_calibration import (
    compute_dimension_drift,
    compute_drift,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/judge", tags=["judge-health"])


# ── Response schemas ──────────────────────────────────────────────────────────


class VerdictDriftView(BaseModel):
    """Verdict-level (pass/fail/inconclusive) calibration drift for one judge."""

    judge_model: str = Field(..., description="Judge model identifier (provider/name).")
    sample_count: int = Field(..., ge=0)
    disagreement_count: int = Field(..., ge=0)
    disagreement_rate: float = Field(..., ge=0.0, le=1.0)
    threshold: float = Field(
        ..., description="Disagreement-rate threshold above which we consider drift breached.",
    )
    breached: bool = Field(
        ..., description="True if disagreement_rate > threshold AND min-samples met.",
    )


class DimensionDriftView(BaseModel):
    """Per-dimension continuous-score drift for one (judge_model, dimension)."""

    judge_model: str
    dimension: str
    sample_count: int = Field(..., ge=0)
    older_mean: float = Field(..., ge=0.0, le=1.0)
    recent_mean: float = Field(..., ge=0.0, le=1.0)
    drift: float = Field(
        ...,
        description=(
            "older_mean - recent_mean. Positive => the recent half's mean is "
            "lower (quality degradation). Negative => improvement."
        ),
    )
    threshold: float = Field(
        ...,
        description="Drift threshold above which we consider degradation material.",
    )
    breached: bool = Field(
        ...,
        description=(
            "True if drift > threshold AND both halves have at least the "
            "minimum sample count."
        ),
    )


class JudgeHealthResponse(BaseModel):
    """Aggregate judge-engine health for the calling tenant."""

    project_id: str
    window_hours: int = Field(
        ..., description="Rolling window size (hours) governing every snapshot here.",
    )
    enabled: bool = Field(
        ..., description="JUDGE_ENABLED setting — when False the engine is dormant.",
    )
    primary_model: str | None = Field(
        None,
        description="The plan-resolved primary judge for this tenant (single or ensemble median).",
    )
    ensemble_models: list[str] = Field(
        default_factory=list,
        description="Ensemble member models when the tenant's plan uses median voting.",
    )
    verdict_drift: list[VerdictDriftView] = Field(
        default_factory=list,
        description="Per-judge verdict-level drift; empty when no calibration anchors recorded yet.",
    )
    dimension_drift: list[DimensionDriftView] = Field(
        default_factory=list,
        description="Per-(judge, dimension) drift covering accuracy/groundedness/etc.",
    )
    any_breached: bool = Field(
        ..., description="True when at least one verdict or dimension is in breach.",
    )


# ── Helpers ───────────────────────────────────────────────────────────────────


# Dimensions tracked by MultiDimEvaluator + ReferenceFreeEvaluator. Listed
# explicitly so the dashboard always renders the same column ordering and the
# "no samples yet" state can be distinguished from "dimension absent".
_TRACKED_DIMENSIONS: tuple[str, ...] = (
    "accuracy",
    "faithfulness",
    "relevance",
    "coherence",
    "groundedness",
    "completeness",
)


def _resolve_judge_models(settings) -> list[str]:
    """Best-effort list of judge models this tenant might be using.

    Combines the single-judge primary with any ensemble members so the
    response covers every model that could have recorded calibration samples.
    """
    models: list[str] = []
    primary = (getattr(settings, "JUDGE_SINGLE_MODEL", "") or "").strip()
    if primary:
        models.append(primary)
    raw_ensemble = getattr(settings, "JUDGE_ENSEMBLE_MODELS_JSON", None)
    if raw_ensemble:
        try:
            import json

            decoded = json.loads(raw_ensemble) if isinstance(raw_ensemble, str) else raw_ensemble
            if isinstance(decoded, list):
                for m in decoded:
                    if isinstance(m, str) and m.strip() and m.strip() not in models:
                        models.append(m.strip())
        except (json.JSONDecodeError, TypeError, ValueError):
            logger.debug("judge_health: ensemble models JSON decode failed; using primary only")
    return models


def _verdict_view(project_id: str, model: str) -> VerdictDriftView:
    status = compute_drift(project_id, model)
    return VerdictDriftView(
        judge_model=model,
        sample_count=status.sample_count,
        disagreement_count=status.disagreement_count,
        disagreement_rate=round(status.disagreement_rate, 4),
        threshold=round(status.threshold, 4),
        breached=status.breached,
    )


def _dimension_view(project_id: str, model: str, dimension: str) -> DimensionDriftView:
    status = compute_dimension_drift(project_id, model, dimension)
    return DimensionDriftView(
        judge_model=model,
        dimension=dimension,
        sample_count=status.sample_count,
        older_mean=status.older_mean,
        recent_mean=status.recent_mean,
        drift=status.drift,
        threshold=status.threshold,
        breached=status.breached,
    )


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/health", response_model=JudgeHealthResponse)
def get_judge_health(
    include_zero_sample: bool = Query(
        default=False,
        description=(
            "When True, return entries even when sample_count == 0. Defaults to "
            "False so the dashboard hides dimensions the project never recorded."
        ),
    ),
    tenant_id: str = Depends(require_tenant_role("viewer")),
) -> JudgeHealthResponse:
    settings = get_settings()
    models = _resolve_judge_models(settings)

    verdict_views: list[VerdictDriftView] = []
    dimension_views: list[DimensionDriftView] = []
    for model in models:
        v = _verdict_view(tenant_id, model)
        if include_zero_sample or v.sample_count > 0:
            verdict_views.append(v)
        for dim in _TRACKED_DIMENSIONS:
            d = _dimension_view(tenant_id, model, dim)
            if include_zero_sample or d.sample_count > 0:
                dimension_views.append(d)

    any_breached = any(v.breached for v in verdict_views) or any(
        d.breached for d in dimension_views
    )

    return JudgeHealthResponse(
        project_id=tenant_id,
        window_hours=int(getattr(settings, "JUDGE_CALIBRATION_WINDOW_HOURS", 168)),
        enabled=bool(getattr(settings, "JUDGE_ENABLED", False)),
        primary_model=models[0] if models else None,
        ensemble_models=models[1:] if len(models) > 1 else [],
        verdict_drift=verdict_views,
        dimension_drift=dimension_views,
        any_breached=any_breached,
    )


@router.get("/health/dimension/{dimension}", response_model=list[DimensionDriftView])
def get_judge_dimension_drift(
    dimension: str,
    tenant_id: str = Depends(require_tenant_role("viewer")),
) -> list[DimensionDriftView]:
    """Focused per-dimension snapshot across every judge model.

    Used by drill-down views. `dimension` is the lower-case dimension name
    (e.g. `groundedness`, `accuracy`). Unknown names return an empty list
    rather than 404 — they may simply have no recorded samples yet.
    """
    settings = get_settings()
    dim = (dimension or "").strip().lower()
    if not dim:
        return []
    models = _resolve_judge_models(settings)
    return [_dimension_view(tenant_id, m, dim) for m in models]
