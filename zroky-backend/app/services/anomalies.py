"""
Anomalies service: internal detector grouping for customer-facing Issues.

Product contract:
  - "Issue" is the customer-facing term used by dashboard and public APIs.
  - "Anomaly" is the internal persisted detector grouping. Keep the model,
    table, and detector plumbing unchanged; project rows through
    `issue_projection_from_anomaly()` before rendering to customers.

Schema notes (ZROKY-TECHNICAL-PLAN-V2 §5.2 + §6.1 + §6.3):
  - `anomalies` groups repeated detector events by a single `fingerprint`
    column instead of the legacy triple `(failure_code, prompt_fingerprint,
    agent_name)`. Fingerprint is a deterministic SHA-256 over the inputs
    that identify the same logical detection event.
  - The detector enum is INTENTIONALLY narrower than legacy `failure_code`s.
    Per plan §6.1 the following codes are demoted to SDK-side preflight
    warnings only and **must not** create anomaly rows:
        AUTH_FAILURE, TOKEN_OVERFLOW, RATE_LIMIT, PROVIDER_ERROR, UNKNOWN
    The mapping helper `map_failure_code_to_detector()` returns None for
    these so callers can skip the upsert cleanly.
  - The public `/v1/issues` API is backed by these internal rows and should
    remain the primary customer-facing route. `/v1/anomalies` is retained
    only as a deprecated compatibility/internal surface.
  - This module never queries the legacy `issues` table.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Anomaly

logger = logging.getLogger(__name__)


# ── status / detector vocabularies (must match db CHECK constraints) ─────────

_OPEN = "open"
_ACKNOWLEDGED = "acknowledged"
_RESOLVED = "resolved"
_MUTED = "muted"
VALID_STATUSES = frozenset({_OPEN, _ACKNOWLEDGED, _RESOLVED, _MUTED})

# Kept detectors per plan §6.1. Anything outside this set is SDK-side only.
VALID_DETECTORS = frozenset({
    "LOOP_DETECTED",
    "COST_SPIKE",
    "ACCURACY_REGRESSION",
    "HALLUCINATION_RISK",
    "SCHEMA_VIOLATION",
    "LATENCY_REGRESSION",
    "TOOL_SELECTION_FAILURE",
    "TOOL_CALL_FAILURE",
    "TOOL_ARGUMENT_MISMATCH",
    "RAG_RETRIEVAL_MISSING",
    "RETRIEVAL_MISSING",
    "TOKEN_USAGE_DRIFT",
    "TOKEN_OVERFLOW",
    "RATE_LIMIT",
    "AUTH_FAILURE",
    "PROVIDER_ERROR",
    "LATENCY_ANOMALY",
    "LATENCY_DRIFT",
    "ERROR_RATE_DRIFT",
    "EMPTY_OUTPUT",
    "OUTPUT_TRUNCATED",
    "OUTPUT_LENGTH_DRIFT",
    "REPEATED_OUTPUT",
    "UNKNOWN",
})

# Legacy failure_code to canonical detector. Empty/unknown codes still skip.
_LEGACY_FAILURE_TO_DETECTOR: dict[str, str | None] = {
    "LOOP_DETECTED": "LOOP_DETECTED",
    "COST_SPIKE": "COST_SPIKE",
    "ACCURACY_REGRESSION": "ACCURACY_REGRESSION",
    "HALLUCINATION_RISK": "HALLUCINATION_RISK",
    "HALLUCINATION": "HALLUCINATION_RISK",
    "SCHEMA_VIOLATION": "SCHEMA_VIOLATION",
    "SCHEMA_MISMATCH": "SCHEMA_VIOLATION",
    "LATENCY_REGRESSION": "LATENCY_REGRESSION",
    "TOOL_SELECTION_FAILURE": "TOOL_SELECTION_FAILURE",
    "TOOL_CALL_FAILURE": "TOOL_CALL_FAILURE",
    "TOOL_ARGUMENT_MISMATCH": "TOOL_ARGUMENT_MISMATCH",
    "RAG_RETRIEVAL_MISSING": "RAG_RETRIEVAL_MISSING",
    "RETRIEVAL_MISSING": "RETRIEVAL_MISSING",
    "TOKEN_USAGE_DRIFT": "TOKEN_USAGE_DRIFT",
    "TOKEN_OVERFLOW": "TOKEN_OVERFLOW",
    "RATE_LIMIT": "RATE_LIMIT",
    "AUTH_FAILURE": "AUTH_FAILURE",
    "PROVIDER_ERROR": "PROVIDER_ERROR",
    "LATENCY_ANOMALY": "LATENCY_ANOMALY",
    "LATENCY_DRIFT": "LATENCY_DRIFT",
    "ERROR_RATE_DRIFT": "ERROR_RATE_DRIFT",
    "EMPTY_OUTPUT": "EMPTY_OUTPUT",
    "OUTPUT_TRUNCATED": "OUTPUT_TRUNCATED",
    "OUTPUT_LENGTH_DRIFT": "OUTPUT_LENGTH_DRIFT",
    "REPEATED_OUTPUT": "REPEATED_OUTPUT",
    "UNKNOWN": None,
    "": None,
}

_MAX_SAMPLE_CALL_IDS = 5


# ── helpers ───────────────────────────────────────────────────────────────────

def map_failure_code_to_detector(failure_code: str | None) -> str | None:
    """Translate a legacy `failure_code` to the new `detector` enum.

    Returns None for empty/unknown codes. Callers should skip the upsert then.
    """
    if not failure_code:
        return None
    code = failure_code.strip().upper()
    if code in _LEGACY_FAILURE_TO_DETECTOR:
        return _LEGACY_FAILURE_TO_DETECTOR[code]
    if code in VALID_DETECTORS:
        return code
    if "TOOL" in code:
        return "TOOL_SELECTION_FAILURE"
    if "RAG" in code or "RETRIEVAL" in code:
        return "RAG_RETRIEVAL_MISSING"
    if "LATENCY" in code:
        return "LATENCY_DRIFT"
    if "TOKEN" in code:
        return "TOKEN_USAGE_DRIFT"
    if "OUTPUT" in code:
        return "ACCURACY_REGRESSION"
    return None


def compute_fingerprint(
    *,
    detector: str,
    prompt_fingerprint: str | None,
    agent_name: str | None,
    extra: str | None = None,
) -> str:
    """Deterministic group key for an anomaly.

    The same logical detection event must always hash to the same value
    so the upsert path can collapse repeats into one row.
    """
    parts = [
        detector.strip().upper(),
        (prompt_fingerprint or "").strip(),
        (agent_name or "").strip(),
        (extra or "").strip(),
    ]
    payload = "|".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _derive_severity(detector: str, occurrence_count: int) -> str:
    """Heuristic severity based on detector class + recurrence."""
    if detector in {
        "AUTH_FAILURE",
        "COST_SPIKE",
        "ACCURACY_REGRESSION",
        "HALLUCINATION_RISK",
        "PROVIDER_ERROR",
    }:
        if occurrence_count >= 5:
            return "critical"
        return "high"
    if detector in {
        "LOOP_DETECTED",
        "SCHEMA_VIOLATION",
        "LATENCY_REGRESSION",
        "LATENCY_ANOMALY",
        "LATENCY_DRIFT",
        "TOKEN_OVERFLOW",
        "ERROR_RATE_DRIFT",
    }:
        if occurrence_count >= 10:
            return "high"
        if occurrence_count >= 3:
            return "medium"
    return "low"


def _merge_sample_call_ids(existing_json: str | None, new_call_id: str | None) -> str | None:
    """Maintain a rolling list of recent sample call IDs (most recent last).

    Returns serialized JSON (or None if no IDs to record). Caps the list at
    _MAX_SAMPLE_CALL_IDS to keep row size bounded.
    """
    ids: list[str] = []
    if existing_json:
        try:
            decoded = json.loads(existing_json)
            if isinstance(decoded, list):
                ids = [str(x) for x in decoded if x]
        except Exception:
            ids = []
    if new_call_id and new_call_id not in ids:
        ids.append(new_call_id)
    if len(ids) > _MAX_SAMPLE_CALL_IDS:
        ids = ids[-_MAX_SAMPLE_CALL_IDS:]
    if not ids:
        return None
    return json.dumps(ids, separators=(",", ":"))


# ── upsert ────────────────────────────────────────────────────────────────────

def upsert_anomaly(
    db: Session,
    *,
    project_id: str,
    detector: str,
    prompt_fingerprint: str | None = None,
    agent_name: str | None = None,
    call_id: str | None = None,
    occurred_at: datetime | None = None,
    evidence: dict[str, Any] | None = None,
    fingerprint_extra: str | None = None,
) -> Anomaly | None:
    """Upsert an anomaly row keyed on (project_id, fingerprint).

    On INSERT: creates an open anomaly with occurrence_count=1.
    On CONFLICT: increments occurrence_count, refreshes last_seen_at +
    sample_call_ids_json, and re-opens the row if it had been resolved.

    Returns None if `detector` is not in `VALID_DETECTORS` so callers can
    safely call this with raw failure_codes after passing them through
    `map_failure_code_to_detector()`.
    """
    detector_norm = (detector or "").strip().upper()
    if detector_norm not in VALID_DETECTORS:
        return None

    now = datetime.now(timezone.utc)
    seen_at = occurred_at or now
    fingerprint = compute_fingerprint(
        detector=detector_norm,
        prompt_fingerprint=prompt_fingerprint,
        agent_name=agent_name,
        extra=fingerprint_extra,
    )
    evidence_json = json.dumps(evidence, separators=(",", ":")) if evidence else None
    initial_sample_ids = _merge_sample_call_ids(None, call_id)

    if db.bind is not None and db.bind.dialect.name == "postgresql":
        return _upsert_postgresql(
            db,
            project_id=project_id,
            detector=detector_norm,
            fingerprint=fingerprint,
            seen_at=seen_at,
            now=now,
            call_id=call_id,
            evidence_json=evidence_json,
            initial_sample_ids=initial_sample_ids,
        )
    return _upsert_portable(
        db,
        project_id=project_id,
        detector=detector_norm,
        fingerprint=fingerprint,
        seen_at=seen_at,
        now=now,
        call_id=call_id,
        evidence_json=evidence_json,
        initial_sample_ids=initial_sample_ids,
    )


def _upsert_postgresql(
    db: Session,
    *,
    project_id: str,
    detector: str,
    fingerprint: str,
    seen_at: datetime,
    now: datetime,
    call_id: str | None,
    evidence_json: str | None,
    initial_sample_ids: str | None,
) -> Anomaly:
    new_count = Anomaly.occurrence_count + 1
    stmt = (
        pg_insert(Anomaly)
        .values(
            id=str(uuid4()),
            project_id=project_id,
            fingerprint=fingerprint,
            detector=detector,
            severity=_derive_severity(detector, 1),
            status=_OPEN,
            first_seen_at=seen_at,
            last_seen_at=seen_at,
            occurrence_count=1,
            sample_call_ids_json=initial_sample_ids,
            evidence_json=evidence_json,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_update(
            constraint="ux_anomalies_project_fingerprint",
            set_={
                "occurrence_count": new_count,
                "last_seen_at": seen_at,
                "evidence_json": evidence_json,
                "status": _OPEN,
                "updated_at": now,
            },
        )
        .returning(Anomaly.id)
    )
    result = db.execute(stmt)
    db.commit()
    anomaly_id = result.scalar_one()
    anomaly = db.execute(select(Anomaly).where(Anomaly.id == anomaly_id)).scalar_one()
    # post-merge: refresh sample_call_ids_json + severity from the canonical row
    merged = _merge_sample_call_ids(anomaly.sample_call_ids_json, call_id)
    anomaly.sample_call_ids_json = merged
    anomaly.severity = _derive_severity(detector, anomaly.occurrence_count or 1)
    db.commit()
    db.refresh(anomaly)
    return anomaly


def _upsert_portable(
    db: Session,
    *,
    project_id: str,
    detector: str,
    fingerprint: str,
    seen_at: datetime,
    now: datetime,
    call_id: str | None,
    evidence_json: str | None,
    initial_sample_ids: str | None,
) -> Anomaly:
    existing = db.execute(
        select(Anomaly).where(
            Anomaly.project_id == project_id,
            Anomaly.fingerprint == fingerprint,
        )
    ).scalar_one_or_none()

    if existing is not None:
        existing.occurrence_count = (existing.occurrence_count or 0) + 1
        existing.last_seen_at = seen_at
        existing.sample_call_ids_json = _merge_sample_call_ids(
            existing.sample_call_ids_json, call_id
        )
        if evidence_json is not None:
            existing.evidence_json = evidence_json
        existing.status = _OPEN
        existing.severity = _derive_severity(detector, existing.occurrence_count)
        existing.updated_at = now
        db.add(existing)
        try:
            db.commit()
            db.refresh(existing)
        except Exception:
            db.rollback()
            raise
        return existing

    anomaly = Anomaly(
        id=str(uuid4()),
        project_id=project_id,
        fingerprint=fingerprint,
        detector=detector,
        severity=_derive_severity(detector, 1),
        status=_OPEN,
        first_seen_at=seen_at,
        last_seen_at=seen_at,
        occurrence_count=1,
        sample_call_ids_json=initial_sample_ids,
        evidence_json=evidence_json,
        created_at=now,
        updated_at=now,
    )
    db.add(anomaly)
    try:
        db.commit()
        db.refresh(anomaly)
    except IntegrityError:
        db.rollback()
        return _upsert_portable(
            db,
            project_id=project_id,
            detector=detector,
            fingerprint=fingerprint,
            seen_at=seen_at,
            now=now,
            call_id=call_id,
            evidence_json=evidence_json,
            initial_sample_ids=initial_sample_ids,
        )
    return anomaly


# ── status transitions ───────────────────────────────────────────────────────

def _transition_status(
    db: Session,
    *,
    project_id: str,
    anomaly_id: str,
    new_status: str,
) -> Anomaly | None:
    if new_status not in VALID_STATUSES:
        raise ValueError(f"invalid status: {new_status!r}")
    anomaly = db.execute(
        select(Anomaly).where(
            Anomaly.project_id == project_id,
            Anomaly.id == anomaly_id,
        )
    ).scalar_one_or_none()
    if anomaly is None:
        return None
    anomaly.status = new_status
    anomaly.updated_at = datetime.now(timezone.utc)
    db.add(anomaly)
    db.commit()
    db.refresh(anomaly)
    return anomaly


def resolve_anomaly(
    db: Session, *, project_id: str, anomaly_id: str
) -> Anomaly | None:
    """Mark an anomaly as resolved."""
    return _transition_status(
        db, project_id=project_id, anomaly_id=anomaly_id, new_status=_RESOLVED
    )


def acknowledge_anomaly(
    db: Session, *, project_id: str, anomaly_id: str
) -> Anomaly | None:
    """Acknowledge an anomaly (operator has seen it; not yet resolved)."""
    return _transition_status(
        db, project_id=project_id, anomaly_id=anomaly_id, new_status=_ACKNOWLEDGED
    )


def mute_anomaly(
    db: Session, *, project_id: str, anomaly_id: str
) -> Anomaly | None:
    """Mute (silence) an anomaly. Replaces the legacy 'ignored' state."""
    return _transition_status(
        db, project_id=project_id, anomaly_id=anomaly_id, new_status=_MUTED
    )
