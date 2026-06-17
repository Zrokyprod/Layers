"""
Entitlements RESOLVER — read surface (Module 6; plan §11.2).

Sister module to `services/entitlements.py` (Module 5 write surface):
  - entitlements.py:           seed_plan / set_trial / set_override / clear_*
  - entitlements_resolver.py:  has() / get() / resolve_all() / invalidate()

Resolution algorithm (per plan §11.2):
  1. Load all `entitlements` rows for `org_id`.
  2. Drop rows whose `expires_at` is in the past (resolver-side, not SQL —
     keeps cache invalidation simple and avoids one INDEX walk).
  3. Group by `key`; for each key, pick the highest-precedence source:
        override > trial > plan
  4. For keys NOT present in any source row, fall back to the canonical
     template `PLAN_ENTITLEMENTS[subscription.plan_code]`.
  5. If no `subscriptions` row exists for `org_id` (brand new org with
     no billing row yet), fall back to `PLAN_ENTITLEMENTS["free"]`.
     This is the safe default — every endpoint's plan-gate evaluates
     against free-tier entitlements until billing infrastructure has
     written rows.

Caching (plan §11.2: O(1), Redis, 60s TTL):
  - Cache key:  `zroky:entitlements:v1:{org_id}`
  - Cache value: JSON of the FULLY-RESOLVED merged dict
  - TTL:        `Settings.ENTITLEMENT_CACHE_TTL_SECONDS` (default 60)
  - Hit:        return cached dict
  - Miss:       resolve from DB, write to cache, return
  - Redis down: fall through to in-process memory cache, then DB. The
                memory cache has the same key/TTL so a single process
                still gets cache benefits when Redis is unreachable.
                Mirrors `services/provider_status.py` and
                `services/currency.py` patterns.

Cache invalidation:
  - The Module 5 write paths (`seed_plan_entitlements`,
    `set_trial_entitlements`, `set_override_entitlement`, `clear_*`)
    call `invalidate(org_id)` in their commit-success path. The 60s
    TTL is the upper bound for staleness; explicit invalidation is
    the lower bound (immediate).

`has()` semantics:
  - bool value          → return as-is
  - int value           → True iff value != 0  (so `_UNLIMITED == -1`
                          is truthy; "0 quota" is falsy)
  - non-empty string    → True
  - everything else     → False (including None / missing key)

This matches plan §11.2's call sites:
  `entitlements.has(org_id, "pilot.autopilot_enabled") -> bool`
  `entitlements.has(org_id, "goldens.max_sets") -> bool`  ← True for
  any tier with a non-zero cap, including unlimited (enterprise).
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any

import redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Entitlement, Subscription
from app.services.billing_plans import (
    DEFAULT_PLAN_CODE,
    PLAN_ENTITLEMENTS,
)
from app.services.entitlements import parse_entitlement_value
from app.services.redis_client import get_redis_client

logger = logging.getLogger(__name__)


# Cache key prefix; bump the version suffix if the merged-dict shape
# ever changes incompatibly so old cached blobs auto-evict.
_CACHE_KEY_PREFIX = "zroky:entitlements:v1"

# Memory fallback cache: org_id → (resolved_dict, expires_at_unix).
# Module-level dict is fine — workers are single-process per pod;
# the lock is for concurrent /v1/* requests in the same process.
_MEMORY_LOCK = threading.Lock()
_MEMORY_CACHE: dict[str, tuple[dict[str, Any], float]] = {}


# Source precedence — higher number wins.
_SOURCE_RANK: dict[str, int] = {"plan": 1, "trial": 2, "override": 3}

_ENTITLEMENT_ELIGIBLE_SUBSCRIPTION_STATUSES: frozenset[str] = frozenset(
    {"active", "trialing", "past_due"}
)


# ── public API ──────────────────────────────────────────────────────────────


def has(db: Session, org_id: str, key: str) -> bool:
    """O(1) entitled-or-not check (plan §11.2 contract).

    See module docstring for the value→bool semantics. Out-of-vocab
    `key` returns False (resolver doesn't raise — callers shouldn't
    have to wrap every `has()` call in try/except).
    """
    value = get(db, org_id, key, default=None)
    return _truthy(value)


def get(
    db: Session, org_id: str, key: str, default: Any = None
) -> Any:
    """Raw resolved value with full precedence merge.

    Returns `default` for unknown keys. The resolved dict is cached
    so repeated calls in a request are free.
    """
    resolved = resolve_all(db, org_id)
    return resolved.get(key, default)


def resolve_all(db: Session, org_id: str) -> dict[str, Any]:
    """Return the FULLY-MERGED entitlement dict for an org.

    Order of attempts:
      1. Redis cache hit
      2. In-process memory fallback hit (used when Redis is down)
      3. DB resolve (also writes both caches)
    """
    if not org_id or not isinstance(org_id, str):
        # Defensive — out-of-tenant context shouldn't reach the
        # resolver, but if it does we return free-tier defaults
        # rather than 500.
        return dict(PLAN_ENTITLEMENTS[DEFAULT_PLAN_CODE])

    settings = get_settings()
    ttl = max(1, settings.ENTITLEMENT_CACHE_TTL_SECONDS)
    cache_key = f"{_CACHE_KEY_PREFIX}:{org_id}"
    now_ts = time.time()
    use_redis = _redis_cache_enabled()

    # Step 1: Redis
    cached_json = None
    if use_redis:
        try:
            cached_json = get_redis_client().get(cache_key)
        except redis.RedisError:
            cached_json = None
    if cached_json:
        try:
            parsed = json.loads(cached_json)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass  # corrupted cache entry — fall through to memory/DB

    # Step 2: in-process memory fallback
    cached = _memory_get(org_id, now_ts)
    if cached is not None:
        return cached

    # Step 3: DB resolve
    resolved = _resolve_from_db(db, org_id)

    # Best-effort write-through to both caches.
    serialized = json.dumps(resolved, separators=(",", ":"), sort_keys=True)
    if use_redis:
        try:
            get_redis_client().setex(cache_key, ttl, serialized)
        except redis.RedisError:
            pass  # Redis flapping; memory cache below still saves us.
    _memory_set(org_id, resolved, now_ts + ttl)

    return resolved


def invalidate(org_id: str) -> None:
    """Drop cached merged dict for `org_id` from BOTH cache layers.

    Called by Module 5 write paths after every successful commit so
    the next read sees fresh data (lower bound on staleness; upper
    bound is the 60s TTL).
    """
    if not org_id:
        return
    cache_key = f"{_CACHE_KEY_PREFIX}:{org_id}"
    if _redis_cache_enabled():
        try:
            get_redis_client().delete(cache_key)
        except redis.RedisError:
            pass  # Best-effort; the TTL is the safety net.
    with _MEMORY_LOCK:
        _MEMORY_CACHE.pop(org_id, None)


def invalidate_all() -> None:
    """Wipe the in-process memory cache. Used by tests AND by ops
    runbooks when entitlement template constants change at deploy
    time. Does NOT scan Redis — that costs O(N) keys and the per-
    org TTL handles it within 60s anyway."""
    with _MEMORY_LOCK:
        _MEMORY_CACHE.clear()


def get_plan_code(db: Session, org_id: str) -> str:
    """Return the org's entitlement-bearing plan_code.

    Payment-request shells (`incomplete`) and ended subscriptions
    (`canceled`, `unpaid`) are deliberately treated as free so plan gates
    and quota checks cannot be unlocked by starting checkout or after a
    cancellation clears paid entitlements.
    """
    sub = db.execute(
        select(Subscription).where(Subscription.org_id == org_id)
    ).scalar_one_or_none()
    return _plan_code_for_entitlements(sub)


# ── internals ───────────────────────────────────────────────────────────────


def _truthy(value: Any) -> bool:
    """Plan §11.2 has() semantics — see module docstring."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return False


def _redis_cache_enabled() -> bool:
    return os.getenv("TESTING", "").strip().lower() != "true"


def _memory_get(org_id: str, now_ts: float) -> dict[str, Any] | None:
    with _MEMORY_LOCK:
        entry = _MEMORY_CACHE.get(org_id)
        if entry is None:
            return None
        resolved, expires_at = entry
        if now_ts >= expires_at:
            _MEMORY_CACHE.pop(org_id, None)
            return None
        # Defensive copy so callers can't mutate the cached entry.
        return dict(resolved)


def _memory_set(
    org_id: str, resolved: dict[str, Any], expires_at: float
) -> None:
    with _MEMORY_LOCK:
        _MEMORY_CACHE[org_id] = (dict(resolved), expires_at)


def _resolve_from_db(db: Session, org_id: str) -> dict[str, Any]:
    """Build the merged entitlement dict by reading ALL relevant rows
    in two queries (subscription + entitlements) — never N+1."""
    # Subscription = source of plan_code for the template fallback
    sub = db.execute(
        select(Subscription).where(Subscription.org_id == org_id)
    ).scalar_one_or_none()
    plan_code = _plan_code_for_entitlements(sub)
    template = PLAN_ENTITLEMENTS.get(plan_code) or PLAN_ENTITLEMENTS[DEFAULT_PLAN_CODE]
    plan_source_allowed = _subscription_entitlement_eligible(sub)

    rows = db.execute(
        select(Entitlement).where(Entitlement.org_id == org_id)
    ).scalars().all()

    now = datetime.now(timezone.utc)

    # Pick highest-precedence non-expired row per key.
    best: dict[str, tuple[int, Any]] = {}
    for row in rows:
        if row.expires_at is not None:
            row_expires = row.expires_at
            # Defensive: SQLAlchemy SQLite path can return naive datetimes
            # for timestamp columns. Treat naive as UTC.
            if row_expires.tzinfo is None:
                row_expires = row_expires.replace(tzinfo=timezone.utc)
            if row_expires <= now:
                continue
        rank = _SOURCE_RANK.get(row.source, 0)
        if rank == 0:
            continue
        if row.source == "plan" and not plan_source_allowed:
            continue
        existing = best.get(row.key)
        if existing is not None and existing[0] >= rank:
            continue
        value = parse_entitlement_value(row.value_json)
        best[row.key] = (rank, value)

    # Start from template, then layer wins from rows.
    resolved: dict[str, Any] = dict(template)
    for key, (_rank, value) in best.items():
        resolved[key] = value
    return resolved


def _subscription_entitlement_eligible(sub: Subscription | None) -> bool:
    if sub is None:
        return False
    status = (sub.status or "").strip().lower()
    return status in _ENTITLEMENT_ELIGIBLE_SUBSCRIPTION_STATUSES


def _plan_code_for_entitlements(sub: Subscription | None) -> str:
    if not _subscription_entitlement_eligible(sub):
        return DEFAULT_PLAN_CODE
    plan_code = (sub.plan_code or "").strip().lower()
    return plan_code if plan_code in PLAN_ENTITLEMENTS else DEFAULT_PLAN_CODE


__all__ = [
    "has",
    "get",
    "resolve_all",
    "invalidate",
    "invalidate_all",
    "get_plan_code",
]
