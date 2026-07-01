from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import (
    TenantContext,
    require_tenant_context,
    require_tenant_role,
)
from app.core.config import Settings, get_settings
from app.core.limiter import limiter
from app.db.session import get_db_session, get_db_session_read
from app.services.dashboard_config import ensure_project_exists
from app.services.outcome_reconciliation import (
    reconcile_outcome,
    reconciliation_to_dict,
)
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
    get_connector_health_snapshot,
    mark_connector_tested,
    serialize_connector_config,
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

router = APIRouter(prefix="/v1/integrations/system-of-record")


class OAuthStartResponse(BaseModel):
    authorization_url: str


def _oauth_state_secret(settings: Settings) -> str:
    secret = (settings.OAUTH_STATE_SECRET or settings.AUTH_JWT_SECRET or "").strip()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OAuth state secret is not configured.",
        )
    return secret


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
    health_status: str = "not_configured"
    last_verdict: str | None = None
    last_error: str | None = None
    last_error_code: str | None = None
    last_http_status: int | None = None
    last_attempts: int | None = None
    last_retryable: bool | None = None
    last_checked_at: Any | None = None
    readiness: dict[str, Any] = Field(default_factory=dict)
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


class StripeRefundConnectorStatusResponse(LedgerRefundConnectorStatusResponse):
    pass


class StripeRefundConnectorConfigRequest(BaseModel):
    base_url: str = Field(default="https://api.stripe.com", max_length=2048)
    path_template: str = Field(default="/v1/refunds/{refund_id}", max_length=512)
    record_path: str | None = Field(default=None, max_length=255)
    query: dict[str, str | int | float | bool] | None = None
    bearer_token: str | None = Field(default=None, max_length=4096)
    clear_bearer_token: bool = False

    @field_validator("base_url")
    @classmethod
    def _normalize_base_url(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("base_url is required")
        return cleaned

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


class StripeRefundConnectorTestRequest(LedgerRefundConnectorTestRequest):
    pass


class StripeRefundConnectorTestResponse(BaseModel):
    ok: bool
    check: dict[str, Any]
    connector: StripeRefundConnectorStatusResponse


class RazorpayRefundConnectorStatusResponse(LedgerRefundConnectorStatusResponse):
    pass


class RazorpayRefundConnectorConfigRequest(BaseModel):
    base_url: str = Field(default="https://api.razorpay.com", max_length=2048)
    path_template: str = Field(default="/v1/refunds/{refund_id}", max_length=512)
    record_path: str | None = Field(default=None, max_length=255)
    query: dict[str, str | int | float | bool] | None = None
    key_id: str = Field(..., min_length=4, max_length=255)
    key_secret: str | None = Field(default=None, max_length=4096)
    clear_key_secret: bool = False

    @field_validator("base_url", "key_id")
    @classmethod
    def _normalize_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value is required")
        return cleaned

    @field_validator("key_secret")
    @classmethod
    def _normalize_secret(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        if len(cleaned) < 8:
            raise ValueError("key_secret must be at least 8 characters")
        return cleaned


class RazorpayRefundConnectorTestRequest(LedgerRefundConnectorTestRequest):
    pass


class RazorpayRefundConnectorTestResponse(BaseModel):
    ok: bool
    check: dict[str, Any]
    connector: RazorpayRefundConnectorStatusResponse


class CustomerRecordConnectorStatusResponse(BaseModel):
    connected: bool
    connector_type: str
    base_url: str | None = None
    path_template: str | None = None
    record_path: str | None = None
    query: dict[str, Any] | None = None
    has_bearer_token: bool
    bearer_token_last4: str | None = None
    last_tested_at: Any | None = None
    health_status: str = "not_configured"
    last_verdict: str | None = None
    last_error: str | None = None
    last_error_code: str | None = None
    last_http_status: int | None = None
    last_attempts: int | None = None
    last_retryable: bool | None = None
    last_checked_at: Any | None = None
    readiness: dict[str, Any] = Field(default_factory=dict)
    created_at: Any | None = None
    updated_at: Any | None = None


class CustomerRecordConnectorConfigRequest(BaseModel):
    base_url: str = Field(..., max_length=2048)
    path_template: str = Field(default="/customers/{customer_id}", max_length=512)
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


class CustomerRecordConnectorTestRequest(BaseModel):
    customer_id: str = Field(..., min_length=1, max_length=255)
    claimed: dict[str, Any] = Field(default_factory=dict)
    call_id: str | None = Field(None, max_length=64)
    trace_id: str | None = Field(None, max_length=128)
    runtime_policy_decision_id: str | None = Field(None, max_length=36)
    action_type: str | None = Field(default="customer_record_update", max_length=64)
    match_fields: list[str] | None = None
    amount_usd: float | None = Field(None, ge=0)
    currency: str | None = Field(None, min_length=3, max_length=3)
    idempotency_key: str | None = Field(None, max_length=255)
    metadata: dict[str, Any] | None = None

    @field_validator("currency")
    @classmethod
    def _normalise_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class CustomerRecordConnectorTestResponse(BaseModel):
    ok: bool
    check: dict[str, Any]
    connector: CustomerRecordConnectorStatusResponse


class GenericRestConnectorStatusResponse(BaseModel):
    connected: bool
    connector_type: str
    base_url: str | None = None
    path_template: str | None = None
    record_path: str | None = None
    query: dict[str, Any] | None = None
    has_bearer_token: bool
    bearer_token_last4: str | None = None
    last_tested_at: Any | None = None
    health_status: str = "not_configured"
    last_verdict: str | None = None
    last_error: str | None = None
    last_error_code: str | None = None
    last_http_status: int | None = None
    last_attempts: int | None = None
    last_retryable: bool | None = None
    last_checked_at: Any | None = None
    readiness: dict[str, Any] = Field(default_factory=dict)
    created_at: Any | None = None
    updated_at: Any | None = None


class GenericRestConnectorConfigRequest(BaseModel):
    base_url: str = Field(..., max_length=2048)
    path_template: str = Field(default="/records/{record_ref}", max_length=512)
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


class GenericRestConnectorTestRequest(BaseModel):
    record_ref: str = Field(..., min_length=1, max_length=255)
    claimed: dict[str, Any] = Field(default_factory=dict)
    call_id: str | None = Field(None, max_length=64)
    trace_id: str | None = Field(None, max_length=128)
    runtime_policy_decision_id: str | None = Field(None, max_length=36)
    action_type: str | None = Field(default="custom", max_length=64)
    system_ref: str | None = Field(default=None, max_length=255)
    match_fields: list[str] | None = None
    amount_usd: float | None = Field(None, ge=0)
    currency: str | None = Field(None, min_length=3, max_length=3)
    idempotency_key: str | None = Field(None, max_length=255)
    metadata: dict[str, Any] | None = None

    @field_validator("currency")
    @classmethod
    def _normalise_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class GenericRestConnectorTestResponse(BaseModel):
    ok: bool
    check: dict[str, Any]
    connector: GenericRestConnectorStatusResponse


class HubSpotCrmConnectorStatusResponse(BaseModel):
    connected: bool
    connector_type: str
    base_url: str | None = None
    path_template: str | None = None
    record_path: str | None = None
    query: dict[str, Any] | None = None
    has_bearer_token: bool
    bearer_token_last4: str | None = None
    last_tested_at: Any | None = None
    health_status: str = "not_configured"
    last_verdict: str | None = None
    last_error: str | None = None
    last_error_code: str | None = None
    last_http_status: int | None = None
    last_attempts: int | None = None
    last_retryable: bool | None = None
    last_checked_at: Any | None = None
    readiness: dict[str, Any] = Field(default_factory=dict)
    created_at: Any | None = None
    updated_at: Any | None = None


class HubSpotCrmConnectorConfigRequest(BaseModel):
    path_template: str = Field(
        default="/crm/v3/objects/contacts/{record_ref}",
        max_length=512,
    )
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


class HubSpotCrmConnectorTestRequest(BaseModel):
    record_ref: str = Field(..., min_length=1, max_length=255)
    claimed: dict[str, Any] = Field(default_factory=dict)
    call_id: str | None = Field(None, max_length=64)
    trace_id: str | None = Field(None, max_length=128)
    runtime_policy_decision_id: str | None = Field(None, max_length=36)
    action_type: str | None = Field(default="customer_record_update", max_length=64)
    system_ref: str | None = Field(default=None, max_length=255)
    match_fields: list[str] | None = None
    amount_usd: float | None = Field(None, ge=0)
    currency: str | None = Field(None, min_length=3, max_length=3)
    idempotency_key: str | None = Field(None, max_length=255)
    metadata: dict[str, Any] | None = None

    @field_validator("currency")
    @classmethod
    def _normalise_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class HubSpotCrmConnectorTestResponse(BaseModel):
    ok: bool
    check: dict[str, Any]
    connector: HubSpotCrmConnectorStatusResponse


class ZendeskTicketConnectorStatusResponse(BaseModel):
    connected: bool
    connector_type: str
    base_url: str | None = None
    path_template: str | None = None
    record_path: str | None = None
    query: dict[str, Any] | None = None
    has_bearer_token: bool
    bearer_token_last4: str | None = None
    last_tested_at: Any | None = None
    health_status: str = "not_configured"
    last_verdict: str | None = None
    last_error: str | None = None
    last_error_code: str | None = None
    last_http_status: int | None = None
    last_attempts: int | None = None
    last_retryable: bool | None = None
    last_checked_at: Any | None = None
    readiness: dict[str, Any] = Field(default_factory=dict)
    created_at: Any | None = None
    updated_at: Any | None = None


class ZendeskTicketConnectorConfigRequest(BaseModel):
    base_url: str = Field(..., max_length=255)
    path_template: str = Field(
        default="/api/v2/tickets/{record_ref}.json",
        max_length=512,
    )
    record_path: str | None = Field(default="ticket", max_length=255)
    query: dict[str, str | int | float | bool] | None = None
    auth_username: str | None = Field(default=None, max_length=255)
    bearer_token: str | None = Field(default=None, max_length=4096)
    clear_bearer_token: bool = False

    @field_validator("base_url")
    @classmethod
    def _normalize_base_url(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("base_url is required")
        return cleaned

    @field_validator("auth_username")
    @classmethod
    def _normalize_auth_username(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

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


class ZendeskTicketConnectorTestRequest(BaseModel):
    record_ref: str = Field(..., min_length=1, max_length=255)
    claimed: dict[str, Any] = Field(default_factory=dict)
    call_id: str | None = Field(None, max_length=64)
    trace_id: str | None = Field(None, max_length=128)
    runtime_policy_decision_id: str | None = Field(None, max_length=36)
    action_type: str | None = Field(default="ticket_close", max_length=64)
    system_ref: str | None = Field(default=None, max_length=255)
    match_fields: list[str] | None = None
    amount_usd: float | None = Field(None, ge=0)
    currency: str | None = Field(None, min_length=3, max_length=3)
    idempotency_key: str | None = Field(None, max_length=255)
    metadata: dict[str, Any] | None = None

    @field_validator("currency")
    @classmethod
    def _normalise_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class ZendeskTicketConnectorTestResponse(BaseModel):
    ok: bool
    check: dict[str, Any]
    connector: ZendeskTicketConnectorStatusResponse


class JiraIssueConnectorStatusResponse(BaseModel):
    connected: bool
    connector_type: str
    base_url: str | None = None
    path_template: str | None = None
    record_path: str | None = None
    query: dict[str, Any] | None = None
    has_bearer_token: bool
    bearer_token_last4: str | None = None
    last_tested_at: Any | None = None
    health_status: str = "not_configured"
    last_verdict: str | None = None
    last_error: str | None = None
    last_error_code: str | None = None
    last_http_status: int | None = None
    last_attempts: int | None = None
    last_retryable: bool | None = None
    last_checked_at: Any | None = None
    readiness: dict[str, Any] = Field(default_factory=dict)
    created_at: Any | None = None
    updated_at: Any | None = None


class JiraIssueConnectorConfigRequest(BaseModel):
    base_url: str = Field(default="https://example.atlassian.net", max_length=2048)
    path_template: str = Field(
        default="/rest/api/3/issue/{record_ref}",
        max_length=512,
    )
    record_path: str | None = Field(default=None, max_length=255)
    query: dict[str, str | int | float | bool] | None = None
    auth_username: str | None = Field(default=None, max_length=255)
    bearer_token: str | None = Field(default=None, max_length=4096)
    clear_bearer_token: bool = False

    @field_validator("base_url")
    @classmethod
    def _normalize_base_url(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("base_url is required")
        return cleaned

    @field_validator("auth_username")
    @classmethod
    def _normalize_auth_username(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

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


class JiraIssueConnectorTestRequest(BaseModel):
    record_ref: str = Field(..., min_length=1, max_length=255)
    claimed: dict[str, Any] = Field(default_factory=dict)
    call_id: str | None = Field(None, max_length=64)
    trace_id: str | None = Field(None, max_length=128)
    runtime_policy_decision_id: str | None = Field(None, max_length=36)
    action_type: str | None = Field(default="ticket_close", max_length=64)
    system_ref: str | None = Field(default=None, max_length=255)
    match_fields: list[str] | None = None
    amount_usd: float | None = Field(None, ge=0)
    currency: str | None = Field(None, min_length=3, max_length=3)
    idempotency_key: str | None = Field(None, max_length=255)
    metadata: dict[str, Any] | None = None

    @field_validator("currency")
    @classmethod
    def _normalise_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class JiraIssueConnectorTestResponse(BaseModel):
    ok: bool
    check: dict[str, Any]
    connector: JiraIssueConnectorStatusResponse


class SalesforceCrmConnectorStatusResponse(BaseModel):
    connected: bool
    connector_type: str
    base_url: str | None = None
    path_template: str | None = None
    record_path: str | None = None
    query: dict[str, Any] | None = None
    has_bearer_token: bool
    bearer_token_last4: str | None = None
    last_tested_at: Any | None = None
    health_status: str = "not_configured"
    last_verdict: str | None = None
    last_error: str | None = None
    last_error_code: str | None = None
    last_http_status: int | None = None
    last_attempts: int | None = None
    last_retryable: bool | None = None
    last_checked_at: Any | None = None
    readiness: dict[str, Any] = Field(default_factory=dict)
    created_at: Any | None = None
    updated_at: Any | None = None


class SalesforceCrmConnectorConfigRequest(BaseModel):
    base_url: str = Field(..., max_length=255)
    path_template: str = Field(
        default="/services/data/v60.0/sobjects/{object_type}/{record_ref}",
        max_length=512,
    )
    record_path: str | None = Field(default=None, max_length=255)
    query: dict[str, str | int | float | bool] | None = None
    bearer_token: str | None = Field(default=None, max_length=4096)
    clear_bearer_token: bool = False

    @field_validator("base_url")
    @classmethod
    def _normalize_base_url(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("base_url is required")
        return cleaned

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


class SalesforceCrmConnectorTestRequest(BaseModel):
    object_type: str = Field(default="Account", min_length=1, max_length=80)
    record_ref: str = Field(..., min_length=1, max_length=255)
    claimed: dict[str, Any] = Field(default_factory=dict)
    call_id: str | None = Field(None, max_length=64)
    trace_id: str | None = Field(None, max_length=128)
    runtime_policy_decision_id: str | None = Field(None, max_length=36)
    action_type: str | None = Field(default="customer_record_update", max_length=64)
    system_ref: str | None = Field(default=None, max_length=255)
    match_fields: list[str] | None = None
    amount_usd: float | None = Field(None, ge=0)
    currency: str | None = Field(None, min_length=3, max_length=3)
    idempotency_key: str | None = Field(None, max_length=255)
    metadata: dict[str, Any] | None = None

    @field_validator("object_type")
    @classmethod
    def _normalize_object_type(cls, value: str) -> str:
        cleaned = value.strip()
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(__c)?", cleaned):
            raise ValueError("object_type must be a Salesforce object API name")
        return cleaned

    @field_validator("currency")
    @classmethod
    def _normalise_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class SalesforceCrmConnectorTestResponse(BaseModel):
    ok: bool
    check: dict[str, Any]
    connector: SalesforceCrmConnectorStatusResponse


class ZohoCrmConnectorStatusResponse(BaseModel):
    connected: bool
    connector_type: str
    base_url: str | None = None
    path_template: str | None = None
    record_path: str | None = None
    query: dict[str, Any] | None = None
    has_bearer_token: bool
    bearer_token_last4: str | None = None
    last_tested_at: Any | None = None
    health_status: str = "not_configured"
    last_verdict: str | None = None
    last_error: str | None = None
    last_error_code: str | None = None
    last_http_status: int | None = None
    last_attempts: int | None = None
    last_retryable: bool | None = None
    last_checked_at: Any | None = None
    readiness: dict[str, Any] = Field(default_factory=dict)
    created_at: Any | None = None
    updated_at: Any | None = None
    has_oauth_refresh_token: bool = False
    oauth_refresh_token_last4: str | None = None


class ZohoCrmConnectorConfigRequest(BaseModel):
    base_url: str = Field(default="https://www.zohoapis.com", max_length=255)
    path_template: str = Field(
        default="/crm/v8/{module_name}/{record_ref}",
        max_length=512,
    )
    record_path: str | None = Field(default="data.0", max_length=255)
    query: dict[str, str | int | float | bool] | None = None
    bearer_token: str | None = Field(default=None, max_length=4096)
    clear_bearer_token: bool = False

    @field_validator("base_url")
    @classmethod
    def _normalize_base_url(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("base_url is required")
        return cleaned

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


class ZohoCrmConnectorTestRequest(BaseModel):
    module_name: str = Field(default="Contacts", min_length=1, max_length=80)
    record_ref: str = Field(..., min_length=1, max_length=255)
    claimed: dict[str, Any] = Field(default_factory=dict)
    call_id: str | None = Field(None, max_length=64)
    trace_id: str | None = Field(None, max_length=128)
    runtime_policy_decision_id: str | None = Field(None, max_length=36)
    action_type: str | None = Field(default="customer_record_update", max_length=64)
    system_ref: str | None = Field(default=None, max_length=255)
    match_fields: list[str] | None = None
    amount_usd: float | None = Field(None, ge=0)
    currency: str | None = Field(None, min_length=3, max_length=3)
    idempotency_key: str | None = Field(None, max_length=255)
    metadata: dict[str, Any] | None = None

    @field_validator("module_name")
    @classmethod
    def _normalize_module_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", cleaned):
            raise ValueError("module_name must be a Zoho CRM module API name")
        return cleaned

    @field_validator("currency")
    @classmethod
    def _normalise_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class ZohoCrmConnectorTestResponse(BaseModel):
    ok: bool
    check: dict[str, Any]
    connector: ZohoCrmConnectorStatusResponse


class NetSuiteFinanceConnectorStatusResponse(BaseModel):
    connected: bool
    connector_type: str
    base_url: str | None = None
    path_template: str | None = None
    record_path: str | None = None
    query: dict[str, Any] | None = None
    has_bearer_token: bool
    bearer_token_last4: str | None = None
    last_tested_at: Any | None = None
    health_status: str = "not_configured"
    last_verdict: str | None = None
    last_error: str | None = None
    last_error_code: str | None = None
    last_http_status: int | None = None
    last_attempts: int | None = None
    last_retryable: bool | None = None
    last_checked_at: Any | None = None
    readiness: dict[str, Any] = Field(default_factory=dict)
    created_at: Any | None = None
    updated_at: Any | None = None


class NetSuiteFinanceConnectorConfigRequest(BaseModel):
    base_url: str = Field(..., max_length=255)
    path_template: str = Field(
        default="/services/rest/record/v1/{record_type}/{record_ref}",
        max_length=512,
    )
    record_path: str | None = Field(default=None, max_length=255)
    query: dict[str, str | int | float | bool] | None = None
    bearer_token: str | None = Field(default=None, max_length=4096)
    clear_bearer_token: bool = False

    @field_validator("base_url")
    @classmethod
    def _normalize_base_url(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("base_url is required")
        return cleaned

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


class NetSuiteFinanceConnectorTestRequest(BaseModel):
    record_type: str = Field(default="vendorBill", min_length=1, max_length=80)
    record_ref: str = Field(..., min_length=1, max_length=255)
    claimed: dict[str, Any] = Field(default_factory=dict)
    call_id: str | None = Field(None, max_length=64)
    trace_id: str | None = Field(None, max_length=128)
    runtime_policy_decision_id: str | None = Field(None, max_length=36)
    action_type: str | None = Field(default="finance_record_update", max_length=64)
    system_ref: str | None = Field(default=None, max_length=255)
    match_fields: list[str] | None = None
    amount_usd: float | None = Field(None, ge=0)
    currency: str | None = Field(None, min_length=3, max_length=3)
    idempotency_key: str | None = Field(None, max_length=255)
    metadata: dict[str, Any] | None = None

    @field_validator("record_type")
    @classmethod
    def _normalize_record_type(cls, value: str) -> str:
        cleaned = value.strip()
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", cleaned):
            raise ValueError("record_type must be a NetSuite record type API name")
        return cleaned

    @field_validator("currency")
    @classmethod
    def _normalise_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class NetSuiteFinanceConnectorTestResponse(BaseModel):
    ok: bool
    check: dict[str, Any]
    connector: NetSuiteFinanceConnectorStatusResponse


class PostgresReadConnectorStatusResponse(BaseModel):
    connected: bool
    connector_type: str
    base_url: str | None = None
    path_template: str | None = None
    record_path: str | None = None
    query: dict[str, Any] | None = None
    has_database_url: bool = False
    database_url_last4: str | None = None
    has_read_query: bool = False
    read_query_digest: str | None = None
    has_bearer_token: bool = False
    bearer_token_last4: str | None = None
    last_tested_at: Any | None = None
    health_status: str = "not_configured"
    last_verdict: str | None = None
    last_error: str | None = None
    last_error_code: str | None = None
    last_http_status: int | None = None
    last_attempts: int | None = None
    last_retryable: bool | None = None
    last_checked_at: Any | None = None
    readiness: dict[str, Any] = Field(default_factory=dict)
    created_at: Any | None = None
    updated_at: Any | None = None


class PostgresReadConnectorConfigRequest(BaseModel):
    database_url: str | None = Field(default=None, max_length=4096)
    read_query: str = Field(..., min_length=1, max_length=8000)

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        return cleaned

    @field_validator("read_query")
    @classmethod
    def _normalize_read_query(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("read_query is required.")
        return cleaned


class PostgresReadConnectorTestRequest(BaseModel):
    claimed: dict[str, Any] = Field(default_factory=dict)
    params: dict[str, str | int | float | bool | None] | None = None
    call_id: str | None = Field(None, max_length=64)
    trace_id: str | None = Field(None, max_length=128)
    runtime_policy_decision_id: str | None = Field(None, max_length=36)
    action_type: str | None = Field(default="internal_record_verification", max_length=64)
    system_ref: str | None = Field(default=None, max_length=255)
    match_fields: list[str] | None = None
    amount_usd: float | None = Field(None, ge=0)
    currency: str | None = Field(None, min_length=3, max_length=3)
    idempotency_key: str | None = Field(None, max_length=255)
    metadata: dict[str, Any] | None = None

    @field_validator("currency")
    @classmethod
    def _normalise_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class PostgresReadConnectorTestResponse(BaseModel):
    ok: bool
    check: dict[str, Any]
    connector: PostgresReadConnectorStatusResponse


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
        bearer_token = decrypt_connector_bearer_token(config, project_id=tenant_id)
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
        bearer_token = decrypt_connector_bearer_token(config, project_id=tenant_id)
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
        key_secret = decrypt_connector_bearer_token(config, project_id=tenant_id)
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
        bearer_token = decrypt_connector_bearer_token(config, project_id=tenant_id)
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
        bearer_token = decrypt_connector_bearer_token(config, project_id=tenant_id)
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
        bearer_token = decrypt_connector_bearer_token(config, project_id=tenant_id)
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
        payload = exchange_zoho_code(code=code, settings=settings)
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


@router.get(
    "/postgres-read/status",
    response_model=PostgresReadConnectorStatusResponse,
)
@limiter.limit("60/minute")
def get_postgres_read_connector_status(
    request: Request,
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session_read),
) -> PostgresReadConnectorStatusResponse:
    row = get_connector_config(
        db, project_id=tenant_id, connector_type=POSTGRES_READ_CONNECTOR_TYPE
    )
    return _postgres_status_response(row, db=db, project_id=tenant_id)


@router.put(
    "/postgres-read/config",
    response_model=PostgresReadConnectorStatusResponse,
)
@limiter.limit("12/minute")
def save_postgres_read_connector_config(
    request: Request,
    body: PostgresReadConnectorConfigRequest = Body(...),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> PostgresReadConnectorStatusResponse:
    if context.role not in {"admin", "owner"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant admin role is required.",
        )
    ensure_project_exists(db, context.tenant_id)
    settings = get_settings()
    try:
        row = upsert_postgres_read_connector_config(
            db,
            project_id=context.tenant_id,
            database_url=body.database_url,
            read_query=body.read_query,
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
    return _postgres_status_response(row, db=db, project_id=context.tenant_id)


@router.post(
    "/postgres-read/test",
    response_model=PostgresReadConnectorTestResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("20/minute")
def test_postgres_read_connector(
    request: Request,
    body: PostgresReadConnectorTestRequest = Body(...),
    tenant_id: str = Depends(require_tenant_role("admin")),
    db: Session = Depends(get_db_session),
) -> PostgresReadConnectorTestResponse:
    config = get_connector_config(
        db, project_id=tenant_id, connector_type=POSTGRES_READ_CONNECTOR_TYPE
    )
    if config is None or not config.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PostgreSQL read connector is not configured.",
        )

    settings = get_settings()
    try:
        database_url = decrypt_connector_database_url(config, project_id=tenant_id)
        if not database_url:
            raise InvalidSystemOfRecordConnectorError(
                "PostgreSQL database URL is not configured."
            )
        connector = build_postgres_read_connector(
            config,
            database_url=database_url,
            params=body.params,
            timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
            allow_private_hosts=settings.OUTCOME_CONNECTOR_ALLOW_PRIVATE_HOSTS,
        )
        row = reconcile_outcome(
            db,
            project_id=tenant_id,
            claimed=body.claimed,
            connector=connector,
            call_id=body.call_id,
            trace_id=body.trace_id,
            runtime_policy_decision_id=body.runtime_policy_decision_id,
            action_type=body.action_type or "internal_record_verification",
            system_ref=body.system_ref or "postgres:source-record",
            amount_usd=body.amount_usd,
            currency=body.currency,
            match_fields=_postgres_match_fields(body.claimed, body.match_fields),
            idempotency_key=body.idempotency_key,
            metadata={
                **(body.metadata or {}),
                "connector_kind": POSTGRES_READ_CONNECTOR_TYPE,
                "connector_config_id": config.id,
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

    return PostgresReadConnectorTestResponse(
        ok=row.verdict == "matched",
        check=reconciliation_to_dict(row),
        connector=_postgres_status_response(
            updated_config, db=db, project_id=tenant_id
        ),
    )
