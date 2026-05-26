"""
GET  /v1/anomalies              — Cursor-paginated anomaly list with filters.
GET  /v1/anomalies/{id}         — Single anomaly detail.
POST /v1/anomalies/{id}/resolve     — Mark resolved.
POST /v1/anomalies/{id}/acknowledge — Acknowledge without resolving.
POST /v1/anomalies/{id}/mute        — Silence (replaces legacy 'ignored').

Phase B of the legacy `issues → anomalies` rename (plan §3.1, §6.1).
This route is deprecated for external clients; use `/v1/issues` for the
customer-facing issue model.
"""
from __future__ import annotations

import base64
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import require_tenant_id
from app.core.limiter import limiter
from app.db.models import Anomaly
from app.db.session import get_db_session
from app.services.anomalies import (
    VALID_DETECTORS,
    VALID_STATUSES,
    acknowledge_anomaly,
    mute_anomaly,
    resolve_anomaly,
)

router = APIRouter(prefix="/v1/anomalies")
logger = logging.getLogger(__name__)

_DEFAULT_LIMIT = 20
_MAX_LIMIT = 100

_VALID_SEVERITIES = frozenset({"low", "medium", "high", "critical"})


def _mark_deprecated(response: Response) -> None:
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = '</v1/issues>; rel="successor-version"'
    response.headers["X-Zroky-Deprecated"] = (
        "Deprecated internal issue alias; use /v1/issues"
    )


# ── schemas ───────────────────────────────────────────────────────────────────

class AnomalyResponse(BaseModel):
    id: str
    project_id: str
    fingerprint: str
    detector: str
    severity: str
    status: str
    occurrence_count: int
    first_seen_at: datetime
    last_seen_at: datetime
    sample_call_ids_json: str | None
    evidence_json: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AnomalyListResponse(BaseModel):
    items: list[AnomalyResponse]
    next_cursor: str | None
    total_in_page: int


# ── cursor helpers ────────────────────────────────────────────────────────────

def _encode_cursor(last_seen_at: datetime, anomaly_id: str) -> str:
    payload = json.dumps(
        {"t": last_seen_at.isoformat(), "id": anomaly_id},
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, str] | None:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        ts = datetime.fromisoformat(payload["t"])
        return ts, str(payload["id"])
    except Exception:
        return None


# ── routes ────────────────────────────────────────────────────────────────────

@router.get("", response_model=AnomalyListResponse)
@limiter.limit("60/minute")
def list_anomalies(
    request: Request,
    response: Response,
    status_filter: str | None = Query(default="open", alias="status"),
    detector: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> AnomalyListResponse:
    _mark_deprecated(response)
    if (
        status_filter is not None
        and status_filter not in VALID_STATUSES
        and status_filter != "all"
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="status must be one of: open, acknowledged, resolved, muted, all",
        )

    if detector is not None and detector.upper() not in VALID_DETECTORS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "detector must be one of: "
                + ", ".join(sorted(VALID_DETECTORS))
            ),
        )

    if severity is not None and severity.lower() not in _VALID_SEVERITIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="severity must be one of: low, medium, high, critical",
        )

    conditions = [Anomaly.project_id == tenant_id]
    if status_filter and status_filter != "all":
        conditions.append(Anomaly.status == status_filter)
    if detector:
        conditions.append(Anomaly.detector == detector.upper())
    if severity:
        conditions.append(Anomaly.severity == severity.lower())

    if cursor:
        decoded = _decode_cursor(cursor)
        if decoded is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid cursor value.",
            )
        cursor_ts, cursor_id = decoded
        conditions.append(
            or_(
                Anomaly.last_seen_at < cursor_ts,
                and_(Anomaly.last_seen_at == cursor_ts, Anomaly.id < cursor_id),
            )
        )

    rows = db.execute(
        select(Anomaly)
        .where(*conditions)
        .order_by(Anomaly.last_seen_at.desc(), Anomaly.id.desc())
        .limit(limit + 1)
    ).scalars().all()

    has_next = len(rows) > limit
    page = list(rows[:limit])

    next_cursor: str | None = None
    if has_next and page:
        last = page[-1]
        next_cursor = _encode_cursor(last.last_seen_at, last.id)

    return AnomalyListResponse(
        items=[AnomalyResponse.model_validate(row) for row in page],
        next_cursor=next_cursor,
        total_in_page=len(page),
    )


@router.get("/{anomaly_id}", response_model=AnomalyResponse)
@limiter.limit("120/minute")
def get_anomaly(
    request: Request,
    response: Response,
    anomaly_id: str,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> AnomalyResponse:
    _mark_deprecated(response)
    anomaly = db.execute(
        select(Anomaly).where(
            Anomaly.project_id == tenant_id,
            Anomaly.id == anomaly_id,
        )
    ).scalar_one_or_none()
    if anomaly is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found"
        )
    return AnomalyResponse.model_validate(anomaly)


@router.post("/{anomaly_id}/resolve", response_model=AnomalyResponse)
@limiter.limit("30/minute")
def resolve_anomaly_endpoint(
    request: Request,
    response: Response,
    anomaly_id: str,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> AnomalyResponse:
    _mark_deprecated(response)
    resolved = resolve_anomaly(db, project_id=tenant_id, anomaly_id=anomaly_id)
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found"
        )
    return AnomalyResponse.model_validate(resolved)


@router.post("/{anomaly_id}/acknowledge", response_model=AnomalyResponse)
@limiter.limit("30/minute")
def acknowledge_anomaly_endpoint(
    request: Request,
    response: Response,
    anomaly_id: str,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> AnomalyResponse:
    _mark_deprecated(response)
    acked = acknowledge_anomaly(db, project_id=tenant_id, anomaly_id=anomaly_id)
    if acked is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found"
        )
    return AnomalyResponse.model_validate(acked)


@router.post("/{anomaly_id}/mute", response_model=AnomalyResponse)
@limiter.limit("30/minute")
def mute_anomaly_endpoint(
    request: Request,
    response: Response,
    anomaly_id: str,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> AnomalyResponse:
    _mark_deprecated(response)
    muted = mute_anomaly(db, project_id=tenant_id, anomaly_id=anomaly_id)
    if muted is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found"
        )
    return AnomalyResponse.model_validate(muted)
