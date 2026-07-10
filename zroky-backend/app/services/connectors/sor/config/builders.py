from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.connector_credentials import resolve_connector_credential
from app.services.connectors.sor.config.core import *  # noqa: F403


def decrypt_connector_bearer_token(
    row: SystemOfRecordConnectorConfig,
    *,
    project_id: str,
    db: Session | None = None,
) -> str | None:
    if row.bearer_credential_id:
        if db is None:
            raise RuntimeError("database session is required for a bound connector credential")
        return resolve_connector_credential(
            db, row=row, project_id=project_id, purpose="bearer_token"
        )
    if not row.bearer_token_ciphertext:
        return None
    return decrypt_provider_key(
        ciphertext=row.bearer_token_ciphertext,
        project_id=project_id,
    )


def decrypt_connector_oauth_refresh_token(
    row: SystemOfRecordConnectorConfig,
    *,
    project_id: str,
    db: Session | None = None,
) -> str | None:
    if row.oauth_refresh_credential_id:
        if db is None:
            raise RuntimeError("database session is required for a bound connector credential")
        return resolve_connector_credential(
            db, row=row, project_id=project_id, purpose="oauth_refresh_token"
        )
    if not row.oauth_refresh_token_ciphertext:
        return None
    return decrypt_provider_key(
        ciphertext=row.oauth_refresh_token_ciphertext,
        project_id=project_id,
    )


def decrypt_connector_database_url(
    row: SystemOfRecordConnectorConfig,
    *,
    project_id: str,
    db: Session | None = None,
) -> str | None:
    if row.database_url_credential_id:
        if db is None:
            raise RuntimeError("database session is required for a bound connector credential")
        return resolve_connector_credential(
            db, row=row, project_id=project_id, purpose="database_url"
        )
    if not row.database_url_ciphertext:
        return None
    return decrypt_provider_key(
        ciphertext=row.database_url_ciphertext,
        project_id=project_id,
    )


def build_inline_ledger_refund_connector(
    *,
    base_url: str,
    refund_id: str,
    bearer_token: str | None,
    path_template: str,
    query: Mapping[str, Any] | None,
    record_path: str | None,
    timeout_seconds: float,
    max_attempts: int,
    allow_private_hosts: bool,
) -> LedgerRefundApiConnector:
    return LedgerRefundApiConnector(
        base_url=base_url,
        refund_id=refund_id,
        bearer_token=bearer_token,
        path_template=path_template,
        query=query,
        record_path=record_path,
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        allow_private_hosts=allow_private_hosts,
    )


def build_inline_customer_record_connector(
    *,
    base_url: str,
    customer_id: str,
    bearer_token: str | None,
    path_template: str,
    query: Mapping[str, Any] | None,
    record_path: str | None,
    timeout_seconds: float,
    max_attempts: int,
    allow_private_hosts: bool,
) -> CustomerRecordApiConnector:
    return CustomerRecordApiConnector(
        base_url=base_url,
        customer_id=customer_id,
        bearer_token=bearer_token,
        path_template=path_template,
        query=query,
        record_path=record_path,
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        allow_private_hosts=allow_private_hosts,
    )


def build_inline_postgres_read_connector(
    *,
    database_url: str,
    query: str,
    params: Mapping[str, Any] | None,
    timeout_seconds: float,
    allow_private_hosts: bool,
) -> PostgresReadOnlyConnector:
    return PostgresReadOnlyConnector(
        database_url=database_url,
        query=query,
        params=params,
        timeout_seconds=timeout_seconds,
        allow_private_hosts=allow_private_hosts,
    )


def build_ledger_refund_connector(
    row: SystemOfRecordConnectorConfig,
    *,
    refund_id: str,
    bearer_token: str | None,
    timeout_seconds: float,
    max_attempts: int,
    allow_private_hosts: bool,
) -> LedgerRefundApiConnector:
    return LedgerRefundApiConnector(
        base_url=row.base_url,
        refund_id=refund_id,
        bearer_token=bearer_token,
        path_template=row.path_template or "/refunds/{refund_id}",
        query=_json_loads(row.query_json),
        record_path=row.record_path,
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        allow_private_hosts=allow_private_hosts,
        fail_closed_config_errors=True,
    )


def build_stripe_refund_connector(
    row: SystemOfRecordConnectorConfig,
    *,
    refund_id: str,
    bearer_token: str | None,
    timeout_seconds: float,
    max_attempts: int,
) -> StripeRefundConnector:
    return StripeRefundConnector(
        refund_id=refund_id,
        bearer_token=bearer_token,
        base_url=row.base_url or "https://api.stripe.com",
        path_template=row.path_template or "/v1/refunds/{refund_id}",
        query=_json_loads(row.query_json),
        record_path=row.record_path,
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        fail_closed_config_errors=True,
    )


def build_razorpay_refund_connector(
    row: SystemOfRecordConnectorConfig,
    *,
    refund_id: str,
    key_secret: str | None,
    timeout_seconds: float,
    max_attempts: int,
) -> RazorpayRefundConnector:
    query = _json_loads(row.query_json)
    key_id = str(query.pop("key_id", "") or "").strip() or None
    return RazorpayRefundConnector(
        refund_id=refund_id,
        key_id=key_id,
        key_secret=key_secret,
        base_url=row.base_url or "https://api.razorpay.com",
        path_template=row.path_template or "/v1/refunds/{refund_id}",
        query=query,
        record_path=row.record_path,
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        fail_closed_config_errors=True,
    )


def build_customer_record_connector(
    row: SystemOfRecordConnectorConfig,
    *,
    customer_id: str,
    bearer_token: str | None,
    timeout_seconds: float,
    max_attempts: int,
    allow_private_hosts: bool,
) -> CustomerRecordApiConnector:
    return CustomerRecordApiConnector(
        base_url=row.base_url,
        customer_id=customer_id,
        bearer_token=bearer_token,
        path_template=row.path_template or "/customers/{customer_id}",
        query=_json_loads(row.query_json),
        record_path=row.record_path,
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        allow_private_hosts=allow_private_hosts,
        fail_closed_config_errors=True,
    )


def build_generic_rest_connector(
    row: SystemOfRecordConnectorConfig,
    *,
    record_ref: str,
    bearer_token: str | None,
    timeout_seconds: float,
    max_attempts: int,
    allow_private_hosts: bool,
) -> GenericRestApiConnector:
    return GenericRestApiConnector(
        base_url=row.base_url,
        record_ref=record_ref,
        bearer_token=bearer_token,
        path_template=row.path_template or "/records/{record_ref}",
        query=_json_loads(row.query_json),
        record_path=row.record_path,
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        allow_private_hosts=allow_private_hosts,
        fail_closed_config_errors=True,
    )


def build_hubspot_crm_connector(
    row: SystemOfRecordConnectorConfig,
    *,
    record_ref: str,
    bearer_token: str | None,
    timeout_seconds: float,
    max_attempts: int,
) -> HubSpotCrmConnector:
    return HubSpotCrmConnector(
        record_ref=record_ref,
        bearer_token=bearer_token,
        base_url=row.base_url or "https://api.hubapi.com",
        path_template=row.path_template or "/crm/v3/objects/contacts/{record_ref}",
        query=_json_loads(row.query_json),
        record_path=row.record_path,
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        fail_closed_config_errors=True,
    )


def build_zendesk_ticket_connector(
    row: SystemOfRecordConnectorConfig,
    *,
    record_ref: str,
    bearer_token: str | None,
    timeout_seconds: float,
    max_attempts: int,
) -> ZendeskTicketConnector:
    query = _json_loads(row.query_json)
    auth_username = str(query.pop("auth_username", "") or "").strip() or None
    return ZendeskTicketConnector(
        record_ref=record_ref,
        bearer_token=bearer_token if not auth_username else None,
        basic_auth_username=f"{auth_username}/token" if auth_username else None,
        basic_auth_password=bearer_token if auth_username else None,
        base_url=row.base_url or "https://example.zendesk.com",
        path_template=row.path_template or "/api/v2/tickets/{record_ref}.json",
        query=query,
        record_path=row.record_path or "ticket",
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        fail_closed_config_errors=True,
    )


def build_jira_issue_connector(
    row: SystemOfRecordConnectorConfig,
    *,
    record_ref: str,
    bearer_token: str | None,
    timeout_seconds: float,
    max_attempts: int,
) -> JiraIssueConnector:
    query = _json_loads(row.query_json)
    auth_username = str(query.pop("auth_username", "") or "").strip() or None
    return JiraIssueConnector(
        record_ref=record_ref,
        bearer_token=bearer_token if not auth_username else None,
        basic_auth_username=auth_username,
        basic_auth_password=bearer_token if auth_username else None,
        base_url=row.base_url or "https://example.atlassian.net",
        path_template=row.path_template or "/rest/api/3/issue/{record_ref}",
        query=query,
        record_path=row.record_path,
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        fail_closed_config_errors=True,
    )


def build_salesforce_crm_connector(
    row: SystemOfRecordConnectorConfig,
    *,
    object_type: str,
    record_ref: str,
    bearer_token: str | None,
    timeout_seconds: float,
    max_attempts: int,
) -> SalesforceCrmConnector:
    return SalesforceCrmConnector(
        object_type=object_type,
        record_ref=record_ref,
        bearer_token=bearer_token,
        base_url=row.base_url or "https://example.my.salesforce.com",
        path_template=row.path_template or "/services/data/v60.0/sobjects/{object_type}/{record_ref}",
        query=_json_loads(row.query_json),
        record_path=row.record_path,
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        fail_closed_config_errors=True,
    )


def build_zoho_crm_connector(
    row: SystemOfRecordConnectorConfig,
    *,
    module_name: str,
    record_ref: str,
    bearer_token: str | None,
    timeout_seconds: float,
    max_attempts: int,
) -> ZohoCrmConnector:
    return ZohoCrmConnector(
        module_name=module_name,
        record_ref=record_ref,
        bearer_token=bearer_token,
        base_url=row.base_url or "https://www.zohoapis.com",
        path_template=row.path_template or "/crm/v8/{module_name}/{record_ref}",
        query=_json_loads(row.query_json),
        record_path=row.record_path or "data.0",
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        fail_closed_config_errors=True,
    )


def build_netsuite_finance_connector(
    row: SystemOfRecordConnectorConfig,
    *,
    record_type: str,
    record_ref: str,
    bearer_token: str | None,
    timeout_seconds: float,
    max_attempts: int,
) -> NetSuiteFinanceConnector:
    return NetSuiteFinanceConnector(
        record_type=record_type,
        record_ref=record_ref,
        bearer_token=bearer_token,
        base_url=row.base_url or "https://example.suitetalk.api.netsuite.com",
        path_template=row.path_template
        or "/services/rest/record/v1/{record_type}/{record_ref}",
        query=_json_loads(row.query_json),
        record_path=row.record_path,
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        fail_closed_config_errors=True,
    )


def build_postgres_read_connector(
    row: SystemOfRecordConnectorConfig,
    *,
    database_url: str,
    params: Mapping[str, Any] | None,
    timeout_seconds: float,
    allow_private_hosts: bool,
) -> PostgresReadOnlyConnector:
    return PostgresReadOnlyConnector(
        database_url=database_url,
        query=row.read_query or "",
        params=params,
        timeout_seconds=timeout_seconds,
        allow_private_hosts=allow_private_hosts,
        fail_closed_config_errors=True,
    )
