"""Owner-only connector credential custody endpoints.

The API accepts a secret only for explicit ``zroky_managed`` custody. All
responses are metadata-only: plaintext, ciphertext, fingerprints, last-four,
and the complete external secret reference are never exposed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.core.limiter import limiter
from app.db.session import get_db_session, get_db_session_read
from app.services.connector_credentials import (
    ConnectorCredentialError,
    CredentialConflictError,
    CredentialNotFoundError,
    bind_connector_credential,
    create_connector_credential,
    get_connector_credential,
    list_connector_credential_audit_events,
    list_connector_credentials,
    revoke_connector_credential,
    rotate_connector_credential,
    serialize_connector_credential,
    serialize_connector_credential_audit_event,
)
from app.services.dashboard_config import ensure_project_exists
from app.services.provider_key_cipher import VaultCipherUnavailable


router = APIRouter()

CredentialKind = Literal["bearer_token", "oauth_refresh_token", "database_url"]
CustodyMode = Literal["zroky_managed", "customer_managed", "private_runner"]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConnectorCredentialCreateRequest(_StrictModel):
    name: str = Field(min_length=2, max_length=128)
    credential_kind: CredentialKind
    custody_mode: CustodyMode
    plaintext_secret: SecretStr | None = Field(default=None, repr=False)
    secret_ref: str | None = Field(default=None, max_length=512)
    scopes: list[str] = Field(default_factory=list, max_length=64)
    allowed_connector_types: list[str] = Field(min_length=1, max_length=32)
    expires_at: datetime | None = None
    rotation_due_at: datetime | None = None


class ConnectorCredentialRotateRequest(_StrictModel):
    custody_mode: CustodyMode
    plaintext_secret: SecretStr | None = Field(default=None, repr=False)
    secret_ref: str | None = Field(default=None, max_length=512)
    scopes: list[str] = Field(default_factory=list, max_length=64)
    allowed_connector_types: list[str] = Field(min_length=1, max_length=32)
    expires_at: datetime | None = None
    rotation_due_at: datetime | None = None


class ConnectorCredentialBindRequest(_StrictModel):
    connector_type: str = Field(min_length=2, max_length=64)
    purpose: CredentialKind


class ConnectorCredentialResponse(_StrictModel):
    id: str
    name: str
    version: int
    credential_kind: CredentialKind
    custody_mode: CustodyMode
    state: str
    reference_configured: bool
    reference_scheme: str | None
    scopes: list[str]
    allowed_connector_types: list[str]
    expires_at: datetime | None
    rotation_due_at: datetime | None
    last_used_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None


class ConnectorCredentialListResponse(_StrictModel):
    items: list[ConnectorCredentialResponse]


class ConnectorCredentialBindingResponse(_StrictModel):
    connector_config_id: str
    connector_type: str
    credential_id: str
    purpose: CredentialKind


class ConnectorCredentialAuditEventResponse(_StrictModel):
    id: str
    credential_id: str
    event_type: str
    actor_subject: str | None
    metadata: dict[str, Any]
    created_at: datetime | None


class ConnectorCredentialAuditListResponse(_StrictModel):
    items: list[ConnectorCredentialAuditEventResponse]


def _require_owner(context: TenantContext) -> None:
    if context.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant owner role is required for connector credential custody.",
        )


def _raise_credential_error(exc: Exception) -> None:
    if isinstance(exc, CredentialNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential was not found.") from exc
    if isinstance(exc, CredentialConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Credential state conflicts with this request.") from exc
    if isinstance(exc, VaultCipherUnavailable):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Managed credential vault is unavailable.",
        ) from exc
    if isinstance(exc, ConnectorCredentialError):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    raise exc


@router.post(
    "/credentials",
    response_model=ConnectorCredentialResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("6/minute")
def create_credential(
    request: Request,
    body: ConnectorCredentialCreateRequest = Body(...),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ConnectorCredentialResponse:
    _require_owner(context)
    ensure_project_exists(db, context.tenant_id)
    try:
        credential = create_connector_credential(
            db,
            project_id=context.tenant_id,
            name=body.name,
            credential_kind=body.credential_kind,
            custody_mode=body.custody_mode,
            plaintext_secret=(
                body.plaintext_secret.get_secret_value()
                if body.plaintext_secret is not None
                else None
            ),
            secret_ref=body.secret_ref,
            scopes=body.scopes,
            allowed_connector_types=body.allowed_connector_types,
            expires_at=body.expires_at,
            rotation_due_at=body.rotation_due_at,
            actor_subject=context.subject,
        )
    except Exception as exc:  # mapped to client-safe errors above
        _raise_credential_error(exc)
    return ConnectorCredentialResponse(**serialize_connector_credential(credential))


@router.get("/credentials", response_model=ConnectorCredentialListResponse)
@limiter.limit("60/minute")
def list_credentials(
    request: Request,
    include_inactive: bool = False,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session_read),
) -> ConnectorCredentialListResponse:
    _require_owner(context)
    rows = list_connector_credentials(
        db, project_id=context.tenant_id, include_inactive=include_inactive
    )
    return ConnectorCredentialListResponse(
        items=[ConnectorCredentialResponse(**serialize_connector_credential(row)) for row in rows]
    )


@router.get("/credentials/{credential_id}", response_model=ConnectorCredentialResponse)
@limiter.limit("60/minute")
def get_credential(
    request: Request,
    credential_id: str,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session_read),
) -> ConnectorCredentialResponse:
    _require_owner(context)
    credential = get_connector_credential(
        db, project_id=context.tenant_id, credential_id=credential_id
    )
    if credential is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential was not found.")
    return ConnectorCredentialResponse(**serialize_connector_credential(credential))


@router.post(
    "/credentials/{credential_id}/rotate",
    response_model=ConnectorCredentialResponse,
)
@limiter.limit("6/minute")
def rotate_credential(
    request: Request,
    credential_id: str,
    body: ConnectorCredentialRotateRequest = Body(...),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ConnectorCredentialResponse:
    _require_owner(context)
    try:
        credential = rotate_connector_credential(
            db,
            project_id=context.tenant_id,
            credential_id=credential_id,
            custody_mode=body.custody_mode,
            plaintext_secret=(
                body.plaintext_secret.get_secret_value()
                if body.plaintext_secret is not None
                else None
            ),
            secret_ref=body.secret_ref,
            scopes=body.scopes,
            allowed_connector_types=body.allowed_connector_types,
            expires_at=body.expires_at,
            rotation_due_at=body.rotation_due_at,
            actor_subject=context.subject,
        )
    except Exception as exc:
        _raise_credential_error(exc)
    return ConnectorCredentialResponse(**serialize_connector_credential(credential))


@router.delete("/credentials/{credential_id}", response_model=ConnectorCredentialResponse)
@limiter.limit("6/minute")
def revoke_credential(
    request: Request,
    credential_id: str,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ConnectorCredentialResponse:
    _require_owner(context)
    credential = revoke_connector_credential(
        db,
        project_id=context.tenant_id,
        credential_id=credential_id,
        actor_subject=context.subject,
    )
    if credential is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential was not found.")
    return ConnectorCredentialResponse(**serialize_connector_credential(credential))


@router.put(
    "/credentials/{credential_id}/binding",
    response_model=ConnectorCredentialBindingResponse,
)
@limiter.limit("12/minute")
def bind_credential(
    request: Request,
    credential_id: str,
    body: ConnectorCredentialBindRequest = Body(...),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ConnectorCredentialBindingResponse:
    _require_owner(context)
    try:
        config = bind_connector_credential(
            db,
            project_id=context.tenant_id,
            connector_type=body.connector_type,
            credential_id=credential_id,
            purpose=body.purpose,
            actor_subject=context.subject,
        )
    except Exception as exc:
        _raise_credential_error(exc)
    return ConnectorCredentialBindingResponse(
        connector_config_id=config.id,
        connector_type=config.connector_type,
        credential_id=credential_id,
        purpose=body.purpose,
    )


@router.get(
    "/credentials/{credential_id}/audit",
    response_model=ConnectorCredentialAuditListResponse,
)
@limiter.limit("60/minute")
def list_credential_audit(
    request: Request,
    credential_id: str,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session_read),
) -> ConnectorCredentialAuditListResponse:
    _require_owner(context)
    try:
        rows = list_connector_credential_audit_events(
            db, project_id=context.tenant_id, credential_id=credential_id
        )
    except Exception as exc:
        _raise_credential_error(exc)
    return ConnectorCredentialAuditListResponse(
        items=[
            ConnectorCredentialAuditEventResponse(
                **serialize_connector_credential_audit_event(row)
            )
            for row in rows
        ]
    )
