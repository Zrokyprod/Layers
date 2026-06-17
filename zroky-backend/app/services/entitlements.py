"""
Entitlements service — write surface (Module 5; plan §11.2).

Module 5 ships only the WRITE side:
  - `seed_plan_entitlements(db, org_id, plan_code)` overwrites all
    `source='plan'` rows for an org with the canonical template from
    `services.billing_plans.PLAN_ENTITLEMENTS`. Called from
    billing provider sync whenever a subscription becomes active /
    is updated to a new plan.
  - `clear_plan_entitlements(db, org_id)` drops the plan-source rows
    when a subscription is canceled (the org falls back to whatever
    'override' or 'trial' rows still exist; if none, Module 6's
    resolver returns the zero-value for any key).
  - `set_trial_entitlements(db, org_id, plan_code, expires_at)` writes
    a trial overlay (source='trial'). Called when a subscription
    enters `trialing` status.
  - `clear_trial_entitlements(db, org_id)` drops trial rows when the
    trial ends (subscription becomes active or canceled).
  - `set_override_entitlement(db, org_id, key, value, expires_at=None)`
    writes a single founder-console override row (source='override').
    Module 5 doesn't expose a route for this — it's the API the
    founder console (Module 11) will call.
  - `list_entitlements(db, org_id)` returns raw ORM rows for a tenant
    (debug/audit; not the resolver).

The READ-side resolver with override>trial>plan precedence + Redis
cache lives in Module 6. Module 5 only ensures the rows exist with the
right values when subscription state changes.

JSON encoding contract:
  `value_json` stores a single JSON value (scalar/array/object).
  Writers always serialise via `json.dumps(value, separators=(",",":"))`
  for byte-stable storage. Readers parse defensively.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import Entitlement
from app.services.billing_plans import (
    PLAN_ENTITLEMENTS,
    InvalidPlanCodeError,
    normalize_plan_code,
)

logger = logging.getLogger(__name__)


VALID_SOURCES: frozenset[str] = frozenset({"plan", "trial", "override"})


def _invalidate_resolver_cache(org_id: str) -> None:
    """Drop the merged-entitlement cache for `org_id` after every
    successful commit. Local import inside the function avoids a
    circular dependency: `entitlements_resolver.py` imports
    `parse_entitlement_value` from this module at module-load time.

    Best-effort: a cache invalidation failure is logged but does NOT
    fail the write — the 60s TTL is the safety net.
    """
    try:
        from app.services.entitlements_resolver import invalidate
        invalidate(org_id)
    except Exception:  # noqa: BLE001 — never propagate from cache hook
        logger.exception(
            "entitlements.cache_invalidate_failed org=%s", org_id
        )


# ── helpers ─────────────────────────────────────────────────────────────────


def _encode_value(value: Any) -> str:
    """Stable JSON encoding for entitlement values. Sorted keys so
    the same dict always serialises to the same bytes."""
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def parse_entitlement_value(raw: str | None) -> Any:
    """Defensive parse of `value_json`. Returns None on missing /
    malformed — callers decide if that's a fatal config bug or just
    'feature off'. Module 6 will use this in the resolver."""
    if raw is None:
        return None
    text = raw.strip() if isinstance(raw, str) else ""
    if not text:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── upsert primitive ────────────────────────────────────────────────────────


def upsert_entitlement(
    db: Session,
    *,
    org_id: str,
    key: str,
    value: Any,
    source: str,
    expires_at: datetime | None = None,
    commit: bool = True,
) -> Entitlement:
    """INSERT-or-UPDATE one entitlement row keyed on (org_id, key, source).

    Mirrors the `ux_entitlements_org_key_source` UNIQUE constraint —
    you can have a 'plan' AND a 'trial' AND an 'override' row for the
    same key, and the resolver picks the highest-precedence one.

    Raises ValueError on bad source.
    """
    if source not in VALID_SOURCES:
        raise ValueError(
            f"source {source!r} must be one of: {sorted(VALID_SOURCES)}"
        )

    encoded = _encode_value(value)
    existing = db.execute(
        select(Entitlement).where(
            Entitlement.org_id == org_id,
            Entitlement.key == key,
            Entitlement.source == source,
        )
    ).scalar_one_or_none()

    if existing is None:
        row = Entitlement(
            id=str(uuid4()),
            org_id=org_id,
            key=key,
            value_json=encoded,
            source=source,
            expires_at=expires_at,
        )
        db.add(row)
    else:
        existing.value_json = encoded
        existing.expires_at = expires_at
        db.add(existing)
        row = existing

    if commit:
        db.commit()
        db.refresh(row)
        _invalidate_resolver_cache(org_id)
    return row


# ── plan-source bulk seed ───────────────────────────────────────────────────


def seed_plan_entitlements(
    db: Session,
    *,
    org_id: str,
    plan_code: str,
    commit: bool = True,
) -> list[Entitlement]:
    """Replace ALL `source='plan'` rows for `org_id` with the canonical
    template from `PLAN_ENTITLEMENTS[plan_code]`.

    Strategy: delete-then-insert in a single transaction. The unique
    constraint (org_id, key, 'plan') means at most one row per key
    pre-exists, so the delete is bounded by the template size.

    Raises InvalidPlanCodeError on out-of-vocab plan_code.
    Returns the list of newly-inserted rows.
    """
    plan_norm = normalize_plan_code(plan_code)  # raises InvalidPlanCodeError
    template = PLAN_ENTITLEMENTS[plan_norm]

    db.execute(
        delete(Entitlement).where(
            Entitlement.org_id == org_id,
            Entitlement.source == "plan",
        )
    )

    rows: list[Entitlement] = []
    for key, value in template.items():
        row = Entitlement(
            id=str(uuid4()),
            org_id=org_id,
            key=key,
            value_json=_encode_value(value),
            source="plan",
            expires_at=None,  # plan rows never expire (replaced on plan change)
        )
        db.add(row)
        rows.append(row)

    if commit:
        db.commit()
        for row in rows:
            db.refresh(row)
        _invalidate_resolver_cache(org_id)
    logger.info(
        "entitlements.plan_seeded org=%s plan=%s keys=%d",
        org_id, plan_norm, len(rows),
    )
    return rows


def clear_plan_entitlements(
    db: Session, *, org_id: str, commit: bool = True
) -> int:
    """Remove all `source='plan'` rows for `org_id`. Used when a
    subscription is canceled and the org has no replacement plan."""
    result = db.execute(
        delete(Entitlement).where(
            Entitlement.org_id == org_id,
            Entitlement.source == "plan",
        )
    )
    deleted = int(result.rowcount or 0)
    if commit:
        db.commit()
        _invalidate_resolver_cache(org_id)
    logger.info(
        "entitlements.plan_cleared org=%s deleted=%d", org_id, deleted
    )
    return deleted


# ── trial overlay ───────────────────────────────────────────────────────────


def set_trial_entitlements(
    db: Session,
    *,
    org_id: str,
    plan_code: str,
    expires_at: datetime,
    commit: bool = True,
) -> list[Entitlement]:
    """Write the entire entitlement template under source='trial' with
    `expires_at = trial_end`. Module 6's resolver will return these
    overlays until expiry, then fall back to the (likely 'free' or
    absent) plan rows.
    """
    plan_norm = normalize_plan_code(plan_code)
    template = PLAN_ENTITLEMENTS[plan_norm]

    # delete-then-insert for cleanliness
    db.execute(
        delete(Entitlement).where(
            Entitlement.org_id == org_id,
            Entitlement.source == "trial",
        )
    )

    rows: list[Entitlement] = []
    for key, value in template.items():
        row = Entitlement(
            id=str(uuid4()),
            org_id=org_id,
            key=key,
            value_json=_encode_value(value),
            source="trial",
            expires_at=expires_at,
        )
        db.add(row)
        rows.append(row)

    if commit:
        db.commit()
        for row in rows:
            db.refresh(row)
        _invalidate_resolver_cache(org_id)
    logger.info(
        "entitlements.trial_set org=%s plan=%s expires=%s keys=%d",
        org_id, plan_norm, expires_at.isoformat(), len(rows),
    )
    return rows


def clear_trial_entitlements(
    db: Session, *, org_id: str, commit: bool = True
) -> int:
    result = db.execute(
        delete(Entitlement).where(
            Entitlement.org_id == org_id,
            Entitlement.source == "trial",
        )
    )
    deleted = int(result.rowcount or 0)
    if commit:
        db.commit()
        _invalidate_resolver_cache(org_id)
    logger.info(
        "entitlements.trial_cleared org=%s deleted=%d", org_id, deleted
    )
    return deleted


# ── override (founder console hook) ─────────────────────────────────────────


def set_override_entitlement(
    db: Session,
    *,
    org_id: str,
    key: str,
    value: Any,
    expires_at: datetime | None = None,
    commit: bool = True,
) -> Entitlement:
    """Write a single founder-console override row. Highest precedence
    in the resolver (override > trial > plan)."""
    return upsert_entitlement(
        db,
        org_id=org_id,
        key=key,
        value=value,
        source="override",
        expires_at=expires_at,
        commit=commit,
    )


def clear_override_entitlement(
    db: Session,
    *,
    org_id: str,
    key: str,
    commit: bool = True,
) -> bool:
    result = db.execute(
        delete(Entitlement).where(
            Entitlement.org_id == org_id,
            Entitlement.key == key,
            Entitlement.source == "override",
        )
    )
    deleted = int(result.rowcount or 0) > 0
    if commit:
        db.commit()
        _invalidate_resolver_cache(org_id)
    return deleted


# ── reads (debug / audit) ───────────────────────────────────────────────────


def list_entitlements(
    db: Session, *, org_id: str
) -> list[Entitlement]:
    """Return raw rows for an org, ordered by (key, source).
    Module 6's resolver is what callers should use for plan-gate
    decisions; this is for the founder-console audit page."""
    rows = db.execute(
        select(Entitlement)
        .where(Entitlement.org_id == org_id)
        .order_by(Entitlement.key.asc(), Entitlement.source.asc())
    ).scalars().all()
    return list(rows)


__all__ = [
    "VALID_SOURCES",
    "parse_entitlement_value",
    "upsert_entitlement",
    "seed_plan_entitlements",
    "clear_plan_entitlements",
    "set_trial_entitlements",
    "clear_trial_entitlements",
    "set_override_entitlement",
    "clear_override_entitlement",
    "list_entitlements",
    "InvalidPlanCodeError",  # re-exported for convenience
]
