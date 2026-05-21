"""
GET /v1/detectors — introspect the live detector plugin registry.

Returns the detectors that are actually loaded at runtime (via entry points
or built-in fallback), enriched with static metadata (failure_code, speed
class, confidence threshold, human-readable description).

This powers the /issues → Rules tab in the dashboard so it is always
truthful about what is running, rather than a hardcoded list.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.api.dependencies.tenant import require_tenant_id
from app.core.limiter import limiter
from app.services.detectors._registry import load_detectors

router = APIRouter(prefix="/v1/detectors")

# ── Static enrichment table ────────────────────────────────────────────────────
# Keyed by the entry-point / registry name.  Mirrors the constants in each
# detector module so the API can surface them without importing the modules.

_METADATA: dict[str, dict] = {
    "token_overflow": {
        "failure_code": "TOKEN_OVERFLOW",
        "label": "Token Overflow",
        "speed_class": "fast",
        "confidence_threshold": 0.98,
        "description": (
            "Fires when prompt_tokens exceeds the model context limit, "
            "or a token-count estimate crosses 90% of the limit."
        ),
    },
    "rate_limit": {
        "failure_code": "RATE_LIMIT",
        "label": "Rate Limit",
        "speed_class": "fast",
        "confidence_threshold": 0.95,
        "description": (
            "Detects HTTP 429 responses or error codes containing rate_limit / "
            "quota / too_many_requests signals."
        ),
    },
    "auth_failure": {
        "failure_code": "AUTH_FAILURE",
        "label": "Auth Failure",
        "speed_class": "fast",
        "confidence_threshold": 0.99,
        "description": (
            "Fires on HTTP 401/403 or error codes containing invalid_api_key / "
            "unauthorized / expired_key. Highest-confidence detector."
        ),
    },
    "provider_error": {
        "failure_code": "PROVIDER_ERROR",
        "label": "Provider Error",
        "speed_class": "fast",
        "confidence_threshold": 0.82,
        "description": (
            "Fallback detector for all 5xx, timeout, network, and content-filter "
            "provider errors not covered by a more specific rule."
        ),
    },
    "loop_detected": {
        "failure_code": "LOOP_DETECTED",
        "label": "Loop Detected",
        "speed_class": "pattern",
        "confidence_threshold": 0.65,
        "description": (
            "Multi-signal pattern rule combining prompt-repeat, output-similarity, "
            "tool-cycle, and retry patterns. Fires when composite loop score ≥ 0.65."
        ),
    },
    "cost_spike": {
        "failure_code": "COST_SPIKE",
        "label": "Cost Spike",
        "speed_class": "pattern",
        "confidence_threshold": 0.90,
        "description": (
            "15-minute spend exceeds max(3× baseline, baseline + $25 USD). "
            "Requires at least 3 days / 200 calls of warmup data."
        ),
    },
}


class DetectorInfo(BaseModel):
    name: str
    failure_code: str
    label: str
    speed_class: str
    confidence_threshold: float
    description: str
    loaded: bool


class DetectorListResponse(BaseModel):
    count: int
    items: list[DetectorInfo]


@router.get("", response_model=DetectorListResponse)
@limiter.limit("60/minute")
def list_detectors(
    request: Request,
    _tenant_id: str = Depends(require_tenant_id),
) -> DetectorListResponse:
    """Return the detectors that are live in this deployment."""
    loaded_names = set(load_detectors().keys())

    items: list[DetectorInfo] = []
    seen: set[str] = set()

    for name, meta in _METADATA.items():
        seen.add(name)
        items.append(DetectorInfo(
            name=name,
            failure_code=meta["failure_code"],
            label=meta["label"],
            speed_class=meta["speed_class"],
            confidence_threshold=meta["confidence_threshold"],
            description=meta["description"],
            loaded=name in loaded_names,
        ))

    for name in loaded_names - seen:
        items.append(DetectorInfo(
            name=name,
            failure_code=name.upper(),
            label=name.replace("_", " ").title(),
            speed_class="unknown",
            confidence_threshold=0.0,
            description="Third-party detector loaded via entry-point plugin.",
            loaded=True,
        ))

    items.sort(key=lambda x: (x.speed_class != "fast", x.name))

    return DetectorListResponse(count=len(items), items=items)
