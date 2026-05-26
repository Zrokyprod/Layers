"""Project canonical anomalies into the public `/v1/issues` contract."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.db.models import Anomaly

PUBLIC_OPEN = "open"
PUBLIC_RESOLVED = "resolved"
PUBLIC_IGNORED = "ignored"
PUBLIC_ISSUE_STATUSES = frozenset({PUBLIC_OPEN, PUBLIC_RESOLVED, PUBLIC_IGNORED})

ANOMALY_OPEN = "open"
ANOMALY_ACKNOWLEDGED = "acknowledged"
ANOMALY_RESOLVED = "resolved"
ANOMALY_MUTED = "muted"


@dataclass(frozen=True)
class IssueProjection:
    id: str
    project_id: str
    failure_code: str
    prompt_fingerprint: str | None
    agent_name: str | None
    status: str
    severity: str
    occurrence_count: int
    blast_radius_usd: float
    first_seen_at: datetime
    last_seen_at: datetime
    sample_call_id: str | None
    sample_diagnosis_id: str | None
    sample_evidence_json: str | None
    last_fix_id: str | None
    resolved_at: datetime | None
    resolution_source: str | None
    assigned_to: str | None
    deploy_pr_url: str | None
    created_at: datetime
    updated_at: datetime


def safe_json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def safe_json_array(raw: str | None) -> list[Any]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []


def public_status_from_anomaly(status: str | None) -> str:
    value = (status or "").lower()
    if value == ANOMALY_RESOLVED:
        return PUBLIC_RESOLVED
    if value == ANOMALY_MUTED:
        return PUBLIC_IGNORED
    return PUBLIC_OPEN


def anomaly_status_from_public(status: str) -> str:
    value = status.lower()
    if value == PUBLIC_RESOLVED:
        return ANOMALY_RESOLVED
    if value == PUBLIC_IGNORED:
        return ANOMALY_MUTED
    return ANOMALY_OPEN


def parse_optional_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _first_text(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _first_float(*values: Any) -> float:
    for value in values:
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _first_sample_call_id(anomaly: Anomaly, legacy: dict[str, Any]) -> str | None:
    explicit = _first_text(legacy.get("sample_call_id"))
    if explicit:
        return explicit
    ids = [str(item).strip() for item in safe_json_array(anomaly.sample_call_ids_json) if str(item).strip()]
    return ids[-1] if ids else None


def projection_evidence(anomaly: Anomaly) -> dict[str, Any]:
    evidence = safe_json_object(anomaly.evidence_json)
    legacy = evidence.get("legacy_issue")
    if not isinstance(legacy, dict):
        legacy = {}

    sample_evidence = legacy.get("sample_evidence_json")
    parsed_sample = safe_json_object(sample_evidence) if isinstance(sample_evidence, str) else {}
    if parsed_sample:
        merged = dict(parsed_sample)
        merged.update({key: value for key, value in evidence.items() if key != "legacy_issue"})
        merged["legacy_issue"] = legacy
        return merged
    return evidence


def issue_projection_from_anomaly(anomaly: Anomaly) -> IssueProjection:
    evidence = safe_json_object(anomaly.evidence_json)
    legacy = evidence.get("legacy_issue")
    if not isinstance(legacy, dict):
        legacy = {}
    triage = evidence.get("issue_triage")
    if not isinstance(triage, dict):
        triage = {}

    resolved_at = parse_optional_datetime(legacy.get("resolved_at"))
    sample_evidence_json = legacy.get("sample_evidence_json")
    if not isinstance(sample_evidence_json, str):
        sample_evidence_json = json.dumps(
            projection_evidence(anomaly), separators=(",", ":")
        )

    return IssueProjection(
        id=anomaly.id,
        project_id=anomaly.project_id,
        failure_code=_first_text(legacy.get("failure_code"), evidence.get("failure_code"), anomaly.detector)
        or anomaly.detector,
        prompt_fingerprint=_first_text(legacy.get("prompt_fingerprint"), evidence.get("prompt_fingerprint")),
        agent_name=_first_text(legacy.get("agent_name"), evidence.get("agent_name")),
        status=public_status_from_anomaly(anomaly.status),
        severity=anomaly.severity,
        occurrence_count=int(anomaly.occurrence_count or 0),
        blast_radius_usd=_first_float(
            legacy.get("blast_radius_usd"),
            evidence.get("blast_radius_usd"),
            evidence.get("cost_impact_usd"),
            evidence.get("cost_usd"),
        ),
        first_seen_at=anomaly.first_seen_at,
        last_seen_at=anomaly.last_seen_at,
        sample_call_id=_first_sample_call_id(anomaly, legacy),
        sample_diagnosis_id=_first_text(legacy.get("sample_diagnosis_id"), evidence.get("diagnosis_id")),
        sample_evidence_json=sample_evidence_json,
        last_fix_id=_first_text(legacy.get("last_fix_id"), evidence.get("last_fix_id")),
        resolved_at=resolved_at if anomaly.status == ANOMALY_RESOLVED else None,
        resolution_source=_first_text(legacy.get("resolution_source"), evidence.get("resolution_source")),
        assigned_to=_first_text(triage.get("assigned_to"), legacy.get("assigned_to")),
        deploy_pr_url=_first_text(triage.get("deploy_pr_url"), legacy.get("deploy_pr_url")),
        created_at=anomaly.created_at,
        updated_at=anomaly.updated_at,
    )


def legacy_issue_payload(
    *,
    failure_code: str,
    prompt_fingerprint: str | None,
    agent_name: str | None,
    call_id: str | None,
    diagnosis_id: str | None,
    call_cost_usd: float,
    sample_evidence_json: str | None,
    last_fix_id: str | None = None,
    resolved_at: datetime | None = None,
    resolution_source: str | None = None,
) -> dict[str, Any]:
    return {
        "failure_code": failure_code,
        "prompt_fingerprint": prompt_fingerprint,
        "agent_name": agent_name,
        "sample_call_id": call_id,
        "sample_diagnosis_id": diagnosis_id,
        "blast_radius_usd": call_cost_usd,
        "sample_evidence_json": sample_evidence_json,
        "last_fix_id": last_fix_id,
        "resolved_at": resolved_at.isoformat() if resolved_at else None,
        "resolution_source": resolution_source,
    }
