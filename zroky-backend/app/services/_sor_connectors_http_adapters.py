from __future__ import annotations

from app.services._sor_connectors_core import *  # noqa: F403
from app.services._sor_connectors_http_base import *  # noqa: F403


@dataclass(frozen=True)
class LedgerRefundApiConnector:
    """Read one refund from a ledger/refund API."""

    base_url: str
    refund_id: str
    bearer_token: str | None = None
    path_template: str = "/refunds/{refund_id}"
    query: Mapping[str, Any] | None = None
    record_path: str | None = None
    timeout_seconds: float = 5.0
    max_attempts: int = 2
    allow_private_hosts: bool = False
    fail_closed_config_errors: bool = False
    transport: httpx.BaseTransport | None = field(default=None, repr=False)
    connector_type: str = "ledger_refund_api"

    def fetch(self) -> SourceRecord:
        connector = HttpJsonRecordConnector(
            base_url=self.base_url,
            path_template=self.path_template,
            path_values={"refund_id": self.refund_id},
            query=self.query,
            bearer_token=self.bearer_token,
            record_path=self.record_path,
            timeout_seconds=self.timeout_seconds,
            max_attempts=self.max_attempts,
            allow_private_hosts=self.allow_private_hosts,
            fail_closed_config_errors=self.fail_closed_config_errors,
            transport=self.transport,
            connector_type=self.connector_type,
        )
        source = connector.fetch()
        record = (
            _normalise_refund_record(source.record, refund_id=self.refund_id)
            if source.record is not None
            else None
        )
        return SourceRecord(
            record=record,
            record_found=source.record_found,
            metadata={**(source.metadata or {}), "refund_id": self.refund_id},
        )


@dataclass(frozen=True)
class StripeRefundConnector:
    """Read one Stripe refund for source-of-record verification."""

    refund_id: str
    bearer_token: str | None = None
    base_url: str = "https://api.stripe.com"
    path_template: str = "/v1/refunds/{refund_id}"
    query: Mapping[str, Any] | None = None
    record_path: str | None = None
    timeout_seconds: float = 5.0
    max_attempts: int = 2
    fail_closed_config_errors: bool = False
    transport: httpx.BaseTransport | None = field(default=None, repr=False)
    connector_type: str = "stripe_refund"

    def fetch(self) -> SourceRecord:
        connector = HttpJsonRecordConnector(
            base_url=self.base_url,
            path_template=self.path_template,
            path_values={"refund_id": self.refund_id},
            query=self.query,
            bearer_token=self.bearer_token,
            record_path=self.record_path,
            timeout_seconds=self.timeout_seconds,
            max_attempts=self.max_attempts,
            allow_private_hosts=False,
            fail_closed_config_errors=self.fail_closed_config_errors,
            transport=self.transport,
            connector_type=self.connector_type,
        )
        source = connector.fetch()
        record = (
            _normalise_stripe_refund_record(source.record, refund_id=self.refund_id)
            if source.record is not None
            else None
        )
        return SourceRecord(
            record=record,
            record_found=source.record_found,
            metadata={
                **(source.metadata or {}),
                "refund_id": self.refund_id,
                "stripe_object": "refund",
            },
        )


@dataclass(frozen=True)
class RazorpayRefundConnector:
    """Read one Razorpay refund for source-of-record verification."""

    refund_id: str
    key_id: str | None = None
    key_secret: str | None = None
    base_url: str = "https://api.razorpay.com"
    path_template: str = "/v1/refunds/{refund_id}"
    query: Mapping[str, Any] | None = None
    record_path: str | None = None
    timeout_seconds: float = 5.0
    max_attempts: int = 2
    fail_closed_config_errors: bool = False
    transport: httpx.BaseTransport | None = field(default=None, repr=False)
    connector_type: str = "razorpay_refund"

    def fetch(self) -> SourceRecord:
        connector = HttpJsonRecordConnector(
            base_url=self.base_url,
            path_template=self.path_template,
            path_values={"refund_id": self.refund_id},
            query=self.query,
            basic_auth_username=self.key_id,
            basic_auth_password=self.key_secret,
            record_path=self.record_path,
            timeout_seconds=self.timeout_seconds,
            max_attempts=self.max_attempts,
            allow_private_hosts=False,
            fail_closed_config_errors=self.fail_closed_config_errors,
            transport=self.transport,
            connector_type=self.connector_type,
        )
        source = connector.fetch()
        record = (
            _normalise_razorpay_refund_record(source.record, refund_id=self.refund_id)
            if source.record is not None
            else None
        )
        return SourceRecord(
            record=record,
            record_found=source.record_found,
            metadata={
                **(source.metadata or {}),
                "refund_id": self.refund_id,
                "razorpay_object": "refund",
            },
        )


@dataclass(frozen=True)
class CustomerRecordApiConnector:
    """Read one customer/contact/account record from a CRM API."""

    base_url: str
    customer_id: str
    bearer_token: str | None = None
    path_template: str = "/customers/{customer_id}"
    query: Mapping[str, Any] | None = None
    record_path: str | None = None
    timeout_seconds: float = 5.0
    max_attempts: int = 2
    allow_private_hosts: bool = False
    fail_closed_config_errors: bool = False
    transport: httpx.BaseTransport | None = field(default=None, repr=False)
    connector_type: str = "customer_record_api"

    def fetch(self) -> SourceRecord:
        connector = HttpJsonRecordConnector(
            base_url=self.base_url,
            path_template=self.path_template,
            path_values={"customer_id": self.customer_id},
            query=self.query,
            bearer_token=self.bearer_token,
            record_path=self.record_path,
            timeout_seconds=self.timeout_seconds,
            max_attempts=self.max_attempts,
            allow_private_hosts=self.allow_private_hosts,
            fail_closed_config_errors=self.fail_closed_config_errors,
            transport=self.transport,
            connector_type=self.connector_type,
        )
        source = connector.fetch()
        record = (
            _normalise_customer_record(source.record, customer_id=self.customer_id)
            if source.record is not None
            else None
        )
        return SourceRecord(
            record=record,
            record_found=source.record_found,
            metadata={**(source.metadata or {}), "customer_id": self.customer_id},
        )


@dataclass(frozen=True)
class HubSpotCrmConnector:
    """Read one HubSpot CRM contact for source-of-record verification."""

    record_ref: str
    bearer_token: str | None = None
    base_url: str = "https://api.hubapi.com"
    path_template: str = "/crm/v3/objects/contacts/{record_ref}"
    query: Mapping[str, Any] | None = None
    record_path: str | None = None
    timeout_seconds: float = 5.0
    max_attempts: int = 2
    fail_closed_config_errors: bool = False
    transport: httpx.BaseTransport | None = field(default=None, repr=False)
    connector_type: str = "hubspot_crm"

    def fetch(self) -> SourceRecord:
        connector = HttpJsonRecordConnector(
            base_url=self.base_url,
            path_template=self.path_template,
            path_values={"record_ref": self.record_ref},
            query=self.query,
            bearer_token=self.bearer_token,
            record_path=self.record_path,
            timeout_seconds=self.timeout_seconds,
            max_attempts=self.max_attempts,
            allow_private_hosts=False,
            fail_closed_config_errors=self.fail_closed_config_errors,
            transport=self.transport,
            connector_type=self.connector_type,
        )
        source = connector.fetch()
        record = (
            _normalise_hubspot_contact_record(source.record, record_ref=self.record_ref)
            if source.record is not None
            else None
        )
        metadata = {
            **(source.metadata or {}),
            "record_ref": self.record_ref,
            "hubspot_object": "contacts",
        }
        id_property = (self.query or {}).get("idProperty")
        if id_property:
            metadata["id_property"] = id_property
        return SourceRecord(
            record=record,
            record_found=source.record_found,
            metadata=metadata,
        )


@dataclass(frozen=True)
class ZendeskTicketConnector:
    """Read one Zendesk Support ticket for source-of-record verification."""

    record_ref: str
    bearer_token: str | None = None
    basic_auth_username: str | None = None
    basic_auth_password: str | None = None
    base_url: str = "https://example.zendesk.com"
    path_template: str = "/api/v2/tickets/{record_ref}.json"
    query: Mapping[str, Any] | None = None
    record_path: str | None = "ticket"
    timeout_seconds: float = 5.0
    max_attempts: int = 2
    fail_closed_config_errors: bool = False
    transport: httpx.BaseTransport | None = field(default=None, repr=False)
    connector_type: str = "zendesk_ticket"

    def fetch(self) -> SourceRecord:
        connector = HttpJsonRecordConnector(
            base_url=self.base_url,
            path_template=self.path_template,
            path_values={"record_ref": self.record_ref},
            query=self.query,
            bearer_token=self.bearer_token,
            basic_auth_username=self.basic_auth_username,
            basic_auth_password=self.basic_auth_password,
            record_path=self.record_path,
            timeout_seconds=self.timeout_seconds,
            max_attempts=self.max_attempts,
            allow_private_hosts=False,
            fail_closed_config_errors=self.fail_closed_config_errors,
            transport=self.transport,
            connector_type=self.connector_type,
        )
        source = connector.fetch()
        record = (
            _normalise_zendesk_ticket_record(source.record, record_ref=self.record_ref)
            if source.record is not None
            else None
        )
        metadata = {
            **(source.metadata or {}),
            "record_ref": self.record_ref,
            "zendesk_object": "ticket",
        }
        return SourceRecord(
            record=record,
            record_found=source.record_found,
            metadata=metadata,
        )


@dataclass(frozen=True)
class JiraIssueConnector:
    """Read one Jira/Jira Service Management issue for source-of-record verification."""

    record_ref: str
    bearer_token: str | None = None
    basic_auth_username: str | None = None
    basic_auth_password: str | None = None
    base_url: str = "https://example.atlassian.net"
    path_template: str = "/rest/api/3/issue/{record_ref}"
    query: Mapping[str, Any] | None = None
    record_path: str | None = None
    timeout_seconds: float = 5.0
    max_attempts: int = 2
    fail_closed_config_errors: bool = False
    transport: httpx.BaseTransport | None = field(default=None, repr=False)
    connector_type: str = "jira_issue"

    def fetch(self) -> SourceRecord:
        connector = HttpJsonRecordConnector(
            base_url=self.base_url,
            path_template=self.path_template,
            path_values={"record_ref": self.record_ref},
            query=self.query,
            bearer_token=self.bearer_token,
            basic_auth_username=self.basic_auth_username,
            basic_auth_password=self.basic_auth_password,
            record_path=self.record_path,
            timeout_seconds=self.timeout_seconds,
            max_attempts=self.max_attempts,
            allow_private_hosts=False,
            fail_closed_config_errors=self.fail_closed_config_errors,
            transport=self.transport,
            connector_type=self.connector_type,
        )
        source = connector.fetch()
        record = (
            _normalise_jira_issue_record(source.record, record_ref=self.record_ref)
            if source.record is not None
            else None
        )
        metadata = {
            **(source.metadata or {}),
            "record_ref": self.record_ref,
            "jira_object": "issue",
        }
        return SourceRecord(
            record=record,
            record_found=source.record_found,
            metadata=metadata,
        )


@dataclass(frozen=True)
class SalesforceCrmConnector:
    """Read one Salesforce sObject row for source-of-record verification."""

    object_type: str
    record_ref: str
    bearer_token: str | None = None
    base_url: str = "https://example.my.salesforce.com"
    path_template: str = "/services/data/v60.0/sobjects/{object_type}/{record_ref}"
    query: Mapping[str, Any] | None = None
    record_path: str | None = None
    timeout_seconds: float = 5.0
    max_attempts: int = 2
    fail_closed_config_errors: bool = False
    transport: httpx.BaseTransport | None = field(default=None, repr=False)
    connector_type: str = "salesforce_crm"

    def fetch(self) -> SourceRecord:
        connector = HttpJsonRecordConnector(
            base_url=self.base_url,
            path_template=self.path_template,
            path_values={"object_type": self.object_type, "record_ref": self.record_ref},
            query=self.query,
            bearer_token=self.bearer_token,
            record_path=self.record_path,
            timeout_seconds=self.timeout_seconds,
            max_attempts=self.max_attempts,
            allow_private_hosts=False,
            fail_closed_config_errors=self.fail_closed_config_errors,
            transport=self.transport,
            connector_type=self.connector_type,
        )
        source = connector.fetch()
        record = (
            _normalise_salesforce_record(
                source.record,
                object_type=self.object_type,
                record_ref=self.record_ref,
            )
            if source.record is not None
            else None
        )
        metadata = {
            **(source.metadata or {}),
            "record_ref": self.record_ref,
            "salesforce_object": self.object_type,
        }
        return SourceRecord(
            record=record,
            record_found=source.record_found,
            metadata=metadata,
        )


@dataclass(frozen=True)
class ZohoCrmConnector:
    """Read one Zoho CRM module record for source-of-record verification."""

    module_name: str
    record_ref: str
    bearer_token: str | None = None
    base_url: str = "https://www.zohoapis.com"
    path_template: str = "/crm/v8/{module_name}/{record_ref}"
    query: Mapping[str, Any] | None = None
    record_path: str | None = "data.0"
    timeout_seconds: float = 5.0
    max_attempts: int = 2
    fail_closed_config_errors: bool = False
    transport: httpx.BaseTransport | None = field(default=None, repr=False)
    connector_type: str = "zoho_crm"

    def fetch(self) -> SourceRecord:
        connector = HttpJsonRecordConnector(
            base_url=self.base_url,
            path_template=self.path_template,
            path_values={"module_name": self.module_name, "record_ref": self.record_ref},
            query=self.query,
            bearer_token=self.bearer_token,
            record_path=self.record_path,
            timeout_seconds=self.timeout_seconds,
            max_attempts=self.max_attempts,
            allow_private_hosts=False,
            fail_closed_config_errors=self.fail_closed_config_errors,
            transport=self.transport,
            connector_type=self.connector_type,
        )
        source = connector.fetch()
        record = (
            _normalise_zoho_record(
                source.record,
                module_name=self.module_name,
                record_ref=self.record_ref,
            )
            if source.record is not None
            else None
        )
        metadata = {
            **(source.metadata or {}),
            "record_ref": self.record_ref,
            "zoho_module": self.module_name,
        }
        return SourceRecord(
            record=record,
            record_found=source.record_found,
            metadata=metadata,
        )


@dataclass(frozen=True)
class NetSuiteFinanceConnector:
    """Read one NetSuite finance/procurement record for source-of-record verification."""

    record_type: str
    record_ref: str
    bearer_token: str | None = None
    base_url: str = "https://example.suitetalk.api.netsuite.com"
    path_template: str = "/services/rest/record/v1/{record_type}/{record_ref}"
    query: Mapping[str, Any] | None = None
    record_path: str | None = None
    timeout_seconds: float = 5.0
    max_attempts: int = 2
    fail_closed_config_errors: bool = False
    transport: httpx.BaseTransport | None = field(default=None, repr=False)
    connector_type: str = "netsuite_finance"

    def fetch(self) -> SourceRecord:
        connector = HttpJsonRecordConnector(
            base_url=self.base_url,
            path_template=self.path_template,
            path_values={"record_type": self.record_type, "record_ref": self.record_ref},
            query=self.query,
            bearer_token=self.bearer_token,
            record_path=self.record_path,
            timeout_seconds=self.timeout_seconds,
            max_attempts=self.max_attempts,
            allow_private_hosts=False,
            fail_closed_config_errors=self.fail_closed_config_errors,
            transport=self.transport,
            connector_type=self.connector_type,
        )
        source = connector.fetch()
        record = (
            _normalise_netsuite_finance_record(
                source.record,
                record_type=self.record_type,
                record_ref=self.record_ref,
            )
            if source.record is not None
            else None
        )
        metadata = {
            **(source.metadata or {}),
            "record_ref": self.record_ref,
            "netsuite_record_type": self.record_type,
        }
        return SourceRecord(
            record=record,
            record_found=source.record_found,
            metadata=metadata,
        )


@dataclass(frozen=True)
class GenericRestApiConnector:
    """Read one arbitrary JSON record from a customer system for proof."""

    base_url: str
    record_ref: str
    bearer_token: str | None = None
    path_template: str = "/records/{record_ref}"
    query: Mapping[str, Any] | None = None
    record_path: str | None = None
    timeout_seconds: float = 5.0
    max_attempts: int = 2
    allow_private_hosts: bool = False
    fail_closed_config_errors: bool = False
    transport: httpx.BaseTransport | None = field(default=None, repr=False)
    connector_type: str = "generic_rest_api"

    def fetch(self) -> SourceRecord:
        connector = HttpJsonRecordConnector(
            base_url=self.base_url,
            path_template=self.path_template,
            path_values={"record_ref": self.record_ref},
            query=self.query,
            bearer_token=self.bearer_token,
            record_path=self.record_path,
            timeout_seconds=self.timeout_seconds,
            max_attempts=self.max_attempts,
            allow_private_hosts=self.allow_private_hosts,
            fail_closed_config_errors=self.fail_closed_config_errors,
            transport=self.transport,
            connector_type=self.connector_type,
        )
        source = connector.fetch()
        record = dict(source.record) if source.record is not None else None
        if record is not None and "record_ref" not in record:
            record["record_ref"] = self.record_ref
        return SourceRecord(
            record=record,
            record_found=source.record_found,
            metadata={**(source.metadata or {}), "record_ref": self.record_ref},
        )

