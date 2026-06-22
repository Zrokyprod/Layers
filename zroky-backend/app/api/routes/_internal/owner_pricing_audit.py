from app.api.routes._internal.owner_common import *
from app.services.owner_audit import create_owner_audit_event, resolve_owner_actor
from app.services.entitlement_catalog import (
    CANONICAL_PLAN_CODES,
    PLAN_ALIASES,
    PLAN_CATALOG,
    PRICING_CONTRACT_PATH,
    UNLIMITED,
    load_pricing_contract,
)

_DEFAULT_PRICING_PATH = Path(__file__).resolve().parents[4] / "pricing_config.json"

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


class PricingPlansResponse(BaseModel):
    schema_version: str
    source_of_truth: str
    currency: str
    unlimited: int
    canonical_plan_order: list[str]
    aliases: dict[str, str]
    plans: list[dict[str, Any]]
    drift: list[str]


def _pricing_contract_drift(contract: dict[str, Any]) -> list[str]:
    drift: list[str] = []
    order = [str(code) for code in contract.get("canonical_plan_order", [])]
    if tuple(order) != CANONICAL_PLAN_CODES:
        drift.append("canonical_plan_order")
    if contract.get("aliases") != PLAN_ALIASES:
        drift.append("aliases")

    plans = contract.get("plans")
    if not isinstance(plans, list):
        return [*drift, "plans"]

    plan_codes = [str(plan.get("code", "")) for plan in plans if isinstance(plan, dict)]
    if tuple(plan_codes) != CANONICAL_PLAN_CODES:
        drift.append("plans.order")

    for raw_plan in plans:
        if not isinstance(raw_plan, dict):
            drift.append("plans.entry")
            continue
        code = str(raw_plan.get("code") or "")
        entry = PLAN_CATALOG.get(code)
        if entry is None:
            drift.append(f"{code or 'unknown'}.code")
            continue
        enforcement = raw_plan.get("enforcement")
        pricing = raw_plan.get("pricing")
        if not isinstance(enforcement, dict) or not isinstance(pricing, dict):
            drift.append(f"{code}.shape")
            continue
        if enforcement.get("limits") != entry.limits:
            drift.append(f"{code}.limits")
        if enforcement.get("entitlements") != entry.entitlements:
            drift.append(f"{code}.entitlements")
        if enforcement.get("compatibility") != entry.compatibility:
            drift.append(f"{code}.compatibility")

        expected_pricing = {
            "calls_per_month": entry.limits["max_calls_per_month"],
            "retention_days": entry.limits["retention_days"],
            "replay_credits": entry.compatibility["replay.monthly_runs"],
            "golden_traces": entry.limits["max_golden_traces"],
            "golden_sets": entry.compatibility["goldens.max_sets"],
            "non_blocking_ci": entry.entitlements["pro.ci_gate_nonblocking"],
            "blocking_ci": entry.entitlements["pro.ci_gate_blocking"],
            "provider_key_vault": entry.entitlements["enterprise.provider_key_vault"],
        }
        for key, expected in expected_pricing.items():
            if pricing.get(key) != expected:
                drift.append(f"{code}.pricing.{key}")
    return drift


@router.get("/pricing/plans", response_model=PricingPlansResponse)
def owner_get_pricing_plans(
    _: None = Depends(require_provisioning_access),
) -> PricingPlansResponse:
    try:
        contract = load_pricing_contract()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read pricing plan contract: {exc}")

    return PricingPlansResponse(
        schema_version=str(contract.get("schema_version", "")),
        source_of_truth=str(contract.get("source_of_truth") or PRICING_CONTRACT_PATH),
        currency=str(contract.get("currency", "USD")),
        unlimited=int(contract.get("unlimited", UNLIMITED)),
        canonical_plan_order=[str(code) for code in contract.get("canonical_plan_order", [])],
        aliases={str(k): str(v) for k, v in dict(contract.get("aliases", {})).items()},
        plans=[dict(plan) for plan in contract.get("plans", []) if isinstance(plan, dict)],
        drift=_pricing_contract_drift(contract),
    )


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
    db: Session = Depends(get_db_session),
) -> PricingConfigResponse:
    if not _redis_ok():
        raise HTTPException(status_code=503, detail="Redis unavailable — cannot persist pricing config")
    try:
        raw_previous = get_redis_client().get(_PRICING_CONFIG_KEY)
        previous_exists = bool(raw_previous)
        get_redis_client().set(_PRICING_CONFIG_KEY, json.dumps(body.config, indent=2))
        _owner_audit(
            db,
            action="owner.pricing.update",
            actor=_resolve_actor(request),
            target_id="pricing_config",
            metadata={
                "previous_exists": previous_exists,
                "config_keys": sorted(str(key) for key in body.config.keys()),
            },
        )
        db.commit()
        return PricingConfigResponse(config=body.config, path="redis", exists=True)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to write pricing config: {exc}")


def _resolve_actor(request: Request) -> str:
    return resolve_owner_actor(request)


def _owner_audit(
    db: Session,
    *,
    action: str,
    actor: str,
    target_id: str,
    metadata: dict[str, Any],
) -> None:
    create_owner_audit_event(
        db,
        action=action,
        actor=actor,
        target_id=target_id,
        metadata=metadata,
    )


__all__ = [name for name in globals() if not name.startswith("__")]
