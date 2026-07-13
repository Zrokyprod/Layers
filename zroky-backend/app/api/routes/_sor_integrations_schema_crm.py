from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

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
    has_oauth_refresh_token: bool = False
    oauth_refresh_token_last4: str | None = None


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

__all__ = [name for name in globals() if not name.startswith("__")]
