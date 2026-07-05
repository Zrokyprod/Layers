from __future__ import annotations

import json
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


def _exchange_zoho_code_for_callback(*, code: str, settings):
    from app.api.routes import system_of_record_integrations as public_routes

    return public_routes.exchange_zoho_code(code=code, settings=settings)

@router.get(
    "/salesforce-crm/status",
    response_model=SalesforceCrmConnectorStatusResponse,
)
@limiter.limit("60/minute")
def get_salesforce_crm_connector_status(
    request: Request,
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session_read),
) -> SalesforceCrmConnectorStatusResponse:
    row = get_connector_config(
        db, project_id=tenant_id, connector_type=SALESFORCE_CRM_CONNECTOR_TYPE
    )
    return _salesforce_status_response(row, db=db, project_id=tenant_id)


@router.put(
    "/salesforce-crm/config",
    response_model=SalesforceCrmConnectorStatusResponse,
)
@limiter.limit("12/minute")
def save_salesforce_crm_connector_config(
    request: Request,
    body: SalesforceCrmConnectorConfigRequest = Body(...),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> SalesforceCrmConnectorStatusResponse:
    if context.role not in {"admin", "owner"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant admin role is required.",
        )
    ensure_project_exists(db, context.tenant_id)
    try:
        row = upsert_salesforce_crm_connector_config(
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
    return _salesforce_status_response(row, db=db, project_id=context.tenant_id)


@router.post(
    "/salesforce-crm/test",
    response_model=SalesforceCrmConnectorTestResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("20/minute")
def test_salesforce_crm_connector(
    request: Request,
    body: SalesforceCrmConnectorTestRequest = Body(...),
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> SalesforceCrmConnectorTestResponse:
    config = get_connector_config(
        db, project_id=tenant_id, connector_type=SALESFORCE_CRM_CONNECTOR_TYPE
    )
    if config is None or not config.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Salesforce CRM connector is not configured.",
        )

    record_ref = body.record_ref.strip()
    object_type = body.object_type.strip()
    claimed = dict(body.claimed)
    claimed.setdefault("record_ref", record_ref)
    claimed.setdefault("salesforce_id", record_ref)
    claimed.setdefault("object_type", object_type)
    settings = get_settings()
    try:
        bearer_token = decrypt_connector_bearer_token(config, project_id=tenant_id)
        connector = build_salesforce_crm_connector(
            config,
            object_type=object_type,
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
            action_type=body.action_type or "customer_record_update",
            system_ref=body.system_ref or f"salesforce:{object_type}:{record_ref}",
            amount_usd=body.amount_usd,
            currency=body.currency,
            match_fields=_salesforce_match_fields(claimed, body.match_fields),
            idempotency_key=body.idempotency_key,
            metadata={
                **(body.metadata or {}),
                "connector_kind": SALESFORCE_CRM_CONNECTOR_TYPE,
                "connector_config_id": config.id,
                "object_type": object_type,
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

    return SalesforceCrmConnectorTestResponse(
        ok=row.verdict == "matched",
        check=reconciliation_to_dict(row),
        connector=_salesforce_status_response(updated_config, db=db, project_id=tenant_id),
    )


@router.get(
    "/zoho-crm/oauth/start",
    response_model=OAuthStartResponse,
)
@limiter.limit("10/minute")
def start_zoho_crm_oauth(
    request: Request,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> OAuthStartResponse:
    if context.role not in {"admin", "owner"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant admin role is required.",
        )
    ensure_project_exists(db, context.tenant_id)
    settings = get_settings()
    try:
        require_zoho_oauth_config(settings)
    except ZohoOAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    state = generate_oauth_state_with_payload(
        _oauth_state_secret(settings),
        {
            "purpose": "zoho_crm_connect",
            "tenant_id": context.tenant_id,
            "subject": context.subject,
        },
    )
    params = {
        "client_id": settings.ZOHO_CLIENT_ID,
        "scope": settings.ZOHO_OAUTH_SCOPES,
        "redirect_uri": settings.ZOHO_OAUTH_REDIRECT_URL,
        "response_type": "code",
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return OAuthStartResponse(
        authorization_url=f"{zoho_accounts_base_url(settings)}{ZOHO_AUTHORIZE_PATH}?{urlencode(params)}"
    )


@router.get("/zoho-crm/oauth/callback")
@limiter.limit("10/minute")
def complete_zoho_crm_oauth(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db_session),
) -> RedirectResponse:
    settings = get_settings()
    try:
        require_zoho_oauth_config(settings)
    except ZohoOAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    state_payload = verify_oauth_state_with_payload(state, _oauth_state_secret(settings))
    if state_payload is None or state_payload.get("purpose") != "zoho_crm_connect":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired Zoho OAuth state.",
        )
    tenant_id = str(state_payload.get("tenant_id") or "").strip()
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zoho OAuth state missing tenant.",
        )
    ensure_project_exists(db, tenant_id)
    try:
        payload = _exchange_zoho_code_for_callback(code=code, settings=settings)
    except ZohoOAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    access_token = str(payload.get("access_token") or "").strip()
    refresh_token = str(payload.get("refresh_token") or "").strip() or None
    api_domain = str(payload.get("api_domain") or "").strip() or settings.ZOHO_DEFAULT_API_BASE_URL
    existing = get_connector_config(
        db, project_id=tenant_id, connector_type=ZOHO_CRM_CONNECTOR_TYPE
    )
    if refresh_token is None and (
        existing is None or not existing.oauth_refresh_token_ciphertext
    ):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Zoho OAuth response missing refresh token. Reconnect with consent enabled.",
        )
    existing_query = None
    if existing is not None and existing.query_json:
        try:
            existing_query = json.loads(existing.query_json)
        except json.JSONDecodeError:
            existing_query = None
    upsert_zoho_crm_connector_config(
        db,
        project_id=tenant_id,
        base_url=api_domain,
        path_template=existing.path_template if existing is not None else "/crm/v8/{module_name}/{record_ref}",
        record_path=existing.record_path if existing is not None else "data.0",
        query=existing_query,
        bearer_token=access_token,
        oauth_refresh_token=refresh_token,
        updated_by_subject=str(state_payload.get("subject") or "").strip() or None,
    )
    return RedirectResponse(
        url=f"{settings.FRONTEND_URL.rstrip('/')}/integrations?connector=zoho_crm&oauth=success"
    )


@router.get(
    "/zoho-crm/status",
    response_model=ZohoCrmConnectorStatusResponse,
)
@limiter.limit("60/minute")
def get_zoho_crm_connector_status(
    request: Request,
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session_read),
) -> ZohoCrmConnectorStatusResponse:
    row = get_connector_config(
        db, project_id=tenant_id, connector_type=ZOHO_CRM_CONNECTOR_TYPE
    )
    return _zoho_status_response(row, db=db, project_id=tenant_id)


@router.put(
    "/zoho-crm/config",
    response_model=ZohoCrmConnectorStatusResponse,
)
@limiter.limit("12/minute")
def save_zoho_crm_connector_config(
    request: Request,
    body: ZohoCrmConnectorConfigRequest = Body(...),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ZohoCrmConnectorStatusResponse:
    if context.role not in {"admin", "owner"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant admin role is required.",
        )
    ensure_project_exists(db, context.tenant_id)
    try:
        row = upsert_zoho_crm_connector_config(
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
    return _zoho_status_response(row, db=db, project_id=context.tenant_id)


@router.post(
    "/zoho-crm/test",
    response_model=ZohoCrmConnectorTestResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("20/minute")
def test_zoho_crm_connector(
    request: Request,
    body: ZohoCrmConnectorTestRequest = Body(...),
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> ZohoCrmConnectorTestResponse:
    config = get_connector_config(
        db, project_id=tenant_id, connector_type=ZOHO_CRM_CONNECTOR_TYPE
    )
    if config is None or not config.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Zoho CRM connector is not configured.",
        )

    record_ref = body.record_ref.strip()
    module_name = body.module_name.strip()
    claimed = dict(body.claimed)
    claimed.setdefault("record_ref", record_ref)
    claimed.setdefault("zoho_record_id", record_ref)
    claimed.setdefault("module_name", module_name)
    settings = get_settings()
    try:
        bearer_token = resolve_zoho_crm_bearer_token(
            config,
            project_id=tenant_id,
            settings=settings,
        )
        connector = build_zoho_crm_connector(
            config,
            module_name=module_name,
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
            action_type=body.action_type or "customer_record_update",
            system_ref=body.system_ref or f"zoho:{module_name}:{record_ref}",
            amount_usd=body.amount_usd,
            currency=body.currency,
            match_fields=_zoho_match_fields(claimed, body.match_fields),
            idempotency_key=body.idempotency_key,
            metadata={
                **(body.metadata or {}),
                "connector_kind": ZOHO_CRM_CONNECTOR_TYPE,
                "connector_config_id": config.id,
                "module_name": module_name,
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

    return ZohoCrmConnectorTestResponse(
        ok=row.verdict == "matched",
        check=reconciliation_to_dict(row),
        connector=_zoho_status_response(updated_config, db=db, project_id=tenant_id),
    )


@router.get(
    "/netsuite-finance/status",
    response_model=NetSuiteFinanceConnectorStatusResponse,
)
@limiter.limit("60/minute")
def get_netsuite_finance_connector_status(
    request: Request,
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session_read),
) -> NetSuiteFinanceConnectorStatusResponse:
    row = get_connector_config(
        db, project_id=tenant_id, connector_type=NETSUITE_FINANCE_CONNECTOR_TYPE
    )
    return _netsuite_status_response(row, db=db, project_id=tenant_id)


@router.put(
    "/netsuite-finance/config",
    response_model=NetSuiteFinanceConnectorStatusResponse,
)
@limiter.limit("12/minute")
def save_netsuite_finance_connector_config(
    request: Request,
    body: NetSuiteFinanceConnectorConfigRequest = Body(...),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> NetSuiteFinanceConnectorStatusResponse:
    if context.role not in {"admin", "owner"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant admin role is required.",
        )
    ensure_project_exists(db, context.tenant_id)
    try:
        row = upsert_netsuite_finance_connector_config(
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
    return _netsuite_status_response(row, db=db, project_id=context.tenant_id)


@router.post(
    "/netsuite-finance/test",
    response_model=NetSuiteFinanceConnectorTestResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("20/minute")
def test_netsuite_finance_connector(
    request: Request,
    body: NetSuiteFinanceConnectorTestRequest = Body(...),
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> NetSuiteFinanceConnectorTestResponse:
    config = get_connector_config(
        db, project_id=tenant_id, connector_type=NETSUITE_FINANCE_CONNECTOR_TYPE
    )
    if config is None or not config.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="NetSuite finance connector is not configured.",
        )

    record_ref = body.record_ref.strip()
    record_type = body.record_type.strip()
    claimed = dict(body.claimed)
    claimed.setdefault("record_ref", record_ref)
    claimed.setdefault("netsuite_record_id", record_ref)
    claimed.setdefault("record_type", record_type)
    settings = get_settings()
    try:
        bearer_token = decrypt_connector_bearer_token(config, project_id=tenant_id)
        connector = build_netsuite_finance_connector(
            config,
            record_type=record_type,
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
            action_type=body.action_type or "finance_record_update",
            system_ref=body.system_ref or f"netsuite:{record_type}:{record_ref}",
            amount_usd=body.amount_usd,
            currency=body.currency,
            match_fields=_netsuite_match_fields(claimed, body.match_fields),
            idempotency_key=body.idempotency_key,
            metadata={
                **(body.metadata or {}),
                "connector_kind": NETSUITE_FINANCE_CONNECTOR_TYPE,
                "connector_config_id": config.id,
                "record_type": record_type,
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

    return NetSuiteFinanceConnectorTestResponse(
        ok=row.verdict == "matched",
        check=reconciliation_to_dict(row),
        connector=_netsuite_status_response(updated_config, db=db, project_id=tenant_id),
    )
