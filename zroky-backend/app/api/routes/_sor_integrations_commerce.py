from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import TenantContext, require_tenant_context, require_tenant_role
from app.core.config import get_settings
from app.core.limiter import limiter
from app.db.session import get_db_session, get_db_session_read
from app.services.dashboard_config import ensure_project_exists
from app.services.outcome_reconciliation import reconcile_outcome, reconciliation_to_dict
from app.services.system_of_record_connector_config import (
    SHOPIFY_ADMIN_CONNECTOR_TYPE,
    STRIPE_PAYMENT_CONNECTOR_TYPE,
    EnvelopeFormatError,
    InvalidSystemOfRecordConnectorError,
    VaultCipherUnavailable,
    build_shopify_admin_connector,
    build_stripe_payment_connector,
    decrypt_connector_bearer_token,
    get_connector_config,
    get_connector_health_snapshot,
    mark_connector_tested,
    serialize_connector_config,
    upsert_shopify_admin_connector_config,
    upsert_stripe_payment_connector_config,
)

from ._sor_integrations_helpers import (
    ProtectedActionMeteringUnavailable,
    ProtectedActionQuotaExceeded,
    _map_config_error,
)
from ._sor_integrations_schemas import *

router = APIRouter()


def _stripe_payment_status_response(
    row,
    *,
    db: Session | None = None,
    project_id: str | None = None,
) -> StripePaymentConnectorStatusResponse:
    health = (
        get_connector_health_snapshot(
            db, project_id=project_id, connector_type=STRIPE_PAYMENT_CONNECTOR_TYPE
        )
        if row is not None and db is not None and project_id
        else None
    )
    return StripePaymentConnectorStatusResponse(
        **serialize_connector_config(
            row,
            connector_type=STRIPE_PAYMENT_CONNECTOR_TYPE,
            health=health,
        )
    )


def _shopify_status_response(
    row,
    *,
    db: Session | None = None,
    project_id: str | None = None,
) -> ShopifyConnectorStatusResponse:
    health = (
        get_connector_health_snapshot(
            db, project_id=project_id, connector_type=SHOPIFY_ADMIN_CONNECTOR_TYPE
        )
        if row is not None and db is not None and project_id
        else None
    )
    return ShopifyConnectorStatusResponse(
        **serialize_connector_config(
            row,
            connector_type=SHOPIFY_ADMIN_CONNECTOR_TYPE,
            health=health,
        )
    )


def _payment_match_fields(claimed: dict[str, Any], explicit: list[str] | None) -> list[str]:
    if explicit:
        fields = [field.strip() for field in explicit if field.strip()]
        return fields or ["payment_id"]
    fields = [
        field
        for field in ("payment_id", "status", "amount_minor", "amount_major", "currency")
        if field in claimed
    ]
    return fields or ["payment_id"]


def _shopify_match_fields(claimed: dict[str, Any], explicit: list[str] | None) -> list[str]:
    if explicit:
        fields = [field.strip() for field in explicit if field.strip()]
        return fields or ["record_ref"]
    fields = [
        field
        for field in (
            "record_ref",
            "order_id",
            "status",
            "financial_status",
            "fulfillment_status",
            "amount_minor",
            "amount_major",
            "currency",
        )
        if field in claimed
    ]
    return fields or ["record_ref"]


@router.get("/stripe-payment/status", response_model=StripePaymentConnectorStatusResponse)
@limiter.limit("60/minute")
def get_stripe_payment_connector_status(
    request: Request,
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session_read),
) -> StripePaymentConnectorStatusResponse:
    row = get_connector_config(
        db, project_id=tenant_id, connector_type=STRIPE_PAYMENT_CONNECTOR_TYPE
    )
    return _stripe_payment_status_response(row, db=db, project_id=tenant_id)


@router.put("/stripe-payment/config", response_model=StripePaymentConnectorStatusResponse)
@limiter.limit("12/minute")
def save_stripe_payment_connector_config(
    request: Request,
    body: StripePaymentConnectorConfigRequest = Body(...),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> StripePaymentConnectorStatusResponse:
    if context.role not in {"admin", "owner"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant admin role is required.")
    ensure_project_exists(db, context.tenant_id)
    try:
        row = upsert_stripe_payment_connector_config(
            db,
            project_id=context.tenant_id,
            base_url=body.base_url,
            path_template=body.path_template,
            record_path=body.record_path,
            query=body.query,
            bearer_token=body.bearer_token,
            clear_bearer_token=body.clear_bearer_token,
            updated_by_subject=context.subject,
        )
    except (
        InvalidSystemOfRecordConnectorError,
        ProtectedActionMeteringUnavailable,
        ProtectedActionQuotaExceeded,
        VaultCipherUnavailable,
    ) as exc:
        raise _map_config_error(exc) from exc
    return _stripe_payment_status_response(row, db=db, project_id=context.tenant_id)


@router.post(
    "/stripe-payment/test",
    response_model=StripePaymentConnectorTestResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("20/minute")
def test_stripe_payment_connector(
    request: Request,
    body: StripePaymentConnectorTestRequest = Body(...),
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> StripePaymentConnectorTestResponse:
    config = get_connector_config(db, project_id=tenant_id, connector_type=STRIPE_PAYMENT_CONNECTOR_TYPE)
    if config is None or not config.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stripe payment connector is not configured.")

    payment_id = body.payment_id.strip()
    claimed = dict(body.claimed)
    claimed.setdefault("payment_id", payment_id)
    settings = get_settings()
    try:
        bearer_token = decrypt_connector_bearer_token(config, project_id=tenant_id)
        connector = build_stripe_payment_connector(
            config,
            payment_id=payment_id,
            bearer_token=bearer_token,
            timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
            max_attempts=settings.OUTCOME_CONNECTOR_MAX_ATTEMPTS,
        )
        row = reconcile_outcome(
            db,
            project_id=tenant_id,
            claimed=claimed,
            connector=connector,
            call_id=body.call_id,
            trace_id=body.trace_id,
            runtime_policy_decision_id=body.runtime_policy_decision_id,
            action_type=body.action_type or "payment_status",
            system_ref=f"stripe_payment:{payment_id}",
            amount_usd=body.amount_usd,
            currency=body.currency,
            match_fields=_payment_match_fields(claimed, body.match_fields),
            idempotency_key=body.idempotency_key,
            metadata={
                **(body.metadata or {}),
                "connector_kind": STRIPE_PAYMENT_CONNECTOR_TYPE,
                "connector_config_id": config.id,
                "payment_id": payment_id,
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

    return StripePaymentConnectorTestResponse(
        ok=row.verdict == "matched",
        check=reconciliation_to_dict(row),
        connector=_stripe_payment_status_response(updated_config, db=db, project_id=tenant_id),
    )


@router.get("/shopify/status", response_model=ShopifyConnectorStatusResponse)
@limiter.limit("60/minute")
def get_shopify_connector_status(
    request: Request,
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session_read),
) -> ShopifyConnectorStatusResponse:
    row = get_connector_config(
        db, project_id=tenant_id, connector_type=SHOPIFY_ADMIN_CONNECTOR_TYPE
    )
    return _shopify_status_response(row, db=db, project_id=tenant_id)


@router.put("/shopify/config", response_model=ShopifyConnectorStatusResponse)
@limiter.limit("12/minute")
def save_shopify_connector_config(
    request: Request,
    body: ShopifyConnectorConfigRequest = Body(...),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ShopifyConnectorStatusResponse:
    if context.role not in {"admin", "owner"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant admin role is required.")
    ensure_project_exists(db, context.tenant_id)
    try:
        row = upsert_shopify_admin_connector_config(
            db,
            project_id=context.tenant_id,
            base_url=body.base_url,
            path_template=body.path_template,
            record_path=body.record_path,
            query=body.query,
            bearer_token=body.bearer_token,
            clear_bearer_token=body.clear_bearer_token,
            updated_by_subject=context.subject,
        )
    except (
        InvalidSystemOfRecordConnectorError,
        ProtectedActionMeteringUnavailable,
        ProtectedActionQuotaExceeded,
        VaultCipherUnavailable,
    ) as exc:
        raise _map_config_error(exc) from exc
    return _shopify_status_response(row, db=db, project_id=context.tenant_id)


@router.post(
    "/shopify/test",
    response_model=ShopifyConnectorTestResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("20/minute")
def test_shopify_connector(
    request: Request,
    body: ShopifyConnectorTestRequest = Body(...),
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> ShopifyConnectorTestResponse:
    config = get_connector_config(db, project_id=tenant_id, connector_type=SHOPIFY_ADMIN_CONNECTOR_TYPE)
    if config is None or not config.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shopify connector is not configured.")

    record_ref = body.record_ref.strip()
    claimed = dict(body.claimed)
    claimed.setdefault("record_ref", record_ref)
    settings = get_settings()
    try:
        bearer_token = decrypt_connector_bearer_token(config, project_id=tenant_id)
        connector = build_shopify_admin_connector(
            config,
            record_ref=record_ref,
            bearer_token=bearer_token,
            timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
            max_attempts=settings.OUTCOME_CONNECTOR_MAX_ATTEMPTS,
        )
        row = reconcile_outcome(
            db,
            project_id=tenant_id,
            claimed=claimed,
            connector=connector,
            call_id=body.call_id,
            trace_id=body.trace_id,
            runtime_policy_decision_id=body.runtime_policy_decision_id,
            action_type=body.action_type or "shopify_record",
            system_ref=f"shopify:{record_ref}",
            amount_usd=body.amount_usd,
            currency=body.currency,
            match_fields=_shopify_match_fields(claimed, body.match_fields),
            idempotency_key=body.idempotency_key,
            metadata={
                **(body.metadata or {}),
                "connector_kind": SHOPIFY_ADMIN_CONNECTOR_TYPE,
                "connector_config_id": config.id,
                "record_ref": record_ref,
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

    return ShopifyConnectorTestResponse(
        ok=row.verdict == "matched",
        check=reconciliation_to_dict(row),
        connector=_shopify_status_response(updated_config, db=db, project_id=tenant_id),
    )


__all__ = [name for name in globals() if not name.startswith("__")]
