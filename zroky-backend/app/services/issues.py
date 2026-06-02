"""Public issue service backed by internal `Anomaly` rows.

The legacy `issues` table is now migration/input compatibility only. New
runtime writes go through `anomalies`, while `/v1/issues` keeps the stable
customer-facing vocabulary.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Anomaly
from app.services.anomalies import (
    compute_fingerprint,
    map_failure_code_to_detector,
    upsert_anomaly,
)
from app.services.issue_projection import (
    ANOMALY_MUTED,
    ANOMALY_OPEN,
    ANOMALY_RESOLVED,
    PUBLIC_IGNORED,
    PUBLIC_ISSUE_STATUSES,
    PUBLIC_OPEN,
    PUBLIC_RESOLVED,
    issue_projection_from_anomaly,
    legacy_issue_payload,
    safe_json_object,
)

VALID_STATUSES = PUBLIC_ISSUE_STATUSES
_UNCHANGED = object()


def _existing_anomaly(
    db: Session,
    *,
    project_id: str,
    detector: str,
    prompt_fingerprint: str | None,
    agent_name: str | None,
) -> Anomaly | None:
    fingerprint = compute_fingerprint(
        detector=detector,
        prompt_fingerprint=prompt_fingerprint,
        agent_name=agent_name,
    )
    return db.execute(
        select(Anomaly).where(
            Anomaly.project_id == project_id,
            Anomaly.fingerprint == fingerprint,
        )
    ).scalar_one_or_none()


def _legacy_blast_radius(anomaly: Anomaly | None) -> float:
    if anomaly is None:
        return 0.0
    evidence = safe_json_object(anomaly.evidence_json)
    legacy = evidence.get("legacy_issue")
    if isinstance(legacy, dict):
        try:
            return float(legacy.get("blast_radius_usd") or 0.0)
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def upsert_issue(
    db: Session,
    *,
    project_id: str,
    failure_code: str,
    prompt_fingerprint: str | None,
    agent_name: str | None,
    call_id: str,
    diagnosis_id: str,
    occurred_at: datetime,
    call_cost_usd: float = 0.0,
    evidence: dict[str, Any] | None = None,
) -> Anomaly | None:
    """Upsert a public issue into the canonical anomalies table."""
    detector = map_failure_code_to_detector(failure_code)
    if detector is None:
        return None

    existing = _existing_anomaly(
        db,
        project_id=project_id,
        detector=detector,
        prompt_fingerprint=prompt_fingerprint,
        agent_name=agent_name,
    )
    cumulative_blast = _legacy_blast_radius(existing) + float(call_cost_usd or 0.0)
    sample_evidence_json = (
        json.dumps(evidence, separators=(",", ":")) if evidence else None
    )
    enriched = dict(evidence or {})
    enriched.update(
        {
            "failure_code": failure_code,
            "prompt_fingerprint": prompt_fingerprint,
            "agent_name": agent_name,
            "call_id": call_id,
            "diagnosis_id": diagnosis_id,
            "blast_radius_usd": cumulative_blast,
            "legacy_issue": legacy_issue_payload(
                failure_code=failure_code,
                prompt_fingerprint=prompt_fingerprint,
                agent_name=agent_name,
                call_id=call_id or None,
                diagnosis_id=diagnosis_id or None,
                call_cost_usd=cumulative_blast,
                sample_evidence_json=sample_evidence_json,
            ),
        }
    )
    return upsert_anomaly(
        db,
        project_id=project_id,
        detector=detector,
        prompt_fingerprint=prompt_fingerprint,
        agent_name=agent_name,
        call_id=call_id or None,
        occurred_at=occurred_at,
        evidence=enriched,
    )


def _update_anomaly_as_issue(
    db: Session,
    *,
    project_id: str,
    issue_id: str,
    public_status: str,
    fix_id: str | None = None,
    resolution_source: str | None = None,
) -> Anomaly | None:
    anomaly = db.execute(
        select(Anomaly).where(Anomaly.project_id == project_id, Anomaly.id == issue_id)
    ).scalar_one_or_none()
    if anomaly is None:
        return None

    now = datetime.now(timezone.utc)
    evidence = safe_json_object(anomaly.evidence_json)
    legacy = evidence.get("legacy_issue")
    if not isinstance(legacy, dict):
        legacy = {}

    if public_status == PUBLIC_RESOLVED:
        anomaly.status = ANOMALY_RESOLVED
        legacy["resolved_at"] = now.isoformat()
        legacy["resolution_source"] = resolution_source or "manual"
        if fix_id:
            legacy["last_fix_id"] = fix_id
    elif public_status == PUBLIC_IGNORED:
        anomaly.status = ANOMALY_MUTED
    else:
        anomaly.status = ANOMALY_OPEN
        legacy["resolved_at"] = None

    evidence["legacy_issue"] = legacy
    anomaly.evidence_json = json.dumps(evidence, separators=(",", ":"))
    anomaly.updated_at = now
    db.add(anomaly)
    db.commit()
    db.refresh(anomaly)
    return anomaly


def resolve_issue(
    db: Session,
    *,
    project_id: str,
    issue_id: str,
    fix_id: str | None = None,
    resolution_source: str = "manual",
) -> Anomaly | None:
    """Mark a public issue as resolved on the canonical anomaly row."""
    return _update_anomaly_as_issue(
        db,
        project_id=project_id,
        issue_id=issue_id,
        public_status=PUBLIC_RESOLVED,
        fix_id=fix_id,
        resolution_source=resolution_source,
    )


def ignore_issue(
    db: Session,
    *,
    project_id: str,
    issue_id: str,
) -> Anomaly | None:
    """Mark a public issue as ignored by muting the canonical anomaly."""
    return _update_anomaly_as_issue(
        db,
        project_id=project_id,
        issue_id=issue_id,
        public_status=PUBLIC_IGNORED,
    )


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def update_issue_triage(
    db: Session,
    *,
    project_id: str,
    issue_id: str,
    assigned_to: str | None | object = _UNCHANGED,
    deploy_pr_url: str | None | object = _UNCHANGED,
) -> Anomaly | None:
    """Persist customer-facing issue triage metadata on the canonical anomaly."""
    anomaly = db.execute(
        select(Anomaly).where(Anomaly.project_id == project_id, Anomaly.id == issue_id)
    ).scalar_one_or_none()
    if anomaly is None:
        return None

    now = datetime.now(timezone.utc)
    evidence = safe_json_object(anomaly.evidence_json)
    triage = evidence.get("issue_triage")
    if not isinstance(triage, dict):
        triage = {}

    if assigned_to is not _UNCHANGED:
        cleaned = _clean_optional_text(assigned_to if isinstance(assigned_to, str) else None)
        if cleaned is None:
            triage.pop("assigned_to", None)
        else:
            triage["assigned_to"] = cleaned

    if deploy_pr_url is not _UNCHANGED:
        cleaned = _clean_optional_text(deploy_pr_url if isinstance(deploy_pr_url, str) else None)
        if cleaned is None:
            triage.pop("deploy_pr_url", None)
        else:
            triage["deploy_pr_url"] = cleaned

    triage["updated_at"] = now.isoformat()
    evidence["issue_triage"] = triage
    anomaly.evidence_json = json.dumps(evidence, separators=(",", ":"))
    anomaly.updated_at = now
    db.add(anomaly)
    db.commit()
    db.refresh(anomaly)
    return anomaly


def project_issue(anomaly: Anomaly):
    return issue_projection_from_anomaly(anomaly)
