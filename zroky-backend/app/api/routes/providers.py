"""
/v1/providers/* — provider connection status (existing) + provider key
vault (Module 4.5; plan §6.4 + §14.2 + migration 0058).

Existing surface:
  GET  /v1/providers/status              connection-verification list
  POST /v1/providers/{provider}/test     trigger a connection check

Module 4.5 adds the vault CRUD endpoints below. The vault stores
per-project encrypted provider API keys for replay-worker
reconstruction. NO endpoint EVER returns plaintext or raw ciphertext —
the response shape is metadata-only (fingerprint, last-4, label,
audit fields).

Vault surface:
  POST   /v1/providers/keys              encrypt + persist a plaintext key
  GET    /v1/providers/keys              list keys (active by default)
  GET    /v1/providers/keys/{key_id}     fetch single key metadata
  DELETE /v1/providers/keys/{key_id}     revoke (idempotent)

Create is plan-gated by `enterprise.provider_key_vault`. Vault metadata
and revoke operations are admin-only so project member API keys cannot
manage BYOK credentials.
"""
import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies.entitlements import require_entitlement
from app.api.dependencies.tenant import require_tenant_role
from app.api.routes.settings import (
    list_provider_verifications,
    test_provider_connection,
)
from app.core.limiter import limiter
from app.db.session import get_db_session, get_db_session_read
from app.schemas.dashboard import (
    ProviderVerificationListResponse,
    ProviderVerificationTestResponse,
)
from app.services.provider_key_cipher import VaultCipherUnavailable
from app.services.provider_key_vault import (
    DuplicateKeyError,
    InvalidKeyPlaintextError,
    InvalidProviderError,
    VALID_PROVIDERS,
    list_provider_keys,
    get_provider_key,
    revoke_provider_key,
    serialize_vault_row,
    store_provider_key,
)

router = APIRouter(prefix="/v1/providers")
logger = logging.getLogger(__name__)


# ── existing endpoints (unchanged) ───────────────────────────────────────────


@router.get("/status", response_model=ProviderVerificationListResponse)
def get_provider_status(
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> ProviderVerificationListResponse:
    return list_provider_verifications(tenant_id=tenant_id, db=db)


@router.post("/{provider}/test", response_model=ProviderVerificationTestResponse)
@limiter.limit("10/minute")
def test_provider_status(
    request: Request,
    provider: str,
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> ProviderVerificationTestResponse:
    return test_provider_connection(provider=provider, tenant_id=tenant_id, db=db)


# ── vault schemas (metadata-only — no plaintext, no ciphertext) ──────────────


class ProviderKeyCreateRequest(BaseModel):
    provider: str = Field(
        description=(
            "Provider identifier; must match the migration 0058 CHECK vocab"
        ),
        examples=["openai"],
    )
    plaintext_key: str = Field(
        min_length=8,
        description="The actual provider API key (never echoed back)",
    )
    label: str | None = Field(
        default=None,
        max_length=128,
        description="Optional human-readable label, e.g. 'prod' or 'staging'",
    )


class ProviderKeyResponse(BaseModel):
    """Metadata-only wire shape. The dashboard renders identity using
    `key_fingerprint` (first 8 chars) + `key_last4`."""

    id: str
    project_id: str
    provider: str
    key_fingerprint: str
    key_last4: str | None = None
    kms_key_id: str | None = None
    label: str | None = None
    is_active: bool
    created_by_user_id: str | None = None
    last_used_at: str | None = None
    revoked_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ProviderKeyListResponse(BaseModel):
    items: list[ProviderKeyResponse]
    total_in_page: int


# ── vault routes ─────────────────────────────────────────────────────────────


@router.post(
    "/keys",
    response_model=ProviderKeyResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("12/minute")
def create_provider_key(
    request: Request,
    body: ProviderKeyCreateRequest = Body(...),
    _: None = Depends(require_entitlement("enterprise.provider_key_vault")),
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> ProviderKeyResponse:
    """Encrypt and persist a provider key for this project.

    Behaviour:
      - 422 on bad provider vocab or empty/short plaintext.
      - 409 if a key with the same fingerprint is already active for
            this provider in this project (re-paste of the same key).
      - 503 if `PROVIDER_KEY_VAULT_KEK` is unset/short — cipher refuses
            to write plaintext.
      - On success the previously-active row for (project_id, provider)
        is automatically revoked so only the new row is active.
    """
    try:
        row = store_provider_key(
            db,
            project_id=tenant_id,
            provider=body.provider,
            plaintext_key=body.plaintext_key,
            label=body.label,
        )
    except (InvalidProviderError, InvalidKeyPlaintextError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except DuplicateKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except VaultCipherUnavailable as exc:
        # Misconfiguration — DO NOT silently downgrade.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    return ProviderKeyResponse(**serialize_vault_row(row))


@router.get("/keys", response_model=ProviderKeyListResponse)
@limiter.limit("60/minute")
def list_provider_key_rows(
    request: Request,
    provider: str | None = Query(
        default=None,
        description="Filter by provider; 422 if not in VALID_PROVIDERS",
    ),
    include_revoked: bool = Query(
        default=False,
        description="When true, also returns is_active=false rows",
    ),
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session_read),
) -> ProviderKeyListResponse:
    """List provider keys for the calling tenant.

    By default returns only active keys (is_active=true). The dashboard
    uses include_revoked=true on the audit/history view to render
    rotated keys."""
    if provider is not None and provider.strip().lower() not in VALID_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "provider must be one of: " + ", ".join(sorted(VALID_PROVIDERS))
            ),
        )
    rows = list_provider_keys(
        db,
        project_id=tenant_id,
        provider=provider,
        include_revoked=include_revoked,
    )
    items = [ProviderKeyResponse(**serialize_vault_row(r)) for r in rows]
    return ProviderKeyListResponse(items=items, total_in_page=len(items))


@router.get("/keys/{key_id}", response_model=ProviderKeyResponse)
@limiter.limit("60/minute")
def get_provider_key_detail(
    request: Request,
    key_id: str,
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session_read),
) -> ProviderKeyResponse:
    """Fetch a single key's metadata. 404 if missing or cross-tenant."""
    row = get_provider_key(db, project_id=tenant_id, key_id=key_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider key not found",
        )
    return ProviderKeyResponse(**serialize_vault_row(row))


@router.delete("/keys/{key_id}", response_model=ProviderKeyResponse)
@limiter.limit("12/minute")
def delete_provider_key(
    request: Request,
    key_id: str,
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> ProviderKeyResponse:
    """Revoke a key. Idempotent — calling on an already-revoked row
    returns the same row unchanged. 404 if missing or cross-tenant."""
    row = revoke_provider_key(db, project_id=tenant_id, key_id=key_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider key not found",
        )
    return ProviderKeyResponse(**serialize_vault_row(row))
