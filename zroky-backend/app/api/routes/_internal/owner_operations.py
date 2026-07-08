from app.api.routes._internal.owner_common import *
from app.api.routes._internal.owner_pricing_audit import _owner_audit, _resolve_actor

_TENANT_RATE_LIMIT_KEY = "zroky:tenant:{project_id}:rate_limit"
_ALLOWED_QUEUES = frozenset({"diagnosis_fast", "diagnosis_pattern", "celery"})


class TenantRateLimitRequest(BaseModel):
    ingest_soft_limit_rpm: int | None = None
    ingest_burst_limit_rpm: int | None = None
    ingest_enforce_rate_limit: bool | None = None


@router.get("/projects/{project_id}/rate-limit")
def owner_get_tenant_rate_limit(
    project_id: str,
    _: None = Depends(require_provisioning_access),
) -> dict:
    key = _TENANT_RATE_LIMIT_KEY.format(project_id=project_id)
    overrides: dict = {}
    if _redis_ok():
        try:
            raw = get_redis_client().get(key)
            if raw:
                overrides = json.loads(raw)
        except Exception:
            pass
    return {"project_id": project_id, "overrides": overrides, "has_override": bool(overrides)}


@router.put("/projects/{project_id}/rate-limit")
@limiter.limit("10/minute")
def owner_set_tenant_rate_limit(
    request: Request,
    project_id: str,
    body: TenantRateLimitRequest,
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> dict:
    p = db.scalar(select(Project).where(Project.id == project_id))
    if not p:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if not _redis_ok():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Redis unavailable")
    overrides = {k: v for k, v in body.model_dump().items() if v is not None}
    key = _TENANT_RATE_LIMIT_KEY.format(project_id=project_id)
    get_redis_client().set(key, json.dumps(overrides))
    _owner_audit(db, action="owner.tenant.rate_limit.set", actor=_resolve_actor(request),
                 target_id=project_id, metadata={"overrides": overrides})
    db.commit()
    return {"ok": True, "project_id": project_id, "overrides": overrides}


@router.delete("/projects/{project_id}/rate-limit")
@limiter.limit("10/minute")
def owner_clear_tenant_rate_limit(
    request: Request,
    project_id: str,
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> dict:
    if _redis_ok():
        get_redis_client().delete(_TENANT_RATE_LIMIT_KEY.format(project_id=project_id))
    _owner_audit(db, action="owner.tenant.rate_limit.clear", actor=_resolve_actor(request),
                 target_id=project_id, metadata={})
    db.commit()
    return {"ok": True, "project_id": project_id}


@router.post("/users/{user_id}/anonymize")
@limiter.limit("10/minute")
def owner_anonymize_user(
    request: Request,
    user_id: str,
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> dict:
    u = db.scalar(select(User).where(User.id == user_id))
    if not u:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    u.email = None  # type: ignore[assignment]
    u.email_hash = None  # type: ignore[assignment]
    u.display_name = "Deleted User"  # type: ignore[assignment]
    u.github_id = None  # type: ignore[assignment]
    u.google_id = None  # type: ignore[assignment]
    u.github_login = None  # type: ignore[assignment]
    u.github_token_encrypted = None  # type: ignore[assignment]
    u.github_token_scopes = None  # type: ignore[assignment]
    u.github_token_connected_at = None  # type: ignore[assignment]
    u.github_token_updated_at = None  # type: ignore[assignment]
    u.is_active = False  # type: ignore[assignment]
    _owner_audit(db, action="owner.user.anonymize", actor=_resolve_actor(request),
                 target_id=user_id, metadata={})
    db.commit()
    return {"ok": True, "user_id": user_id, "action": "anonymized"}


@router.delete("/users/{user_id}")
@limiter.limit("5/minute")
def owner_delete_user(
    request: Request,
    user_id: str,
    confirm: str = Query(..., description="Must be 'DELETE_CONFIRMED'"),
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> dict:
    if confirm != "DELETE_CONFIRMED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pass ?confirm=DELETE_CONFIRMED to hard-delete a user.",
        )
    u = db.scalar(select(User).where(User.id == user_id))
    if not u:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    _owner_audit(db, action="owner.user.delete", actor=_resolve_actor(request),
                 target_id=user_id, metadata={"subject": u.subject})
    db.flush()
    db.delete(u)
    db.commit()
    return {"ok": True, "user_id": user_id, "action": "deleted"}


class OwnerDestructiveChallengeRequest(BaseModel):
    confirm: str
    reason: str | None = None


class RevokeTaskRequest(OwnerDestructiveChallengeRequest):
    terminate: bool = False


@router.delete("/queues/{queue_name}/purge")
@limiter.limit("5/minute")
def owner_purge_queue(
    request: Request,
    queue_name: str,
    body: OwnerDestructiveChallengeRequest,
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> dict:
    if body.confirm != f"PURGE {queue_name}":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Confirmation must be 'PURGE {queue_name}'.",
        )
    if queue_name not in _ALLOWED_QUEUES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown queue. Allowed: {sorted(_ALLOWED_QUEUES)}",
        )
    if not _redis_ok():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Redis unavailable")
    deleted = get_redis_client().delete(queue_name)
    _owner_audit(db, action="owner.queue.purge", actor=_resolve_actor(request),
                 target_id=queue_name, metadata={"deleted_keys": deleted, "reason": body.reason})
    db.commit()
    return {"ok": True, "queue": queue_name, "deleted_keys": int(deleted)}


@router.post("/tasks/{task_id}/revoke")
@limiter.limit("20/minute")
def owner_revoke_task(
    request: Request,
    task_id: str,
    body: RevokeTaskRequest,
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> dict:
    if body.confirm != f"REVOKE {task_id}":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Confirmation must be 'REVOKE {task_id}'.",
        )
    try:
        celery_app.control.revoke(
            task_id,
            terminate=body.terminate,
            signal="SIGKILL" if body.terminate else None,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail=f"Celery revoke failed: {exc}") from exc
    _owner_audit(db, action="owner.task.revoke", actor=_resolve_actor(request),
                 target_id=task_id, metadata={"terminate": body.terminate, "reason": body.reason})
    db.commit()
    return {"ok": True, "task_id": task_id, "terminate": body.terminate}


class BroadcastRequest(BaseModel):
    title: str
    body: str | None = None
    category: str = "announcement"
    action_url: str | None = None
    tenant_ids: list[str] | None = None


@router.post("/broadcast", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
def owner_broadcast(
    request: Request,
    body: BroadcastRequest,
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> dict:
    if body.tenant_ids:
        user_ids = list(db.scalars(
            select(ProjectMembership.user_id)
            .where(ProjectMembership.project_id.in_(body.tenant_ids))
            .where(ProjectMembership.is_active.is_(True))
            .distinct()
        ).all())
    else:
        user_ids = list(db.scalars(
            select(User.id).where(User.is_active.is_(True))
        ).all())

    for uid in user_ids:
        db.add(Notification(
            user_id=uid,
            title=body.title,
            body=body.body,
            category=body.category,
            action_url=body.action_url,
            is_read=False,
        ))
    _owner_audit(db, action="owner.broadcast", actor=_resolve_actor(request),
                 target_id="all" if not body.tenant_ids else ",".join(body.tenant_ids),
                 metadata={"title": body.title, "recipient_count": len(user_ids),
                            "tenant_ids": body.tenant_ids})
    db.commit()
    return {"ok": True, "sent_to": len(user_ids), "title": body.title}


@router.get("/retention")
def owner_retention_config(
    _: None = Depends(require_provisioning_access),
) -> dict:
    s = get_settings()
    return {
        "call_retention_days": getattr(s, "CALL_RETENTION_DAYS", None),
        "diagnosis_retention_days": getattr(s, "DIAGNOSIS_RETENTION_DAYS", None),
        "audit_log_retention_days": getattr(s, "AUDIT_LOG_RETENTION_DAYS", None),
        "notification_retention_days": getattr(s, "NOTIFICATION_RETENTION_DAYS", None),
        "note": "Retention is enforced by scheduled purge tasks. Contact infrastructure team to modify.",
    }


__all__ = [name for name in globals() if not name.startswith("__")]
