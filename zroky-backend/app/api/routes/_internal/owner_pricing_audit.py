from app.api.routes._internal.owner_common import *

def _pricing_config_path() -> Path:
    env_path = os.environ.get("PRICING_CONFIG_PATH", "")
    if env_path:
        return Path(env_path)
    return _DEFAULT_PRICING_PATH


_PRICING_CONFIG_KEY = "zroky:owner:pricing_config"


class PricingConfigResponse(BaseModel):
    config: dict[str, Any]
    path: str
    exists: bool


@router.get("/pricing", response_model=PricingConfigResponse)
def owner_get_pricing(
    _: None = Depends(require_provisioning_access),
) -> PricingConfigResponse:
    if _redis_ok():
        try:
            raw = get_redis_client().get(_PRICING_CONFIG_KEY)
            if raw:
                return PricingConfigResponse(config=json.loads(raw), path="redis", exists=True)
        except Exception:
            pass
    # Filesystem fallback (migrate to Redis on first read)
    p = _pricing_config_path()
    if not p.exists():
        return PricingConfigResponse(config={}, path=str(p), exists=False)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if _redis_ok():
            try:
                get_redis_client().set(_PRICING_CONFIG_KEY, json.dumps(data))
            except Exception:
                pass
        return PricingConfigResponse(config=data, path=str(p), exists=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read pricing config: {exc}")


class PricingConfigUpdateRequest(BaseModel):
    config: dict[str, Any]


@router.put("/pricing", response_model=PricingConfigResponse)
@limiter.limit("10/minute")
def owner_update_pricing(
    request: Request,
    body: PricingConfigUpdateRequest,
    _: None = Depends(require_provisioning_access),
) -> PricingConfigResponse:
    if not _redis_ok():
        raise HTTPException(status_code=503, detail="Redis unavailable — cannot persist pricing config")
    try:
        get_redis_client().set(_PRICING_CONFIG_KEY, json.dumps(body.config, indent=2))
        return PricingConfigResponse(config=body.config, path="redis", exists=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to write pricing config: {exc}")


def _resolve_actor(request: Request) -> str:
    from app.auth.identity import build_identity_context, decode_jwt_claims, extract_bearer_token
    token = extract_bearer_token(request)
    if token:
        try:
            ctx = build_identity_context(decode_jwt_claims(token))
            if ctx.subject:
                return ctx.subject
        except Exception:
            pass
    return "provisioning_token"


def _owner_audit(
    db: Session,
    *,
    action: str,
    actor: str,
    target_id: str,
    metadata: dict[str, Any],
) -> None:
    db.add(AuditLog(
        tenant_id="PLATFORM",
        diagnosis_id="owner_action",
        action=action,
        actor_subject=actor,
        metadata_json=json.dumps({"target_id": target_id, **metadata}, default=str),
    ))


__all__ = [name for name in globals() if not name.startswith("__")]
