from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import require_tenant_id
from app.db.session import get_db_session_read
from app.services.digest_engine import (
    WeekFormatError,
    get_digest,
    list_digests,
    parse_week_param,
    serialize_digest,
    serialize_digest_summary,
)

router = APIRouter(prefix="/v1/digest")


class DigestSummaryResponse(BaseModel):
    id: str
    project_id: str
    week_start: str
    sent_to_emails: list[str] = Field(default_factory=list)
    sent_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class DigestListResponse(BaseModel):
    items: list[DigestSummaryResponse]
    next_cursor: str | None = None
    total_in_page: int


class DigestDetailResponse(DigestSummaryResponse):
    summary: dict[str, Any] = Field(default_factory=dict)
    html_blob: str | None = None


def _project_id(
    tenant_id: str = Depends(require_tenant_id),
    x_project_id: str | None = Header(default=None, alias="X-Project-Id"),
) -> str:
    return tenant_id or (x_project_id or "").strip()


@router.get("", response_model=DigestListResponse)
def list_project_digests(
    project_id: str = Depends(_project_id),
    db: Session = Depends(get_db_session_read),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> DigestListResponse:
    before: date | None = None
    if cursor:
        try:
            before = parse_week_param(cursor)
        except WeekFormatError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    rows = list_digests(db, project_id=project_id, limit=limit + 1, before_week_start=before)
    page = rows[:limit]
    return DigestListResponse(
        items=[DigestSummaryResponse(**serialize_digest_summary(row)) for row in page],
        next_cursor=page[-1].week_start.isoformat() if len(rows) > limit and page else None,
        total_in_page=len(page),
    )


@router.get("/{week}", response_model=DigestDetailResponse)
def get_project_digest(
    week: str,
    project_id: str = Depends(_project_id),
    db: Session = Depends(get_db_session_read),
) -> DigestDetailResponse:
    try:
        week_start = parse_week_param(week)
    except WeekFormatError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    digest = get_digest(db, project_id=project_id, week_start=week_start)
    if digest is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Digest not found")
    return DigestDetailResponse(**serialize_digest(digest))
