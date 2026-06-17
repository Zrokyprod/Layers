"""Cost-of-Failure Attribution service.

Core question answered: "What is each AI failure actually costing us?"

Join chain:
  outcome_events.call_id
    → calls.agent_name / calls.model
    → diagnosis_jobs.agent_name (+ payload_json → detector type)

Replay savings (pre-deploy $ tag):
  replay_run_traces(status='pass') → golden_traces.call_id → outcome_events

All attribution is computed on read — no materialised views.  Queries are
index-covered by ix_outcome_events_project_occurred and ix_outcome_events_call_id.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.models import (
    Call,
    DiagnosisJob,
    GoldenTrace,
    OutcomeEvent,
    ReplayRunTrace,
)

logger = logging.getLogger(__name__)

# ── Known outcome types (open-ended — customers may use custom strings) ────────

KNOWN_OUTCOME_TYPES = frozenset({
    "refund_issued",
    "ticket_escalated",
    "human_handoff",
    "churn",
    "compliance_fine",
    "retry_cost",
    "custom",
})


# ── Result dataclasses ─────────────────────────────────────────────────────────


@dataclass
class OutcomeTypeRow:
    outcome_type: str
    total_usd: float
    count: int
    avg_usd: float


@dataclass
class AttributionClusterRow:
    """One cluster = unique (agent_name, detector) pair with outcome cost."""

    agent_name: str | None
    detector: str | None
    outcome_cost_usd: float
    outcome_count: int
    failure_count: int
    estimated_monthly_savings_usd: float
    top_outcome_type: str | None


@dataclass
class OutcomeSummary:
    window_days: int
    total_outcome_usd: float
    linked_outcome_count: int
    unlinked_outcome_count: int
    avg_cost_per_linked: float
    by_type: list[OutcomeTypeRow]
    by_cluster: list[AttributionClusterRow]


@dataclass
class CallOutcomeView:
    id: str
    outcome_type: str
    amount_usd: float
    source: str
    occurred_at: datetime
    external_ref: str | None


# ── Ingest ─────────────────────────────────────────────────────────────────────


def ingest_outcome(
    db: Session,
    *,
    project_id: str,
    outcome_type: str,
    amount_usd: float,
    call_id: str | None = None,
    source: str = "api",
    external_ref: str | None = None,
    idempotency_key: str | None = None,
    occurred_at: datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> OutcomeEvent:
    """Persist one outcome event.

    Idempotent when ``idempotency_key`` is supplied: returns the existing
    row if the key was already seen for this project.
    """
    if idempotency_key:
        existing = db.execute(
            select(OutcomeEvent).where(
                OutcomeEvent.project_id == project_id,
                OutcomeEvent.idempotency_key == idempotency_key,
            )
        ).scalar_one_or_none()
        if existing is not None:
            logger.debug(
                "outcome_attribution.idempotent_skip project=%s key=%s",
                project_id,
                idempotency_key,
            )
            return existing

    evt = OutcomeEvent(
        id=str(uuid4()),
        project_id=project_id,
        call_id=call_id,
        outcome_type=outcome_type,
        amount_usd=Decimal(str(amount_usd)),
        source=source,
        external_ref=external_ref,
        idempotency_key=idempotency_key,
        occurred_at=occurred_at or datetime.now(timezone.utc),
        metadata_json=json.dumps(metadata, separators=(",", ":")) if metadata else None,
    )
    db.add(evt)
    db.commit()
    db.refresh(evt)
    logger.info(
        "outcome_attribution.ingested id=%s project=%s type=%s amount=%.4f",
        evt.id,
        project_id,
        outcome_type,
        float(amount_usd),
    )
    return evt


# ── Zendesk / Salesforce webhook normalisation ─────────────────────────────────


def normalise_zendesk_ticket(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract canonical outcome fields from a Zendesk ticket webhook."""
    ticket = payload.get("ticket", payload)
    ticket_id = str(ticket.get("id", ""))
    external_ref = f"zendesk:{ticket_id}"
    call_id = (ticket.get("fields") or ticket.get("custom_fields") or [None])[0]
    if isinstance(call_id, dict):
        call_id = call_id.get("value")
    for cf in ticket.get("custom_fields", []):
        if isinstance(cf, dict) and cf.get("id") in ("zroky_call_id", "zroky-call-id"):
            call_id = cf.get("value")
            break
    return dict(
        outcome_type="ticket_escalated",
        amount_usd=18.0,
        call_id=call_id,
        source="zendesk",
        external_ref=external_ref,
        idempotency_key=f"zendesk:{ticket_id}",
        metadata={"zendesk_status": ticket.get("status"), "zendesk_priority": ticket.get("priority")},
    )


def normalise_salesforce_event(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract canonical outcome fields from a Salesforce churn/loss event."""
    opp = payload.get("sobject", payload)
    amount = float(opp.get("Amount") or opp.get("amount") or 0)
    sf_id = str(opp.get("Id") or opp.get("id") or "")
    call_id = opp.get("Zroky_Call_Id__c") or opp.get("zroky_call_id")
    return dict(
        outcome_type="churn",
        amount_usd=amount,
        call_id=call_id,
        source="salesforce",
        external_ref=sf_id or None,
        idempotency_key=f"salesforce:{sf_id}" if sf_id else None,
        metadata={"sf_stage": opp.get("StageName"), "sf_close_reason": opp.get("CloseReason__c")},
    )


# ── Attribution queries ────────────────────────────────────────────────────────


def get_attribution_summary(
    db: Session,
    *,
    project_id: str,
    days: int = 30,
) -> OutcomeSummary:
    """Full attribution summary: KPIs + by-type + by-cluster.

    The by-cluster breakdown joins outcome_events → calls → diagnosis_jobs
    to group cost by (agent_name, detector_type).  Unlinked outcomes (no
    call_id or no matching call) fall into agent_name=None, detector=None.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # ── 1. Raw outcome rows in window ──────────────────────────────────────────
    raw_outcomes = db.execute(
        select(OutcomeEvent).where(
            OutcomeEvent.project_id == project_id,
            OutcomeEvent.occurred_at >= since,
        )
    ).scalars().all()

    if not raw_outcomes:
        return OutcomeSummary(
            window_days=days,
            total_outcome_usd=0.0,
            linked_outcome_count=0,
            unlinked_outcome_count=0,
            avg_cost_per_linked=0.0,
            by_type=[],
            by_cluster=[],
        )

    total_usd = sum(float(o.amount_usd) for o in raw_outcomes)
    linked = [o for o in raw_outcomes if o.call_id]
    unlinked = [o for o in raw_outcomes if not o.call_id]

    # ── 2. By-type aggregation (pure Python — small result set) ───────────────
    type_agg: dict[str, dict[str, float]] = {}
    for o in raw_outcomes:
        bucket = type_agg.setdefault(o.outcome_type, {"usd": 0.0, "count": 0})
        bucket["usd"] += float(o.amount_usd)
        bucket["count"] += 1
    by_type = [
        OutcomeTypeRow(
            outcome_type=t,
            total_usd=v["usd"],
            count=int(v["count"]),
            avg_usd=v["usd"] / v["count"] if v["count"] else 0.0,
        )
        for t, v in sorted(type_agg.items(), key=lambda kv: -kv[1]["usd"])
    ]

    # ── 3. By-cluster: join outcome → calls → diagnosis_jobs ──────────────────
    by_cluster = _compute_cluster_attribution(
        db,
        project_id=project_id,
        linked_outcomes=linked,
        unlinked_outcomes=unlinked,
        window_days=days,
    )

    avg_per_linked = (
        sum(float(o.amount_usd) for o in linked) / len(linked) if linked else 0.0
    )

    return OutcomeSummary(
        window_days=days,
        total_outcome_usd=total_usd,
        linked_outcome_count=len(linked),
        unlinked_outcome_count=len(unlinked),
        avg_cost_per_linked=avg_per_linked,
        by_type=by_type,
        by_cluster=by_cluster,
    )


def _compute_cluster_attribution(
    db: Session,
    *,
    project_id: str,
    linked_outcomes: list[OutcomeEvent],
    unlinked_outcomes: list[OutcomeEvent],
    window_days: int,
) -> list[AttributionClusterRow]:
    """Group linked outcomes by (agent_name, detector) via call + diagnosis_job join."""
    if not linked_outcomes:
        rows: list[AttributionClusterRow] = []
        if unlinked_outcomes:
            rows.append(_make_unlinked_row(unlinked_outcomes, window_days))
        return rows

    call_ids = list({o.call_id for o in linked_outcomes if o.call_id})

    # Fetch relevant calls
    calls_map: dict[str, Call] = {}
    if call_ids:
        call_rows = db.execute(
            select(Call).where(
                Call.id.in_(call_ids),
                Call.project_id == project_id,
            )
        ).scalars().all()
        calls_map = {c.id: c for c in call_rows}

    # Fetch diagnosis_jobs for those call_ids (agent_name + detector from payload_json)
    diag_map: dict[str, str | None] = {}  # call_id → detector type
    if call_ids:
        dj_rows = db.execute(
            select(DiagnosisJob).where(
                DiagnosisJob.call_id.in_(call_ids),
                DiagnosisJob.tenant_id == project_id,
            )
        ).scalars().all()
        for dj in dj_rows:
            if dj.call_id and dj.call_id not in diag_map:
                detector = _extract_detector(dj.payload_json or "{}")
                diag_map[dj.call_id] = detector

    # Group outcomes by cluster key
    ClusterKey = tuple[str | None, str | None]  # (agent_name, detector)
    cluster_agg: dict[ClusterKey, dict] = {}

    for o in linked_outcomes:
        call = calls_map.get(o.call_id or "")
        agent = (call.agent_name if call else None) or "unknown"
        detector = diag_map.get(o.call_id or "")
        key: ClusterKey = (agent, detector)
        bucket = cluster_agg.setdefault(key, {
            "usd": 0.0, "count": 0, "failures": set(), "types": {}
        })
        bucket["usd"] += float(o.amount_usd)
        bucket["count"] += 1
        bucket["failures"].add(o.call_id)
        t = bucket["types"]
        t[o.outcome_type] = t.get(o.outcome_type, 0) + 1

    result: list[AttributionClusterRow] = []
    for (agent, detector), b in sorted(
        cluster_agg.items(), key=lambda kv: -kv[1]["usd"]
    ):
        monthly = b["usd"] * (30.0 / max(window_days, 1))
        top_type = max(b["types"], key=lambda t: b["types"][t]) if b["types"] else None
        result.append(
            AttributionClusterRow(
                agent_name=agent,
                detector=detector,
                outcome_cost_usd=b["usd"],
                outcome_count=b["count"],
                failure_count=len(b["failures"]),
                estimated_monthly_savings_usd=round(monthly, 2),
                top_outcome_type=top_type,
            )
        )

    if unlinked_outcomes:
        result.append(_make_unlinked_row(unlinked_outcomes, window_days))

    return result


def _make_unlinked_row(
    outcomes: list[OutcomeEvent], window_days: int
) -> AttributionClusterRow:
    total = sum(float(o.amount_usd) for o in outcomes)
    types: dict[str, int] = {}
    for o in outcomes:
        types[o.outcome_type] = types.get(o.outcome_type, 0) + 1
    top_type = max(types, key=lambda t: types[t]) if types else None
    monthly = total * (30.0 / max(window_days, 1))
    return AttributionClusterRow(
        agent_name=None,
        detector=None,
        outcome_cost_usd=total,
        outcome_count=len(outcomes),
        failure_count=0,
        estimated_monthly_savings_usd=round(monthly, 2),
        top_outcome_type=top_type,
    )


def _extract_detector(payload_json: str) -> str | None:
    try:
        data = json.loads(payload_json)
        return data.get("detector") or data.get("detector_type") or data.get("type")
    except (json.JSONDecodeError, AttributeError):
        return None


# ── Call-level view ────────────────────────────────────────────────────────────


def get_call_outcomes(
    db: Session,
    *,
    project_id: str,
    call_id: str,
) -> list[CallOutcomeView]:
    """Return all outcome events linked to a specific call."""
    rows = db.execute(
        select(OutcomeEvent).where(
            OutcomeEvent.project_id == project_id,
            OutcomeEvent.call_id == call_id,
        ).order_by(OutcomeEvent.occurred_at)
    ).scalars().all()
    return [
        CallOutcomeView(
            id=r.id,
            outcome_type=r.outcome_type,
            amount_usd=float(r.amount_usd),
            source=r.source,
            occurred_at=r.occurred_at,
            external_ref=r.external_ref,
        )
        for r in rows
    ]


# ── Replay savings ─────────────────────────────────────────────────────────────


def get_replay_prevented_savings(
    db: Session,
    *,
    project_id: str,
    run_id: str,
) -> float:
    """Sum outcome costs for calls fixed by this replay run.

    A 'fixed' trace is one where replay_run_traces.status = 'pass' AND the
    original golden_trace.call_id has linked outcome_events.  The sum is the
    dollar value Pilot would prevent if the candidate prompt/model ships.
    """
    result = db.execute(
        select(func.coalesce(func.sum(OutcomeEvent.amount_usd), 0)).select_from(
            ReplayRunTrace.__table__
            .join(
                GoldenTrace.__table__,
                ReplayRunTrace.golden_trace_id == GoldenTrace.id,
            )
            .join(
                OutcomeEvent.__table__,
                (OutcomeEvent.call_id == GoldenTrace.call_id)
                & (OutcomeEvent.project_id == project_id),
            )
        ).where(
            ReplayRunTrace.replay_run_id == run_id,
            ReplayRunTrace.status == "pass",
            GoldenTrace.call_id.isnot(None),
        )
    ).scalar()
    return float(result or 0)
