import json
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import DiagnosisFixWatch, DiagnosisJob, ProjectDashboardConfig, User
from app.schemas.diagnosis import DiagnosisFixWatchResponse
from app.services.audit_logs import safe_actor_subject_from_request
from app.services.github_tokens import decrypt_github_token
from app.services.privacy import mask_payload
from app.services.user_identity import resolve_request_identity

FIX_WATCH_WINDOW = timedelta(days=7)
FIX_HOLD_WINDOW = timedelta(hours=48)


def _safe_actor_subject(request: Request) -> str | None:
    return safe_actor_subject_from_request(request)


def _resolve_github_pr_token(request: Request, db: Session) -> tuple[str, str]:
    settings = get_settings()

    identity = resolve_request_identity(request)
    if identity is not None:
        user = db.execute(
            select(User).where(User.subject == identity.subject, User.is_active.is_(True))
        ).scalar_one_or_none()
        if user is not None:
            token = decrypt_github_token(user.github_token_encrypted)
            if token:
                return token, "user_oauth"

    bot_token = (settings.GITHUB_PR_BOT_TOKEN or "").strip()
    if bot_token:
        return bot_token, "bot_token"

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            "GitHub token source is not configured. "
            "Connect GitHub in Settings or configure GITHUB_PR_BOT_TOKEN."
        ),
    )


def _get_job_or_404(
    *,
    db: Session,
    tenant_id: str,
    diagnosis_id: str,
) -> DiagnosisJob:
    query = select(DiagnosisJob).where(
        DiagnosisJob.tenant_id == tenant_id,
        DiagnosisJob.diagnosis_id == diagnosis_id,
    )
    job = db.execute(query).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Diagnosis not found")
    return job


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _safe_json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}

    if not isinstance(payload, dict):
        return {}
    return mask_payload(payload)


def _safe_json_array(raw: str | None) -> list[Any]:
    if not raw:
        return []

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []

    if not isinstance(payload, list):
        return []
    return payload


def _project_pii_patterns(db: Session, tenant_id: str) -> list[str]:
    config = db.execute(
        select(ProjectDashboardConfig).where(ProjectDashboardConfig.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if config is None:
        return []
    try:
        parsed = json.loads(config.pii_custom_patterns_json or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [item.strip() for item in parsed if isinstance(item, str) and item.strip()]


def _payload_text_field(payload: dict[str, Any], key: str) -> str | None:
    raw = payload.get(key)
    if not isinstance(raw, str):
        return None

    value = raw.strip()
    return value or None


def _normalize_category(value: Any) -> str | None:
    if not isinstance(value, str):
        return None

    normalized = value.strip().upper().replace(" ", "_")
    return normalized or None


def _extract_categories_from_payload(payload: dict[str, Any]) -> set[str]:
    categories: set[str] = set()

    for key in ("category", "error_code", "expected_category", "failure_category"):
        normalized = _normalize_category(payload.get(key))
        if normalized:
            categories.add(normalized)

    diagnoses = payload.get("diagnoses")
    if isinstance(diagnoses, list):
        for item in diagnoses:
            if not isinstance(item, dict):
                continue
            normalized = _normalize_category(item.get("category"))
            if normalized:
                categories.add(normalized)

    return categories


def _extract_job_categories(job: DiagnosisJob) -> set[str]:
    result_payload = _safe_json_object(job.result_json)
    categories = _extract_categories_from_payload(result_payload)
    if categories:
        return categories

    request_payload = _safe_json_object(job.payload_json)
    return _extract_categories_from_payload(request_payload)


def _parse_target_categories(raw: str | None) -> list[str]:
    categories: list[str] = []
    for item in _safe_json_array(raw):
        normalized = _normalize_category(item)
        if normalized and normalized not in categories:
            categories.append(normalized)
    return categories


def _scan_fix_watch_recurrence(
    *,
    db: Session,
    watch: DiagnosisFixWatch,
    target_categories: list[str],
) -> tuple[int, datetime | None]:
    if not target_categories:
        return 0, None

    resolved_at = _as_utc(watch.resolved_at)
    watch_expires_at = _as_utc(watch.watch_expires_at)

    query = (
        select(DiagnosisJob)
        .where(
            DiagnosisJob.tenant_id == watch.tenant_id,
            DiagnosisJob.diagnosis_id != watch.diagnosis_id,
            DiagnosisJob.created_at >= resolved_at,
            DiagnosisJob.created_at <= watch_expires_at,
        )
        .order_by(DiagnosisJob.created_at.asc())
        .limit(500)
    )
    jobs = db.execute(query).scalars().all()
    recurrence_count = 0
    last_recurrence_at: datetime | None = None
    target_set = set(target_categories)
    for job in jobs:
        created_at = _as_utc(job.created_at)
        if created_at < resolved_at or created_at > watch_expires_at:
            continue

        categories = _extract_job_categories(job)
        if not target_set.intersection(categories):
            continue

        recurrence_count += 1
        if last_recurrence_at is None or created_at > last_recurrence_at:
            last_recurrence_at = created_at

    return recurrence_count, last_recurrence_at


def _build_fix_watch_response(
    *,
    db: Session,
    watch: DiagnosisFixWatch,
) -> DiagnosisFixWatchResponse:
    now = datetime.now(timezone.utc)
    resolved_at = _as_utc(watch.resolved_at)
    watch_expires_at = _as_utc(watch.watch_expires_at)
    target_categories = _parse_target_categories(watch.target_categories_json)
    recurrence_count, last_recurrence_at = _scan_fix_watch_recurrence(
        db=db,
        watch=watch,
        target_categories=target_categories,
    )

    if recurrence_count > 0:
        status_value = "recurrence_detected"
        message = "Recurrence detected during fix-watch window."
    elif now >= watch_expires_at:
        status_value = "expired"
        message = "Fix-watch window completed with no recurrence."
    elif now >= resolved_at + FIX_HOLD_WINDOW:
        status_value = "holding_48h"
        message = "48h hold passed. Watch remains active through day 7."
    else:
        status_value = "active"
        message = "Fix-watch active. Monitoring recurrence."

    return DiagnosisFixWatchResponse(
        tenant_id=watch.tenant_id,
        diagnosis_id=watch.diagnosis_id,
        status=status_value,
        resolved_at=resolved_at,
        watch_expires_at=watch_expires_at,
        target_categories=target_categories,
        recurrence_count=recurrence_count,
        last_recurrence_at=last_recurrence_at,
        message=message,
    )


