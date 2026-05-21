"""
/v1/intel/* — Intel Pulse read surface (Module 4.6; plan §13).

Single endpoint:

  GET /v1/intel/feed   filterable, paginated feed of currently-active
                       provider outages, model deprecations, CVEs,
                       pricing changes, and advisories.

Backed by `intel_signals` (migration 0055). The table is global —
every authenticated tenant sees the same intel — but we still require
tenant context to keep the route consistent with the rest of /v1/*
(authn rate-limiting, no anonymous access).

Watch-network / cross-tenant anonymized fleet aggregation is a separate
future module (see services/intel_feed.py docstring); the route prefix
chosen here is forward-compatible so adding `/v1/intel/watch` later
won't break consumers of /v1/intel/feed.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import require_tenant_id
from app.core.limiter import limiter
from app.db.session import get_db_session_read
from app.services.intel_feed import (
    IntelFeedFilterError,
    decode_cursor,
    encode_cursor,
    list_intel_signals,
    parse_kind,
    parse_min_severity,
    parse_model,
    parse_source,
    serialize_intel_signal,
)

router = APIRouter(prefix="/v1/intel")
logger = logging.getLogger(__name__)

_DEFAULT_LIMIT = 20
_MAX_LIMIT = 100


# ── schemas ─────────────────────────────────────────────────────────────────


class IntelSignalResponse(BaseModel):
    id: str
    source: str
    kind: str
    severity: str
    confidence: float
    url: str | None = None
    model_affected: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Parsed payload_json; {} when missing or corrupt",
    )
    created_at: str | None = None


class IntelFeedResponse(BaseModel):
    items: list[IntelSignalResponse]
    next_cursor: str | None
    total_in_page: int


# ── route ───────────────────────────────────────────────────────────────────


@router.get("/feed", response_model=IntelFeedResponse)
@limiter.limit("60/minute")
def get_intel_feed(
    request: Request,
    kind: str | None = Query(
        default=None,
        description=(
            "Filter to one signal kind: outage | deprecation | cve | "
            "pricing_change | advisory"
        ),
    ),
    min_severity: str | None = Query(
        default=None,
        description=(
            "Minimum severity threshold (≥): low | medium | high | critical"
        ),
    ),
    source: str | None = Query(
        default=None,
        description=(
            "Filter by source identifier, e.g. 'openai_status' (case-insensitive)"
        ),
    ),
    model: str | None = Query(
        default=None,
        description=(
            "Substring match on model_affected; e.g. 'gpt-4' matches "
            "'gpt-4o-2024-05-13' and 'gpt-4-turbo'"
        ),
    ),
    only_active: bool = Query(
        default=True,
        description=(
            "When true (default), filters to signals whose validity window "
            "contains now. Pass false to include expired/historical signals."
        ),
    ),
    cursor: str | None = Query(
        default=None,
        description="Opaque cursor from the previous page's next_cursor",
    ),
    limit: int = Query(
        default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT,
    ),
    tenant_id: str = Depends(require_tenant_id),  # noqa: ARG001 — auth gate only
    db: Session = Depends(get_db_session_read),
) -> IntelFeedResponse:
    """Read-only Intel Pulse feed.

    422 on any malformed filter (unknown kind/severity, oversize source/
    model, undecodable cursor, expired cursor row).
    """
    try:
        kind_norm = parse_kind(kind)
        min_severity_norm = parse_min_severity(min_severity)
        source_norm = parse_source(source)
        model_norm = parse_model(model)
        cursor_id = decode_cursor(cursor)
    except IntelFeedFilterError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    try:
        rows = list_intel_signals(
            db,
            kind=kind_norm,
            min_severity=min_severity_norm,
            source=source_norm,
            model=model_norm,
            only_active=only_active,
            limit=limit + 1,
            cursor_id=cursor_id,
        )
    except IntelFeedFilterError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    has_next = len(rows) > limit
    page = rows[:limit]

    next_cursor: str | None = None
    if has_next and page:
        next_cursor = encode_cursor(page[-1].id)

    return IntelFeedResponse(
        items=[IntelSignalResponse(**serialize_intel_signal(r)) for r in page],
        next_cursor=next_cursor,
        total_in_page=len(page),
    )
