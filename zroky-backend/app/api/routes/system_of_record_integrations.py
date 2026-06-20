from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import TenantContext, require_tenant_context, require_tenant_role
from app.core.config import get_settings
from app.core.limiter import limiter
from app.db.session import get_db_session, get_db_session_read
from app.services.dashboard_config import ensure_project_exists
from app.services.outcome_reconciliation import reconcile_outcome, reconciliation_to_dict
from app.services.system_of_record_connector_config import (
    EnvelopeFormatError,
    InvalidSystemOfRecordConnectorError,
    VaultCipherUnavailable,
    build_ledger_refund_connector,
    decrypt_connector_bearer_token,
    get_connector_config,
    mark_connector_tested,
    serialize_connector_config,
    upsert_ledger_refund_connector_config,
)

router = APIRouter(prefix="/v1/integrations/system-of-record")


class LedgerRefundConnectorStatusResponse(BaseModel):
    connected: bool
    connector_type: str
    base_url: str | None = None
    path_template: str | None = None
    record_path: str | None = None
    query: dict[str, Any] | None = None
    has_bearer_token: bool
    bearer_token_last4: str | None = None
    last_tested_at: Any | None = None
    created_at: Any | None = None
    updated_at: Any | None = None


class LedgerRefundConnectorConfigRequest(BaseModel):
    base_url: str = Field(..., max_length=2048)
    path_template: str = Field(default="/refunds/{refund_id}", max_length=512)
    record_path: str | None = Field(default=None, max_length=255)
    query: dict[str, str | int | float | bool] | None = None
    bearer_token: str | None = Field(default=None, max_length=4096)
    clear_bearer_token: bool = False

    @field_validator("bearer_token")
    @classmethod
    def _normalize_token(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        if len(cleaned) < 8:
            raise ValueError("bearer_token must be at least 8 characters")
        return cleaned


class LedgerRefundConnectorTestRequest(BaseModel):
    refund_id: str = Field(..., min_length=1, max_length=255)
    claimed: dict[str, Any] = Field(default_factory=dict)
    call_id: str | None = Field(None, max_length=64)
    trace_id: str | None = Field(None, max_length=128)
    runtime_policy_decision_id: str | None = Field(None, max_length=36)
    action_type: str | None = Field(default="refund", max_length=64)
    match_fields: list[str] | None = None
    amount_usd: float | None = Field(None, ge=0)
    currency: str | None = Field(None, min_length=3, max_length=3)
    idempotency_key: str | None = Field(None, max_length=255)
    metadata: dict[str, Any] | None = None

    @field_validator("currency")
    @classmethod
    def _normalise_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class LedgerRefundConnectorTestResponse(BaseModel):
    ok: bool
    check: dict[str, Any]
    connector: LedgerRefundConnectorStatusResponse


def _status_response(row) -> LedgerRefundConnectorStatusResponse:
    return LedgerRefundConnectorStatusResponse(**serialize_connector_config(row))


def _claim_text(claimed: dict[str, Any], key: str) -> str | None:
    value = claimed.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _match_fields(claimed: dict[str, Any], explicit: list[str] | None) -> list[str]:
    if explicit:
        fields = [field.strip() for field in explicit if field.strip()]
        return fields or ["refund_id"]
    fields = [
        field
        for field in ("refund_id", "amount_usd", "currency", "status")
        if field in claimed
    ]
    return fields or ["refund_id"]


def _map_config_error(exc: Exception) -> HTTPException:
    if isinstance(exc, VaultCipherUnavailable):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
    if isinstance(exc, EnvelopeFormatError):
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Connector secret could not be decrypted.",
        )
    return HTTPException(
        status_code=422,
        detail=str(exc),
    )


@router.get(
    "/ledger-refund/status",
    response_model=LedgerRefundConnectorStatusResponse,
)
@limiter.limit("60/minute")
def get_ledger_refund_connector_status(
    request: Request,
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session_read),
) -> LedgerRefundConnectorStatusResponse:
    row = get_connector_config(db, project_id=tenant_id)
    return _status_response(row)


@router.put(
    "/ledger-refund/config",
    response_model=LedgerRefundConnectorStatusResponse,
)
@limiter.limit("12/minute")
def save_ledger_refund_connector_config(
    request: Request,
    body: LedgerRefundConnectorConfigRequest = Body(...),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> LedgerRefundConnectorStatusResponse:
    if context.role not in {"admin", "owner"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant admin role is required.",
        )
    ensure_project_exists(db, context.tenant_id)
    settings = get_settings()
    try:
        row = upsert_ledger_refund_connector_config(
            db,
            project_id=context.tenant_id,
            base_url=body.base_url,
            path_template=body.path_template,
            record_path=body.record_path,
            query=body.query,
            bearer_token=body.bearer_token,
            clear_bearer_token=body.clear_bearer_token,
            updated_by_subject=context.subject,
            allow_private_hosts=settings.OUTCOME_CONNECTOR_ALLOW_PRIVATE_HOSTS,
        )
    except (InvalidSystemOfRecordConnectorError, VaultCipherUnavailable) as exc:
        raise _map_config_error(exc) from exc
    return _status_response(row)


@router.post(
    "/ledger-refund/test",
    response_model=LedgerRefundConnectorTestResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("20/minute")
def test_ledger_refund_connector(
    request: Request,
    body: LedgerRefundConnectorTestRequest = Body(...),
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> LedgerRefundConnectorTestResponse:
    config = get_connector_config(db, project_id=tenant_id)
    if config is None or not config.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ledger refund connector is not configured.",
        )

    refund_id = body.refund_id.strip()
    claimed = dict(body.claimed)
    claimed.setdefault("refund_id", refund_id)
    settings = get_settings()
    try:
        bearer_token = decrypt_connector_bearer_token(config, project_id=tenant_id)
        connector = build_ledger_refund_connector(
            config,
            refund_id=refund_id,
            bearer_token=bearer_token,
            timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
            allow_private_hosts=settings.OUTCOME_CONNECTOR_ALLOW_PRIVATE_HOSTS,
        )
        row = reconcile_outcome(
            db,
            project_id=tenant_id,
            claimed=claimed,
            connector=connector,
            call_id=body.call_id,
            trace_id=body.trace_id,
            runtime_policy_decision_id=body.runtime_policy_decision_id,
            action_type=body.action_type or "refund",
            system_ref=f"ledger:{refund_id}",
            amount_usd=body.amount_usd
            if body.amount_usd is not None
            else float(claimed["amount_usd"])
            if "amount_usd" in claimed and str(claimed["amount_usd"]).strip()
            else None,
            currency=body.currency or _claim_text(claimed, "currency"),
            match_fields=_match_fields(claimed, body.match_fields),
            idempotency_key=body.idempotency_key,
            metadata={
                **(body.metadata or {}),
                "connector_kind": "ledger_refund_api",
                "connector_config_id": config.id,
                "refund_id": refund_id,
                "source": "saved_connector_test",
            },
        )
        updated_config = mark_connector_tested(db, config, tested_at=row.checked_at)
    except (
        InvalidSystemOfRecordConnectorError,
        VaultCipherUnavailable,
        EnvelopeFormatError,
        ValueError,
    ) as exc:
        raise _map_config_error(exc) from exc

    return LedgerRefundConnectorTestResponse(
        ok=row.verdict == "matched",
        check=reconciliation_to_dict(row),
        connector=_status_response(updated_config),
    )
