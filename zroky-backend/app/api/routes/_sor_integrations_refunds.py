from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import (
    TenantContext,
    require_tenant_context,
    require_tenant_role,
)
from app.core.config import get_settings
from app.core.limiter import limiter
from app.db.session import get_db_session, get_db_session_read
from app.services.dashboard_config import ensure_project_exists
from app.services.outcome_reconciliation import (
    reconcile_outcome,
    reconciliation_to_dict,
)
from app.services.system_of_record_connector_config import (
    CUSTOMER_RECORD_CONNECTOR_TYPE,
    GENERIC_REST_CONNECTOR_TYPE,
    HUBSPOT_CRM_CONNECTOR_TYPE,
    JIRA_ISSUE_CONNECTOR_TYPE,
    LEDGER_REFUND_CONNECTOR_TYPE,
    NETSUITE_FINANCE_CONNECTOR_TYPE,
    POSTGRES_READ_CONNECTOR_TYPE,
    RAZORPAY_REFUND_CONNECTOR_TYPE,
    SALESFORCE_CRM_CONNECTOR_TYPE,
    STRIPE_REFUND_CONNECTOR_TYPE,
    ZENDESK_TICKET_CONNECTOR_TYPE,
    ZOHO_CRM_CONNECTOR_TYPE,
    EnvelopeFormatError,
    InvalidSystemOfRecordConnectorError,
    VaultCipherUnavailable,
    build_customer_record_connector,
    build_generic_rest_connector,
    build_hubspot_crm_connector,
    build_jira_issue_connector,
    build_ledger_refund_connector,
    build_netsuite_finance_connector,
    build_postgres_read_connector,
    build_razorpay_refund_connector,
    build_salesforce_crm_connector,
    build_stripe_refund_connector,
    build_zendesk_ticket_connector,
    build_zoho_crm_connector,
    decrypt_connector_bearer_token,
    decrypt_connector_database_url,
    get_connector_config,
    mark_connector_tested,
    upsert_customer_record_connector_config,
    upsert_generic_rest_connector_config,
    upsert_hubspot_crm_connector_config,
    upsert_jira_issue_connector_config,
    upsert_ledger_refund_connector_config,
    upsert_netsuite_finance_connector_config,
    upsert_postgres_read_connector_config,
    upsert_razorpay_refund_connector_config,
    upsert_salesforce_crm_connector_config,
    upsert_stripe_refund_connector_config,
    upsert_zendesk_ticket_connector_config,
    upsert_zoho_crm_connector_config,
)
from app.services.security import generate_oauth_state_with_payload, verify_oauth_state_with_payload
from app.services.zoho_oauth import (
    ZOHO_AUTHORIZE_PATH,
    ZohoOAuthError,
    exchange_zoho_code,
    require_zoho_oauth_config,
    resolve_zoho_crm_bearer_token,
    zoho_accounts_base_url,
)

from ._sor_integrations_helpers import *
from ._sor_integrations_schemas import *

router = APIRouter()

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
    return _ledger_status_response(row, db=db, project_id=tenant_id)


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
    except (
        InvalidSystemOfRecordConnectorError,
        ProtectedActionMeteringUnavailable,
        ProtectedActionQuotaExceeded,
        VaultCipherUnavailable,
    ) as exc:
        raise _map_config_error(exc) from exc
    return _ledger_status_response(row, db=db, project_id=context.tenant_id)


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
        bearer_token = decrypt_connector_bearer_token(config, project_id=tenant_id, db=db)
        connector = build_ledger_refund_connector(
            config,
            refund_id=refund_id,
            bearer_token=bearer_token,
            timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
            max_attempts=settings.OUTCOME_CONNECTOR_MAX_ATTEMPTS,
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
        ZohoOAuthError,
        ValueError,
    ) as exc:
        raise _map_config_error(exc) from exc

    return LedgerRefundConnectorTestResponse(
        ok=row.verdict == "matched",
        check=reconciliation_to_dict(row),
        connector=_ledger_status_response(updated_config, db=db, project_id=tenant_id),
    )


@router.get(
    "/stripe-refund/status",
    response_model=StripeRefundConnectorStatusResponse,
)
@limiter.limit("60/minute")
def get_stripe_refund_connector_status(
    request: Request,
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session_read),
) -> StripeRefundConnectorStatusResponse:
    row = get_connector_config(
        db, project_id=tenant_id, connector_type=STRIPE_REFUND_CONNECTOR_TYPE
    )
    return _stripe_status_response(row, db=db, project_id=tenant_id)


@router.put(
    "/stripe-refund/config",
    response_model=StripeRefundConnectorStatusResponse,
)
@limiter.limit("12/minute")
def save_stripe_refund_connector_config(
    request: Request,
    body: StripeRefundConnectorConfigRequest = Body(...),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> StripeRefundConnectorStatusResponse:
    if context.role not in {"admin", "owner"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant admin role is required.",
        )
    ensure_project_exists(db, context.tenant_id)
    try:
        row = upsert_stripe_refund_connector_config(
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
    return _stripe_status_response(row, db=db, project_id=context.tenant_id)


@router.post(
    "/stripe-refund/test",
    response_model=StripeRefundConnectorTestResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("20/minute")
def test_stripe_refund_connector(
    request: Request,
    body: StripeRefundConnectorTestRequest = Body(...),
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> StripeRefundConnectorTestResponse:
    config = get_connector_config(
        db, project_id=tenant_id, connector_type=STRIPE_REFUND_CONNECTOR_TYPE
    )
    if config is None or not config.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stripe refund connector is not configured.",
        )

    refund_id = body.refund_id.strip()
    claimed = dict(body.claimed)
    claimed.setdefault("refund_id", refund_id)
    claimed.setdefault("stripe_refund_id", refund_id)
    settings = get_settings()
    try:
        bearer_token = decrypt_connector_bearer_token(config, project_id=tenant_id, db=db)
        connector = build_stripe_refund_connector(
            config,
            refund_id=refund_id,
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
            action_type=body.action_type or "refund",
            system_ref=f"stripe:refund:{refund_id}",
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
                "connector_kind": STRIPE_REFUND_CONNECTOR_TYPE,
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
        ZohoOAuthError,
        ValueError,
    ) as exc:
        raise _map_config_error(exc) from exc

    return StripeRefundConnectorTestResponse(
        ok=row.verdict == "matched",
        check=reconciliation_to_dict(row),
        connector=_stripe_status_response(updated_config, db=db, project_id=tenant_id),
    )


@router.get(
    "/razorpay-refund/status",
    response_model=RazorpayRefundConnectorStatusResponse,
)
@limiter.limit("60/minute")
def get_razorpay_refund_connector_status(
    request: Request,
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session_read),
) -> RazorpayRefundConnectorStatusResponse:
    row = get_connector_config(
        db, project_id=tenant_id, connector_type=RAZORPAY_REFUND_CONNECTOR_TYPE
    )
    return _razorpay_status_response(row, db=db, project_id=tenant_id)


@router.put(
    "/razorpay-refund/config",
    response_model=RazorpayRefundConnectorStatusResponse,
)
@limiter.limit("12/minute")
def save_razorpay_refund_connector_config(
    request: Request,
    body: RazorpayRefundConnectorConfigRequest = Body(...),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> RazorpayRefundConnectorStatusResponse:
    if context.role not in {"admin", "owner"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant admin role is required.",
        )
    ensure_project_exists(db, context.tenant_id)
    try:
        row = upsert_razorpay_refund_connector_config(
            db,
            project_id=context.tenant_id,
            key_id=body.key_id,
            key_secret=body.key_secret,
            base_url=body.base_url,
            path_template=body.path_template,
            record_path=body.record_path,
            query=body.query,
            clear_key_secret=body.clear_key_secret,
            updated_by_subject=context.subject,
        )
    except (
        InvalidSystemOfRecordConnectorError,
        ProtectedActionMeteringUnavailable,
        ProtectedActionQuotaExceeded,
        VaultCipherUnavailable,
    ) as exc:
        raise _map_config_error(exc) from exc
    return _razorpay_status_response(row, db=db, project_id=context.tenant_id)


@router.post(
    "/razorpay-refund/test",
    response_model=RazorpayRefundConnectorTestResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("20/minute")
def test_razorpay_refund_connector(
    request: Request,
    body: RazorpayRefundConnectorTestRequest = Body(...),
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> RazorpayRefundConnectorTestResponse:
    config = get_connector_config(
        db, project_id=tenant_id, connector_type=RAZORPAY_REFUND_CONNECTOR_TYPE
    )
    if config is None or not config.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Razorpay refund connector is not configured.",
        )

    refund_id = body.refund_id.strip()
    claimed = dict(body.claimed)
    claimed.setdefault("refund_id", refund_id)
    claimed.setdefault("razorpay_refund_id", refund_id)
    settings = get_settings()
    try:
        key_secret = decrypt_connector_bearer_token(config, project_id=tenant_id, db=db)
        connector = build_razorpay_refund_connector(
            config,
            refund_id=refund_id,
            key_secret=key_secret,
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
            action_type=body.action_type or "refund",
            system_ref=f"razorpay:refund:{refund_id}",
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
                "connector_kind": RAZORPAY_REFUND_CONNECTOR_TYPE,
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
        ZohoOAuthError,
        ValueError,
    ) as exc:
        raise _map_config_error(exc) from exc

    return RazorpayRefundConnectorTestResponse(
        ok=row.verdict == "matched",
        check=reconciliation_to_dict(row),
        connector=_razorpay_status_response(updated_config, db=db, project_id=tenant_id),
    )
