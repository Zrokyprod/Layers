"""
GET /v1/issues  — Cursor-paginated issue list with grouping.

Grouping key: (failure_code, prompt_fingerprint, agent_name).
Cursor: opaque base64-encoded (last_seen_at ISO, id) tuple — stable across pages.
"""
from __future__ import annotations

import base64
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import require_tenant_id
from app.core.limiter import limiter
from fastapi import Request
from app.db.models import Issue
from app.db.session import get_db_session
from app.services.issues import resolve_issue, VALID_STATUSES

router = APIRouter(prefix="/v1/issues")
logger = logging.getLogger(__name__)

_DEFAULT_LIMIT = 20
_MAX_LIMIT = 100


# ── schemas ───────────────────────────────────────────────────────────────────

class IssueResponse(BaseModel):
    id: str
    project_id: str
    failure_code: str
    prompt_fingerprint: str | None
    agent_name: str | None
    status: str
    severity: str
    occurrence_count: int
    blast_radius_usd: float
    first_seen_at: datetime
    last_seen_at: datetime
    sample_call_id: str | None
    sample_diagnosis_id: str | None
    last_fix_id: str | None
    resolved_at: datetime | None
    resolution_source: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class IssueListResponse(BaseModel):
    items: list[IssueResponse]
    next_cursor: str | None
    total_in_page: int


class IssueResolveRequest(BaseModel):
    fix_id: str | None = None
    resolution_source: str = "manual"


# ── cursor helpers ────────────────────────────────────────────────────────────

def _encode_cursor(last_seen_at: datetime, issue_id: str) -> str:
    payload = json.dumps(
        {"t": last_seen_at.isoformat(), "id": issue_id},
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

@router.get("", response_model=IssueListResponse)
@limiter.limit("60/minute")
def list_issues(
    request: Request,
    status_filter: str | None = Query(default="open", alias="status"),
    failure_code: str | None = Query(default=None),
    agent_name: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    has_fix: bool | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> IssueListResponse:
    if status_filter is not None and status_filter not in VALID_STATUSES and status_filter != "all":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"status must be one of: open, resolved, ignored, all",
        )

    conditions = [Issue.project_id == tenant_id]

    if status_filter and status_filter != "all":
        conditions.append(Issue.status == status_filter)
    if failure_code:
        conditions.append(Issue.failure_code == failure_code.upper())
    if agent_name:
        conditions.append(Issue.agent_name == agent_name)
    if severity:
        conditions.append(Issue.severity == severity.lower())
    if has_fix is True:
        conditions.append(Issue.last_fix_id.isnot(None))
    elif has_fix is False:
        conditions.append(Issue.last_fix_id.is_(None))

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
                Issue.last_seen_at < cursor_ts,
                and_(Issue.last_seen_at == cursor_ts, Issue.id < cursor_id),
            )
        )

    rows = db.execute(
        select(Issue)
        .where(*conditions)
        .order_by(Issue.last_seen_at.desc(), Issue.id.desc())
        .limit(limit + 1)
    ).scalars().all()

    has_next = len(rows) > limit
    page = list(rows[:limit])

    next_cursor: str | None = None
    if has_next and page:
        last = page[-1]
        next_cursor = _encode_cursor(last.last_seen_at, last.id)

    return IssueListResponse(
        items=[IssueResponse.model_validate(row) for row in page],
        next_cursor=next_cursor,
        total_in_page=len(page),
    )


@router.get("/{issue_id}", response_model=IssueResponse)
@limiter.limit("120/minute")
def get_issue(
    request: Request,
    issue_id: str,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> IssueResponse:
    issue = db.execute(
        select(Issue).where(Issue.project_id == tenant_id, Issue.id == issue_id)
    ).scalar_one_or_none()
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")
    return IssueResponse.model_validate(issue)


@router.post("/{issue_id}/resolve", response_model=IssueResponse)
@limiter.limit("30/minute")
def resolve_issue_endpoint(
    request: Request,
    issue_id: str,
    body: IssueResolveRequest,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> IssueResponse:
    resolved = resolve_issue(
        db,
        project_id=tenant_id,
        issue_id=issue_id,
        fix_id=body.fix_id,
        resolution_source=body.resolution_source,
    )
    if resolved is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")
    return IssueResponse.model_validate(resolved)
