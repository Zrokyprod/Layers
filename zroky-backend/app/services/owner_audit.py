from __future__ import annotations

import json
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.db.models import AuditLog


def resolve_owner_actor(request: Request) -> str:
    from app.auth.identity import build_identity_context, decode_jwt_claims, extract_bearer_token

    token = extract_bearer_token(request)
    if token:
        try:
            ctx = build_identity_context(decode_jwt_claims(token))
            if ctx.subject:
                return ctx.subject
        except Exception:
            pass
    return "provisioning_token"


def create_owner_audit_event(
    db: Session,
    *,
    action: str,
    actor: str,
    target_id: str,
    metadata: dict[str, Any],
) -> None:
    db.add(
        AuditLog(
            tenant_id="PLATFORM",
            diagnosis_id="owner_action",
            action=action,
            actor_subject=actor,
            metadata_json=json.dumps({"target_id": target_id, **metadata}, default=str),
        )
    )
