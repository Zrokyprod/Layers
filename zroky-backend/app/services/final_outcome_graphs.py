from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FinalAssurancePack, FinalObservation, FinalOutcomeGraph, FinalWorkflowIntent
from app.domain.outcome_graph import build_outcome_graph_snapshot, classify_outcome_graph_snapshot


FINAL_OUTCOME_CLASSIFICATIONS = {
    "verified",
    "wrong",
    "missing",
    "stale",
    "duplicate",
    "conflicted",
    "forbidden",
    "unknown",
    "pending",
}
FINAL_OUTCOME_REASON_CODES = {"no_connector", "runner_offline", "no_sor_trace", "sor_unreachable"}
_TERMINAL_CLASSIFICATIONS = {"verified", "wrong", "missing", "forbidden"}
_FAILED_CLASSIFICATIONS = {"wrong", "missing", "forbidden", "duplicate"}
MAX_RECHECKS = 5


def graph_digest(graph: dict[str, Any]) -> str:
    return hashlib.sha256(_json(graph).encode("utf-8")).hexdigest()


def apply_outcome_graph_ledger_state(
    row: FinalOutcomeGraph,
    graph: dict[str, Any],
    *,
    now: datetime | None = None,
    verification_window_seconds: int,
) -> None:
    current = now or datetime.now(timezone.utc)
    classification = _classification(graph)
    row.classification = classification
    row.reason_code = _reason_code(graph, classification)
    row.last_checked_at = current
    row.verification_status = _verification_status(classification)
    row.verified_at = current if classification == "verified" else None
    row.next_check_at = (
        current + timedelta(seconds=max(1, int(verification_window_seconds)))
        if classification in {"pending", "unknown"}
        else None
    )


def recheck_due_outcome_graphs(
    db: Session,
    *,
    now: datetime | None = None,
    limit: int = 100,
    verification_window_seconds: int,
) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    rows = list(
        db.execute(
            select(FinalOutcomeGraph)
            .where(
                FinalOutcomeGraph.classification.in_(("pending", "unknown")),
                FinalOutcomeGraph.next_check_at.is_not(None),
                FinalOutcomeGraph.next_check_at <= current,
            )
            .order_by(FinalOutcomeGraph.next_check_at, FinalOutcomeGraph.id)
            .limit(max(1, min(int(limit), 100)))
        ).scalars()
    )
    updated = 0
    for row in rows:
        graph = _loads(row.graph_json)
        recheck_count = int(graph.get("recheck_count") or 0) + 1
        if recheck_count > MAX_RECHECKS:
            graph["classification"] = "unknown"
            graph["recheck_count"] = recheck_count
            row.reason_code = "no_sor_trace"
            row.classification = "unknown"
            row.verification_status = "inconclusive"
            row.last_checked_at = current
            row.next_check_at = None
            row.graph_json = _json(graph)
            row.graph_digest = graph_digest(graph)
            db.add(row)
            updated += 1
            continue
        snapshot = rebuild_outcome_graph_snapshot(db, row)
        if snapshot is None:
            graph["recheck_count"] = recheck_count
            graph["reason_code"] = "no_sor_trace"
        else:
            graph = snapshot
            graph["recheck_count"] = recheck_count
        row.graph_json = _json(graph)
        row.graph_digest = graph_digest(graph)
        apply_outcome_graph_ledger_state(
            row,
            graph,
            now=current,
            verification_window_seconds=verification_window_seconds,
        )
        db.add(row)
        updated += 1
    if updated:
        db.commit()
    return {"checked": len(rows), "updated": updated}


def rebuild_outcome_graph_snapshot(db: Session, row: FinalOutcomeGraph) -> dict[str, Any] | None:
    current = _loads(row.graph_json)
    intent = db.execute(
        select(FinalWorkflowIntent).where(
            FinalWorkflowIntent.id == row.intent_id,
            FinalWorkflowIntent.project_id == row.project_id,
        )
    ).scalar_one_or_none()
    if intent is None:
        return None
    pack = _pack_for_graph(db, row, current)
    if pack is None:
        return None
    graph = build_outcome_graph_snapshot(
        intent=_loads(intent.intent_json),
        assurance_pack=_loads(pack.pack_json),
        observations=_observation_payloads(
            db,
            project_id=row.project_id,
            environment=row.environment,
            intent_id=row.intent_id,
        ),
    )
    for key in ("run_id", "intent_id", "assurance_pack_id"):
        if key in current:
            graph[key] = current[key]
    return graph


def _pack_for_graph(db: Session, row: FinalOutcomeGraph, graph: dict[str, Any]) -> FinalAssurancePack | None:
    query = select(FinalAssurancePack).where(
        FinalAssurancePack.project_id == row.project_id,
        FinalAssurancePack.environment == row.environment,
    )
    assurance_pack_id = graph.get("assurance_pack_id")
    if isinstance(assurance_pack_id, str) and assurance_pack_id:
        query = query.where(FinalAssurancePack.id == assurance_pack_id)
    else:
        query = query.where(
            FinalAssurancePack.workflow_key == graph.get("workflow_key"),
            FinalAssurancePack.version == graph.get("pack_version"),
        )
    return db.execute(query.order_by(FinalAssurancePack.created_at.desc())).scalars().first()


def _observation_payloads(
    db: Session,
    *,
    project_id: str,
    environment: str,
    intent_id: str,
) -> list[dict[str, Any]]:
    rows = db.execute(
        select(FinalObservation)
        .where(
            FinalObservation.project_id == project_id,
            FinalObservation.environment == environment,
            FinalObservation.intent_id == intent_id,
        )
        .order_by(FinalObservation.observed_at.asc(), FinalObservation.created_at.asc())
    ).scalars()
    payloads: list[dict[str, Any]] = []
    for row in rows:
        payload = _loads(row.observation_json)
        payload["observation_digest"] = row.observation_digest
        payloads.append(payload)
    return payloads


def _classification(graph: dict[str, Any]) -> str:
    if int(graph.get("observation_count") or 0) == 0:
        return "pending"
    value = str(graph.get("classification") or classify_outcome_graph_snapshot(graph))
    return value if value in FINAL_OUTCOME_CLASSIFICATIONS else "unknown"


def _verification_status(classification: str) -> str:
    if classification == "verified":
        return "verified"
    if classification in _FAILED_CLASSIFICATIONS:
        return "failed"
    if classification in {"pending"}:
        return "pending"
    return "inconclusive"


def _reason_code(graph: dict[str, Any], classification: str) -> str | None:
    explicit = graph.get("reason_code")
    if explicit in FINAL_OUTCOME_REASON_CODES:
        return str(explicit)
    if classification not in {"pending", "unknown"}:
        return None
    effects = graph.get("actual_effects")
    if isinstance(effects, list) and any(isinstance(item, dict) and item.get("source_binding") is None for item in effects):
        return "no_connector"
    return "no_sor_trace"


def _loads(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        payload = json.loads(value)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _json(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
