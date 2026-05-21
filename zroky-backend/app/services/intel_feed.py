"""
Read-only Intel feed (Module 4.6; plan §3.3 + §13).

Surfaces the global `intel_signals` table (migration 0055) as a
filterable, paginated feed for the dashboard's "Intel Pulse" panel:

  GET /v1/intel/feed → list of currently-active outages, deprecations,
                       CVEs, pricing changes, and advisories.

Note on plan §5.2 inconsistency:
  The plan's table description for `intel_signals` (line 486) talks
  about an "anonymized cross-tenant Watch network" with columns
  `(anonymized_org_hash, detector, provider, model, signal_at,
  payload_json)`. The schema actually shipped in migration 0055 is
  for **Intel Pulse** — externally-scraped global signals (provider
  status pages, CVE feeds, pricing trackers). Module 4.6 implements
  the read surface over THAT shipped schema. The plan's "Watch
  network" anonymized fleet aggregation is a separate concern that
  requires:
    - the contributor opt-in/opt-out toggle in `entitlements`,
    - `intel_aggregator.py` with weekly-rotated hash salt (§13 risk #6),
    - a different table (likely `watch_signals`).
  All deferred to a future module. The route prefix /v1/intel/feed is
  forward-compatible with either source.

Service contract:
  - Globally scoped reads (signals are shared across orgs); no RLS.
  - Filters: kind, min_severity, source, model substring, only_active.
  - Pagination: cursor by previous-page tail id; (created_at DESC,
    id DESC) ordering with id as tiebreaker.
  - Defensive payload_json parse: corrupt rows → {} so the dashboard
    never 500s on bit-rot.
"""
from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.db.models import IntelSignal

logger = logging.getLogger(__name__)


# ── vocab (must match migration 0055 CHECK constraint) ──────────────────────


VALID_KINDS: frozenset[str] = frozenset(
    {"outage", "deprecation", "cve", "pricing_change", "advisory"}
)

# Ordered low → critical so callers can compute "≥ medium" cleanly.
SEVERITY_RANK: dict[str, int] = {
    "low": 10,
    "medium": 20,
    "high": 30,
    "critical": 40,
}
VALID_SEVERITIES: frozenset[str] = frozenset(SEVERITY_RANK.keys())


# ── exceptions ──────────────────────────────────────────────────────────────


class IntelFeedFilterError(ValueError):
    """Bad query parameter — the route maps this to 422."""


# ── validators ──────────────────────────────────────────────────────────────


def parse_kind(value: str | None) -> str | None:
    if value is None:
        return None
    norm = value.strip().lower()
    if not norm:
        return None
    if norm not in VALID_KINDS:
        raise IntelFeedFilterError(
            f"kind {value!r} must be one of: {sorted(VALID_KINDS)}"
        )
    return norm


def parse_min_severity(value: str | None) -> str | None:
    if value is None:
        return None
    norm = value.strip().lower()
    if not norm:
        return None
    if norm not in VALID_SEVERITIES:
        raise IntelFeedFilterError(
            f"min_severity {value!r} must be one of: "
            f"{sorted(VALID_SEVERITIES, key=lambda s: SEVERITY_RANK[s])}"
        )
    return norm


def parse_source(value: str | None) -> str | None:
    """Source is open-ended (the migration doesn't constrain it) but we
    cap length and lowercase to keep filtering predictable."""
    if value is None:
        return None
    norm = value.strip().lower()
    if not norm:
        return None
    if len(norm) > 64:
        raise IntelFeedFilterError("source must be at most 64 characters")
    return norm


def parse_model(value: str | None) -> str | None:
    """Model filter is a substring match against `model_affected`. We
    don't constrain syntax — `gpt-4`, `claude-3`, `*-mini` are all OK."""
    if value is None:
        return None
    norm = value.strip()
    if not norm:
        return None
    if len(norm) > 128:
        raise IntelFeedFilterError("model must be at most 128 characters")
    return norm


def severities_at_or_above(min_severity: str) -> list[str]:
    """Return the set of severities ≥ min_severity, in canonical order."""
    threshold = SEVERITY_RANK[min_severity]
    return sorted(
        (s for s, r in SEVERITY_RANK.items() if r >= threshold),
        key=lambda s: SEVERITY_RANK[s],
    )


# ── cursor encoding ─────────────────────────────────────────────────────────


def encode_cursor(last_id: str) -> str:
    """Cursor is just the previous-page tail id, base64-url-encoded so
    it survives a query-string round-trip without escaping fuss."""
    return base64.urlsafe_b64encode(last_id.encode("utf-8")).decode("ascii")


def decode_cursor(token: str | None) -> str | None:
    if token is None:
        return None
    raw = token.strip()
    if not raw:
        return None
    try:
        decoded = base64.urlsafe_b64decode(raw.encode("ascii")).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise IntelFeedFilterError("invalid cursor") from exc
    decoded = decoded.strip()
    if not decoded:
        raise IntelFeedFilterError("invalid cursor")
    return decoded


# ── parsers ─────────────────────────────────────────────────────────────────


def parse_payload(raw: str | None) -> dict[str, Any]:
    """Defensive parse of `payload_json`. Returns {} on missing,
    malformed, or non-object payload — the dashboard never 500s on
    bit-rot.

    Same pattern as `parse_summary_json` in Module 4.4 digest_engine.
    """
    if raw is None:
        return {}
    if not isinstance(raw, str):
        return {}
    text = raw.strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    return parsed


# ── reads ───────────────────────────────────────────────────────────────────


def list_intel_signals(
    db: Session,
    *,
    kind: str | None = None,
    min_severity: str | None = None,
    source: str | None = None,
    model: str | None = None,
    only_active: bool = True,
    limit: int = 20,
    cursor_id: str | None = None,
    now: datetime | None = None,
) -> list[IntelSignal]:
    """Return signals newest-first, applying the requested filters.

    Args:
      kind:         single allowed value or None (no kind filter)
      min_severity: 'low'|'medium'|'high'|'critical'; rows whose severity
                    rank is ≥ the threshold are returned. None = no filter.
      source:       exact match (case-insensitive) on `source`
      model:        substring match (case-insensitive) on `model_affected`
      only_active:  when True, returns only rows whose validity window
                    contains `now` (defaults to UTC now)
      limit:        page size; 1..100
      cursor_id:    id of the previous-page tail; the service looks up
                    its created_at and walks (created_at < that.created_at
                    OR (created_at = ... AND id < that.id))
      now:          override for tests; default datetime.now(timezone.utc)

    Raises:
      IntelFeedFilterError on bad inputs (inc. unknown cursor_id).
    """
    if limit < 1 or limit > 100:
        raise IntelFeedFilterError("limit must be between 1 and 100")

    conditions: list[Any] = []

    if kind is not None:
        conditions.append(IntelSignal.kind == kind)
    if min_severity is not None:
        conditions.append(
            IntelSignal.severity.in_(severities_at_or_above(min_severity))
        )
    if source is not None:
        conditions.append(IntelSignal.source == source)
    if model is not None:
        # case-insensitive substring on model_affected
        like = f"%{model.lower()}%"
        conditions.append(IntelSignal.model_affected.isnot(None))
        conditions.append(IntelSignal.model_affected.ilike(like))
    if only_active:
        moment = now or datetime.now(timezone.utc)
        conditions.append(IntelSignal.valid_from <= moment)
        conditions.append(
            or_(
                IntelSignal.valid_to.is_(None),
                IntelSignal.valid_to >= moment,
            )
        )

    if cursor_id is not None:
        anchor = db.execute(
            select(IntelSignal).where(IntelSignal.id == cursor_id)
        ).scalar_one_or_none()
        if anchor is None:
            raise IntelFeedFilterError(
                f"cursor row {cursor_id!r} not found (expired or invalid)"
            )
        conditions.append(
            or_(
                IntelSignal.created_at < anchor.created_at,
                and_(
                    IntelSignal.created_at == anchor.created_at,
                    IntelSignal.id < anchor.id,
                ),
            )
        )

    stmt = (
        select(IntelSignal)
        .where(*conditions)
        .order_by(IntelSignal.created_at.desc(), IntelSignal.id.desc())
        .limit(limit)
    )
    return list(db.execute(stmt).scalars().all())


# ── serialiser ──────────────────────────────────────────────────────────────


def serialize_intel_signal(row: IntelSignal) -> dict[str, Any]:
    """Wire shape for a single signal. `payload` is parsed JSON (dict);
    invalid stored JSON degrades to {} rather than 500ing."""
    return {
        "id": row.id,
        "source": row.source,
        "kind": row.kind,
        "severity": row.severity,
        "confidence": float(row.confidence),
        "url": row.url,
        "model_affected": row.model_affected,
        "valid_from": row.valid_from.isoformat() if row.valid_from else None,
        "valid_to": row.valid_to.isoformat() if row.valid_to else None,
        "payload": parse_payload(row.payload_json),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


__all__ = [
    "IntelFeedFilterError",
    "VALID_KINDS",
    "VALID_SEVERITIES",
    "SEVERITY_RANK",
    "parse_kind",
    "parse_min_severity",
    "parse_source",
    "parse_model",
    "severities_at_or_above",
    "encode_cursor",
    "decode_cursor",
    "parse_payload",
    "list_intel_signals",
    "serialize_intel_signal",
]
