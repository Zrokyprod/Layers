"""WebSocket endpoints for realtime dashboard updates."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.identity import build_identity_context, decode_jwt_claims, resolve_project_from_identity
from app.db.models import ApiKey, Project
from app.db.session import SessionLocal
from app.realtime import get_hub
from app.realtime.hub import start_redis_bridge
from app.services.security import hash_api_key

logger = logging.getLogger(__name__)
router = APIRouter()


def _resolve_tenant_for_ws(
    *,
    db: Session,
    api_key: str | None,
    bearer: str | None,
    project_id: str | None,
) -> str | None:
    """Resolve a tenant ID from either an API key or a bearer JWT.

    Returns ``None`` when authentication fails.
    """
    if api_key:
        row = db.execute(
            select(ApiKey)
            .join(Project, Project.id == ApiKey.project_id)
            .where(
                ApiKey.key_hash == hash_api_key(api_key),
                ApiKey.revoked_at.is_(None),
                Project.is_active.is_(True),
            )
        ).scalar_one_or_none()
        if row is not None:
            return row.project_id
        return None

    if bearer:
        try:
            claims = decode_jwt_claims(bearer)
            identity = build_identity_context(claims)
            return resolve_project_from_identity(identity, project_id)
        except Exception as exc:  # noqa: BLE001
            logger.debug("realtime ws: bearer rejected: %s", exc)
            return None

    return None


@router.websocket("/v1/realtime")
async def realtime_ws(
    websocket: WebSocket,
    project_id: str | None = Query(default=None),
    topics: str | None = Query(
        default=None,
        description="Comma-separated topic filter (e.g. 'diagnosis,loop_alert'). Empty = all.",
    ),
) -> None:
    """Tenant-scoped WebSocket for live dashboard updates.

    Auth precedence (in this order):
    1. ``x-api-key`` header
    2. ``Authorization: Bearer <jwt>`` header
    3. ``?api_key=`` query string fallback (useful for browser clients)
    """
    api_key = (
        websocket.headers.get("x-api-key")
        or websocket.query_params.get("api_key")
    )
    auth_header = websocket.headers.get("authorization", "")
    bearer = auth_header.removeprefix("Bearer ").strip() if auth_header.lower().startswith("bearer ") else None

    db = SessionLocal()
    try:
        tenant_id = _resolve_tenant_for_ws(
            db=db,
            api_key=api_key,
            bearer=bearer,
            project_id=project_id,
        )
    finally:
        db.close()

    if not tenant_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    topic_filter = (
        {t.strip() for t in topics.split(",") if t.strip()}
        if topics
        else set()
    )

    hub = get_hub()
    await start_redis_bridge()
    sub = await hub.connect(websocket, tenant_id=tenant_id, topics=topic_filter)
    try:
        # Keep the connection alive and listen for client pings.
        while True:
            try:
                await websocket.receive_text()
            except WebSocketDisconnect:
                break
    finally:
        await hub.disconnect(sub)
