from app.api.routes._internal.analytics_common import *

@router.get("/activity-feed", response_model=ActivityFeedResponse)
def get_activity_feed(
    action: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session_read),
) -> ActivityFeedResponse:
    base_query = select(AuditLog).where(AuditLog.tenant_id == tenant_id)
    total_query = select(func.count()).select_from(AuditLog).where(AuditLog.tenant_id == tenant_id)

    normalized_action = action.strip().lower() if isinstance(action, str) and action.strip() else None
    if normalized_action:
        base_query = base_query.where(AuditLog.action == normalized_action)
        total_query = total_query.where(AuditLog.action == normalized_action)

    rows = db.execute(
        base_query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
    ).scalars().all()
    total = int(db.execute(total_query).scalar_one() or 0)

    return ActivityFeedResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[
            ActivityFeedItemResponse(
                log_id=row.id,
                tenant_id=row.tenant_id,
                diagnosis_id=row.diagnosis_id,
                action=row.action,
                actor_subject=row.actor_subject,
                metadata=parse_metadata(row.metadata_json),
                created_at=row.created_at,
            )
            for row in rows
        ],
    )


@router.get("/fixes", response_model=FixAnalyticsResponse)
def get_fix_analytics(
    days: int = Query(default=30, ge=1, le=180),
    tenant_id: str = Depends(require_tenant_role("viewer")),
    db: Session = Depends(get_db_session_read),
) -> FixAnalyticsResponse:
    return build_fix_analytics(db, tenant_id=tenant_id, window_days=days)


__all__ = [name for name in globals() if not name.startswith("__")]
