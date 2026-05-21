"""Determinism classifier — statistical probe, zero LLM calls.

Queries the Call table for historical calls with the same
(project_id, agent_name, prompt_fingerprint) and computes the fail
rate to determine how deterministic the failure is.

Classes
-------
deterministic   fail_rate >= 0.75 AND same prompt_fingerprint
                → fix is in the prompt template or model choice
stochastic      fail_rate in (0.20, 0.75)
                → sampling variance; lower temperature, add seed
environmental   error_code in infra-error set OR timeout_triggered
                → infra failure; fix retries / fallback / timeout
unknown         insufficient history (< MIN_SAMPLE_SIZE calls)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Call, DiagnosisJob

logger = logging.getLogger(__name__)

_INFRA_ERROR_CODES = frozenset({
    "PROVIDER_ERROR", "RATE_LIMIT", "AUTH_FAILURE",
    "TIMEOUT", "CONNECTION_ERROR", "NETWORK_ERROR",
})

MIN_SAMPLE_SIZE = 5
LOOKBACK_DAYS = 14

FAIL_STATUSES = frozenset({"error", "failed", "timeout", "rate_limited"})


@dataclass(frozen=True)
class DeterminismResult:
    determinism_class: str
    fail_rate: float
    sample_size: int
    same_fingerprint_size: int
    infra_error_fraction: float
    probe_detail: dict


def classify_determinism(
    db: Session,
    *,
    project_id: str,
    call: Call,
) -> DeterminismResult:
    """Compute determinism class for a failing call using historical data.

    Parameters
    ----------
    db:     Active SQLAlchemy session.
    project_id: Tenant scope.
    call:   The failing Call ORM instance.
    """
    since = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    agent = call.agent_name
    fp = _get_fingerprint(call)

    # ── Query historical diagnosis jobs with same agent / fingerprint ──────────
    # We join via DiagnosisJob (which stores prompt_fingerprint) to get the
    # status of each associated call.  This avoids referencing
    # Call.prompt_fingerprint which is not a column on the calls table.
    base_q = (
        select(Call.status, Call.error_code)
        .join(DiagnosisJob, DiagnosisJob.call_id == Call.id, isouter=True)
        .where(
            Call.project_id == project_id,
            Call.created_at >= since,
        )
    )

    if agent:
        base_q = base_q.where(Call.agent_name == agent)

    if fp:
        base_q = base_q.where(DiagnosisJob.prompt_fingerprint == fp)

    rows = db.execute(base_q).all()
    sample_size = len(rows)

    if sample_size < MIN_SAMPLE_SIZE:
        return DeterminismResult(
            determinism_class="unknown",
            fail_rate=0.0,
            sample_size=sample_size,
            same_fingerprint_size=0,
            infra_error_fraction=0.0,
            probe_detail={
                "reason": "insufficient_history",
                "required": MIN_SAMPLE_SIZE,
                "found": sample_size,
                "agent_name": agent,
                "prompt_fingerprint": fp,
            },
        )

    fail_count = sum(1 for r in rows if r.status in FAIL_STATUSES or r.status not in {"completed", "success", "ok"})
    fail_rate = fail_count / sample_size

    infra_errors = sum(
        1 for r in rows
        if r.error_code and str(r.error_code).upper() in _INFRA_ERROR_CODES
    )
    infra_fraction = infra_errors / sample_size

    # ── Check if current call itself has an infra error ────────────────────────
    current_is_infra = (
        call.error_code and str(call.error_code).upper() in _INFRA_ERROR_CODES
    )
    payload = _parse_payload(call.payload_json or "{}")
    current_timeout = bool(payload.get("timeout_triggered", False))

    probe_detail = {
        "agent_name": agent,
        "prompt_fingerprint": fp,
        "sample_size": sample_size,
        "fail_count": fail_count,
        "fail_rate": round(fail_rate, 4),
        "infra_error_fraction": round(infra_fraction, 4),
        "current_error_code": call.error_code,
        "current_timeout": current_timeout,
        "lookback_days": LOOKBACK_DAYS,
    }

    # ── Classify ───────────────────────────────────────────────────────────────
    if current_is_infra or current_timeout or infra_fraction >= 0.40:
        det_class = "environmental"
    elif fail_rate >= 0.75:
        det_class = "deterministic"
    elif fail_rate >= 0.20:
        det_class = "stochastic"
    else:
        # Very low fail rate for this fingerprint; current failure is anomalous
        det_class = "environmental"

    return DeterminismResult(
        determinism_class=det_class,
        fail_rate=round(fail_rate, 4),
        sample_size=sample_size,
        same_fingerprint_size=sample_size,
        infra_error_fraction=round(infra_fraction, 4),
        probe_detail=probe_detail,
    )


def _get_fingerprint(call: Call) -> str | None:
    if hasattr(call, "prompt_fingerprint") and call.prompt_fingerprint:
        return call.prompt_fingerprint
    payload = _parse_payload(call.payload_json or "{}")
    return payload.get("prompt_fingerprint")


def _parse_payload(payload_json: str) -> dict:
    try:
        return json.loads(payload_json)
    except Exception:
        return {}
