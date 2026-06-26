from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DiagnosisJob, ProjectAlert
from app.services.dashboard_data import extract_result, severity_for_category
from app.services.slack_integration import get_slack_install


ACTIONABLE_SLACK_SEVERITIES = {"critical", "high"}
PENDING_SLACK_DELIVERY_STATUS = "not_attempted"


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
        "slack_delivery_status": alert.slack_delivery_status,
        "slack_delivery_attempted_at": alert.slack_delivery_attempted_at,
        "slack_delivery_error": alert.slack_delivery_error,
        "created_at": alert.created_at,
        "updated_at": alert.updated_at,
        "resolved_at": alert.resolved_at,
    }


def pending_slack_delivery_categories(
    db: Session,
    *,
    tenant_id: str,
    diagnosis_id: str,
    categories: Sequence[str],
) -> list[str]:
    normalized_categories = sorted({category.strip().upper() for category in categories if category and category.strip()})
    if not normalized_categories:
        return []

    rows = db.execute(
        select(ProjectAlert).where(
            ProjectAlert.tenant_id == tenant_id,
            ProjectAlert.diagnosis_id == diagnosis_id,
            ProjectAlert.category.in_(normalized_categories),
            ProjectAlert.status == "OPEN",
            ProjectAlert.severity.in_(ACTIONABLE_SLACK_SEVERITIES),
            ProjectAlert.slack_delivery_status == PENDING_SLACK_DELIVERY_STATUS,
        )
    ).scalars().all()
    return [row.category for row in rows]


def tenant_slack_delivery_ready(db: Session, tenant_id: str) -> bool:
    install = get_slack_install(db, tenant_id)
    return bool(install and install.webhook_url)


def record_slack_delivery_for_alerts(
    db: Session,
    *,
    tenant_id: str,
    diagnosis_id: str,
    categories: Sequence[str],
    delivery_status: str,
    error: str | None = None,
) -> int:
    normalized_categories = sorted({category.strip().upper() for category in categories if category and category.strip()})
    if not normalized_categories:
        return 0

    now = datetime.now(timezone.utc)
    rows = db.execute(
        select(ProjectAlert).where(
            ProjectAlert.tenant_id == tenant_id,
            ProjectAlert.diagnosis_id == diagnosis_id,
            ProjectAlert.category.in_(normalized_categories),
        )
    ).scalars().all()
    for row in rows:
        row.slack_delivery_status = delivery_status
        row.slack_delivery_attempted_at = now
        row.slack_delivery_error = error[:255] if error else None
        db.add(row)
    if rows:
        db.commit()
    return len(rows)


def reset_slack_delivery_for_new_occurrence(alert: ProjectAlert) -> None:
    if alert.severity.lower() not in ACTIONABLE_SLACK_SEVERITIES:
        return
    alert.slack_delivery_status = PENDING_SLACK_DELIVERY_STATUS
    alert.slack_delivery_attempted_at = None
    alert.slack_delivery_error = None


def auto_send_pending_alerts_to_slack(
    db: Session,
    *,
    tenant_id: str,
    diagnosis_id: str,
    categories: Sequence[str],
    agent_name: str | None = None,
) -> dict[str, Any]:
    pending_categories = pending_slack_delivery_categories(
        db,
        tenant_id=tenant_id,
        diagnosis_id=diagnosis_id,
        categories=categories,
    )
    if not pending_categories:
        return {"attempted": 0, "slack": False, "status": "skipped"}

    if not tenant_slack_delivery_ready(db, tenant_id):
        updated = record_slack_delivery_for_alerts(
            db,
            tenant_id=tenant_id,
            diagnosis_id=diagnosis_id,
            categories=pending_categories,
            delivery_status="not_connected",
            error="Slack is not connected for this project.",
        )
        return {"attempted": updated, "slack": False, "status": "not_connected"}

    from app.services.notification_dispatch import dispatch_alert_to_tenant_channels

    slack_result = dispatch_alert_to_tenant_channels(
        db=db,
        tenant_id=tenant_id,
        categories=pending_categories,
        agent_name=agent_name,
        diagnosis_id=diagnosis_id,
    )
    sent = bool(slack_result.get("slack"))
    updated = record_slack_delivery_for_alerts(
        db,
        tenant_id=tenant_id,
        diagnosis_id=diagnosis_id,
        categories=pending_categories,
        delivery_status="sent" if sent else "failed",
        error=None if sent else "Slack webhook delivery failed.",
    )
    return {"attempted": updated, "slack": sent, "status": "sent" if sent else "failed"}


def auto_send_all_pending_alerts_to_slack(
    db: Session,
    *,
    tenant_id: str,
    limit: int = 100,
) -> dict[str, Any]:
    """Best-effort fallback for pending actionable alerts.

    Primary producers should call ``auto_send_pending_alerts_to_slack`` with the
    exact diagnosis/category they just created. This sweep covers lazy alert
    sync paths without re-sending rows that already have a terminal delivery
    status.
    """
    rows = db.execute(
        select(ProjectAlert)
        .where(
            ProjectAlert.tenant_id == tenant_id,
            ProjectAlert.status == "OPEN",
            ProjectAlert.severity.in_(ACTIONABLE_SLACK_SEVERITIES),
            ProjectAlert.slack_delivery_status == PENDING_SLACK_DELIVERY_STATUS,
        )
        .order_by(ProjectAlert.created_at.asc(), ProjectAlert.id.asc())
        .limit(max(1, min(limit, 500)))
    ).scalars().all()
    grouped: dict[tuple[str, str | None], set[str]] = defaultdict(set)
    for row in rows:
        grouped[(row.diagnosis_id, row.source)].add(row.category)

    summary: dict[str, Any] = {
        "groups": 0,
        "attempted": 0,
        "sent": 0,
        "failed": 0,
        "not_connected": 0,
        "skipped": 0,
    }
    for (diagnosis_id, source), categories in grouped.items():
        result = auto_send_pending_alerts_to_slack(
            db,
            tenant_id=tenant_id,
            diagnosis_id=diagnosis_id,
            categories=sorted(categories),
            agent_name=source,
        )
        status = str(result.get("status") or "skipped")
        attempted = int(result.get("attempted") or 0)
        summary["groups"] += 1
        summary["attempted"] += attempted
        if status in {"sent", "failed", "not_connected", "skipped"}:
            summary[status] += 1
        else:
            summary["skipped"] += 1

    return summary


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
