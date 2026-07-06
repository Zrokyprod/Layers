"""Outcome API request and response schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

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
)

# ── Schemas ───────────────────────────────────────────────────────────────────


class OutcomeIngest(BaseModel):
    call_id: str | None = Field(
        None, description="Zroky call_id to attribute this outcome to."
    )
    outcome_type: str = Field(
        ...,
        description=(
            "Business event type: refund_issued | ticket_escalated | "
            "human_handoff | churn | compliance_fine | retry_cost | custom"
        ),
    )
    amount_usd: float = Field(
        ..., ge=0, description="Monetary cost of this outcome in USD."
    )
    occurred_at: datetime | None = Field(
        None, description="When the event happened (defaults to now)."
    )
    external_ref: str | None = Field(
        None, description="Your own reference ID (order_id, ticket_id, …)."
    )
    idempotency_key: str | None = Field(
        None,
        description="Dedup key — same key + project always returns the same row.",
    )
    metadata: dict[str, Any] | None = Field(
        None, description="Arbitrary key-value context."
    )

    @field_validator("outcome_type")
    @classmethod
    def _normalise_type(cls, v: str) -> str:
        return v.strip().lower()


class OutcomeView(BaseModel):
    id: str
    project_id: str
    call_id: str | None
    outcome_type: str
    amount_usd: float
    source: str
    occurred_at: datetime
    external_ref: str | None
    created_at: datetime


class OutcomeTypeView(BaseModel):
    outcome_type: str
    total_usd: float
    count: int
    avg_usd: float


class ClusterView(BaseModel):
    agent_name: str | None
    detector: str | None
    outcome_cost_usd: float
    outcome_count: int
    failure_count: int
    estimated_monthly_savings_usd: float
    top_outcome_type: str | None


class SummaryResponse(BaseModel):
    window_days: int
    total_outcome_usd: float
    linked_outcome_count: int
    unlinked_outcome_count: int
    avg_cost_per_linked: float
    by_type: list[OutcomeTypeView]
    by_cluster: list[ClusterView]


class ReplaySavingsResponse(BaseModel):
    run_id: str
    prevented_outcome_cost_usd: float
    message: str


class OutcomeReconciliationIngest(BaseModel):
    call_id: str | None = Field(None, max_length=64)
    trace_id: str | None = Field(None, max_length=128)
    runtime_policy_decision_id: str | None = Field(None, max_length=36)
    action_type: str | None = Field(None, max_length=64)
    connector_type: str = Field(default="api_record", max_length=64)
    system_ref: str | None = Field(None, max_length=255)
    claimed: dict[str, Any] = Field(default_factory=dict)
    actual: dict[str, Any] | None = None
    actual_record_found: bool | None = None
    match_fields: list[str] | None = None
    amount_usd: float | None = Field(None, ge=0)
    currency: str | None = Field(None, min_length=3, max_length=3)
    idempotency_key: str | None = Field(None, max_length=255)
    metadata: dict[str, Any] | None = None

    @field_validator("connector_type")
    @classmethod
    def _normalise_connector_type(cls, value: str) -> str:
        return value.strip().lower() or "api_record"

    @field_validator("currency")
    @classmethod
    def _normalise_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class LedgerRefundConnectorIngest(BaseModel):
    base_url: str = Field(..., max_length=2048)
    path_template: str = Field(default="/refunds/{refund_id}", max_length=512)
    bearer_token: str | None = Field(default=None, min_length=8, max_length=4096)
    record_path: str | None = Field(default=None, max_length=255)
    query: dict[str, str | int | float | bool] | None = None
    timeout_seconds: float | None = Field(default=None, ge=0.1, le=30)
    max_attempts: int | None = Field(default=None, ge=1, le=4)


class LedgerRefundReconciliationIngest(BaseModel):
    call_id: str | None = Field(None, max_length=64)
    trace_id: str | None = Field(None, max_length=128)
    runtime_policy_decision_id: str | None = Field(None, max_length=36)
    action_type: str | None = Field(default="refund", max_length=64)
    refund_id: str | None = Field(None, max_length=255)
    system_ref: str | None = Field(None, max_length=255)
    claimed: dict[str, Any] = Field(default_factory=dict)
    match_fields: list[str] | None = None
    amount_usd: float | None = Field(None, ge=0)
    currency: str | None = Field(None, min_length=3, max_length=3)
    idempotency_key: str | None = Field(None, max_length=255)
    metadata: dict[str, Any] | None = None
    connector: LedgerRefundConnectorIngest

    @field_validator("currency")
    @classmethod
    def _normalise_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class SavedLedgerRefundReconciliationIngest(BaseModel):
    call_id: str | None = Field(None, max_length=64)
    trace_id: str | None = Field(None, max_length=128)
    runtime_policy_decision_id: str | None = Field(None, max_length=36)
    action_type: str | None = Field(default="refund", max_length=64)
    refund_id: str | None = Field(None, max_length=255)
    system_ref: str | None = Field(None, max_length=255)
    claimed: dict[str, Any] = Field(default_factory=dict)
    match_fields: list[str] | None = None
    amount_usd: float | None = Field(None, ge=0)
    currency: str | None = Field(None, min_length=3, max_length=3)
    idempotency_key: str | None = Field(None, max_length=255)
    metadata: dict[str, Any] | None = None

    @field_validator("currency")
    @classmethod
    def _normalise_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class CustomerRecordConnectorIngest(BaseModel):
    base_url: str = Field(..., max_length=2048)
    path_template: str = Field(default="/customers/{customer_id}", max_length=512)
    bearer_token: str | None = Field(default=None, min_length=8, max_length=4096)
    record_path: str | None = Field(default=None, max_length=255)
    query: dict[str, str | int | float | bool] | None = None
    timeout_seconds: float | None = Field(default=None, ge=0.1, le=30)
    max_attempts: int | None = Field(default=None, ge=1, le=4)


class CustomerRecordReconciliationIngest(BaseModel):
    call_id: str | None = Field(None, max_length=64)
    trace_id: str | None = Field(None, max_length=128)
    runtime_policy_decision_id: str | None = Field(None, max_length=36)
    action_type: str | None = Field(default="customer_record_update", max_length=64)
    customer_id: str | None = Field(None, max_length=255)
    system_ref: str | None = Field(None, max_length=255)
    claimed: dict[str, Any] = Field(default_factory=dict)
    match_fields: list[str] | None = None
    amount_usd: float | None = Field(None, ge=0)
    currency: str | None = Field(None, min_length=3, max_length=3)
    idempotency_key: str | None = Field(None, max_length=255)
    metadata: dict[str, Any] | None = None
    connector: CustomerRecordConnectorIngest

    @field_validator("currency")
    @classmethod
    def _normalise_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class SavedCustomerRecordReconciliationIngest(BaseModel):
    call_id: str | None = Field(None, max_length=64)
    trace_id: str | None = Field(None, max_length=128)
    runtime_policy_decision_id: str | None = Field(None, max_length=36)
    action_type: str | None = Field(default="customer_record_update", max_length=64)
    customer_id: str | None = Field(None, max_length=255)
    system_ref: str | None = Field(None, max_length=255)
    claimed: dict[str, Any] = Field(default_factory=dict)
    match_fields: list[str] | None = None
    amount_usd: float | None = Field(None, ge=0)
    currency: str | None = Field(None, min_length=3, max_length=3)
    idempotency_key: str | None = Field(None, max_length=255)
    metadata: dict[str, Any] | None = None

    @field_validator("currency")
    @classmethod
    def _normalise_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class SavedGenericRestReconciliationIngest(BaseModel):
    call_id: str | None = Field(None, max_length=64)
    trace_id: str | None = Field(None, max_length=128)
    runtime_policy_decision_id: str | None = Field(None, max_length=36)
    action_type: str | None = Field(default="custom", max_length=64)
    record_ref: str = Field(..., min_length=1, max_length=255)
    system_ref: str | None = Field(None, max_length=255)
    claimed: dict[str, Any] = Field(default_factory=dict)
    match_fields: list[str] | None = None
    amount_usd: float | None = Field(None, ge=0)
    currency: str | None = Field(None, min_length=3, max_length=3)
    idempotency_key: str | None = Field(None, max_length=255)
    metadata: dict[str, Any] | None = None

    @field_validator("currency")
    @classmethod
    def _normalise_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value

    @field_validator("record_ref")
    @classmethod
    def _normalise_record_ref(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("record_ref is required.")
        return cleaned


class PostgresReadConnectorIngest(BaseModel):
    database_url: str = Field(..., min_length=1, max_length=4096)
    query: str = Field(..., min_length=1, max_length=8000)
    params: dict[str, str | int | float | bool | None] | None = None
    timeout_seconds: float | None = Field(default=None, ge=0.1, le=30)

    @field_validator("database_url", "query")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value is required.")
        return cleaned


class PostgresReadReconciliationIngest(BaseModel):
    call_id: str | None = Field(None, max_length=64)
    trace_id: str | None = Field(None, max_length=128)
    runtime_policy_decision_id: str | None = Field(None, max_length=36)
    action_type: str | None = Field(default="internal_record_verification", max_length=64)
    system_ref: str | None = Field(None, max_length=255)
    claimed: dict[str, Any] = Field(default_factory=dict)
    match_fields: list[str] | None = None
    amount_usd: float | None = Field(None, ge=0)
    currency: str | None = Field(None, min_length=3, max_length=3)
    idempotency_key: str | None = Field(None, max_length=255)
    metadata: dict[str, Any] | None = None
    connector: PostgresReadConnectorIngest

    @field_validator("currency")
    @classmethod
    def _normalise_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class SavedPostgresReadReconciliationIngest(BaseModel):
    call_id: str | None = Field(None, max_length=64)
    trace_id: str | None = Field(None, max_length=128)
    runtime_policy_decision_id: str | None = Field(None, max_length=36)
    action_type: str | None = Field(default="internal_record_verification", max_length=64)
    system_ref: str | None = Field(None, max_length=255)
    claimed: dict[str, Any] = Field(default_factory=dict)
    params: dict[str, str | int | float | bool | None] | None = None
    match_fields: list[str] | None = None
    amount_usd: float | None = Field(None, ge=0)
    currency: str | None = Field(None, min_length=3, max_length=3)
    idempotency_key: str | None = Field(None, max_length=255)
    metadata: dict[str, Any] | None = None

    @field_validator("currency")
    @classmethod
    def _normalise_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value


_SAVED_RECONCILIATION_BRIDGE_CONNECTORS = {
    "ledger_refund": LEDGER_REFUND_CONNECTOR_TYPE,
    "ledger_refund_api": LEDGER_REFUND_CONNECTOR_TYPE,
    "stripe": STRIPE_REFUND_CONNECTOR_TYPE,
    "stripe_refund": STRIPE_REFUND_CONNECTOR_TYPE,
    "stripe_refunds": STRIPE_REFUND_CONNECTOR_TYPE,
    "razorpay": RAZORPAY_REFUND_CONNECTOR_TYPE,
    "razorpay_refund": RAZORPAY_REFUND_CONNECTOR_TYPE,
    "razorpay_refunds": RAZORPAY_REFUND_CONNECTOR_TYPE,
    "crm_record": CUSTOMER_RECORD_CONNECTOR_TYPE,
    "customer_record": CUSTOMER_RECORD_CONNECTOR_TYPE,
    "customer_record_api": CUSTOMER_RECORD_CONNECTOR_TYPE,
    "generic_rest": GENERIC_REST_CONNECTOR_TYPE,
    "generic_rest_api": GENERIC_REST_CONNECTOR_TYPE,
    "hubspot": HUBSPOT_CRM_CONNECTOR_TYPE,
    "hubspot_crm": HUBSPOT_CRM_CONNECTOR_TYPE,
    "hubspot_customer": HUBSPOT_CRM_CONNECTOR_TYPE,
    "salesforce": SALESFORCE_CRM_CONNECTOR_TYPE,
    "salesforce_crm": SALESFORCE_CRM_CONNECTOR_TYPE,
    "salesforce_customer": SALESFORCE_CRM_CONNECTOR_TYPE,
    "zoho": ZOHO_CRM_CONNECTOR_TYPE,
    "zoho_crm": ZOHO_CRM_CONNECTOR_TYPE,
    "zoho_customer": ZOHO_CRM_CONNECTOR_TYPE,
    "jira": JIRA_ISSUE_CONNECTOR_TYPE,
    "jira_issue": JIRA_ISSUE_CONNECTOR_TYPE,
    "jira_ticket": JIRA_ISSUE_CONNECTOR_TYPE,
    "jsm": JIRA_ISSUE_CONNECTOR_TYPE,
    "ticket_status": ZENDESK_TICKET_CONNECTOR_TYPE,
    "zendesk": ZENDESK_TICKET_CONNECTOR_TYPE,
    "zendesk_ticket": ZENDESK_TICKET_CONNECTOR_TYPE,
    "netsuite": NETSUITE_FINANCE_CONNECTOR_TYPE,
    "netsuite_finance": NETSUITE_FINANCE_CONNECTOR_TYPE,
    "netsuite_record": NETSUITE_FINANCE_CONNECTOR_TYPE,
    "finance_record": NETSUITE_FINANCE_CONNECTOR_TYPE,
    "procurement_record": NETSUITE_FINANCE_CONNECTOR_TYPE,
    "postgres": POSTGRES_READ_CONNECTOR_TYPE,
    "postgres_read": POSTGRES_READ_CONNECTOR_TYPE,
}


class SavedConnectorReconciliationIngest(BaseModel):
    connector: str = Field(..., min_length=1, max_length=64)
    call_id: str | None = Field(None, max_length=64)
    trace_id: str | None = Field(None, max_length=128)
    runtime_policy_decision_id: str | None = Field(None, max_length=36)
    action_type: str | None = Field(default=None, max_length=64)
    refund_id: str | None = Field(None, max_length=255)
    customer_id: str | None = Field(None, max_length=255)
    record_ref: str | None = Field(None, max_length=255)
    params: dict[str, str | int | float | bool | None] | None = None
    system_ref: str | None = Field(None, max_length=255)
    claimed: dict[str, Any] = Field(default_factory=dict)
    match_fields: list[str] | None = None
    amount_usd: float | None = Field(None, ge=0)
    currency: str | None = Field(None, min_length=3, max_length=3)
    idempotency_key: str | None = Field(None, max_length=255)
    metadata: dict[str, Any] | None = None

    @field_validator("connector")
    @classmethod
    def _normalise_connector(cls, value: str) -> str:
        key = value.strip().lower().replace("-", "_")
        connector = _SAVED_RECONCILIATION_BRIDGE_CONNECTORS.get(key)
        if connector is None:
            allowed = ", ".join(sorted(_SAVED_RECONCILIATION_BRIDGE_CONNECTORS))
            raise ValueError(f"connector must be one of: {allowed}.")
        return connector

    @field_validator("currency")
    @classmethod
    def _normalise_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class OutcomeReconciliationView(BaseModel):
    id: str
    project_id: str
    call_id: str | None
    trace_id: str | None
    runtime_policy_decision_id: str | None
    action_type: str | None
    connector_type: str
    system_ref: str | None
    verdict: str
    verification_status: str
    reason: str | None
    amount_usd: float | None
    currency: str | None
    claimed: dict[str, Any]
    actual: dict[str, Any] | None
    comparison: dict[str, Any]
    idempotency_key: str | None
    metadata: dict[str, Any] | None
    checked_at: datetime
    created_at: datetime


class OutcomeReconciliationListResponse(BaseModel):
    items: list[OutcomeReconciliationView]
    total_in_page: int


class OutcomeReconciliationSummaryResponse(BaseModel):
    window_days: int
    total: int
    matched: int
    mismatched: int
    not_verified: int
    verified: int
    pending: int
    unverifiable: int
    cancelled: int


class SourceMutationIngest(BaseModel):
    source_system: str = Field(..., min_length=1, max_length=64)
    mutation_id: str = Field(..., min_length=1, max_length=255)
    action_type: str | None = Field(default=None, max_length=64)
    resource_type: str | None = Field(default=None, max_length=64)
    resource_id: str | None = Field(default=None, max_length=255)
    system_ref: str | None = Field(default=None, max_length=255)
    actor_type: str | None = Field(default=None, max_length=64)
    actor_id: str | None = Field(default=None, max_length=255)
    zroky_action_id: str | None = Field(default=None, max_length=36)
    action_receipt_id: str | None = Field(default=None, max_length=36)
    idempotency_key: str | None = Field(default=None, max_length=255)
    metadata: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime | None = None

    @field_validator("source_system", "mutation_id")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value is required.")
        return cleaned


class SourceMutationView(BaseModel):
    id: str
    project_id: str
    source_system: str
    mutation_id: str
    action_type: str | None
    resource_type: str | None
    resource_id: str | None
    system_ref: str | None
    actor_type: str | None
    actor_id: str | None
    zroky_action_id: str | None
    action_receipt_id: str | None
    idempotency_key: str | None
    classification: str
    metadata: dict[str, Any]
    occurred_at: datetime
    created_at: datetime


class SourceMutationListResponse(BaseModel):
    items: list[SourceMutationView]
    total_in_page: int


class SourceMutationSummaryResponse(BaseModel):
    total: int
    matched_receipt: int
    authorized_external: int
    legacy_path: int
    unmanaged_agent_action: int
    policy_bypass: int
    unknown_actor: int
    unreceipted: int
    connected_feeds: int = 0
    successful_pollers: int = 0


