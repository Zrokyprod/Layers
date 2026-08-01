from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import exists, literal, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import FinalAgentRun, FinalAssurancePack, FinalObservation, FinalOutcomeGraph, FinalOutcomeIncident, FinalWorkflowIntent
from app.domain.incident import build_incident_from_outcome_graph
from app.domain.outcome_graph import build_outcome_graph_snapshot, classify_outcome_graph_snapshot
from app.services.audit_logs import AUDIT_ACTION_RESOLVED, add_audit_log
from app.services.final_observation_pull import ObservationPullError, active_source_connector, pull_observation


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
RECHECK_BACKOFF_SECONDS = (60, 300, 900, 3600, 21600)


def graph_digest(graph: dict[str, Any]) -> str:
    return hashlib.sha256(_json(graph).encode("utf-8")).hexdigest()


def active_assurance_pack(
    db: Session,
    *,
    project_id: str,
    environment: str,
    workflow_key: str | None = None,
    assurance_pack_id: str | None = None,
) -> FinalAssurancePack | None:
    query = select(FinalAssurancePack).where(
        FinalAssurancePack.project_id == project_id,
        FinalAssurancePack.environment == environment,
        FinalAssurancePack.status == "active",
    )
    if assurance_pack_id:
        query = query.where(FinalAssurancePack.id == assurance_pack_id)
    elif workflow_key:
        query = query.where(FinalAssurancePack.workflow_key == workflow_key)
    else:
        return None
    return db.execute(query.order_by(FinalAssurancePack.created_at.desc())).scalars().first()


def ensure_initial_outcome_graph(
    db: Session,
    *,
    run: FinalAgentRun,
    intent: FinalWorkflowIntent,
    pack: FinalAssurancePack,
    verification_window_seconds: int,
    refresh_existing: bool = False,
) -> tuple[FinalOutcomeGraph, bool]:
    key = f"initial:{run.id}:{intent.id}"
    existing = db.execute(
        select(FinalOutcomeGraph).where(
            FinalOutcomeGraph.project_id == run.project_id,
            FinalOutcomeGraph.environment == run.environment,
            FinalOutcomeGraph.idempotency_key == key,
        )
    ).scalar_one_or_none()
    if existing is not None:
        if refresh_existing:
            graph = _initial_graph_snapshot(db, run=run, intent=intent, pack=pack)
            digest = graph_digest(graph)
            if existing.classification not in {"pending", "unknown"} and existing.graph_digest != digest:
                snapshot_key = f"snapshot:{run.id}:{intent.id}:{digest}"
                snapshot = db.execute(
                    select(FinalOutcomeGraph).where(
                        FinalOutcomeGraph.project_id == run.project_id,
                        FinalOutcomeGraph.environment == run.environment,
                        FinalOutcomeGraph.idempotency_key == snapshot_key,
                    )
                ).scalar_one_or_none()
                if snapshot is not None:
                    return snapshot, False
                snapshot = _new_graph_row(
                    run=run,
                    intent=intent,
                    graph=graph,
                    idempotency_key=snapshot_key,
                    verification_window_seconds=verification_window_seconds,
                )
                try:
                    with db.begin_nested():
                        db.add(snapshot)
                        db.flush()
                        _open_actionable_incident(db, snapshot, graph)
                except IntegrityError:
                    snapshot = db.execute(
                        select(FinalOutcomeGraph).where(
                            FinalOutcomeGraph.project_id == run.project_id,
                            FinalOutcomeGraph.environment == run.environment,
                            FinalOutcomeGraph.idempotency_key == snapshot_key,
                        )
                    ).scalar_one()
                    return snapshot, False
                return snapshot, True
            previous_classification = existing.classification
            existing.graph_json = _json(graph)
            existing.graph_digest = digest
            apply_outcome_graph_ledger_state(
                existing,
                graph,
                verification_window_seconds=verification_window_seconds,
            )
            db.add(existing)
            if previous_classification != "verified" and existing.classification == "verified":
                _resolve_recovering_incidents(
                    db,
                    existing,
                    now=existing.last_checked_at or datetime.now(timezone.utc),
                )
            else:
                _open_actionable_incident(db, existing, graph)
        return existing, False

    graph = _initial_graph_snapshot(db, run=run, intent=intent, pack=pack)
    row = _new_graph_row(
        run=run,
        intent=intent,
        graph=graph,
        idempotency_key=key,
        verification_window_seconds=verification_window_seconds,
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
            _open_actionable_incident(db, row, graph)
    except IntegrityError:
        existing = db.execute(
            select(FinalOutcomeGraph).where(
                FinalOutcomeGraph.project_id == run.project_id,
                FinalOutcomeGraph.environment == run.environment,
                FinalOutcomeGraph.idempotency_key == key,
            )
        ).scalar_one()
        return existing, False
    return row, True


def _new_graph_row(
    *,
    run: FinalAgentRun,
    intent: FinalWorkflowIntent,
    graph: dict[str, Any],
    idempotency_key: str,
    verification_window_seconds: int,
) -> FinalOutcomeGraph:
    row = FinalOutcomeGraph(
        project_id=run.project_id,
        environment=run.environment,
        intent_id=intent.id,
        idempotency_key=idempotency_key,
        graph_digest=graph_digest(graph),
        graph_json=_json(graph),
    )
    apply_outcome_graph_ledger_state(
        row,
        graph,
        verification_window_seconds=verification_window_seconds,
    )
    return row


def _initial_graph_snapshot(
    db: Session,
    *,
    run: FinalAgentRun,
    intent: FinalWorkflowIntent,
    pack: FinalAssurancePack,
) -> dict[str, Any]:
    graph = build_outcome_graph_snapshot(
        intent=_loads(intent.intent_json),
        assurance_pack=_loads(pack.pack_json),
        observations=_observation_payloads(
            db,
            project_id=run.project_id,
            environment=run.environment,
            intent_id=intent.id,
        ),
    )
    graph.update({"run_id": run.id, "intent_id": intent.id, "assurance_pack_id": pack.id})
    return graph


def create_missing_outcome_graphs(
    db: Session,
    *,
    limit: int,
    verification_window_seconds: int,
) -> int:
    key = literal("initial:") + FinalAgentRun.id + literal(":") + FinalAgentRun.intent_id
    rows = list(
        db.execute(
            select(FinalAgentRun, FinalWorkflowIntent)
            .join(
                FinalWorkflowIntent,
                (FinalWorkflowIntent.id == FinalAgentRun.intent_id)
                & (FinalWorkflowIntent.project_id == FinalAgentRun.project_id),
            )
            .where(
                FinalAgentRun.intent_id.is_not(None),
                exists(
                    select(FinalAssurancePack.id).where(
                        FinalAssurancePack.project_id == FinalAgentRun.project_id,
                        FinalAssurancePack.environment == FinalAgentRun.environment,
                        FinalAssurancePack.workflow_key == FinalAgentRun.workflow_key,
                        FinalAssurancePack.status == "active",
                    )
                ),
                ~exists(
                    select(FinalOutcomeGraph.id).where(
                        FinalOutcomeGraph.project_id == FinalAgentRun.project_id,
                        FinalOutcomeGraph.environment == FinalAgentRun.environment,
                        FinalOutcomeGraph.idempotency_key == key,
                    )
                ),
            )
            .order_by(FinalAgentRun.created_at)
            .limit(max(1, min(int(limit), 100)))
        ).all()
    )
    created = 0
    for run, intent in rows:
        pack = active_assurance_pack(
            db,
            project_id=run.project_id,
            environment=run.environment,
            workflow_key=run.workflow_key,
        )
        if pack is None:
            continue
        _, was_created = ensure_initial_outcome_graph(
            db,
            run=run,
            intent=intent,
            pack=pack,
            verification_window_seconds=verification_window_seconds,
        )
        created += int(was_created)
    if created:
        db.commit()
    return created


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
    if classification in {"pending", "unknown"}:
        row.next_check_at = current + timedelta(
            seconds=recheck_backoff_seconds(int(graph.get("recheck_count") or 0), default_seconds=verification_window_seconds)
        )
    else:
        row.next_check_at = None


def recheck_due_outcome_graphs(
    db: Session,
    *,
    now: datetime | None = None,
    limit: int = 100,
    project_id: str | None = None,
    verification_window_seconds: int,
    observation_pull_max_per_sweep: int = 50,
) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    query = select(FinalOutcomeGraph).where(
        FinalOutcomeGraph.classification.in_(("pending", "unknown")),
        FinalOutcomeGraph.next_check_at.is_not(None),
        FinalOutcomeGraph.next_check_at <= current,
    )
    if project_id is not None:
        query = query.where(FinalOutcomeGraph.project_id == project_id)
    rows = list(
        db.execute(
            query.order_by(FinalOutcomeGraph.next_check_at, FinalOutcomeGraph.id).limit(max(1, min(int(limit), 100)))
        ).scalars()
    )
    updated = 0
    pull_budget = max(0, int(observation_pull_max_per_sweep))
    for row in rows:
        previous_classification = row.classification
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
            _open_actionable_incident(db, row, graph)
            updated += 1
            continue
        pull_status = _pull_missing_observations(db, row, graph=graph, pull_budget=pull_budget)
        pull_budget = pull_status["remaining_budget"]
        if pull_status["error"]:
            graph["recheck_count"] = recheck_count
            graph["reason_code"] = "sor_unreachable"
        else:
            snapshot = rebuild_outcome_graph_snapshot(db, row)
            if snapshot is None:
                graph["recheck_count"] = recheck_count
                graph["reason_code"] = "no_connector" if pull_status["missing_connector"] else "no_sor_trace"
            else:
                graph = snapshot
                graph["recheck_count"] = recheck_count
                if pull_status["missing_connector"]:
                    graph["reason_code"] = "no_connector"
        row.graph_json = _json(graph)
        row.graph_digest = graph_digest(graph)
        apply_outcome_graph_ledger_state(
            row,
            graph,
            now=current,
            verification_window_seconds=verification_window_seconds,
        )
        db.add(row)
        if previous_classification != "verified" and row.classification == "verified":
            _resolve_recovering_incidents(db, row, now=current)
        else:
            _open_actionable_incident(db, row, graph)
        updated += 1
    if updated:
        db.commit()
    return {"checked": len(rows), "updated": updated}


def recheck_backoff_seconds(attempt_count: int, *, default_seconds: int = 300) -> int:
    if attempt_count <= 0:
        return max(1, int(default_seconds))
    return RECHECK_BACKOFF_SECONDS[min(attempt_count - 1, len(RECHECK_BACKOFF_SECONDS) - 1)]


def _pull_missing_observations(
    db: Session,
    row: FinalOutcomeGraph,
    *,
    graph: dict[str, Any],
    pull_budget: int,
) -> dict[str, Any]:
    pack = _pack_for_graph(db, row, graph)
    if pack is None:
        return {"remaining_budget": pull_budget, "missing_connector": False, "error": False}
    pack_payload = _loads(pack.pack_json)
    bindings = [binding for binding in pack_payload.get("source_bindings", []) if isinstance(binding, dict)]
    observations = _observation_payloads(
        db,
        project_id=row.project_id,
        environment=row.environment,
        intent_id=row.intent_id,
    )
    missing_connector = False
    for binding in bindings:
        if pull_budget <= 0:
            break
        if _has_fresh_observation(observations, str(binding.get("key") or "")):
            continue
        if active_source_connector(db, graph=row, binding=binding) is None:
            missing_connector = True
            continue
        try:
            pulled = pull_observation(db, graph=row, binding=binding)
        except ObservationPullError:
            return {"remaining_budget": pull_budget, "missing_connector": missing_connector, "error": True}
        pull_budget -= 1
        if pulled is not None:
            payload = _loads(pulled.observation_json)
            payload["observation_digest"] = pulled.observation_digest
            observations.append(payload)
    return {"remaining_budget": pull_budget, "missing_connector": missing_connector, "error": False}


def _has_fresh_observation(observations: list[dict[str, Any]], source_binding: str) -> bool:
    for observation in observations:
        provenance = observation.get("provenance")
        freshness = observation.get("freshness")
        if (
            isinstance(provenance, dict)
            and provenance.get("source_binding") == source_binding
            and isinstance(freshness, dict)
            and freshness.get("fresh") is True
        ):
            return True
    return False


def _resolve_recovering_incidents(db: Session, row: FinalOutcomeGraph, *, now: datetime) -> None:
    incidents = list(
        db.execute(
            select(FinalOutcomeIncident).where(
                FinalOutcomeIncident.project_id == row.project_id,
                FinalOutcomeIncident.environment == row.environment,
                FinalOutcomeIncident.outcome_graph_id == row.id,
                FinalOutcomeIncident.status == "recovering",
            )
        ).scalars()
    )
    for incident in incidents:
        incident.status = "resolved"
        incident.resolved_at = now
        add_audit_log(
            db,
            tenant_id=row.project_id,
            diagnosis_id=incident.id,
            action=AUDIT_ACTION_RESOLVED,
            actor_subject="system:outcome-graph-sweep",
            metadata={
                "incident_id": incident.id,
                "outcome_graph_id": row.id,
                "classification": row.classification,
                "resolved_by": "outcome_graph_recheck",
            },
        )
        db.add(incident)


def _open_actionable_incident(db: Session, row: FinalOutcomeGraph, graph: dict[str, Any]) -> None:
    if row.classification in {None, "pending", "verified"}:
        return
    existing = db.execute(
        select(FinalOutcomeIncident.id).where(
            FinalOutcomeIncident.project_id == row.project_id,
            FinalOutcomeIncident.environment == row.environment,
            FinalOutcomeIncident.outcome_graph_id == row.id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return
    incident = build_incident_from_outcome_graph(row.id, graph)
    db.add(
        FinalOutcomeIncident(
            project_id=row.project_id,
            environment=row.environment,
            outcome_graph_id=row.id,
            severity=incident["severity"],
            status="open",
            incident_json=_json(incident),
        )
    )


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
