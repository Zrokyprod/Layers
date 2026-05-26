from app.api.routes._internal.owner_common import *
from app.api.routes._internal.owner_pricing_audit import _owner_audit, _resolve_actor

_RATE_LIMIT_OVERRIDE_KEY = "zroky:owner:rate_limit_overrides"


class RateLimitConfig(BaseModel):
    ingest_soft_limit_rpm: int
    ingest_burst_limit_rpm: int
    ingest_rate_limit_window_seconds: int
    ingest_sustained_breach_threshold: int
    ingest_backpressure_ttl_seconds: int
    ingest_enforce_rate_limit: bool
    # Runtime overrides stored in Redis (None means "use env default")
    overrides: dict[str, Any]


@router.get("/rate-limits", response_model=RateLimitConfig)
def owner_get_rate_limits(
    _: None = Depends(require_provisioning_access),
) -> RateLimitConfig:
    s = get_settings()
    overrides: dict[str, Any] = {}
    if _redis_ok():
        try:
            raw = get_redis_client().get(_RATE_LIMIT_OVERRIDE_KEY)
            if raw:
                overrides = json.loads(raw)
        except Exception:
            pass
    return RateLimitConfig(
        ingest_soft_limit_rpm=overrides.get("ingest_soft_limit_rpm", s.INGEST_SOFT_LIMIT_RPM),
        ingest_burst_limit_rpm=overrides.get("ingest_burst_limit_rpm", s.INGEST_BURST_LIMIT_RPM),
        ingest_rate_limit_window_seconds=overrides.get(
            "ingest_rate_limit_window_seconds", s.INGEST_RATE_LIMIT_WINDOW_SECONDS
        ),
        ingest_sustained_breach_threshold=overrides.get(
            "ingest_sustained_breach_threshold", s.INGEST_SUSTAINED_BREACH_THRESHOLD
        ),
        ingest_backpressure_ttl_seconds=overrides.get(
            "ingest_backpressure_ttl_seconds", s.INGEST_BACKPRESSURE_TTL_SECONDS
        ),
        ingest_enforce_rate_limit=overrides.get("ingest_enforce_rate_limit", s.INGEST_ENFORCE_RATE_LIMIT),
        overrides=overrides,
    )


class RateLimitOverrideRequest(BaseModel):
    overrides: dict[str, Any]


@router.put("/rate-limits/overrides")
@limiter.limit("10/minute")
def owner_set_rate_limit_overrides(
    request: Request,
    body: RateLimitOverrideRequest,
    _: None = Depends(require_provisioning_access),
) -> dict:
    if not _redis_ok():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Redis unavailable")
    # Validate keys
    allowed_keys = {
        "ingest_soft_limit_rpm", "ingest_burst_limit_rpm", "ingest_rate_limit_window_seconds",
        "ingest_sustained_breach_threshold", "ingest_backpressure_ttl_seconds", "ingest_enforce_rate_limit",
    }
    bad_keys = set(body.overrides.keys()) - allowed_keys
    if bad_keys:
        raise HTTPException(status_code=400, detail=f"Unknown override keys: {bad_keys}")
    get_redis_client().set(_RATE_LIMIT_OVERRIDE_KEY, json.dumps(body.overrides))
    return {"ok": True, "overrides": body.overrides}


@router.delete("/rate-limits/overrides")
@limiter.limit("10/minute")
def owner_clear_rate_limit_overrides(
    request: Request,
    _: None = Depends(require_provisioning_access),
) -> dict:
    if _redis_ok():
        get_redis_client().delete(_RATE_LIMIT_OVERRIDE_KEY)
    return {"ok": True}


class AuditLogItem(BaseModel):
    id: str
    tenant_id: str
    diagnosis_id: str
    action: str
    actor_subject: str | None
    metadata_json: str
    created_at: datetime


class AuditLogResponse(BaseModel):
    entries: list[AuditLogItem]
    total: int


@router.get("/audit-log", response_model=AuditLogResponse)
def owner_audit_log(
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
    limit: int = 100,
    offset: int = 0,
    action: str | None = None,
    tenant_id: str | None = None,
) -> AuditLogResponse:
    q = select(AuditLog).order_by(AuditLog.created_at.desc())
    count_q = select(func.count()).select_from(AuditLog)
    if action:
        q = q.where(AuditLog.action == action)
        count_q = count_q.where(AuditLog.action == action)
    if tenant_id:
        q = q.where(AuditLog.tenant_id == tenant_id)
        count_q = count_q.where(AuditLog.tenant_id == tenant_id)
    total = db.scalar(count_q) or 0
    rows = db.execute(q.limit(limit).offset(offset)).scalars().all()
    return AuditLogResponse(
        entries=[
            AuditLogItem(
                id=e.id, tenant_id=e.tenant_id, diagnosis_id=e.diagnosis_id,
                action=e.action, actor_subject=e.actor_subject,
                metadata_json=e.metadata_json, created_at=e.created_at,
            )
            for e in rows
        ],
        total=total,
    )


class PlatformLlmUsageItem(BaseModel):
    id: str
    purpose: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    latency_ms: float | None
    tenant_id: str | None
    diagnosis_id: str | None
    created_at: datetime


class PlatformLlmUsageSummaryResponse(BaseModel):
    total_calls: int
    total_cost_usd: float
    total_tokens: int
    avg_latency_ms: float
    by_purpose: dict[str, dict[str, Any]]
    by_model: dict[str, dict[str, Any]]
    recent: list[PlatformLlmUsageItem]


@router.get("/platform-llm-usage", response_model=PlatformLlmUsageSummaryResponse)
def owner_platform_llm_usage(
    _: None = Depends(require_provisioning_access),
    db: Session = Depends(get_db_session),
    limit: int = 100,
) -> PlatformLlmUsageSummaryResponse:
    """Summarize ZROKY's own LLM usage (fix generation, assistant, analytics, etc.)."""
    total_calls = db.scalar(select(func.count()).select_from(PlatformLlmUsage)) or 0
    total_cost = db.scalar(select(func.sum(PlatformLlmUsage.cost_usd))) or 0.0
    total_tokens = db.scalar(select(func.sum(PlatformLlmUsage.total_tokens))) or 0
    avg_latency = db.scalar(select(func.avg(PlatformLlmUsage.latency_ms))) or 0.0

    # Purpose breakdown
    by_purpose: dict[str, dict[str, Any]] = {}
    purpose_rows = db.execute(
        select(PlatformLlmUsage.purpose, func.count(), func.sum(PlatformLlmUsage.cost_usd), func.sum(PlatformLlmUsage.total_tokens))
        .group_by(PlatformLlmUsage.purpose)
    ).all()
    for purpose, calls, cost, tokens in purpose_rows:
        by_purpose[purpose] = {
            "calls": int(calls or 0),
            "cost_usd": float(cost or 0.0),
            "tokens": int(tokens or 0),
        }

    # Model breakdown
    by_model: dict[str, dict[str, Any]] = {}
    model_rows = db.execute(
        select(PlatformLlmUsage.model, func.count(), func.sum(PlatformLlmUsage.cost_usd), func.sum(PlatformLlmUsage.total_tokens))
        .group_by(PlatformLlmUsage.model)
    ).all()
    for model, calls, cost, tokens in model_rows:
        by_model[model or "unknown"] = {
            "calls": int(calls or 0),
            "cost_usd": float(cost or 0.0),
            "tokens": int(tokens or 0),
        }

    recent_rows = db.execute(
        select(PlatformLlmUsage).order_by(PlatformLlmUsage.created_at.desc()).limit(limit)
    ).scalars().all()

    return PlatformLlmUsageSummaryResponse(
        total_calls=int(total_calls),
        total_cost_usd=float(total_cost),
        total_tokens=int(total_tokens),
        avg_latency_ms=float(avg_latency),
        by_purpose=by_purpose,
        by_model=by_model,
        recent=[
            PlatformLlmUsageItem(
                id=r.id,
                purpose=r.purpose,
                provider=r.provider,
                model=r.model,
                prompt_tokens=r.prompt_tokens,
                completion_tokens=r.completion_tokens,
                total_tokens=r.total_tokens,
                cost_usd=float(r.cost_usd),
                latency_ms=r.latency_ms,
                tenant_id=r.tenant_id,
                diagnosis_id=r.diagnosis_id,
                created_at=r.created_at,
            )
            for r in recent_rows
        ],
    )


__all__ = [name for name in globals() if not name.startswith("__")]
