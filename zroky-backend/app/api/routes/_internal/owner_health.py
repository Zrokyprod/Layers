from app.api.routes._internal.owner_common import *
from app.api.routes._internal.owner_pricing_audit import _owner_audit, _resolve_actor

@router.get("/health", response_model=HealthResponse)
def owner_health(
    _: None = Depends(require_provisioning_access),
) -> HealthResponse:
    services: list[ServiceStatus] = []
    overall = "ok"

    # Database
    t0 = time.perf_counter()
    db_ok = db_healthcheck()
    db_latency = round((time.perf_counter() - t0) * 1000, 1)
    services.append(ServiceStatus(
        name="PostgreSQL",
        status="ok" if db_ok else "down",
        latency_ms=db_latency,
        detail=None if db_ok else "Ping failed",
    ))
    if not db_ok:
        overall = "degraded"

    # Redis
    t0 = time.perf_counter()
    redis_ok = _redis_ok()
    redis_latency = round((time.perf_counter() - t0) * 1000, 1)
    services.append(ServiceStatus(
        name="Redis",
        status="ok" if redis_ok else "down",
        latency_ms=redis_latency,
        detail=None if redis_ok else "Ping failed",
    ))
    if not redis_ok:
        overall = "degraded"

    # Celery workers
    try:
        inspect = celery_app.control.inspect(timeout=2)
        active = inspect.active() or {}
        worker_count = len(active)
        worker_status = "ok" if worker_count > 0 else "down"
        worker_detail = f"{worker_count} worker(s) active" if worker_count > 0 else "No workers responding"
    except Exception as exc:
        worker_status = "unknown"
        worker_detail = str(exc)[:80]
        worker_count = 0
    services.append(ServiceStatus(name="Celery", status=worker_status, detail=worker_detail))
    if worker_status in ("down", "unknown"):
        overall = "degraded"

    # Exchange rate
    exchange_snap = get_exchange_rate_debug_snapshot()
    er_usable = exchange_snap.get("cache_is_usable", False)
    er_stale = exchange_snap.get("cache_is_stale", True)
    er_status = "ok" if er_usable else ("degraded" if not er_stale else "down")
    er_age = exchange_snap.get("cache_age_seconds")
    services.append(ServiceStatus(
        name="Exchange Rate",
        status=er_status,
        detail=f"Age: {er_age}s" if er_age is not None else "No cache",
    ))
    if er_status != "ok":
        overall = "degraded"

    # Maintenance mode
    maintenance = False
    if redis_ok:
        try:
            raw = get_redis_client().get(_MAINTENANCE_KEY)
            if raw:
                data = json.loads(raw)
                maintenance = bool(data.get("enabled", False))
        except Exception:
            pass

    return HealthResponse(
        overall=overall,
        services=services,
        exchange_rate=exchange_snap,
        maintenance_mode=maintenance,
        checked_at=datetime.now(UTC),
    )


@router.post("/maintenance", response_model=MaintenanceModeResponse)
@limiter.limit("10/minute")
def set_maintenance_mode(
    request: Request,
    body: MaintenanceModeRequest,
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> MaintenanceModeResponse:
    if not _redis_ok():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Redis unavailable")
    payload = json.dumps({"enabled": body.enabled, "message": body.message})
    get_redis_client().set(_MAINTENANCE_KEY, payload)
    _owner_audit(
        db,
        action="owner.maintenance.set",
        actor=_resolve_actor(request),
        target_id="maintenance_mode",
        metadata={"enabled": body.enabled, "message_present": bool(body.message)},
    )
    db.commit()
    return MaintenanceModeResponse(enabled=body.enabled, message=body.message)


@router.get("/infra", response_model=InfraStatsResponse)
def owner_infra(
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
) -> InfraStatsResponse:
    # Celery workers
    try:
        inspect = celery_app.control.inspect(timeout=2)
        active = inspect.active() or {}
        worker_count = len(active)
        worker_names = list(active.keys())
    except Exception:
        worker_count = 0
        worker_names = []

    # Queue depths (Redis-based)
    queues: list[QueueStats] = []
    if _redis_ok():
        r = get_redis_client()
        for q_name in ("diagnosis_fast", "diagnosis_pattern", "celery"):
            try:
                pending = r.llen(q_name) or 0
            except Exception:
                pending = 0
            # Failed tasks in Redis (result backend stores them with status FAILURE)
            # Failed-task counts require Celery Flower or result-backend scanning;
            # setting to 0 here to avoid misleading data from inspect.reserved().
            queues.append(QueueStats(queue_name=q_name, pending=pending, failed=0))

    # DB table row counts (fast — uses pg stats when available)
    table_names = ["calls", "users", "projects", "api_keys", "project_memberships",
                   "diagnosis_jobs", "audit_logs", "project_alerts"]
    db_table_sizes: dict[str, int] = {}
    for table in table_names:
        try:
            count = db.scalar(text(f"SELECT COUNT(*) FROM {table}")) or 0
            db_table_sizes[table] = int(count)
        except Exception:
            db_table_sizes[table] = -1

    return InfraStatsResponse(
        queues=queues,
        worker_count=worker_count,
        worker_names=worker_names,
        db_table_sizes=db_table_sizes,
    )


__all__ = [name for name in globals() if not name.startswith("__")]
