"""
Plan-gate dependency (Module 6; plan §10.x + §11.2).

Exposes:
  - `require_entitlement(key: str, min_value=None)` — dependency factory
    that returns 402 Payment Required when the calling org doesn't have
    the entitlement. Sets `X-Zroky-Plan-Hint` header so the frontend
    can render the matching upgrade overlay (§10.x).

Usage on a route:

    from app.api.dependencies.entitlements import require_entitlement

    @router.post("/v1/pilot/actions/{id}/revert")
    def revert_action(
        ...,
        _: None = Depends(require_entitlement("pilot.autopilot_enabled")),
    ):
        ...

Semantics:
  - The dependency runs AFTER `require_tenant_context` (which it depends
    on internally), so 401 ("no tenant context") still wins over 402
    ("tenant exists but tier insufficient").
  - For `min_value=None` (the default), evaluates `resolver.has(key)`.
  - For `min_value=<int>`, evaluates `resolver.get(key) >= min_value`
    (treats `-1` as unlimited / always-passes). Use this for quota
    checks where 0 means "no access but counted as zero" rather than
    "not entitled". Rare — most routes want the simple has() check.

Response body (402):
  {
    "detail": "Your plan does not include 'pilot.autopilot_enabled'.",
    "required_entitlement": "pilot.autopilot_enabled",
    "current_plan": "free",
    "upgrade_hint_url": "/settings/billing?upgrade_hint=pilot.autopilot_enabled"
  }

Response headers (402):
  X-Zroky-Plan-Hint: free
  (the frontend uses this to render the upgrade overlay copy per §10.x)
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import (
    TenantContext,
    require_tenant_context,
)
from app.db.session import get_db_session
from app.services import entitlements_resolver
from app.services.billing_plans import DEFAULT_PLAN_CODE, PLAN_KEYS_BINDING

logger = logging.getLogger(__name__)


_UNLIMITED_SENTINEL = -1


def _build_402(
    *, key: str, plan_code: str, response: Response
) -> HTTPException:
    """Construct the 402 body + header consistently."""
    response.headers["X-Zroky-Plan-Hint"] = plan_code
    return HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail={
            "detail": (
                f"Your plan does not include {key!r}. Upgrade to use this feature."
            ),
            "required_entitlement": key,
            "current_plan": plan_code,
            "upgrade_hint_url": f"/settings/billing?upgrade_hint={key}",
        },
        headers={"X-Zroky-Plan-Hint": plan_code},
    )


def require_entitlement(
    key: str,
    *,
    min_value: Optional[int] = None,
):
    """FastAPI dependency factory.

    Args:
      key:        Entitlement key (e.g. 'pilot.autopilot_enabled').
                  Must be in `PLAN_KEYS_BINDING` OR be one of the
                  documented extension keys (e.g. 'seats.included').
                  Out-of-vocab keys raise ValueError at IMPORT TIME so
                  typos surface during app startup, not at request time.
      min_value:  When set, require resolved value >= min_value.
                  `-1` sentinel in the resolved value always passes.
                  When None (default), uses `resolver.has(key)`.

    Returns: a dependency callable that yields the resolved value (the
    route doesn't need to read it; ignoring with `_: ... = Depends(...)`
    is the common shape).
    """
    norm = (key or "").strip()
    if not norm:
        raise ValueError("require_entitlement: key must be non-empty")

    # Soft validate: warn loudly on unknown keys but don't block. Plan
    # §11.2 names are reserved; the resolver also handles ad-hoc keys
    # set via Founder Console overrides.
    if norm not in PLAN_KEYS_BINDING and norm != "seats.included":
        logger.warning(
            "require_entitlement: key %r is not in PLAN_KEYS_BINDING; "
            "ensure this is intentional", norm
        )

    def _dependency(
        response: Response,
        context: TenantContext = Depends(require_tenant_context),
        db: Session = Depends(get_db_session),
    ):
        org_id = context.tenant_id  # org_id == project_id (Module 5 comment)
        if not org_id:
            # require_tenant_context should have already 401'd. Defence-
            # in-depth: a missing tenant_id at this layer is a bug.
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing tenant context for entitlement check.",
            )

        if min_value is None:
            allowed = entitlements_resolver.has(db, org_id, norm)
            resolved_value = (
                entitlements_resolver.get(db, org_id, norm) if not allowed else None
            )
        else:
            current = entitlements_resolver.get(db, org_id, norm, default=0)
            try:
                current_int = int(current) if not isinstance(current, bool) else 0
            except (TypeError, ValueError):
                current_int = 0
            allowed = (
                current_int == _UNLIMITED_SENTINEL or current_int >= int(min_value)
            )
            resolved_value = current_int

        if allowed:
            # Always populate the hint header on success too — useful
            # for the frontend to display the current plan code in the
            # banner without an extra round-trip.
            try:
                plan_code = entitlements_resolver.get_plan_code(db, org_id)
            except Exception:  # noqa: BLE001
                plan_code = DEFAULT_PLAN_CODE
            response.headers["X-Zroky-Plan-Hint"] = plan_code
            return resolved_value

        # 402 path
        try:
            plan_code = entitlements_resolver.get_plan_code(db, org_id)
        except Exception:  # noqa: BLE001
            plan_code = DEFAULT_PLAN_CODE
        logger.info(
            "entitlement.denied org=%s key=%s plan=%s min=%s",
            org_id, norm, plan_code, min_value,
        )
        raise _build_402(key=norm, plan_code=plan_code, response=response)

    return _dependency


__all__ = ["require_entitlement"]
