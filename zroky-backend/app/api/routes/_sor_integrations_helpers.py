from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.services.protected_action_billing import (
    ProtectedActionMeteringUnavailable,
    ProtectedActionQuotaExceeded,
    quota_error_detail,
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
    VaultCipherUnavailable,
    get_connector_health_snapshot,
    serialize_connector_config,
)
from app.services.zoho_oauth import ZohoOAuthError

from ._sor_integrations_schemas import *

def _oauth_state_secret(settings: Settings) -> str:
    secret = (settings.OAUTH_STATE_SECRET or settings.AUTH_JWT_SECRET or "").strip()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OAuth state secret is not configured.",
        )
    return secret


def _ledger_status_response(
    row,
    *,
    db: Session | None = None,
    project_id: str | None = None,
) -> LedgerRefundConnectorStatusResponse:
    health = (
        get_connector_health_snapshot(
            db, project_id=project_id, connector_type=LEDGER_REFUND_CONNECTOR_TYPE
        )
        if row is not None and db is not None and project_id
        else None
    )
    return LedgerRefundConnectorStatusResponse(
        **serialize_connector_config(
            row,
            connector_type=LEDGER_REFUND_CONNECTOR_TYPE,
            health=health,
        )
    )


def _stripe_status_response(
    row,
    *,
    db: Session | None = None,
    project_id: str | None = None,
) -> StripeRefundConnectorStatusResponse:
    health = (
        get_connector_health_snapshot(
            db, project_id=project_id, connector_type=STRIPE_REFUND_CONNECTOR_TYPE
        )
        if row is not None and db is not None and project_id
        else None
    )
    return StripeRefundConnectorStatusResponse(
        **serialize_connector_config(
            row,
            connector_type=STRIPE_REFUND_CONNECTOR_TYPE,
            health=health,
        )
    )


def _razorpay_status_response(
    row,
    *,
    db: Session | None = None,
    project_id: str | None = None,
) -> RazorpayRefundConnectorStatusResponse:
    health = (
        get_connector_health_snapshot(
            db, project_id=project_id, connector_type=RAZORPAY_REFUND_CONNECTOR_TYPE
        )
        if row is not None and db is not None and project_id
        else None
    )
    return RazorpayRefundConnectorStatusResponse(
        **serialize_connector_config(
            row,
            connector_type=RAZORPAY_REFUND_CONNECTOR_TYPE,
            health=health,
        )
    )


def _customer_status_response(
    row,
    *,
    db: Session | None = None,
    project_id: str | None = None,
) -> CustomerRecordConnectorStatusResponse:
    health = (
        get_connector_health_snapshot(
            db, project_id=project_id, connector_type=CUSTOMER_RECORD_CONNECTOR_TYPE
        )
        if row is not None and db is not None and project_id
        else None
    )
    return CustomerRecordConnectorStatusResponse(
        **serialize_connector_config(
            row,
            connector_type=CUSTOMER_RECORD_CONNECTOR_TYPE,
            health=health,
        )
    )


def _generic_status_response(
    row,
    *,
    db: Session | None = None,
    project_id: str | None = None,
) -> GenericRestConnectorStatusResponse:
    health = (
        get_connector_health_snapshot(
            db, project_id=project_id, connector_type=GENERIC_REST_CONNECTOR_TYPE
        )
        if row is not None and db is not None and project_id
        else None
    )
    return GenericRestConnectorStatusResponse(
        **serialize_connector_config(
            row,
            connector_type=GENERIC_REST_CONNECTOR_TYPE,
            health=health,
        )
    )


def _hubspot_status_response(
    row,
    *,
    db: Session | None = None,
    project_id: str | None = None,
) -> HubSpotCrmConnectorStatusResponse:
    health = (
        get_connector_health_snapshot(
            db, project_id=project_id, connector_type=HUBSPOT_CRM_CONNECTOR_TYPE
        )
        if row is not None and db is not None and project_id
        else None
    )
    return HubSpotCrmConnectorStatusResponse(
        **serialize_connector_config(
            row,
            connector_type=HUBSPOT_CRM_CONNECTOR_TYPE,
            health=health,
        )
    )


def _zendesk_status_response(
    row,
    *,
    db: Session | None = None,
    project_id: str | None = None,
) -> ZendeskTicketConnectorStatusResponse:
    health = (
        get_connector_health_snapshot(
            db, project_id=project_id, connector_type=ZENDESK_TICKET_CONNECTOR_TYPE
        )
        if row is not None and db is not None and project_id
        else None
    )
    return ZendeskTicketConnectorStatusResponse(
        **serialize_connector_config(
            row,
            connector_type=ZENDESK_TICKET_CONNECTOR_TYPE,
            health=health,
        )
    )


def _jira_status_response(
    row,
    *,
    db: Session | None = None,
    project_id: str | None = None,
) -> JiraIssueConnectorStatusResponse:
    health = (
        get_connector_health_snapshot(
            db, project_id=project_id, connector_type=JIRA_ISSUE_CONNECTOR_TYPE
        )
        if row is not None and db is not None and project_id
        else None
    )
    return JiraIssueConnectorStatusResponse(
        **serialize_connector_config(
            row,
            connector_type=JIRA_ISSUE_CONNECTOR_TYPE,
            health=health,
        )
    )


def _salesforce_status_response(
    row,
    *,
    db: Session | None = None,
    project_id: str | None = None,
) -> SalesforceCrmConnectorStatusResponse:
    health = (
        get_connector_health_snapshot(
            db, project_id=project_id, connector_type=SALESFORCE_CRM_CONNECTOR_TYPE
        )
        if row is not None and db is not None and project_id
        else None
    )
    return SalesforceCrmConnectorStatusResponse(
        **serialize_connector_config(
            row,
            connector_type=SALESFORCE_CRM_CONNECTOR_TYPE,
            health=health,
        )
    )


def _zoho_status_response(
    row,
    *,
    db: Session | None = None,
    project_id: str | None = None,
) -> ZohoCrmConnectorStatusResponse:
    health = (
        get_connector_health_snapshot(
            db, project_id=project_id, connector_type=ZOHO_CRM_CONNECTOR_TYPE
        )
        if row is not None and db is not None and project_id
        else None
    )
    return ZohoCrmConnectorStatusResponse(
        **serialize_connector_config(
            row,
            connector_type=ZOHO_CRM_CONNECTOR_TYPE,
            health=health,
        )
    )


def _netsuite_status_response(
    row,
    *,
    db: Session | None = None,
    project_id: str | None = None,
) -> NetSuiteFinanceConnectorStatusResponse:
    health = (
        get_connector_health_snapshot(
            db, project_id=project_id, connector_type=NETSUITE_FINANCE_CONNECTOR_TYPE
        )
        if row is not None and db is not None and project_id
        else None
    )
    return NetSuiteFinanceConnectorStatusResponse(
        **serialize_connector_config(
            row,
            connector_type=NETSUITE_FINANCE_CONNECTOR_TYPE,
            health=health,
        )
    )


def _postgres_status_response(
    row,
    *,
    db: Session | None = None,
    project_id: str | None = None,
) -> PostgresReadConnectorStatusResponse:
    health = (
        get_connector_health_snapshot(
            db, project_id=project_id, connector_type=POSTGRES_READ_CONNECTOR_TYPE
        )
        if row is not None and db is not None and project_id
        else None
    )
    return PostgresReadConnectorStatusResponse(
        **serialize_connector_config(
            row,
            connector_type=POSTGRES_READ_CONNECTOR_TYPE,
            health=health,
        )
    )


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


def _customer_match_fields(
    claimed: dict[str, Any], explicit: list[str] | None
) -> list[str]:
    if explicit:
        fields = [field.strip() for field in explicit if field.strip()]
        return fields or ["customer_id"]
    fields = [
        field
        for field in (
            "customer_id",
            "email",
            "account_id",
            "status",
            "lifecycle_stage",
            "plan",
            "tier",
        )
        if field in claimed
    ]
    return fields or ["customer_id"]


def _generic_match_fields(claimed: dict[str, Any], explicit: list[str] | None) -> list[str]:
    if explicit:
        fields = [field.strip() for field in explicit if field.strip()]
        return fields or ["record_ref"]
    fields = [field for field in claimed.keys() if field != "record_ref"]
    return fields or ["record_ref"]


def _hubspot_match_fields(claimed: dict[str, Any], explicit: list[str] | None) -> list[str]:
    if explicit:
        fields = [field.strip() for field in explicit if field.strip()]
        return fields or ["email"]
    fields = [
        field
        for field in (
            "email",
            "lifecyclestage",
            "hs_lead_status",
            "status",
            "firstname",
            "lastname",
            "hs_object_id",
        )
        if field in claimed
    ]
    return fields or ["record_ref"]


def _zendesk_match_fields(claimed: dict[str, Any], explicit: list[str] | None) -> list[str]:
    if explicit:
        fields = [field.strip() for field in explicit if field.strip()]
        return fields or ["ticket_id"]
    fields = [
        field
        for field in (
            "ticket_id",
            "status",
            "subject",
            "requester_id",
            "assignee_id",
            "priority",
            "type",
        )
        if field in claimed
    ]
    return fields or ["record_ref"]


def _jira_match_fields(claimed: dict[str, Any], explicit: list[str] | None) -> list[str]:
    if explicit:
        fields = [field.strip() for field in explicit if field.strip()]
        return fields or ["jira_issue_key"]
    fields = [
        field
        for field in (
            "jira_issue_key",
            "issue_key",
            "record_ref",
            "status",
            "summary",
            "assignee_id",
            "assignee",
            "reporter_id",
            "issue_type",
            "project_key",
            "priority",
        )
        if field in claimed
    ]
    return fields or ["jira_issue_key"]


def _salesforce_match_fields(claimed: dict[str, Any], explicit: list[str] | None) -> list[str]:
    if explicit:
        fields = [field.strip() for field in explicit if field.strip()]
        return fields or ["salesforce_id"]
    fields = [
        field
        for field in (
            "Id",
            "salesforce_id",
            "Name",
            "Status",
            "StageName",
            "LeadStatus",
            "Amount",
            "Email",
            "status",
            "amount_usd",
        )
        if field in claimed
    ]
    return fields or ["record_ref"]


def _zoho_match_fields(claimed: dict[str, Any], explicit: list[str] | None) -> list[str]:
    if explicit:
        fields = [field.strip() for field in explicit if field.strip()]
        return fields or ["zoho_record_id"]
    fields = [
        field
        for field in (
            "id",
            "zoho_record_id",
            "Full_Name",
            "Email",
            "Phone",
            "Company",
            "Stage",
            "Lead_Status",
            "Owner",
            "Amount",
            "status",
            "amount_usd",
        )
        if field in claimed
    ]
    return fields or ["record_ref"]


def _netsuite_match_fields(
    claimed: dict[str, Any], explicit: list[str] | None
) -> list[str]:
    if explicit:
        fields = [field.strip() for field in explicit if field.strip()]
        return fields or ["netsuite_record_id"]
    fields = [
        field
        for field in (
            "netsuite_record_id",
            "record_ref",
            "record_type",
            "tran_id",
            "status",
            "amount_usd",
            "currency",
            "entity_id",
        )
        if field in claimed
    ]
    return fields or ["record_ref"]


def _postgres_match_fields(
    claimed: dict[str, Any], explicit: list[str] | None
) -> list[str] | None:
    if explicit:
        fields = [field.strip() for field in explicit if field.strip()]
        return fields or None
    fields = [field for field in claimed.keys() if field]
    return fields or None


def _map_config_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ProtectedActionQuotaExceeded):
        detail = quota_error_detail(exc)
        headers = {}
        if detail.get("current_plan"):
            headers["X-Zroky-Plan-Hint"] = str(detail["current_plan"])
        return HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=detail,
            headers=headers,
        )
    if isinstance(exc, ProtectedActionMeteringUnavailable):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
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
    if isinstance(exc, ZohoOAuthError):
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    return HTTPException(
        status_code=422,
        detail=str(exc),
    )

__all__ = [name for name in globals() if not name.startswith("__")]
