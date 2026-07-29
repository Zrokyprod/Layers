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
    "/customer-record/status",
    response_model=CustomerRecordConnectorStatusResponse,
)
@limiter.limit("60/minute")
def get_customer_record_connector_status(
    request: Request,
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session_read),
) -> CustomerRecordConnectorStatusResponse:
    row = get_connector_config(
        db, project_id=tenant_id, connector_type=CUSTOMER_RECORD_CONNECTOR_TYPE
    )
    return _customer_status_response(row, db=db, project_id=tenant_id)


@router.put(
    "/customer-record/config",
    response_model=CustomerRecordConnectorStatusResponse,
)
@limiter.limit("12/minute")
def save_customer_record_connector_config(
    request: Request,
    body: CustomerRecordConnectorConfigRequest = Body(...),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> CustomerRecordConnectorStatusResponse:
    if context.role not in {"admin", "owner"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant admin role is required.",
        )
    ensure_project_exists(db, context.tenant_id)
    settings = get_settings()
    try:
        row = upsert_customer_record_connector_config(
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
    return _customer_status_response(row, db=db, project_id=context.tenant_id)


@router.post(
    "/customer-record/test",
    response_model=CustomerRecordConnectorTestResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("20/minute")
def test_customer_record_connector(
    request: Request,
    body: CustomerRecordConnectorTestRequest = Body(...),
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> CustomerRecordConnectorTestResponse:
    config = get_connector_config(
        db, project_id=tenant_id, connector_type=CUSTOMER_RECORD_CONNECTOR_TYPE
    )
    if config is None or not config.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer record connector is not configured.",
        )

    customer_id = body.customer_id.strip()
    claimed = dict(body.claimed)
    claimed.setdefault("customer_id", customer_id)
    settings = get_settings()
    try:
        bearer_token = decrypt_connector_bearer_token(config, project_id=tenant_id, db=db)
        connector = build_customer_record_connector(
            config,
            customer_id=customer_id,
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
            action_type=body.action_type or "customer_record_update",
            system_ref=f"crm:{customer_id}",
            amount_usd=body.amount_usd,
            currency=body.currency,
            match_fields=_customer_match_fields(claimed, body.match_fields),
            idempotency_key=body.idempotency_key,
            metadata={
                **(body.metadata or {}),
                "connector_kind": "customer_record_api",
                "connector_config_id": config.id,
                "customer_id": customer_id,
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

    return CustomerRecordConnectorTestResponse(
        ok=row.verdict == "matched",
        check=reconciliation_to_dict(row),
        connector=_customer_status_response(
            updated_config, db=db, project_id=tenant_id
        ),
    )


@router.get(
    "/generic-rest/status",
    response_model=GenericRestConnectorStatusResponse,
)
@limiter.limit("60/minute")
def get_generic_rest_connector_status(
    request: Request,
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session_read),
) -> GenericRestConnectorStatusResponse:
    row = get_connector_config(
        db, project_id=tenant_id, connector_type=GENERIC_REST_CONNECTOR_TYPE
    )
    return _generic_status_response(row, db=db, project_id=tenant_id)


@router.put(
    "/generic-rest/config",
    response_model=GenericRestConnectorStatusResponse,
)
@limiter.limit("12/minute")
def save_generic_rest_connector_config(
    request: Request,
    body: GenericRestConnectorConfigRequest = Body(...),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> GenericRestConnectorStatusResponse:
    if context.role not in {"admin", "owner"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant admin role is required.",
        )
    ensure_project_exists(db, context.tenant_id)
    settings = get_settings()
    try:
        row = upsert_generic_rest_connector_config(
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
    return _generic_status_response(row, db=db, project_id=context.tenant_id)


@router.post(
    "/generic-rest/test",
    response_model=GenericRestConnectorTestResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("20/minute")
def test_generic_rest_connector(
    request: Request,
    body: GenericRestConnectorTestRequest = Body(...),
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> GenericRestConnectorTestResponse:
    config = get_connector_config(
        db, project_id=tenant_id, connector_type=GENERIC_REST_CONNECTOR_TYPE
    )
    if config is None or not config.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generic REST connector is not configured.",
        )

    record_ref = body.record_ref.strip()
    claimed = dict(body.claimed)
    claimed.setdefault("record_ref", record_ref)
    settings = get_settings()
    try:
        bearer_token = decrypt_connector_bearer_token(config, project_id=tenant_id, db=db)
        connector = build_generic_rest_connector(
            config,
            record_ref=record_ref,
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
            action_type=body.action_type or "custom",
            system_ref=body.system_ref or f"generic:{record_ref}",
            amount_usd=body.amount_usd,
            currency=body.currency,
            match_fields=_generic_match_fields(claimed, body.match_fields),
            idempotency_key=body.idempotency_key,
            metadata={
                **(body.metadata or {}),
                "connector_kind": GENERIC_REST_CONNECTOR_TYPE,
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

    return GenericRestConnectorTestResponse(
        ok=row.verdict == "matched",
        check=reconciliation_to_dict(row),
        connector=_generic_status_response(updated_config, db=db, project_id=tenant_id),
    )
