from __future__ import annotations

import json
import logging
from typing import Any, Mapping

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.auth.identity import build_identity_context, decode_jwt_claims, extract_bearer_token
from app.db.models import AuditLog
from app.services.privacy import hash_identifier, mask_metadata

logger = logging.getLogger(__name__)

AUDIT_ACTION_DIAGNOSIS_VIEWED = "diagnosis_viewed"
AUDIT_ACTION_FIX_COPIED = "fix_copied"
AUDIT_ACTION_PR_GENERATED = "pr_generated"
AUDIT_ACTION_RECOVERY_EXECUTE_REQUESTED = "recovery_execute_requested"
AUDIT_ACTION_RESOLVED = "resolved"

_ALLOWED_ACTIONS = {
    AUDIT_ACTION_DIAGNOSIS_VIEWED,
    AUDIT_ACTION_FIX_COPIED,
    AUDIT_ACTION_PR_GENERATED,
    AUDIT_ACTION_RECOVERY_EXECUTE_REQUESTED,
    AUDIT_ACTION_RESOLVED,
}


def safe_actor_subject_from_request(request: Request | None) -> str | None:
    if request is None:
        return None

    token = extract_bearer_token(request)
    if not token:
        return None

    try:
        claims = decode_jwt_claims(token)
        return build_identity_context(claims).subject
    except HTTPException:
        return None


def _normalize_action(action: str) -> str:
    normalized = action.strip().lower()
    if normalized not in _ALLOWED_ACTIONS:
        raise ValueError(f"Unsupported audit action: {action}")
    return normalized


def _serialize_metadata(metadata: Mapping[str, Any] | None) -> str:
    if not metadata:
        return "{}"

    normalized = mask_metadata({str(key): value for key, value in metadata.items()})
    return json.dumps(normalized, separators=(",", ":"))


def parse_metadata(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}

    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}

    if isinstance(parsed, dict):
        return parsed
    return {}


def create_audit_log(
    db: Session,
    *,
    tenant_id: str,
    diagnosis_id: str,
    action: str,
    actor_subject: str | None,
    metadata: Mapping[str, Any] | None = None,
) -> AuditLog:
    entry = add_audit_log(
        db,
        tenant_id=tenant_id,
        diagnosis_id=diagnosis_id,
        action=action,
        actor_subject=actor_subject,
        metadata=metadata,
    )
    db.commit()
    db.refresh(entry)
    return entry


def add_audit_log(
    db: Session,
    *,
    tenant_id: str,
    diagnosis_id: str,
    action: str,
    actor_subject: str | None,
    metadata: Mapping[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        tenant_id=tenant_id,
        diagnosis_id=diagnosis_id,
        action=_normalize_action(action),
        actor_subject=hash_identifier(actor_subject) if actor_subject else None,
        metadata_json=_serialize_metadata(metadata),
    )
    db.add(entry)
    return entry


def create_audit_log_best_effort(
    db: Session,
    *,
    tenant_id: str,
    diagnosis_id: str,
    action: str,
    actor_subject: str | None,
    metadata: Mapping[str, Any] | None = None,
) -> AuditLog | None:
    try:
        return create_audit_log(
            db,
            tenant_id=tenant_id,
            diagnosis_id=diagnosis_id,
            action=action,
            actor_subject=actor_subject,
            metadata=metadata,
        )
    except Exception:
        db.rollback()
        logger.warning(
            "Failed to persist audit log",
            extra={
                "tenant_id": tenant_id,
                "diagnosis_id": diagnosis_id,
                "action": action,
            },
        )
        return None
