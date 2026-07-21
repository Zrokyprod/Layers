from __future__ import annotations

from typing import Any


SEVERITY_BY_CLASSIFICATION = {
    "forbidden": "critical",
    "conflicted": "high",
    "wrong": "high",
    "duplicate": "medium",
    "missing": "medium",
    "stale": "medium",
    "unknown": "low",
}


def build_incident_from_outcome_graph(graph_id: str, graph: dict[str, Any]) -> dict[str, Any]:
    classification = str(graph.get("classification") or "unknown")
    return {
        "schema_version": "zroky.outcome_incident.v1",
        "outcome_graph_id": graph_id,
        "run_id": graph.get("run_id"),
        "intent_id": graph.get("intent_id"),
        "workflow_key": graph.get("workflow_key"),
        "deviation_type": classification,
        "severity": SEVERITY_BY_CLASSIFICATION.get(classification, "low"),
        "owner_path": ["operations", "workflow_owner"],
        "next_action": "review_outcome_graph_and_select_manual_or_recovery_path",
        "reason": f"Outcome graph classified as {classification}.",
        "effects": graph.get("actual_effects", []),
    }
