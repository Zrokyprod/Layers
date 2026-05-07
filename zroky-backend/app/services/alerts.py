from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import DiagnosisJob, ProjectAlert
from app.services.dashboard_data import extract_result, severity_for_category


def _safe_load_json(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
        return parsed
    return None


def alert_to_payload(alert: ProjectAlert) -> dict[str, Any]:
    return {
        "alert_id": alert.id,
        "diagnosis_id": alert.diagnosis_id,
        "category": alert.category,
        "severity": alert.severity,
        "status": alert.status,
        "source": alert.source,
        "title": alert.title,
        "evidence": _safe_load_json(alert.evidence_json),
        "created_at": alert.created_at,
        "updated_at": alert.updated_at,
        "resolved_at": alert.resolved_at,
    }


def sync_alerts_from_jobs(db: Session, tenant_id: str, jobs: Sequence[DiagnosisJob]) -> int:
    if not jobs:
        return 0

    diagnosis_ids = list({job.diagnosis_id for job in jobs})
    existing_alerts = db.execute(
        select(ProjectAlert).where(
            ProjectAlert.tenant_id == tenant_id,
            ProjectAlert.diagnosis_id.in_(diagnosis_ids),
        )
    ).scalars().all()
    existing_keys = {(row.diagnosis_id, row.category) for row in existing_alerts}

    created = 0
    for job in jobs:
        result_payload = extract_result(job)
        diagnoses = result_payload.get("diagnoses")
        if not isinstance(diagnoses, list):
            continue

        for diagnosis in diagnoses:
            if not isinstance(diagnosis, Mapping):
                continue

            category_raw = diagnosis.get("category")
            if not isinstance(category_raw, str) or not category_raw.strip():
                continue
            category = category_raw.strip().upper()
            key = (job.diagnosis_id, category)
            if key in existing_keys:
                continue

            root_cause = diagnosis.get("root_cause")
            title = (
                str(root_cause).strip()
                if isinstance(root_cause, str) and root_cause.strip()
                else f"{category} detected"
            )
            evidence = diagnosis.get("evidence")
            evidence_json = json.dumps(evidence, separators=(",", ":")) if isinstance(evidence, Mapping) else None

            db.add(
                ProjectAlert(
                    tenant_id=tenant_id,
                    diagnosis_id=job.diagnosis_id,
                    category=category,
                    severity=severity_for_category(category),
                    status="OPEN",
                    source="diagnosis_engine",
                    title=title,
                    evidence_json=evidence_json,
                )
            )
            existing_keys.add(key)
            created += 1

    return created
