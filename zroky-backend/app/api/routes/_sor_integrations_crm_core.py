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
from app.services.atlassian_oauth import (
    ATLASSIAN_API_BASE_URL,
    ATLASSIAN_AUTHORIZE_URL,
    AtlassianOAuthError,
    exchange_atlassian_code,
    list_atlassian_accessible_resources,
    pick_jira_resource,
    require_atlassian_oauth_config,
    resolve_jira_bearer_token,
)
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


def _existing_query(row) -> dict[str, object]:
    if row is None or not row.query_json:
        return {}
    try:
        import json

        loaded = json.loads(row.query_json)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}

@router.get(
    "/hubspot-crm/status",
    response_model=HubSpotCrmConnectorStatusResponse,
)
@limiter.limit("60/minute")
def get_hubspot_crm_connector_status(
    request: Request,
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session_read),
) -> HubSpotCrmConnectorStatusResponse:
    row = get_connector_config(
        db, project_id=tenant_id, connector_type=HUBSPOT_CRM_CONNECTOR_TYPE
    )
    return _hubspot_status_response(row, db=db, project_id=tenant_id)


@router.put(
    "/hubspot-crm/config",
    response_model=HubSpotCrmConnectorStatusResponse,
)
@limiter.limit("12/minute")
def save_hubspot_crm_connector_config(
    request: Request,
    body: HubSpotCrmConnectorConfigRequest = Body(...),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> HubSpotCrmConnectorStatusResponse:
    if context.role not in {"admin", "owner"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant admin role is required.",
        )
    ensure_project_exists(db, context.tenant_id)
    try:
        row = upsert_hubspot_crm_connector_config(
            db,
            project_id=context.tenant_id,
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
    return _hubspot_status_response(row, db=db, project_id=context.tenant_id)


@router.post(
    "/hubspot-crm/test",
    response_model=HubSpotCrmConnectorTestResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("20/minute")
def test_hubspot_crm_connector(
    request: Request,
    body: HubSpotCrmConnectorTestRequest = Body(...),
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> HubSpotCrmConnectorTestResponse:
    config = get_connector_config(
        db, project_id=tenant_id, connector_type=HUBSPOT_CRM_CONNECTOR_TYPE
    )
    if config is None or not config.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="HubSpot CRM connector is not configured.",
        )

    record_ref = body.record_ref.strip()
    claimed = dict(body.claimed)
    claimed.setdefault("record_ref", record_ref)
    if "@" in record_ref and "email" not in claimed:
        claimed["email"] = record_ref.strip().lower()
    settings = get_settings()
    try:
        bearer_token = decrypt_connector_bearer_token(config, project_id=tenant_id)
        connector = build_hubspot_crm_connector(
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
            action_type=body.action_type or "customer_record_update",
            system_ref=body.system_ref or f"hubspot:contact:{record_ref}",
            amount_usd=body.amount_usd,
            currency=body.currency,
            match_fields=_hubspot_match_fields(claimed, body.match_fields),
            idempotency_key=body.idempotency_key,
            metadata={
                **(body.metadata or {}),
                "connector_kind": HUBSPOT_CRM_CONNECTOR_TYPE,
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

    return HubSpotCrmConnectorTestResponse(
        ok=row.verdict == "matched",
        check=reconciliation_to_dict(row),
        connector=_hubspot_status_response(updated_config, db=db, project_id=tenant_id),
    )


@router.get(
    "/zendesk-ticket/status",
    response_model=ZendeskTicketConnectorStatusResponse,
)
@limiter.limit("60/minute")
def get_zendesk_ticket_connector_status(
    request: Request,
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session_read),
) -> ZendeskTicketConnectorStatusResponse:
    row = get_connector_config(
        db, project_id=tenant_id, connector_type=ZENDESK_TICKET_CONNECTOR_TYPE
    )
    return _zendesk_status_response(row, db=db, project_id=tenant_id)


@router.put(
    "/zendesk-ticket/config",
    response_model=ZendeskTicketConnectorStatusResponse,
)
@limiter.limit("12/minute")
def save_zendesk_ticket_connector_config(
    request: Request,
    body: ZendeskTicketConnectorConfigRequest = Body(...),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> ZendeskTicketConnectorStatusResponse:
    if context.role not in {"admin", "owner"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant admin role is required.",
        )
    ensure_project_exists(db, context.tenant_id)
    try:
        row = upsert_zendesk_ticket_connector_config(
            db,
            project_id=context.tenant_id,
            base_url=body.base_url,
            path_template=body.path_template,
            record_path=body.record_path,
            query=body.query,
            auth_username=body.auth_username,
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
    return _zendesk_status_response(row, db=db, project_id=context.tenant_id)


@router.post(
    "/zendesk-ticket/test",
    response_model=ZendeskTicketConnectorTestResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("20/minute")
def test_zendesk_ticket_connector(
    request: Request,
    body: ZendeskTicketConnectorTestRequest = Body(...),
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> ZendeskTicketConnectorTestResponse:
    config = get_connector_config(
        db, project_id=tenant_id, connector_type=ZENDESK_TICKET_CONNECTOR_TYPE
    )
    if config is None or not config.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Zendesk ticket connector is not configured.",
        )

    record_ref = body.record_ref.strip()
    claimed = dict(body.claimed)
    claimed.setdefault("record_ref", record_ref)
    claimed.setdefault("ticket_id", record_ref)
    settings = get_settings()
    try:
        bearer_token = decrypt_connector_bearer_token(config, project_id=tenant_id)
        connector = build_zendesk_ticket_connector(
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
            action_type=body.action_type or "ticket_close",
            system_ref=body.system_ref or f"zendesk:ticket:{record_ref}",
            amount_usd=body.amount_usd,
            currency=body.currency,
            match_fields=_zendesk_match_fields(claimed, body.match_fields),
            idempotency_key=body.idempotency_key,
            metadata={
                **(body.metadata or {}),
                "connector_kind": ZENDESK_TICKET_CONNECTOR_TYPE,
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

    return ZendeskTicketConnectorTestResponse(
        ok=row.verdict == "matched",
        check=reconciliation_to_dict(row),
        connector=_zendesk_status_response(updated_config, db=db, project_id=tenant_id),
    )


@router.get(
    "/jira-issue/oauth/start",
    response_model=OAuthStartResponse,
)
@limiter.limit("10/minute")
def start_jira_issue_oauth(
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
        require_atlassian_oauth_config(settings)
    except AtlassianOAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    state = generate_oauth_state_with_payload(
        _oauth_state_secret(settings),
        {
            "purpose": "jira_issue_connect",
            "tenant_id": context.tenant_id,
            "subject": context.subject,
        },
    )
    params = {
        "audience": "api.atlassian.com",
        "client_id": settings.ATLASSIAN_CLIENT_ID,
        "scope": settings.ATLASSIAN_OAUTH_SCOPES,
        "redirect_uri": settings.ATLASSIAN_OAUTH_REDIRECT_URL,
        "state": state,
        "response_type": "code",
        "prompt": "consent",
    }
    return OAuthStartResponse(authorization_url=f"{ATLASSIAN_AUTHORIZE_URL}?{urlencode(params)}")


@router.get("/jira-issue/oauth/callback")
@limiter.limit("10/minute")
def complete_jira_issue_oauth(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db_session),
) -> RedirectResponse:
    settings = get_settings()
    try:
        require_atlassian_oauth_config(settings)
    except AtlassianOAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    state_payload = verify_oauth_state_with_payload(state, _oauth_state_secret(settings))
    if state_payload is None or state_payload.get("purpose") != "jira_issue_connect":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired Jira OAuth state.",
        )
    tenant_id = str(state_payload.get("tenant_id") or "").strip()
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Jira OAuth state missing tenant.",
        )
    ensure_project_exists(db, tenant_id)
    try:
        payload = exchange_atlassian_code(code=code, settings=settings)
        access_token = str(payload.get("access_token") or "").strip()
        refresh_token = str(payload.get("refresh_token") or "").strip() or None
        if not refresh_token:
            raise AtlassianOAuthError(
                "Atlassian OAuth did not return a refresh token; include offline_access in ATLASSIAN_OAUTH_SCOPES."
            )
        resource = pick_jira_resource(
            list_atlassian_accessible_resources(access_token=access_token)
        )
    except AtlassianOAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    cloud_id = str(resource.get("id") or "").strip()
    site_url = str(resource.get("url") or "").strip()
    site_name = str(resource.get("name") or "").strip()
    if not cloud_id:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Atlassian OAuth response missing Jira cloud id.",
        )

    existing = get_connector_config(
        db, project_id=tenant_id, connector_type=JIRA_ISSUE_CONNECTOR_TYPE
    )
    query = {
        **_existing_query(existing),
        "auth_mode": "oauth",
        "atlassian_cloud_id": cloud_id,
        "atlassian_site_url": site_url,
        "atlassian_site_name": site_name,
    }
    query.pop("auth_username", None)
    upsert_jira_issue_connector_config(
        db,
        project_id=tenant_id,
        base_url=f"{ATLASSIAN_API_BASE_URL}/ex/jira/{cloud_id}",
        path_template=existing.path_template if existing is not None else "/rest/api/3/issue/{record_ref}",
        record_path=existing.record_path if existing is not None else None,
        query=query,
        bearer_token=access_token,
        oauth_refresh_token=refresh_token,
        updated_by_subject=str(state_payload.get("subject") or "").strip() or None,
    )
    return RedirectResponse(
        url=f"{settings.FRONTEND_URL.rstrip('/')}/integrations?connector=jira_issue&oauth=success"
    )


@router.get(
    "/jira-issue/status",
    response_model=JiraIssueConnectorStatusResponse,
)
@limiter.limit("60/minute")
def get_jira_issue_connector_status(
    request: Request,
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session_read),
) -> JiraIssueConnectorStatusResponse:
    row = get_connector_config(
        db, project_id=tenant_id, connector_type=JIRA_ISSUE_CONNECTOR_TYPE
    )
    return _jira_status_response(row, db=db, project_id=tenant_id)


@router.put(
    "/jira-issue/config",
    response_model=JiraIssueConnectorStatusResponse,
)
@limiter.limit("12/minute")
def save_jira_issue_connector_config(
    request: Request,
    body: JiraIssueConnectorConfigRequest = Body(...),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> JiraIssueConnectorStatusResponse:
    if context.role not in {"admin", "owner"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant admin role is required.",
        )
    ensure_project_exists(db, context.tenant_id)
    try:
        row = upsert_jira_issue_connector_config(
            db,
            project_id=context.tenant_id,
            base_url=body.base_url,
            path_template=body.path_template,
            record_path=body.record_path,
            query=body.query,
            auth_username=body.auth_username,
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
    return _jira_status_response(row, db=db, project_id=context.tenant_id)


@router.post(
    "/jira-issue/test",
    response_model=JiraIssueConnectorTestResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("20/minute")
def test_jira_issue_connector(
    request: Request,
    body: JiraIssueConnectorTestRequest = Body(...),
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> JiraIssueConnectorTestResponse:
    config = get_connector_config(
        db, project_id=tenant_id, connector_type=JIRA_ISSUE_CONNECTOR_TYPE
    )
    if config is None or not config.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Jira issue connector is not configured.",
        )

    record_ref = body.record_ref.strip()
    claimed = dict(body.claimed)
    claimed.setdefault("record_ref", record_ref)
    claimed.setdefault("jira_issue_key", record_ref)
    claimed.setdefault("issue_key", record_ref)
    settings = get_settings()
    try:
        bearer_token = resolve_jira_bearer_token(
            config,
            project_id=tenant_id,
            settings=settings,
            db=db,
        )
        connector = build_jira_issue_connector(
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
            action_type=body.action_type or "ticket_close",
            system_ref=body.system_ref or f"jira:issue:{record_ref}",
            amount_usd=body.amount_usd,
            currency=body.currency,
            match_fields=_jira_match_fields(claimed, body.match_fields),
            idempotency_key=body.idempotency_key,
            metadata={
                **(body.metadata or {}),
                "connector_kind": JIRA_ISSUE_CONNECTOR_TYPE,
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

    return JiraIssueConnectorTestResponse(
        ok=row.verdict == "matched",
        check=reconciliation_to_dict(row),
        connector=_jira_status_response(updated_config, db=db, project_id=tenant_id),
    )
