from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import ROLE_RANK
from app.auth.identity import (
    build_identity_context,
    decode_jwt_claims,
    extract_bearer_token,
    resolve_project_from_identity,
)
from app.core.config import get_settings
from app.db.models import ApiKey, Project, ProjectMembership
from app.db.session import get_db_session, set_db_tenant_context
from app.services.membership import get_membership
from app.services.security import decode_session_token, hash_api_key


@dataclass(frozen=True)
class TenantContext:
    tenant_id: str
    role: str
    subject: str | None = None


def _resolve_project_from_bearer(
    request: Request,
    selected_project_id: str | None,
    db: Session,
) -> TenantContext | None:
    token = extract_bearer_token(request)
    if not token:
        return None

    settings = get_settings()

    # --- Path A: external JWT (RS256/JWKS) ---
    try:
        claims = decode_jwt_claims(token)
        identity = build_identity_context(claims)
        project_id = resolve_project_from_identity(identity, selected_project_id)
        membership = get_membership(db, project_id=project_id, subject=identity.subject)
        if settings.ENFORCE_JWT_PROJECT_MEMBERSHIP and membership is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Identity is not a member of the requested project.",
            )
        resolved_role = membership.role if membership is not None else "viewer"
        return TenantContext(tenant_id=project_id, role=resolved_role, subject=identity.subject)
    except HTTPException:
        pass  # External JWT failed — try internal session token below

    # --- Path B: internal HS256 session JWT (AUTH_JWT_SECRET) ---
    if not settings.AUTH_JWT_SECRET:
        return None

    try:
        claims = decode_session_token(token, settings.AUTH_JWT_SECRET)
    except Exception:
        return None

    user_id = str(claims.get("user_id") or "").strip()
    subject = str(claims.get("sub") or "").strip()
    if not user_id:
        return None

    # Resolve the user's project from their membership row
    membership_row = db.execute(
        select(ProjectMembership)
        .join(Project, Project.id == ProjectMembership.project_id)
        .where(
            ProjectMembership.user_id == user_id,
            ProjectMembership.is_active.is_(True),
            Project.is_active.is_(True),
        )
        .limit(1)
    ).scalar_one_or_none()

    if membership_row is None:
        return None

    set_db_tenant_context(db, membership_row.project_id)
    return TenantContext(tenant_id=membership_row.project_id, role=membership_row.role, subject=subject)


def _resolve_project_from_api_key(api_key_value: str, db: Session) -> str | None:
    query = (
        select(ApiKey)
        .join(Project, Project.id == ApiKey.project_id)
        .where(
            ApiKey.key_hash == hash_api_key(api_key_value),
            ApiKey.revoked_at.is_(None),
            Project.is_active.is_(True),
        )
    )
    api_key = db.execute(query).scalar_one_or_none()
    if api_key is None:
        return None

    api_key.last_used_at = datetime.now(timezone.utc)
    db.add(api_key)
    return api_key.project_id


def require_tenant_context(
    request: Request,
    db: Session = Depends(get_db_session),
) -> TenantContext:
    settings = get_settings()
    selected_project_id: str | None = None

    primary = request.headers.get(settings.TENANT_HEADER_NAME)
    if primary and primary.strip():
        selected_project_id = primary.strip()

    if settings.ACCEPT_LEGACY_TENANT_HEADER and not selected_project_id:
        legacy = request.headers.get(settings.LEGACY_TENANT_HEADER_NAME)
        if legacy and legacy.strip():
            selected_project_id = legacy.strip()

    if selected_project_id and settings.ALLOW_PROJECT_HEADER_CONTEXT:
        set_db_tenant_context(db, selected_project_id)
        return TenantContext(tenant_id=selected_project_id, role="member", subject=None)

    api_key_value = request.headers.get(settings.API_KEY_HEADER_NAME)
    if not api_key_value and settings.ACCEPT_BEARER_AS_API_KEY:
        api_key_value = extract_bearer_token(request)

    if api_key_value and api_key_value.strip():
        project_id = _resolve_project_from_api_key(api_key_value.strip(), db)
        if project_id:
            set_db_tenant_context(db, project_id)
            return TenantContext(tenant_id=project_id, role="member", subject=None)

    bearer_tenant_context = _resolve_project_from_bearer(request, selected_project_id, db)
    if bearer_tenant_context:
        set_db_tenant_context(db, bearer_tenant_context.tenant_id)
        return bearer_tenant_context

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=(
            f"Missing project context. Provide a valid API key in {settings.API_KEY_HEADER_NAME}"
            if not settings.ALLOW_PROJECT_HEADER_CONTEXT
            else (
                f"Missing project context. Provide {settings.TENANT_HEADER_NAME} "
                f"or a valid API key in {settings.API_KEY_HEADER_NAME}."
            )
        ),
    )


def require_tenant_id(
    context: TenantContext = Depends(require_tenant_context),
) -> str:
    return context.tenant_id


def require_tenant_role(min_role: str):
    normalized = min_role.strip().lower()
    if normalized not in ROLE_RANK:
        raise ValueError(f"Unsupported tenant role guard: {min_role}")

    def _dependency(context: TenantContext = Depends(require_tenant_context)) -> str:
        if ROLE_RANK[context.role] < ROLE_RANK[normalized]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Tenant role '{context.role}' does not allow this action.",
            )
        return context.tenant_id

    return _dependency
