"""Pulls the smallest sufficient set of evidence rows for the synthesizer.

Strict rules:
    * Always scope by project_id (multi-tenant isolation).
    * Hard cap row counts so context stays small enough for Haiku.
    * Return primitive dicts only â€” no ORM objects leak to the synthesizer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.db.models import Anomaly, Call, DiagnosisJob
from app.services.issue_projection import issue_projection_from_anomaly
from .intent_router import Intent

_MAX_ROWS = 8


def _approval_href(key: str, value: str) -> str:
    return f"/approvals?{key}={quote(value, safe='')}"


def _evidence_href(key: str, value: str) -> str:
    return f"/evidence?{key}={quote(value, safe='')}"


@dataclass
class EvidenceLink:
    """A clickable pointer the UI renders next to the answer."""

    kind: str
    id: str
    label: str
    href: str


@dataclass
class EvidenceBundle:
    """Container handed to the synthesizer."""

    intent: str
    window_days: int
    summary: dict[str, Any] = field(default_factory=dict)
    rows: list[dict[str, Any]] = field(default_factory=list)
    links: list[EvidenceLink] = field(default_factory=list)


def collect_evidence(
    db: Session,
    *,
    project_id: str,
    intent: Intent,
    question: str,
    context: dict[str, Any],
) -> EvidenceBundle:
    bundle = EvidenceBundle(intent=intent.name, window_days=intent.window_days)
    since = datetime.now(timezone.utc) - timedelta(days=intent.window_days)

    # Resolve any context hints supplied by the UI (e.g. user opened a call
    # detail page and pressed "Ask about this call").
    ctx_call_id = str(context.get("call_id") or "").strip() or intent.call_id
    ctx_issue_id = (
        str(context.get("issue_id") or context.get("anomaly_id") or "").strip()
        or intent.issue_id
        or intent.anomaly_id
    )

    if ctx_call_id:
        _populate_call_context(db, project_id, ctx_call_id, bundle)
    if ctx_issue_id:
        _populate_issue_context(db, project_id, ctx_issue_id, bundle)

    if intent.name == "cost":
        _populate_cost(db, project_id, since, intent.agent_name, bundle)
    elif intent.name == "latency":
        _populate_latency(db, project_id, since, intent.agent_name, bundle)
    elif intent.name == "failure":
        _populate_failures(db, project_id, since, intent.agent_name, bundle)
    elif intent.name == "behavior":
        _populate_recent_calls(db, project_id, since, intent.agent_name, bundle)
    elif intent.name == "general":
        _populate_overview(db, project_id, since, bundle)

    return bundle


# â”€â”€ intent-specific population â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _populate_overview(
    db: Session, project_id: str, since: datetime, bundle: EvidenceBundle
) -> None:
    totals = db.execute(
        select(
            func.count(Call.id),
            func.coalesce(func.sum(Call.cost_total), 0),
            func.coalesce(
                func.sum(
                    func.case(
                        (Call.status == "error", 1),
                        else_=0,
                    )
                ),
                0,
            ),
        ).where(Call.project_id == project_id, Call.created_at >= since)
    ).one()
    total_calls, total_cost, error_count = totals
    bundle.summary["total_calls"] = int(total_calls or 0)
    bundle.summary["total_cost_usd"] = float(total_cost or 0)
    bundle.summary["error_count"] = int(error_count or 0)
    bundle.summary["error_rate"] = (
        float(error_count) / float(total_calls) if total_calls else 0.0
    )


def _populate_cost(
    db: Session,
    project_id: str,
    since: datetime,
    agent_name: str | None,
    bundle: EvidenceBundle,
) -> None:
    _populate_overview(db, project_id, since, bundle)

    stmt = (
        select(Call.id, Call.agent_name, Call.model, Call.cost_total, Call.created_at)
        .where(Call.project_id == project_id, Call.created_at >= since)
    )
    if agent_name:
        stmt = stmt.where(Call.agent_name == agent_name)
    stmt = stmt.order_by(desc(Call.cost_total)).limit(_MAX_ROWS)

    for call_id, agent, model, cost, created_at in db.execute(stmt).all():
        bundle.rows.append(
            {
                "call_id": call_id,
                "agent_name": agent,
                "model": model,
                "cost_usd": float(cost or 0),
                "created_at": _iso(created_at),
            }
        )
        bundle.links.append(
            EvidenceLink(
                kind="call",
                id=call_id,
                label=f"${float(cost or 0):.4f} Â· {agent or model or call_id[:8]}",
                href=_evidence_href("call_id", call_id),
            )
        )


def _populate_latency(
    db: Session,
    project_id: str,
    since: datetime,
    agent_name: str | None,
    bundle: EvidenceBundle,
) -> None:
    _populate_overview(db, project_id, since, bundle)

    stmt = (
        select(Call.id, Call.agent_name, Call.model, Call.latency_ms, Call.created_at)
        .where(
            Call.project_id == project_id,
            Call.created_at >= since,
            Call.latency_ms.isnot(None),
        )
    )
    if agent_name:
        stmt = stmt.where(Call.agent_name == agent_name)
    stmt = stmt.order_by(desc(Call.latency_ms)).limit(_MAX_ROWS)

    for call_id, agent, model, latency_ms, created_at in db.execute(stmt).all():
        bundle.rows.append(
            {
                "call_id": call_id,
                "agent_name": agent,
                "model": model,
                "latency_ms": float(latency_ms or 0),
                "created_at": _iso(created_at),
            }
        )
        bundle.links.append(
            EvidenceLink(
                kind="call",
                id=call_id,
                label=f"{float(latency_ms or 0):.0f}ms Â· {agent or model or call_id[:8]}",
                href=_evidence_href("call_id", call_id),
            )
        )


def _populate_failures(
    db: Session,
    project_id: str,
    since: datetime,
    agent_name: str | None,
    bundle: EvidenceBundle,
) -> None:
    _populate_overview(db, project_id, since, bundle)

    issue_stmt = (
        select(Anomaly)
        .where(
            Anomaly.project_id == project_id,
            Anomaly.last_seen_at >= since,
            Anomaly.status.in_(["open", "acknowledged"]),
        )
    )
    issue_stmt = issue_stmt.order_by(desc(Anomaly.last_seen_at)).limit(_MAX_ROWS * 3)

    for anomaly in db.execute(issue_stmt).scalars().all():
        row = issue_projection_from_anomaly(anomaly)
        if agent_name and row.agent_name != agent_name:
            continue
        bundle.rows.append(
            {
                "issue_id": row.id,
                "failure_code": row.failure_code,
                "agent_name": row.agent_name,
                "severity": row.severity,
                "occurrence_count": int(row.occurrence_count or 0),
                "blast_radius_usd": float(row.blast_radius_usd or 0),
                "last_seen_at": _iso(row.last_seen_at),
            }
        )
        bundle.links.append(
            EvidenceLink(
                kind="issue",
                id=row.id,
                label=f"{row.failure_code} Â· {row.agent_name or 'agent'} Â· {row.occurrence_count}Ã—",
                href=_approval_href("issue_id", row.id),
            )
        )
        if len(bundle.rows) >= _MAX_ROWS:
            break


def _populate_recent_calls(
    db: Session,
    project_id: str,
    since: datetime,
    agent_name: str | None,
    bundle: EvidenceBundle,
) -> None:
    _populate_overview(db, project_id, since, bundle)

    stmt = select(Call).where(Call.project_id == project_id, Call.created_at >= since)
    if agent_name:
        stmt = stmt.where(Call.agent_name == agent_name)
    stmt = stmt.order_by(desc(Call.created_at)).limit(_MAX_ROWS)

    for call in db.execute(stmt).scalars().all():
        bundle.rows.append(
            {
                "call_id": call.id,
                "agent_name": call.agent_name,
                "model": call.model,
                "status": call.status,
                "latency_ms": float(call.latency_ms) if call.latency_ms is not None else None,
                "cost_usd": float(call.cost_total or 0),
                "created_at": _iso(call.created_at),
            }
        )
        bundle.links.append(
            EvidenceLink(
                kind="call",
                id=call.id,
                label=f"{call.status} Â· {call.agent_name or call.model or call.id[:8]}",
                href=_evidence_href("call_id", call.id),
            )
        )


# â”€â”€ context-driven enrichment â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _populate_call_context(
    db: Session, project_id: str, call_id: str, bundle: EvidenceBundle
) -> None:
    call = db.execute(
        select(Call).where(Call.project_id == project_id, Call.id == call_id)
    ).scalar_one_or_none()
    if not call:
        return
    bundle.summary["focused_call"] = {
        "call_id": call.id,
        "agent_name": call.agent_name,
        "model": call.model,
        "status": call.status,
        "latency_ms": float(call.latency_ms) if call.latency_ms is not None else None,
        "cost_usd": float(call.cost_total or 0),
        "error_code": call.error_code,
        "created_at": _iso(call.created_at),
    }
    bundle.links.append(
        EvidenceLink(
            kind="call",
            id=call.id,
            label=f"This call Â· {call.status}",
            href=_evidence_href("call_id", call.id),
        )
    )

    diag_rows = db.execute(
        select(DiagnosisJob)
        .where(DiagnosisJob.tenant_id == project_id, DiagnosisJob.call_id == call_id)
        .order_by(desc(DiagnosisJob.created_at))
        .limit(3)
    ).scalars().all()
    if diag_rows:
        bundle.summary["focused_call_diagnoses"] = [
            {
                "diagnosis_id": d.diagnosis_id,
                "status": d.status,
                "agent_name": d.agent_name,
                "created_at": _iso(d.created_at),
            }
            for d in diag_rows
        ]


def _populate_issue_context(
    db: Session, project_id: str, issue_id: str, bundle: EvidenceBundle
) -> None:
    anomaly = db.execute(
        select(Anomaly).where(Anomaly.project_id == project_id, Anomaly.id == issue_id)
    ).scalar_one_or_none()
    if not anomaly:
        return
    issue = issue_projection_from_anomaly(anomaly)
    bundle.summary["focused_issue"] = {
        "issue_id": issue.id,
        "failure_code": issue.failure_code,
        "agent_name": issue.agent_name,
        "severity": issue.severity,
        "occurrence_count": int(issue.occurrence_count or 0),
        "blast_radius_usd": float(issue.blast_radius_usd or 0),
        "first_seen_at": _iso(issue.first_seen_at),
        "last_seen_at": _iso(issue.last_seen_at),
        "sample_call_id": issue.sample_call_id,
    }
    bundle.links.append(
        EvidenceLink(
            kind="issue",
            id=issue.id,
            label=f"This issue - {issue.failure_code}",
            href=_approval_href("issue_id", issue.id),
        )
    )
    if issue.sample_call_id:
        bundle.links.append(
            EvidenceLink(
                kind="call",
                id=issue.sample_call_id,
                label="Sample call",
                href=_evidence_href("call_id", issue.sample_call_id),
            )
        )


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()
