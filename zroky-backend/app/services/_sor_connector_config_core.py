"""Tenant-scoped system-of-record connector configuration."""

from __future__ import annotations

import json
import hashlib
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models import OutcomeReconciliationCheck, SystemOfRecordConnectorConfig
from app.services.provider_key_cipher import (
    EnvelopeFormatError,
    VaultCipherUnavailable,
    decrypt_provider_key,
    encrypt_provider_key,
)
from app.services.protected_action_billing import enforce_system_of_record_connector_limit
from app.services.system_of_record_connectors import (
    ConnectorConfigError,
    CustomerRecordApiConnector,
    GenericRestApiConnector,
    HubSpotCrmConnector,
    JiraIssueConnector,
    LedgerRefundApiConnector,
    NetSuiteFinanceConnector,
    PostgresReadOnlyConnector,
    RazorpayRefundConnector,
    SalesforceCrmConnector,
    ShopifyAdminConnector,
    StripePaymentConnector,
    StripeRefundConnector,
    ZendeskTicketConnector,
    ZohoCrmConnector,
    validate_customer_record_api_config,
    validate_generic_rest_api_config,
    validate_hubspot_crm_config,
    validate_jira_issue_config,
    validate_ledger_refund_api_config,
    validate_netsuite_finance_config,
    validate_postgres_read_config,
    validate_razorpay_refund_config,
    validate_salesforce_crm_config,
    validate_stripe_refund_config,
    validate_zendesk_ticket_config,
    validate_zoho_crm_config,
)

CUSTOMER_RECORD_CONNECTOR_TYPE = "customer_record_api"
GENERIC_REST_CONNECTOR_TYPE = "generic_rest_api"
HUBSPOT_CRM_CONNECTOR_TYPE = "hubspot_crm"
JIRA_ISSUE_CONNECTOR_TYPE = "jira_issue"
LEDGER_REFUND_CONNECTOR_TYPE = "ledger_refund_api"
NETSUITE_FINANCE_CONNECTOR_TYPE = "netsuite_finance"
POSTGRES_READ_CONNECTOR_TYPE = "postgres_read"
RAZORPAY_REFUND_CONNECTOR_TYPE = "razorpay_refund"
SALESFORCE_CRM_CONNECTOR_TYPE = "salesforce_crm"
SHOPIFY_ADMIN_CONNECTOR_TYPE = "shopify_admin"
STRIPE_PAYMENT_CONNECTOR_TYPE = "stripe_payment"
STRIPE_REFUND_CONNECTOR_TYPE = "stripe_refund"
ZENDESK_TICKET_CONNECTOR_TYPE = "zendesk_ticket"
ZOHO_CRM_CONNECTOR_TYPE = "zoho_crm"
_SALESFORCE_DEFAULT_QUERY = {
    "fields": "Id,Name",
}
_ZOHO_DEFAULT_QUERY = {
    "fields": "id,Full_Name,Email,Phone,Company,Stage,Amount,Lead_Status,Owner,Modified_Time",
}
_HUBSPOT_DEFAULT_QUERY = {
    "properties": "email,firstname,lastname,lifecyclestage,hs_lead_status,hs_object_id",
}
_JIRA_DEFAULT_QUERY = {
    "fields": "summary,status,assignee,reporter,issuetype,project,priority,updated,created,resolutiondate,labels",
}
_NETSUITE_DEFAULT_QUERY: dict[str, str] = {}
VALID_CONNECTOR_TYPES = frozenset(
    {
        CUSTOMER_RECORD_CONNECTOR_TYPE,
        GENERIC_REST_CONNECTOR_TYPE,
        HUBSPOT_CRM_CONNECTOR_TYPE,
        JIRA_ISSUE_CONNECTOR_TYPE,
        LEDGER_REFUND_CONNECTOR_TYPE,
        NETSUITE_FINANCE_CONNECTOR_TYPE,
        POSTGRES_READ_CONNECTOR_TYPE,
        RAZORPAY_REFUND_CONNECTOR_TYPE,
        SALESFORCE_CRM_CONNECTOR_TYPE,
        SHOPIFY_ADMIN_CONNECTOR_TYPE,
        STRIPE_PAYMENT_CONNECTOR_TYPE,
        STRIPE_REFUND_CONNECTOR_TYPE,
        ZENDESK_TICKET_CONNECTOR_TYPE,
        ZOHO_CRM_CONNECTOR_TYPE,
    }
)

_CONNECTOR_CONTRACTS: dict[str, dict[str, Any]] = {
    LEDGER_REFUND_CONNECTOR_TYPE: {
        "schema_version": "system_of_record_connector.v1",
        "connector_type": LEDGER_REFUND_CONNECTOR_TYPE,
        "adapter": "https_json_record",
        "system_of_record": "ledger_refund",
        "config_endpoint": "/v1/integrations/system-of-record/ledger-refund/config",
        "status_endpoint": "/v1/integrations/system-of-record/ledger-refund/status",
        "test_endpoint": "/v1/integrations/system-of-record/ledger-refund/test",
        "required_inputs": [
            "https_base_url",
            "path_template_with_refund_id",
            "read_scoped_bearer_token",
            "safe_existing_refund_id",
        ],
        "required_record_fields": ["refund_id", "status"],
        "recommended_record_fields": ["amount_minor", "amount_major", "currency"],
        "pass_rule": (
            "A saved connector test must fetch one refund record from the "
            "system of record and reconcile it as matched."
        ),
    },
    STRIPE_REFUND_CONNECTOR_TYPE: {
        "schema_version": "system_of_record_connector.v1",
        "connector_type": STRIPE_REFUND_CONNECTOR_TYPE,
        "adapter": "stripe_refund_read",
        "system_of_record": "stripe",
        "config_endpoint": "/v1/integrations/system-of-record/stripe-refund/config",
        "status_endpoint": "/v1/integrations/system-of-record/stripe-refund/status",
        "test_endpoint": "/v1/integrations/system-of-record/stripe-refund/test",
        "auth_mode": "stripe_secret_key",
        "oauth_status": "not_required",
        "required_inputs": [
            "stripe_secret_key_with_read_scope",
            "safe_existing_refund_id",
            "fields_to_verify",
        ],
        "required_record_fields": ["refund_id", "status"],
        "recommended_record_fields": [
            "amount_minor",
            "amount_major",
            "currency",
            "charge_id",
            "payment_intent_id",
        ],
        "pass_rule": (
            "A saved connector test must fetch one Stripe refund through the "
            "read-only Stripe API and reconcile the configured fields as matched."
        ),
    },
    RAZORPAY_REFUND_CONNECTOR_TYPE: {
        "schema_version": "system_of_record_connector.v1",
        "connector_type": RAZORPAY_REFUND_CONNECTOR_TYPE,
        "adapter": "razorpay_refund_read",
        "system_of_record": "razorpay",
        "config_endpoint": "/v1/integrations/system-of-record/razorpay-refund/config",
        "status_endpoint": "/v1/integrations/system-of-record/razorpay-refund/status",
        "test_endpoint": "/v1/integrations/system-of-record/razorpay-refund/test",
        "auth_mode": "basic_key_id_secret",
        "oauth_status": "not_required",
        "required_inputs": [
            "razorpay_key_id",
            "razorpay_key_secret_with_read_scope",
            "safe_existing_refund_id",
            "fields_to_verify",
        ],
        "required_record_fields": ["refund_id", "status"],
        "recommended_record_fields": [
            "amount_minor",
            "amount_major",
            "currency",
            "payment_id",
            "receipt",
        ],
        "pass_rule": (
            "A saved connector test must fetch one Razorpay refund through the "
            "read-only Razorpay API and reconcile the configured fields as matched."
        ),
    },
    STRIPE_PAYMENT_CONNECTOR_TYPE: {
        "schema_version": "system_of_record_connector.v1",
        "connector_type": STRIPE_PAYMENT_CONNECTOR_TYPE,
        "adapter": "stripe_payment_read",
        "system_of_record": "stripe",
        "config_endpoint": "/v1/integrations/system-of-record/stripe-payment/config",
        "status_endpoint": "/v1/integrations/system-of-record/stripe-payment/status",
        "test_endpoint": "/v1/integrations/system-of-record/stripe-payment/test",
        "auth_mode": "stripe_secret_key",
        "oauth_status": "not_required",
        "required_inputs": [
            "stripe_secret_key_with_read_scope",
            "safe_existing_payment_id",
            "fields_to_verify",
        ],
        "required_record_fields": ["payment_id", "status"],
        "recommended_record_fields": [
            "amount_minor",
            "amount_major",
            "currency",
            "customer",
            "payment_method",
        ],
        "pass_rule": (
            "A saved connector test must fetch one Stripe payment object and "
            "reconcile the configured fields as matched."
        ),
    },
    SHOPIFY_ADMIN_CONNECTOR_TYPE: {
        "schema_version": "system_of_record_connector.v1",
        "connector_type": SHOPIFY_ADMIN_CONNECTOR_TYPE,
        "adapter": "shopify_admin_record_read",
        "system_of_record": "shopify",
        "config_endpoint": "/v1/integrations/system-of-record/shopify/config",
        "status_endpoint": "/v1/integrations/system-of-record/shopify/status",
        "test_endpoint": "/v1/integrations/system-of-record/shopify/test",
        "auth_mode": "admin_api_access_token",
        "oauth_status": "planned",
        "required_inputs": [
            "shopify_shop_admin_base_url",
            "read_scoped_admin_api_token",
            "safe_existing_order_or_record_id",
            "fields_to_verify",
        ],
        "required_record_fields": ["record_ref", "status"],
        "recommended_record_fields": [
            "order_id",
            "amount_minor",
            "amount_major",
            "currency",
            "financial_status",
            "fulfillment_status",
        ],
        "pass_rule": (
            "A saved connector test must fetch one Shopify Admin record and "
            "reconcile the configured fields as matched."
        ),
    },
    CUSTOMER_RECORD_CONNECTOR_TYPE: {
        "schema_version": "system_of_record_connector.v1",
        "connector_type": CUSTOMER_RECORD_CONNECTOR_TYPE,
        "adapter": "https_json_record",
        "system_of_record": "customer_record",
        "config_endpoint": "/v1/integrations/system-of-record/customer-record/config",
        "status_endpoint": "/v1/integrations/system-of-record/customer-record/status",
        "test_endpoint": "/v1/integrations/system-of-record/customer-record/test",
        "required_inputs": [
            "https_base_url",
            "path_template_with_customer_id",
            "read_scoped_bearer_token",
            "safe_existing_customer_id",
        ],
        "required_record_fields": ["customer_id", "status"],
        "recommended_record_fields": ["email", "account_id"],
        "pass_rule": (
            "A saved connector test must fetch one customer record from the "
            "system of record and reconcile it as matched."
        ),
    },
    GENERIC_REST_CONNECTOR_TYPE: {
        "schema_version": "system_of_record_connector.v1",
        "connector_type": GENERIC_REST_CONNECTOR_TYPE,
        "adapter": "https_json_record",
        "system_of_record": "generic_rest",
        "config_endpoint": "/v1/integrations/system-of-record/generic-rest/config",
        "status_endpoint": "/v1/integrations/system-of-record/generic-rest/status",
        "test_endpoint": "/v1/integrations/system-of-record/generic-rest/test",
        "required_inputs": [
            "https_base_url",
            "path_template_with_record_ref",
            "read_scoped_bearer_token",
            "safe_existing_record_ref",
        ],
        "required_record_fields": ["record_ref"],
        "recommended_record_fields": ["status", "updated_at"],
        "pass_rule": (
            "A saved connector test must fetch one JSON record from the "
            "customer system and reconcile the configured match fields as matched."
        ),
    },
    HUBSPOT_CRM_CONNECTOR_TYPE: {
        "schema_version": "system_of_record_connector.v1",
        "connector_type": HUBSPOT_CRM_CONNECTOR_TYPE,
        "adapter": "hubspot_crm_contact_read",
        "system_of_record": "hubspot_crm",
        "config_endpoint": "/v1/integrations/system-of-record/hubspot-crm/config",
        "status_endpoint": "/v1/integrations/system-of-record/hubspot-crm/status",
        "test_endpoint": "/v1/integrations/system-of-record/hubspot-crm/test",
        "auth_mode": "private_app_bearer_token",
        "oauth_status": "planned",
        "required_inputs": [
            "hubspot_private_app_token",
            "safe_existing_contact_id_or_email",
            "properties_to_verify",
        ],
        "required_record_fields": ["hs_object_id"],
        "recommended_record_fields": ["email", "lifecyclestage", "hs_lead_status"],
        "pass_rule": (
            "A saved connector test must fetch one HubSpot contact through the "
            "CRM v3 API and reconcile the configured fields as matched."
        ),
    },
    ZENDESK_TICKET_CONNECTOR_TYPE: {
        "schema_version": "system_of_record_connector.v1",
        "connector_type": ZENDESK_TICKET_CONNECTOR_TYPE,
        "adapter": "zendesk_ticket_read",
        "system_of_record": "zendesk_support",
        "config_endpoint": "/v1/integrations/system-of-record/zendesk-ticket/config",
        "status_endpoint": "/v1/integrations/system-of-record/zendesk-ticket/status",
        "test_endpoint": "/v1/integrations/system-of-record/zendesk-ticket/test",
        "auth_mode": "oauth_bearer_or_api_token_basic",
        "oauth_status": "planned",
        "required_inputs": [
            "zendesk_subdomain_url",
            "read_scoped_token",
            "safe_existing_ticket_id",
        ],
        "required_record_fields": ["ticket_id", "status"],
        "recommended_record_fields": ["subject", "requester_id", "assignee_id"],
        "pass_rule": (
            "A saved connector test must fetch one Zendesk Support ticket and "
            "reconcile the configured fields as matched."
        ),
    },
    JIRA_ISSUE_CONNECTOR_TYPE: {
        "schema_version": "system_of_record_connector.v1",
        "connector_type": JIRA_ISSUE_CONNECTOR_TYPE,
        "adapter": "jira_issue_read",
        "system_of_record": "jira_service_management",
        "config_endpoint": "/v1/integrations/system-of-record/jira-issue/config",
        "status_endpoint": "/v1/integrations/system-of-record/jira-issue/status",
        "test_endpoint": "/v1/integrations/system-of-record/jira-issue/test",
        "auth_mode": "api_token_basic_or_bearer",
        "oauth_status": "planned",
        "required_inputs": [
            "jira_cloud_base_url",
            "read_scoped_api_token_or_bearer_token",
            "safe_existing_issue_key_or_id",
        ],
        "required_record_fields": ["jira_issue_key"],
        "recommended_record_fields": [
            "summary",
            "status",
            "assignee",
            "reporter",
            "issue_type",
            "project",
            "priority",
            "updated_at",
        ],
        "pass_rule": (
            "A saved connector test must fetch one Jira/JSM issue and "
            "reconcile the configured fields as matched."
        ),
    },
    SALESFORCE_CRM_CONNECTOR_TYPE: {
        "schema_version": "system_of_record_connector.v1",
        "connector_type": SALESFORCE_CRM_CONNECTOR_TYPE,
        "adapter": "salesforce_crm_sobject_read",
        "system_of_record": "salesforce_crm",
        "config_endpoint": "/v1/integrations/system-of-record/salesforce-crm/config",
        "status_endpoint": "/v1/integrations/system-of-record/salesforce-crm/status",
        "test_endpoint": "/v1/integrations/system-of-record/salesforce-crm/test",
        "auth_mode": "oauth_bearer_token",
        "oauth_status": "planned",
        "required_inputs": [
            "salesforce_instance_url",
            "read_scoped_access_token",
            "safe_existing_object_type_and_record_id",
            "fields_to_verify",
        ],
        "required_record_fields": ["Id"],
        "recommended_record_fields": ["Name", "Status", "StageName", "Amount"],
        "pass_rule": (
            "A saved connector test must fetch one Salesforce sObject record and "
            "reconcile the configured fields as matched."
        ),
    },
    ZOHO_CRM_CONNECTOR_TYPE: {
        "schema_version": "system_of_record_connector.v1",
        "connector_type": ZOHO_CRM_CONNECTOR_TYPE,
        "adapter": "zoho_crm_module_record_read",
        "system_of_record": "zoho_crm",
        "config_endpoint": "/v1/integrations/system-of-record/zoho-crm/config",
        "status_endpoint": "/v1/integrations/system-of-record/zoho-crm/status",
        "test_endpoint": "/v1/integrations/system-of-record/zoho-crm/test",
        "auth_mode": "oauth_bearer_token",
        "oauth_status": "available",
        "oauth_start_endpoint": "/v1/integrations/system-of-record/zoho-crm/oauth/start",
        "required_inputs": [
            "zoho_api_domain",
            "read_scoped_oauth_connection_or_access_token",
            "safe_existing_module_and_record_id",
            "fields_to_verify",
        ],
        "required_record_fields": ["id"],
        "recommended_record_fields": [
            "Full_Name",
            "Email",
            "Stage",
            "Lead_Status",
            "Owner",
            "Amount",
        ],
        "pass_rule": (
            "A saved connector test must fetch one Zoho CRM module record and "
            "reconcile the configured fields as matched."
        ),
    },
    NETSUITE_FINANCE_CONNECTOR_TYPE: {
        "schema_version": "system_of_record_connector.v1",
        "connector_type": NETSUITE_FINANCE_CONNECTOR_TYPE,
        "adapter": "netsuite_finance_record_read",
        "system_of_record": "netsuite",
        "config_endpoint": "/v1/integrations/system-of-record/netsuite-finance/config",
        "status_endpoint": "/v1/integrations/system-of-record/netsuite-finance/status",
        "test_endpoint": "/v1/integrations/system-of-record/netsuite-finance/test",
        "auth_mode": "bearer_token",
        "oauth_status": "manual_token_supported",
        "required_inputs": [
            "netsuite_account_rest_base_url",
            "record_type",
            "record_ref",
            "read_scoped_bearer_token",
        ],
        "required_record_fields": ["record_type", "record_ref"],
        "recommended_record_fields": [
            "tran_id",
            "status",
            "amount_minor",
            "amount_major",
            "currency",
            "entity_id",
        ],
        "pass_rule": (
            "A saved connector test must fetch one NetSuite finance or "
            "procurement record and reconcile the configured fields as matched."
        ),
    },
    POSTGRES_READ_CONNECTOR_TYPE: {
        "schema_version": "system_of_record_connector.v1",
        "connector_type": POSTGRES_READ_CONNECTOR_TYPE,
        "adapter": "postgresql_readonly",
        "system_of_record": "postgres_read",
        "config_endpoint": "/v1/integrations/system-of-record/postgres-read/config",
        "status_endpoint": "/v1/integrations/system-of-record/postgres-read/status",
        "test_endpoint": "/v1/integrations/system-of-record/postgres-read/test",
        "required_inputs": [
            "postgres_database_url",
            "single_read_only_select_query",
            "safe_existing_query_params",
        ],
        "required_record_fields": [],
        "recommended_record_fields": ["id", "status", "updated_at"],
        "pass_rule": (
            "A saved connector test must execute one read-only query against "
            "PostgreSQL and reconcile the configured match fields as matched."
        ),
    },
}


class InvalidSystemOfRecordConnectorError(ValueError):
    """Raised when a connector config is invalid or unsupported."""


def _json_dumps(value: Any) -> str | None:
    if value in (None, {}, []):
        return None
    return json.dumps(value, separators=(",", ":"), sort_keys=True, default=str)


def _json_loads(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        loaded = json.loads(value)
    except Exception:
        return None
    return dict(loaded) if isinstance(loaded, Mapping) else None


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    return None


def _connector_contract(connector_type: str) -> dict[str, Any]:
    connector_type = _normalize_connector_type(connector_type)
    return json.loads(json.dumps(_CONNECTOR_CONTRACTS[connector_type]))


def _connector_readiness(
    row: SystemOfRecordConnectorConfig | None,
    *,
    connector_type: str,
    health: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    connector_type = _normalize_connector_type(connector_type)
    health_payload = dict(health or {})
    last_http_status = _as_int(health_payload.get("last_http_status"))
    last_attempts = _as_int(health_payload.get("last_attempts"))
    last_error_code = health_payload.get("last_error_code")
    last_retryable = _as_bool(health_payload.get("last_retryable"))
    if connector_type == POSTGRES_READ_CONNECTOR_TYPE:
        checks = {
            "config_saved": row is not None and bool(row.is_active),
            "database_url_present": row is not None
            and bool(row.database_url_ciphertext),
            "read_query_present": row is not None and bool(row.read_query),
            "saved_test_matched": health_payload.get("last_verdict") == "matched",
            "connector_attempted": last_attempts is not None and last_attempts >= 1,
            "no_connector_error_code": last_error_code in (None, ""),
            "not_retryable_failure": last_retryable in (None, False),
        }
        blocker_messages = {
            "config_saved": "connector config has not been saved",
            "database_url_present": "encrypted PostgreSQL database URL is missing",
            "read_query_present": "read-only verification query is missing",
            "saved_test_matched": "latest connector test did not reconcile as matched",
            "connector_attempted": "connector has not attempted a system-of-record read",
            "no_connector_error_code": "latest connector test has an error code",
            "not_retryable_failure": "latest connector test ended in a retryable failure",
        }
    else:
        token_present = row is not None and bool(row.bearer_token_ciphertext)
        if connector_type == ZOHO_CRM_CONNECTOR_TYPE:
            token_present = row is not None and (
                bool(row.bearer_token_ciphertext)
                or bool(row.oauth_refresh_token_ciphertext)
            )
        checks = {
            "config_saved": row is not None and bool(row.is_active),
            "bearer_token_present": token_present,
            "saved_test_matched": health_payload.get("last_verdict") == "matched",
            "connector_attempted": last_attempts is not None and last_attempts >= 1,
            "http_2xx": last_http_status is not None
            and 200 <= last_http_status <= 299,
            "no_connector_error_code": last_error_code in (None, ""),
            "not_retryable_failure": last_retryable in (None, False),
        }
        blocker_messages = {
            "config_saved": "connector config has not been saved",
            "bearer_token_present": "read-scoped OAuth connection or bearer token is missing",
            "saved_test_matched": "latest connector test did not reconcile as matched",
            "connector_attempted": "connector has not attempted a system-of-record read",
            "http_2xx": "latest connector test did not return a 2xx HTTP response",
            "no_connector_error_code": "latest connector test has an error code",
            "not_retryable_failure": "latest connector test ended in a retryable failure",
        }
    blockers = [
        blocker_messages[key]
        for key, passed in checks.items()
        if not passed
    ]
    return {
        "status": "ready" if not blockers else "not_ready",
        "contract": _connector_contract(connector_type),
        "checks": checks,
        "blockers": blockers,
        "last_checked_at": health_payload.get("last_checked_at"),
    }


def _normalize_connector_type(connector_type: str) -> str:
    normalized = connector_type.strip().lower()
    if normalized not in VALID_CONNECTOR_TYPES:
        raise InvalidSystemOfRecordConnectorError(
            "connector_type must be one of: " + ", ".join(sorted(VALID_CONNECTOR_TYPES))
        )
    return normalized


def _normalize_query(
    query: Mapping[str, Any] | None,
) -> dict[str, str | int | float | bool] | None:
    if not query:
        return None
    normalized: dict[str, str | int | float | bool] = {}
    for raw_key, value in query.items():
        key = str(raw_key).strip()
        if not key or value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            normalized[key] = value
            continue
        raise InvalidSystemOfRecordConnectorError(
            "connector query values must be strings, numbers, or booleans"
        )
    return normalized or None


def get_connector_config(
    db: Session,
    *,
    project_id: str,
    connector_type: str = LEDGER_REFUND_CONNECTOR_TYPE,
) -> SystemOfRecordConnectorConfig | None:
    connector_type = _normalize_connector_type(connector_type)
    return db.execute(
        select(SystemOfRecordConnectorConfig).where(
            SystemOfRecordConnectorConfig.project_id == project_id,
            SystemOfRecordConnectorConfig.connector_type == connector_type,
        )
    ).scalar_one_or_none()


__all__ = [name for name in globals() if not name.startswith("__")]
