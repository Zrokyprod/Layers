"""Cost-of-Failure Attribution API — outcome ingest + attribution reads + webhooks.

Surface:
  POST /v1/outcomes                      — ingest (SDK + direct)
  GET  /v1/outcomes/summary              — KPI strip: total cost, by-type, by-cluster
  GET  /v1/outcomes/by-call/{call_id}    — outcome events for a specific call
  GET  /v1/outcomes/replay/{run_id}      — prevented savings for a replay run
  POST /v1/outcomes/webhooks/zendesk     — Zendesk ticket.created / ticket.updated
  POST /v1/outcomes/webhooks/salesforce  — Salesforce Opportunity stage-change
"""

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Mapping

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies.tenant import require_tenant_id
from app.api.routes.outcome_serializers import (
    _serialize_outcome,
    _serialize_reconciliation,
    _serialize_source_mutation,
    _serialize_summary,
)
from app.schemas.outcomes import (
    CustomerRecordReconciliationIngest,
    LedgerRefundReconciliationIngest,
    OutcomeIngest,
    OutcomeReconciliationIngest,
    OutcomeReconciliationListResponse,
    OutcomeReconciliationSummaryResponse,
    OutcomeReconciliationView,
    OutcomeTypeView,
    OutcomeView,
    PostgresReadReconciliationIngest,
    ReplaySavingsResponse,
    SavedConnectorReconciliationIngest,
    SavedCustomerRecordReconciliationIngest,
    SavedGenericRestReconciliationIngest,
    SavedLedgerRefundReconciliationIngest,
    SavedPostgresReadReconciliationIngest,
    SourceMutationIngest,
    SourceMutationListResponse,
    SourceMutationSummaryResponse,
    SourceMutationView,
    SummaryResponse,
)
from app.core.config import get_settings
from app.core.limiter import limiter
from app.db.session import get_db_session
from app.services.outcome_attribution import (
    KNOWN_OUTCOME_TYPES,
    AttributionClusterRow,
    CallOutcomeView,
    OutcomeTypeRow,
    get_attribution_summary,
    get_call_outcomes,
    get_replay_prevented_savings,
    ingest_outcome,
    normalise_salesforce_event,
    normalise_zendesk_ticket,
)
from app.services.outcome_reconciliation import (
    ApiRecordConnector,
    VALID_VERDICTS,
    get_reconciliation,
    get_reconciliation_summary,
    list_reconciliations,
    reconcile_outcome,
)
from app.services.protected_action_billing import (
    ProtectedActionMeteringUnavailable,
    ProtectedActionQuotaExceeded,
    quota_error_detail,
)
from app.services.system_of_record_connectors import (
    ConnectorConfigError,
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
    build_customer_record_connector,
    build_generic_rest_connector,
    build_hubspot_crm_connector,
    build_inline_customer_record_connector,
    build_inline_ledger_refund_connector,
    build_inline_postgres_read_connector,
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
)
from app.services.source_mutations import (
    ingest_source_mutation,
    list_source_mutations,
    source_mutation_summary,
)
from app.services.zoho_oauth import ZohoOAuthError, resolve_zoho_crm_bearer_token

router = APIRouter(prefix="/v1/outcomes", tags=["outcomes"])
logger = logging.getLogger(__name__)


def _map_protected_action_billing_error(
    exc: ProtectedActionQuotaExceeded | ProtectedActionMeteringUnavailable,
) -> HTTPException:
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
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=str(exc),
    )


# ── Helpers ───────────────────────────────────────────────────────────────────


def _optional_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _claim_text(claimed: dict[str, Any], key: str) -> str | None:
    value = claimed.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _refund_id(body: LedgerRefundReconciliationIngest) -> str:
    refund_id = (body.refund_id or _claim_text(body.claimed, "refund_id") or "").strip()
    if not refund_id:
        raise HTTPException(
            status_code=422,
            detail="refund_id is required for ledger refund reconciliation.",
        )
    return refund_id


def _customer_id(body: CustomerRecordReconciliationIngest) -> str:
    customer_id = (
        body.customer_id
        or _claim_text(body.claimed, "customer_id")
        or _claim_text(body.claimed, "id")
        or ""
    ).strip()
    if not customer_id:
        raise HTTPException(
            status_code=422,
            detail="customer_id is required for customer record reconciliation.",
        )
    return customer_id


def _ledger_refund_match_fields(
    claimed: dict[str, Any], explicit: list[str] | None
) -> list[str]:
    if explicit:
        fields = [field.strip() for field in explicit if field.strip()]
        return fields or ["refund_id"]
    fields = [
        field
        for field in ("refund_id", "amount_usd", "currency", "status")
        if field in claimed
    ]
    return fields or ["refund_id"]


def _customer_record_match_fields(
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


def _generic_rest_match_fields(
    claimed: dict[str, Any], explicit: list[str] | None
) -> list[str]:
    if explicit:
        fields = [field.strip() for field in explicit if field.strip()]
        return fields or ["record_ref"]
    fields = [field for field in claimed.keys() if field != "record_ref"]
    return fields or ["record_ref"]


def _hubspot_crm_match_fields(
    claimed: dict[str, Any], explicit: list[str] | None
) -> list[str]:
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


def _zendesk_ticket_match_fields(
    claimed: dict[str, Any], explicit: list[str] | None
) -> list[str]:
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


def _jira_issue_match_fields(
    claimed: dict[str, Any], explicit: list[str] | None
) -> list[str]:
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


def _salesforce_crm_match_fields(
    claimed: dict[str, Any], explicit: list[str] | None
) -> list[str]:
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


def _zoho_crm_match_fields(
    claimed: dict[str, Any], explicit: list[str] | None
) -> list[str]:
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


def _netsuite_finance_match_fields(
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


def _postgres_read_match_fields(
    claimed: dict[str, Any], explicit: list[str] | None
) -> list[str] | None:
    if explicit:
        fields = [field.strip() for field in explicit if field.strip()]
        return fields or None
    fields = [field for field in claimed.keys() if field]
    return fields or None


def _ledger_refund_idempotency_key(
    body: LedgerRefundReconciliationIngest,
    *,
    refund_id: str,
) -> str:
    if body.idempotency_key:
        return body.idempotency_key
    scope = (
        body.runtime_policy_decision_id or body.call_id or body.trace_id or "unlinked"
    )
    return f"ledger_refund:{scope}:{refund_id}"


def _customer_record_idempotency_key(
    body: CustomerRecordReconciliationIngest,
    *,
    customer_id: str,
) -> str:
    if body.idempotency_key:
        return body.idempotency_key
    scope = (
        body.runtime_policy_decision_id or body.call_id or body.trace_id or "unlinked"
    )
    return f"customer_record:{scope}:{customer_id}"


def _saved_ledger_refund_idempotency_key(
    body: SavedLedgerRefundReconciliationIngest,
    *,
    refund_id: str,
) -> str:
    if body.idempotency_key:
        return body.idempotency_key
    scope = (
        body.runtime_policy_decision_id or body.call_id or body.trace_id or "unlinked"
    )
    return f"saved_ledger_refund:{scope}:{refund_id}"


def _saved_razorpay_refund_idempotency_key(
    body: SavedLedgerRefundReconciliationIngest,
    *,
    refund_id: str,
) -> str:
    if body.idempotency_key:
        return body.idempotency_key
    scope = (
        body.runtime_policy_decision_id or body.call_id or body.trace_id or "unlinked"
    )
    return f"saved_razorpay_refund:{scope}:{refund_id}"


def _saved_customer_record_idempotency_key(
    body: SavedCustomerRecordReconciliationIngest,
    *,
    customer_id: str,
) -> str:
    if body.idempotency_key:
        return body.idempotency_key
    scope = (
        body.runtime_policy_decision_id or body.call_id or body.trace_id or "unlinked"
    )
    return f"saved_customer_record:{scope}:{customer_id}"


def _saved_generic_rest_idempotency_key(
    body: SavedGenericRestReconciliationIngest,
    *,
    record_ref: str,
) -> str:
    if body.idempotency_key:
        return body.idempotency_key
    scope = (
        body.runtime_policy_decision_id or body.call_id or body.trace_id or "unlinked"
    )
    return f"saved_generic_rest:{scope}:{record_ref}"


def _saved_hubspot_crm_idempotency_key(
    body: SavedGenericRestReconciliationIngest,
    *,
    record_ref: str,
) -> str:
    if body.idempotency_key:
        return body.idempotency_key
    scope = (
        body.runtime_policy_decision_id or body.call_id or body.trace_id or "unlinked"
    )
    return f"saved_hubspot_crm:{scope}:{record_ref}"


def _saved_zendesk_ticket_idempotency_key(
    body: SavedGenericRestReconciliationIngest,
    *,
    record_ref: str,
) -> str:
    if body.idempotency_key:
        return body.idempotency_key
    scope = (
        body.runtime_policy_decision_id or body.call_id or body.trace_id or "unlinked"
    )
    return f"saved_zendesk_ticket:{scope}:{record_ref}"


def _saved_jira_issue_idempotency_key(
    body: SavedGenericRestReconciliationIngest,
    *,
    record_ref: str,
) -> str:
    if body.idempotency_key:
        return body.idempotency_key
    scope = (
        body.runtime_policy_decision_id or body.call_id or body.trace_id or "unlinked"
    )
    return f"saved_jira_issue:{scope}:{record_ref}"


def _saved_salesforce_crm_idempotency_key(
    body: SavedGenericRestReconciliationIngest,
    *,
    object_type: str,
    record_ref: str,
) -> str:
    if body.idempotency_key:
        return body.idempotency_key
    scope = (
        body.runtime_policy_decision_id or body.call_id or body.trace_id or "unlinked"
    )
    return f"saved_salesforce_crm:{scope}:{object_type}:{record_ref}"


def _saved_zoho_crm_idempotency_key(
    body: SavedGenericRestReconciliationIngest,
    *,
    module_name: str,
    record_ref: str,
) -> str:
    if body.idempotency_key:
        return body.idempotency_key
    scope = (
        body.runtime_policy_decision_id or body.call_id or body.trace_id or "unlinked"
    )
    return f"saved_zoho_crm:{scope}:{module_name}:{record_ref}"


def _saved_netsuite_finance_idempotency_key(
    body: SavedGenericRestReconciliationIngest,
    *,
    record_type: str,
    record_ref: str,
) -> str:
    if body.idempotency_key:
        return body.idempotency_key
    scope = (
        body.runtime_policy_decision_id or body.call_id or body.trace_id or "unlinked"
    )
    return f"saved_netsuite_finance:{scope}:{record_type}:{record_ref}"


def _postgres_read_idempotency_key(body: PostgresReadReconciliationIngest) -> str:
    if body.idempotency_key:
        return body.idempotency_key
    scope = (
        body.runtime_policy_decision_id or body.call_id or body.trace_id or "unlinked"
    )
    query_material = json.dumps(
        {
            "query": body.connector.query.strip(),
            "params": body.connector.params or {},
        },
        default=str,
        separators=(",", ":"),
        sort_keys=True,
    )
    digest = hashlib.sha256(query_material.encode("utf-8")).hexdigest()[:16]
    return f"postgres_read:{scope}:{digest}"


def _saved_postgres_read_idempotency_key(
    body: SavedPostgresReadReconciliationIngest,
    *,
    read_query: str,
) -> str:
    if body.idempotency_key:
        return body.idempotency_key
    scope = (
        body.runtime_policy_decision_id or body.call_id or body.trace_id or "unlinked"
    )
    query_material = json.dumps(
        {
            "query": read_query.strip(),
            "params": body.params or {},
        },
        default=str,
        separators=(",", ":"),
        sort_keys=True,
    )
    digest = hashlib.sha256(query_material.encode("utf-8")).hexdigest()[:16]
    return f"saved_postgres_read:{scope}:{digest}"


def _map_saved_connector_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (ProtectedActionQuotaExceeded, ProtectedActionMeteringUnavailable)):
        return _map_protected_action_billing_error(exc)
    if isinstance(exc, VaultCipherUnavailable):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, EnvelopeFormatError):
        return HTTPException(
            status_code=500,
            detail="Connector secret could not be decrypted.",
        )
    if isinstance(exc, ZohoOAuthError):
        return HTTPException(status_code=502, detail=str(exc))
    return HTTPException(status_code=422, detail=str(exc))


def _bridge_record_ref(body: SavedConnectorReconciliationIngest) -> str:
    record_ref = (
        body.record_ref
        or _claim_text(body.claimed, "record_ref")
        or _claim_text(body.claimed, "id")
        or _claim_text(body.claimed, "external_ref")
        or ""
    ).strip()
    if not record_ref:
        raise HTTPException(
            status_code=422,
            detail="record_ref is required for Generic REST saved reconciliation.",
        )
    return record_ref


def _bridge_metadata(body: SavedConnectorReconciliationIngest) -> dict[str, Any]:
    return {
        **(body.metadata or {}),
        "runtime_path": "webhook_bridge",
        "bridge_connector": body.connector,
    }


def _bridge_salesforce_object_type(body: SavedConnectorReconciliationIngest) -> str:
    for source in (body.params, body.metadata):
        if not isinstance(source, Mapping):
            continue
        value = source.get("object_type") or source.get("salesforce_object")
        if value is None:
            continue
        cleaned = str(value).strip()
        if not cleaned:
            continue
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(__c)?", cleaned):
            raise HTTPException(
                status_code=422,
                detail="object_type must be a Salesforce object API name.",
            )
        return cleaned
    return "Account"


def _bridge_zoho_module_name(body: SavedConnectorReconciliationIngest) -> str:
    for source in (body.params, body.metadata):
        if not isinstance(source, Mapping):
            continue
        value = source.get("module_name") or source.get("zoho_module")
        if value is None:
            continue
        cleaned = str(value).strip()
        if not cleaned:
            continue
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", cleaned):
            raise HTTPException(
                status_code=422,
                detail="module_name must be a Zoho CRM module API name.",
            )
        return cleaned
    return "Contacts"


def _bridge_netsuite_record_type(body: SavedConnectorReconciliationIngest) -> str:
    for source in (body.params, body.metadata):
        if not isinstance(source, Mapping):
            continue
        value = source.get("record_type") or source.get("netsuite_record_type")
        if value is None:
            continue
        cleaned = str(value).strip()
        if not cleaned:
            continue
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", cleaned):
            raise HTTPException(
                status_code=422,
                detail="record_type must be a NetSuite record type API name.",
            )
        return cleaned
    return "vendorBill"


def _create_saved_ledger_refund_reconciliation(
    *,
    db: Session,
    tenant_id: str,
    body: SavedLedgerRefundReconciliationIngest,
) -> OutcomeReconciliationView:
    config = get_connector_config(
        db,
        project_id=tenant_id,
        connector_type=LEDGER_REFUND_CONNECTOR_TYPE,
    )
    if config is None or not config.is_active:
        raise HTTPException(
            status_code=404,
            detail="Ledger refund connector is not configured.",
        )

    refund_id = _refund_id(body)
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
            system_ref=body.system_ref or f"ledger:{refund_id}",
            amount_usd=body.amount_usd
            if body.amount_usd is not None
            else _optional_float(claimed.get("amount_usd")),
            currency=body.currency or _claim_text(claimed, "currency"),
            match_fields=_ledger_refund_match_fields(claimed, body.match_fields),
            idempotency_key=_saved_ledger_refund_idempotency_key(
                body, refund_id=refund_id
            ),
            metadata={
                **(body.metadata or {}),
                "connector_kind": "ledger_refund_api",
                "connector_config_id": config.id,
                "refund_id": refund_id,
                "source": "saved_connector_runtime",
            },
        )
    except (
        ConnectorConfigError,
        EnvelopeFormatError,
        VaultCipherUnavailable,
        ValueError,
    ) as exc:
        raise _map_saved_connector_error(exc) from exc

    return _serialize_reconciliation(row)


def _create_saved_stripe_refund_reconciliation(
    *,
    db: Session,
    tenant_id: str,
    body: SavedLedgerRefundReconciliationIngest,
) -> OutcomeReconciliationView:
    config = get_connector_config(
        db,
        project_id=tenant_id,
        connector_type=STRIPE_REFUND_CONNECTOR_TYPE,
    )
    if config is None or not config.is_active:
        raise HTTPException(
            status_code=404,
            detail="Stripe refund connector is not configured.",
        )

    refund_id = _refund_id(body)
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
            system_ref=body.system_ref or f"stripe:refund:{refund_id}",
            amount_usd=body.amount_usd
            if body.amount_usd is not None
            else _optional_float(claimed.get("amount_usd")),
            currency=body.currency or _claim_text(claimed, "currency"),
            match_fields=_ledger_refund_match_fields(claimed, body.match_fields),
            idempotency_key=_saved_razorpay_refund_idempotency_key(
                body, refund_id=refund_id
            ),
            metadata={
                **(body.metadata or {}),
                "connector_kind": STRIPE_REFUND_CONNECTOR_TYPE,
                "connector_config_id": config.id,
                "refund_id": refund_id,
                "source": "saved_connector_runtime",
            },
        )
    except (
        ConnectorConfigError,
        EnvelopeFormatError,
        VaultCipherUnavailable,
        ValueError,
    ) as exc:
        raise _map_saved_connector_error(exc) from exc

    return _serialize_reconciliation(row)


def _create_saved_razorpay_refund_reconciliation(
    *,
    db: Session,
    tenant_id: str,
    body: SavedLedgerRefundReconciliationIngest,
) -> OutcomeReconciliationView:
    config = get_connector_config(
        db,
        project_id=tenant_id,
        connector_type=RAZORPAY_REFUND_CONNECTOR_TYPE,
    )
    if config is None or not config.is_active:
        raise HTTPException(
            status_code=404,
            detail="Razorpay refund connector is not configured.",
        )

    refund_id = _refund_id(body)
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
            system_ref=body.system_ref or f"razorpay:refund:{refund_id}",
            amount_usd=body.amount_usd
            if body.amount_usd is not None
            else _optional_float(claimed.get("amount_usd")),
            currency=body.currency or _claim_text(claimed, "currency"),
            match_fields=_ledger_refund_match_fields(claimed, body.match_fields),
            idempotency_key=_saved_ledger_refund_idempotency_key(
                body, refund_id=refund_id
            ),
            metadata={
                **(body.metadata or {}),
                "connector_kind": RAZORPAY_REFUND_CONNECTOR_TYPE,
                "connector_config_id": config.id,
                "refund_id": refund_id,
                "source": "saved_connector_runtime",
            },
        )
    except (
        ConnectorConfigError,
        EnvelopeFormatError,
        VaultCipherUnavailable,
        ValueError,
    ) as exc:
        raise _map_saved_connector_error(exc) from exc

    return _serialize_reconciliation(row)


def _create_saved_customer_record_reconciliation(
    *,
    db: Session,
    tenant_id: str,
    body: SavedCustomerRecordReconciliationIngest,
) -> OutcomeReconciliationView:
    config = get_connector_config(
        db,
        project_id=tenant_id,
        connector_type=CUSTOMER_RECORD_CONNECTOR_TYPE,
    )
    if config is None or not config.is_active:
        raise HTTPException(
            status_code=404,
            detail="Customer record connector is not configured.",
        )

    customer_id = _customer_id(body)
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
            system_ref=body.system_ref or f"crm:{customer_id}",
            amount_usd=body.amount_usd,
            currency=body.currency,
            match_fields=_customer_record_match_fields(claimed, body.match_fields),
            idempotency_key=_saved_customer_record_idempotency_key(
                body, customer_id=customer_id
            ),
            metadata={
                **(body.metadata or {}),
                "connector_kind": "customer_record_api",
                "connector_config_id": config.id,
                "customer_id": customer_id,
                "source": "saved_connector_runtime",
            },
        )
    except (
        ConnectorConfigError,
        EnvelopeFormatError,
        VaultCipherUnavailable,
        ValueError,
    ) as exc:
        raise _map_saved_connector_error(exc) from exc

    return _serialize_reconciliation(row)


def _create_saved_generic_rest_reconciliation(
    *,
    db: Session,
    tenant_id: str,
    body: SavedGenericRestReconciliationIngest,
) -> OutcomeReconciliationView:
    config = get_connector_config(
        db,
        project_id=tenant_id,
        connector_type=GENERIC_REST_CONNECTOR_TYPE,
    )
    if config is None or not config.is_active:
        raise HTTPException(
            status_code=404,
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
            match_fields=_generic_rest_match_fields(claimed, body.match_fields),
            idempotency_key=_saved_generic_rest_idempotency_key(
                body, record_ref=record_ref
            ),
            metadata={
                **(body.metadata or {}),
                "connector_kind": GENERIC_REST_CONNECTOR_TYPE,
                "connector_config_id": config.id,
                "record_ref": record_ref,
                "source": "saved_connector_runtime",
            },
        )
    except (
        ConnectorConfigError,
        EnvelopeFormatError,
        VaultCipherUnavailable,
        ValueError,
    ) as exc:
        raise _map_saved_connector_error(exc) from exc

    return _serialize_reconciliation(row)


def _create_saved_hubspot_crm_reconciliation(
    *,
    db: Session,
    tenant_id: str,
    body: SavedGenericRestReconciliationIngest,
) -> OutcomeReconciliationView:
    config = get_connector_config(
        db,
        project_id=tenant_id,
        connector_type=HUBSPOT_CRM_CONNECTOR_TYPE,
    )
    if config is None or not config.is_active:
        raise HTTPException(
            status_code=404,
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
            match_fields=_hubspot_crm_match_fields(claimed, body.match_fields),
            idempotency_key=_saved_hubspot_crm_idempotency_key(
                body, record_ref=record_ref
            ),
            metadata={
                **(body.metadata or {}),
                "connector_kind": HUBSPOT_CRM_CONNECTOR_TYPE,
                "connector_config_id": config.id,
                "record_ref": record_ref,
                "source": "saved_connector_runtime",
            },
        )
    except (
        ConnectorConfigError,
        EnvelopeFormatError,
        VaultCipherUnavailable,
        ValueError,
    ) as exc:
        raise _map_saved_connector_error(exc) from exc

    return _serialize_reconciliation(row)


def _create_saved_zendesk_ticket_reconciliation(
    *,
    db: Session,
    tenant_id: str,
    body: SavedGenericRestReconciliationIngest,
) -> OutcomeReconciliationView:
    config = get_connector_config(
        db,
        project_id=tenant_id,
        connector_type=ZENDESK_TICKET_CONNECTOR_TYPE,
    )
    if config is None or not config.is_active:
        raise HTTPException(
            status_code=404,
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
            match_fields=_zendesk_ticket_match_fields(claimed, body.match_fields),
            idempotency_key=_saved_zendesk_ticket_idempotency_key(
                body, record_ref=record_ref
            ),
            metadata={
                **(body.metadata or {}),
                "connector_kind": ZENDESK_TICKET_CONNECTOR_TYPE,
                "connector_config_id": config.id,
                "record_ref": record_ref,
                "source": "saved_connector_runtime",
            },
        )
    except (
        ConnectorConfigError,
        EnvelopeFormatError,
        VaultCipherUnavailable,
        ValueError,
    ) as exc:
        raise _map_saved_connector_error(exc) from exc

    return _serialize_reconciliation(row)


def _create_saved_jira_issue_reconciliation(
    *,
    db: Session,
    tenant_id: str,
    body: SavedGenericRestReconciliationIngest,
) -> OutcomeReconciliationView:
    config = get_connector_config(
        db,
        project_id=tenant_id,
        connector_type=JIRA_ISSUE_CONNECTOR_TYPE,
    )
    if config is None or not config.is_active:
        raise HTTPException(
            status_code=404,
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
            match_fields=_jira_issue_match_fields(claimed, body.match_fields),
            idempotency_key=_saved_jira_issue_idempotency_key(
                body, record_ref=record_ref
            ),
            metadata={
                **(body.metadata or {}),
                "connector_kind": JIRA_ISSUE_CONNECTOR_TYPE,
                "connector_config_id": config.id,
                "record_ref": record_ref,
                "source": "saved_connector_runtime",
            },
        )
    except (
        ConnectorConfigError,
        EnvelopeFormatError,
        VaultCipherUnavailable,
        ValueError,
    ) as exc:
        raise _map_saved_connector_error(exc) from exc

    return _serialize_reconciliation(row)


def _create_saved_salesforce_crm_reconciliation(
    *,
    db: Session,
    tenant_id: str,
    body: SavedGenericRestReconciliationIngest,
    object_type: str,
) -> OutcomeReconciliationView:
    config = get_connector_config(
        db,
        project_id=tenant_id,
        connector_type=SALESFORCE_CRM_CONNECTOR_TYPE,
    )
    if config is None or not config.is_active:
        raise HTTPException(
            status_code=404,
            detail="Salesforce CRM connector is not configured.",
        )

    record_ref = body.record_ref.strip()
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
            amount_usd=body.amount_usd
            if body.amount_usd is not None
            else _optional_float(claimed.get("amount_usd") or claimed.get("Amount")),
            currency=body.currency or _claim_text(claimed, "currency"),
            match_fields=_salesforce_crm_match_fields(claimed, body.match_fields),
            idempotency_key=_saved_salesforce_crm_idempotency_key(
                body,
                object_type=object_type,
                record_ref=record_ref,
            ),
            metadata={
                **(body.metadata or {}),
                "connector_kind": SALESFORCE_CRM_CONNECTOR_TYPE,
                "connector_config_id": config.id,
                "object_type": object_type,
                "record_ref": record_ref,
                "source": "saved_connector_runtime",
            },
        )
    except (
        ConnectorConfigError,
        EnvelopeFormatError,
        VaultCipherUnavailable,
        ValueError,
    ) as exc:
        raise _map_saved_connector_error(exc) from exc

    return _serialize_reconciliation(row)


def _create_saved_zoho_crm_reconciliation(
    *,
    db: Session,
    tenant_id: str,
    body: SavedGenericRestReconciliationIngest,
    module_name: str,
) -> OutcomeReconciliationView:
    config = get_connector_config(
        db,
        project_id=tenant_id,
        connector_type=ZOHO_CRM_CONNECTOR_TYPE,
    )
    if config is None or not config.is_active:
        raise HTTPException(
            status_code=404,
            detail="Zoho CRM connector is not configured.",
        )

    record_ref = body.record_ref.strip()
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
            amount_usd=body.amount_usd
            if body.amount_usd is not None
            else _optional_float(claimed.get("amount_usd") or claimed.get("Amount")),
            currency=body.currency or _claim_text(claimed, "currency"),
            match_fields=_zoho_crm_match_fields(claimed, body.match_fields),
            idempotency_key=_saved_zoho_crm_idempotency_key(
                body,
                module_name=module_name,
                record_ref=record_ref,
            ),
            metadata={
                **(body.metadata or {}),
                "connector_kind": ZOHO_CRM_CONNECTOR_TYPE,
                "connector_config_id": config.id,
                "module_name": module_name,
                "record_ref": record_ref,
                "source": "saved_connector_runtime",
            },
        )
    except (
        ConnectorConfigError,
        EnvelopeFormatError,
        VaultCipherUnavailable,
        ZohoOAuthError,
        ValueError,
    ) as exc:
        raise _map_saved_connector_error(exc) from exc

    return _serialize_reconciliation(row)


def _create_saved_netsuite_finance_reconciliation(
    *,
    db: Session,
    tenant_id: str,
    body: SavedGenericRestReconciliationIngest,
    record_type: str,
) -> OutcomeReconciliationView:
    config = get_connector_config(
        db,
        project_id=tenant_id,
        connector_type=NETSUITE_FINANCE_CONNECTOR_TYPE,
    )
    if config is None or not config.is_active:
        raise HTTPException(
            status_code=404,
            detail="NetSuite finance connector is not configured.",
        )

    record_ref = body.record_ref.strip()
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
            amount_usd=body.amount_usd
            if body.amount_usd is not None
            else _optional_float(
                claimed.get("amount_usd")
                or claimed.get("Amount")
                or claimed.get("total")
            ),
            currency=body.currency or _claim_text(claimed, "currency"),
            match_fields=_netsuite_finance_match_fields(claimed, body.match_fields),
            idempotency_key=_saved_netsuite_finance_idempotency_key(
                body,
                record_type=record_type,
                record_ref=record_ref,
            ),
            metadata={
                **(body.metadata or {}),
                "connector_kind": NETSUITE_FINANCE_CONNECTOR_TYPE,
                "connector_config_id": config.id,
                "record_type": record_type,
                "record_ref": record_ref,
                "source": "saved_connector_runtime",
            },
        )
    except (
        ConnectorConfigError,
        EnvelopeFormatError,
        VaultCipherUnavailable,
        ValueError,
    ) as exc:
        raise _map_saved_connector_error(exc) from exc

    return _serialize_reconciliation(row)


def _create_saved_postgres_read_reconciliation(
    *,
    db: Session,
    tenant_id: str,
    body: SavedPostgresReadReconciliationIngest,
) -> OutcomeReconciliationView:
    config = get_connector_config(
        db,
        project_id=tenant_id,
        connector_type=POSTGRES_READ_CONNECTOR_TYPE,
    )
    if config is None or not config.is_active:
        raise HTTPException(
            status_code=404,
            detail="PostgreSQL read connector is not configured.",
        )
    if not config.read_query:
        raise HTTPException(
            status_code=422,
            detail="PostgreSQL read connector query is not configured.",
        )

    settings = get_settings()
    try:
        database_url = decrypt_connector_database_url(config, project_id=tenant_id)
        if not database_url:
            raise ValueError("PostgreSQL database URL is not configured.")
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
            match_fields=_postgres_read_match_fields(body.claimed, body.match_fields),
            idempotency_key=_saved_postgres_read_idempotency_key(
                body,
                read_query=config.read_query,
            ),
            metadata={
                **(body.metadata or {}),
                "connector_kind": POSTGRES_READ_CONNECTOR_TYPE,
                "connector_config_id": config.id,
                "source": "saved_connector_runtime",
            },
        )
    except (
        ConnectorConfigError,
        EnvelopeFormatError,
        VaultCipherUnavailable,
        ValueError,
    ) as exc:
        raise _map_saved_connector_error(exc) from exc

    return _serialize_reconciliation(row)


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post("", response_model=OutcomeView, status_code=201)
@limiter.limit("120/minute")
def create_outcome(
    request: Request,
    body: OutcomeIngest = Body(...),
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> OutcomeView:
    """Ingest one business-outcome event and attribute it to a call."""
    evt = ingest_outcome(
        db,
        project_id=tenant_id,
        call_id=body.call_id,
        outcome_type=body.outcome_type,
        amount_usd=body.amount_usd,
        source="api",
        external_ref=body.external_ref,
        idempotency_key=body.idempotency_key,
        occurred_at=body.occurred_at,
        metadata=body.metadata,
    )
    return _serialize_outcome(evt)


@router.get("/summary", response_model=SummaryResponse)
@limiter.limit("30/minute")
def get_summary(
    request: Request,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
    days: int = Query(default=30, ge=1, le=365),
) -> SummaryResponse:
    """Attribution summary: total cost + by-type + by-cluster (agent × detector)."""
    s = get_attribution_summary(db, project_id=tenant_id, days=days)
    return _serialize_summary(s)


@router.post(
    "/reconciliation", response_model=OutcomeReconciliationView, status_code=201
)
@limiter.limit("120/minute")
def create_reconciliation(
    request: Request,
    body: OutcomeReconciliationIngest = Body(...),
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> OutcomeReconciliationView:
    """Reconcile an agent's claimed outcome against system-of-record evidence."""
    try:
        row = reconcile_outcome(
            db,
            project_id=tenant_id,
            claimed=body.claimed,
            connector=ApiRecordConnector(
                record=body.actual,
                record_found=body.actual_record_found,
                connector_type=body.connector_type,
            ),
            call_id=body.call_id,
            trace_id=body.trace_id,
            runtime_policy_decision_id=body.runtime_policy_decision_id,
            action_type=body.action_type,
            system_ref=body.system_ref,
            amount_usd=body.amount_usd,
            currency=body.currency,
            match_fields=body.match_fields,
            idempotency_key=body.idempotency_key,
            metadata=body.metadata,
        )
    except (ProtectedActionQuotaExceeded, ProtectedActionMeteringUnavailable) as exc:
        raise _map_protected_action_billing_error(exc) from exc
    return _serialize_reconciliation(row)


@router.post(
    "/reconciliation/postgres-read",
    response_model=OutcomeReconciliationView,
    status_code=201,
)
@limiter.limit("30/minute")
def create_postgres_read_reconciliation(
    request: Request,
    body: PostgresReadReconciliationIngest = Body(...),
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> OutcomeReconciliationView:
    """Verify a claimed state against one read-only PostgreSQL source row."""
    settings = get_settings()
    timeout = body.connector.timeout_seconds or settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS
    connector = build_inline_postgres_read_connector(
        database_url=body.connector.database_url,
        query=body.connector.query,
        params=body.connector.params,
        timeout_seconds=timeout,
        allow_private_hosts=settings.OUTCOME_CONNECTOR_ALLOW_PRIVATE_HOSTS,
    )

    try:
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
            match_fields=_postgres_read_match_fields(body.claimed, body.match_fields),
            idempotency_key=_postgres_read_idempotency_key(body),
            metadata={
                **(body.metadata or {}),
                "connector_kind": "postgres_read",
                "source": "postgres_read_verifier",
            },
        )
    except ConnectorConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (ProtectedActionQuotaExceeded, ProtectedActionMeteringUnavailable) as exc:
        raise _map_protected_action_billing_error(exc) from exc

    return _serialize_reconciliation(row)


@router.post(
    "/reconciliation/ledger-refund",
    response_model=OutcomeReconciliationView,
    status_code=201,
)
@limiter.limit("60/minute")
def create_ledger_refund_reconciliation(
    request: Request,
    body: LedgerRefundReconciliationIngest = Body(...),
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> OutcomeReconciliationView:
    """Fetch a refund from a ledger API and reconcile it against the agent claim."""
    refund_id = _refund_id(body)
    claimed = dict(body.claimed)
    claimed.setdefault("refund_id", refund_id)

    settings = get_settings()
    timeout = (
        body.connector.timeout_seconds or settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS
    )
    max_attempts = (
        body.connector.max_attempts or settings.OUTCOME_CONNECTOR_MAX_ATTEMPTS
    )
    connector = build_inline_ledger_refund_connector(
        base_url=body.connector.base_url,
        refund_id=refund_id,
        bearer_token=body.connector.bearer_token,
        path_template=body.connector.path_template,
        query=body.connector.query,
        record_path=body.connector.record_path,
        timeout_seconds=timeout,
        max_attempts=max_attempts,
        allow_private_hosts=settings.OUTCOME_CONNECTOR_ALLOW_PRIVATE_HOSTS,
    )

    try:
        row = reconcile_outcome(
            db,
            project_id=tenant_id,
            claimed=claimed,
            connector=connector,
            call_id=body.call_id,
            trace_id=body.trace_id,
            runtime_policy_decision_id=body.runtime_policy_decision_id,
            action_type=body.action_type or "refund",
            system_ref=body.system_ref or f"ledger:{refund_id}",
            amount_usd=body.amount_usd
            if body.amount_usd is not None
            else _optional_float(claimed.get("amount_usd")),
            currency=body.currency or _claim_text(claimed, "currency"),
            match_fields=_ledger_refund_match_fields(claimed, body.match_fields),
            idempotency_key=_ledger_refund_idempotency_key(body, refund_id=refund_id),
            metadata={
                **(body.metadata or {}),
                "connector_kind": "ledger_refund_api",
                "refund_id": refund_id,
            },
        )
    except ConnectorConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (ProtectedActionQuotaExceeded, ProtectedActionMeteringUnavailable) as exc:
        raise _map_protected_action_billing_error(exc) from exc

    return _serialize_reconciliation(row)


@router.post(
    "/reconciliation/ledger-refund/saved",
    response_model=OutcomeReconciliationView,
    status_code=201,
)
@limiter.limit("60/minute")
def create_saved_ledger_refund_reconciliation(
    request: Request,
    body: SavedLedgerRefundReconciliationIngest = Body(...),
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> OutcomeReconciliationView:
    """Use the saved ledger connector to verify a refund without resending its secret."""
    return _create_saved_ledger_refund_reconciliation(
        db=db,
        tenant_id=tenant_id,
        body=body,
    )


@router.post(
    "/reconciliation/stripe-refund/saved",
    response_model=OutcomeReconciliationView,
    status_code=201,
)
@limiter.limit("60/minute")
def create_saved_stripe_refund_reconciliation(
    request: Request,
    body: SavedLedgerRefundReconciliationIngest = Body(...),
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> OutcomeReconciliationView:
    """Use the saved Stripe connector to verify a refund without resending its secret."""
    return _create_saved_stripe_refund_reconciliation(
        db=db,
        tenant_id=tenant_id,
        body=body,
    )


@router.post(
    "/reconciliation/razorpay-refund/saved",
    response_model=OutcomeReconciliationView,
    status_code=201,
)
@limiter.limit("60/minute")
def create_saved_razorpay_refund_reconciliation(
    request: Request,
    body: SavedLedgerRefundReconciliationIngest = Body(...),
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> OutcomeReconciliationView:
    """Use the saved Razorpay connector to verify a refund without resending its secret."""
    return _create_saved_razorpay_refund_reconciliation(
        db=db,
        tenant_id=tenant_id,
        body=body,
    )


@router.post(
    "/reconciliation/customer-record",
    response_model=OutcomeReconciliationView,
    status_code=201,
)
@limiter.limit("60/minute")
def create_customer_record_reconciliation(
    request: Request,
    body: CustomerRecordReconciliationIngest = Body(...),
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> OutcomeReconciliationView:
    """Fetch a CRM/customer record and reconcile it against the agent claim."""
    customer_id = _customer_id(body)
    claimed = dict(body.claimed)
    claimed.setdefault("customer_id", customer_id)

    settings = get_settings()
    timeout = (
        body.connector.timeout_seconds or settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS
    )
    max_attempts = (
        body.connector.max_attempts or settings.OUTCOME_CONNECTOR_MAX_ATTEMPTS
    )
    connector = build_inline_customer_record_connector(
        base_url=body.connector.base_url,
        customer_id=customer_id,
        bearer_token=body.connector.bearer_token,
        path_template=body.connector.path_template,
        query=body.connector.query,
        record_path=body.connector.record_path,
        timeout_seconds=timeout,
        max_attempts=max_attempts,
        allow_private_hosts=settings.OUTCOME_CONNECTOR_ALLOW_PRIVATE_HOSTS,
    )

    try:
        row = reconcile_outcome(
            db,
            project_id=tenant_id,
            claimed=claimed,
            connector=connector,
            call_id=body.call_id,
            trace_id=body.trace_id,
            runtime_policy_decision_id=body.runtime_policy_decision_id,
            action_type=body.action_type or "customer_record_update",
            system_ref=body.system_ref or f"crm:{customer_id}",
            amount_usd=body.amount_usd,
            currency=body.currency,
            match_fields=_customer_record_match_fields(claimed, body.match_fields),
            idempotency_key=_customer_record_idempotency_key(
                body, customer_id=customer_id
            ),
            metadata={
                **(body.metadata or {}),
                "connector_kind": "customer_record_api",
                "customer_id": customer_id,
            },
        )
    except ConnectorConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (ProtectedActionQuotaExceeded, ProtectedActionMeteringUnavailable) as exc:
        raise _map_protected_action_billing_error(exc) from exc

    return _serialize_reconciliation(row)


@router.post(
    "/reconciliation/customer-record/saved",
    response_model=OutcomeReconciliationView,
    status_code=201,
)
@limiter.limit("60/minute")
def create_saved_customer_record_reconciliation(
    request: Request,
    body: SavedCustomerRecordReconciliationIngest = Body(...),
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> OutcomeReconciliationView:
    """Use the saved CRM connector to verify a customer record without resending its secret."""
    return _create_saved_customer_record_reconciliation(
        db=db,
        tenant_id=tenant_id,
        body=body,
    )


@router.post(
    "/reconciliation/generic-rest/saved",
    response_model=OutcomeReconciliationView,
    status_code=201,
)
@limiter.limit("60/minute")
def create_saved_generic_rest_reconciliation(
    request: Request,
    body: SavedGenericRestReconciliationIngest = Body(...),
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> OutcomeReconciliationView:
    """Use the saved Generic REST connector to verify a custom system record."""
    return _create_saved_generic_rest_reconciliation(
        db=db,
        tenant_id=tenant_id,
        body=body,
    )


@router.post(
    "/reconciliation/postgres-read/saved",
    response_model=OutcomeReconciliationView,
    status_code=201,
)
@limiter.limit("60/minute")
def create_saved_postgres_read_reconciliation(
    request: Request,
    body: SavedPostgresReadReconciliationIngest = Body(...),
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> OutcomeReconciliationView:
    """Use the saved PostgreSQL connector to verify one source-of-record row."""
    return _create_saved_postgres_read_reconciliation(
        db=db,
        tenant_id=tenant_id,
        body=body,
    )


@router.post(
    "/reconciliation/saved",
    response_model=OutcomeReconciliationView,
    status_code=201,
)
@limiter.limit("60/minute")
def create_saved_connector_reconciliation(
    request: Request,
    body: SavedConnectorReconciliationIngest = Body(...),
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> OutcomeReconciliationView:
    """Bridge webhook/HTTP agents into the saved connector verification runtime."""
    common = {
        "call_id": body.call_id,
        "trace_id": body.trace_id,
        "runtime_policy_decision_id": body.runtime_policy_decision_id,
        "action_type": body.action_type,
        "system_ref": body.system_ref,
        "claimed": body.claimed,
        "match_fields": body.match_fields,
        "amount_usd": body.amount_usd,
        "currency": body.currency,
        "idempotency_key": body.idempotency_key,
        "metadata": _bridge_metadata(body),
    }

    if body.connector == LEDGER_REFUND_CONNECTOR_TYPE:
        return _create_saved_ledger_refund_reconciliation(
            db=db,
            tenant_id=tenant_id,
            body=SavedLedgerRefundReconciliationIngest(
                refund_id=body.refund_id,
                **common,
            ),
        )
    if body.connector == STRIPE_REFUND_CONNECTOR_TYPE:
        return _create_saved_stripe_refund_reconciliation(
            db=db,
            tenant_id=tenant_id,
            body=SavedLedgerRefundReconciliationIngest(
                refund_id=body.refund_id,
                **common,
            ),
        )
    if body.connector == RAZORPAY_REFUND_CONNECTOR_TYPE:
        return _create_saved_razorpay_refund_reconciliation(
            db=db,
            tenant_id=tenant_id,
            body=SavedLedgerRefundReconciliationIngest(
                refund_id=body.refund_id,
                **common,
            ),
        )
    if body.connector == CUSTOMER_RECORD_CONNECTOR_TYPE:
        return _create_saved_customer_record_reconciliation(
            db=db,
            tenant_id=tenant_id,
            body=SavedCustomerRecordReconciliationIngest(
                customer_id=body.customer_id,
                **common,
            ),
        )
    if body.connector == GENERIC_REST_CONNECTOR_TYPE:
        return _create_saved_generic_rest_reconciliation(
            db=db,
            tenant_id=tenant_id,
            body=SavedGenericRestReconciliationIngest(
                record_ref=_bridge_record_ref(body),
                **common,
            ),
        )
    if body.connector == HUBSPOT_CRM_CONNECTOR_TYPE:
        return _create_saved_hubspot_crm_reconciliation(
            db=db,
            tenant_id=tenant_id,
            body=SavedGenericRestReconciliationIngest(
                record_ref=_bridge_record_ref(body),
                **common,
            ),
        )
    if body.connector == ZENDESK_TICKET_CONNECTOR_TYPE:
        return _create_saved_zendesk_ticket_reconciliation(
            db=db,
            tenant_id=tenant_id,
            body=SavedGenericRestReconciliationIngest(
                record_ref=_bridge_record_ref(body),
                **common,
            ),
        )
    if body.connector == JIRA_ISSUE_CONNECTOR_TYPE:
        return _create_saved_jira_issue_reconciliation(
            db=db,
            tenant_id=tenant_id,
            body=SavedGenericRestReconciliationIngest(
                record_ref=_bridge_record_ref(body),
                **common,
            ),
        )
    if body.connector == SALESFORCE_CRM_CONNECTOR_TYPE:
        return _create_saved_salesforce_crm_reconciliation(
            db=db,
            tenant_id=tenant_id,
            body=SavedGenericRestReconciliationIngest(
                record_ref=_bridge_record_ref(body),
                **common,
            ),
            object_type=_bridge_salesforce_object_type(body),
        )
    if body.connector == ZOHO_CRM_CONNECTOR_TYPE:
        return _create_saved_zoho_crm_reconciliation(
            db=db,
            tenant_id=tenant_id,
            body=SavedGenericRestReconciliationIngest(
                record_ref=_bridge_record_ref(body),
                **common,
            ),
            module_name=_bridge_zoho_module_name(body),
        )
    if body.connector == NETSUITE_FINANCE_CONNECTOR_TYPE:
        return _create_saved_netsuite_finance_reconciliation(
            db=db,
            tenant_id=tenant_id,
            body=SavedGenericRestReconciliationIngest(
                record_ref=_bridge_record_ref(body),
                **common,
            ),
            record_type=_bridge_netsuite_record_type(body),
        )
    if body.connector == POSTGRES_READ_CONNECTOR_TYPE:
        return _create_saved_postgres_read_reconciliation(
            db=db,
            tenant_id=tenant_id,
            body=SavedPostgresReadReconciliationIngest(
                params=body.params,
                **common,
            ),
        )

    raise HTTPException(status_code=422, detail="Unsupported saved connector.")


@router.get("/reconciliation", response_model=OutcomeReconciliationListResponse)
@limiter.limit("60/minute")
def list_reconciliation_checks(
    request: Request,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
    verdict: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
) -> OutcomeReconciliationListResponse:
    """List recent outcome reconciliation checks for the current project."""
    if verdict is not None and verdict not in VALID_VERDICTS:
        raise HTTPException(
            status_code=422,
            detail=f"verdict must be one of: {', '.join(sorted(VALID_VERDICTS))}",
        )
    rows = list_reconciliations(db, project_id=tenant_id, verdict=verdict, limit=limit)
    return OutcomeReconciliationListResponse(
        items=[_serialize_reconciliation(row) for row in rows],
        total_in_page=len(rows),
    )


@router.get(
    "/reconciliation/summary", response_model=OutcomeReconciliationSummaryResponse
)
@limiter.limit("30/minute")
def get_reconciliation_kpis(
    request: Request,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
    days: int = Query(default=30, ge=1, le=365),
) -> OutcomeReconciliationSummaryResponse:
    """Summary of matched, mismatched, and not_verified outcome checks."""
    summary = get_reconciliation_summary(db, project_id=tenant_id, days=days)
    return OutcomeReconciliationSummaryResponse(
        window_days=summary.window_days,
        total=summary.total,
        matched=summary.matched,
        mismatched=summary.mismatched,
        not_verified=summary.not_verified,
        verified=summary.verified,
        pending=summary.pending,
        unverifiable=summary.unverifiable,
        cancelled=summary.cancelled,
    )


@router.get(
    "/reconciliation/by-call/{call_id}",
    response_model=OutcomeReconciliationListResponse,
)
@limiter.limit("60/minute")
def get_reconciliations_for_call(
    request: Request,
    call_id: str,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> OutcomeReconciliationListResponse:
    """List reconciliation checks linked to a specific Zroky call."""
    rows = list_reconciliations(db, project_id=tenant_id, call_id=call_id, limit=100)
    return OutcomeReconciliationListResponse(
        items=[_serialize_reconciliation(row) for row in rows],
        total_in_page=len(rows),
    )


@router.post(
    "/reconciliation/source-mutations",
    response_model=SourceMutationView,
    status_code=201,
)
@limiter.limit("60/minute")
def ingest_source_mutation_record(
    request: Request,
    body: SourceMutationIngest,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> SourceMutationView:
    try:
        row = ingest_source_mutation(
            db,
            project_id=tenant_id,
            source_system=body.source_system,
            mutation_id=body.mutation_id,
            action_type=body.action_type,
            resource_type=body.resource_type,
            resource_id=body.resource_id,
            system_ref=body.system_ref,
            actor_type=body.actor_type,
            actor_id=body.actor_id,
            zroky_action_id=body.zroky_action_id,
            action_receipt_id=body.action_receipt_id,
            idempotency_key=body.idempotency_key,
            metadata=body.metadata,
            occurred_at=body.occurred_at,
        )
    except (ProtectedActionQuotaExceeded, ProtectedActionMeteringUnavailable) as exc:
        raise _map_protected_action_billing_error(exc) from exc
    db.commit()
    return _serialize_source_mutation(row)


@router.get(
    "/reconciliation/source-mutations",
    response_model=SourceMutationListResponse,
)
@limiter.limit("60/minute")
def list_source_mutation_records(
    request: Request,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
    classification: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=100, ge=1, le=500),
) -> SourceMutationListResponse:
    rows = list_source_mutations(
        db,
        project_id=tenant_id,
        classification=classification,
        limit=limit,
    )
    return SourceMutationListResponse(
        items=[_serialize_source_mutation(row) for row in rows],
        total_in_page=len(rows),
    )


@router.get(
    "/reconciliation/source-mutations/unreceipted",
    response_model=SourceMutationListResponse,
)
@limiter.limit("60/minute")
def list_unreceipted_source_mutations(
    request: Request,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
    limit: int = Query(default=100, ge=1, le=500),
) -> SourceMutationListResponse:
    rows = list_source_mutations(
        db,
        project_id=tenant_id,
        unreceipted_only=True,
        limit=limit,
    )
    return SourceMutationListResponse(
        items=[_serialize_source_mutation(row) for row in rows],
        total_in_page=len(rows),
    )


@router.get(
    "/reconciliation/source-mutations/summary",
    response_model=SourceMutationSummaryResponse,
)
@limiter.limit("60/minute")
def get_source_mutation_summary(
    request: Request,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> SourceMutationSummaryResponse:
    return SourceMutationSummaryResponse(**source_mutation_summary(db, project_id=tenant_id))


@router.get("/reconciliation/{check_id}", response_model=OutcomeReconciliationView)
@limiter.limit("60/minute")
def get_reconciliation_check(
    request: Request,
    check_id: str,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> OutcomeReconciliationView:
    """Read one outcome reconciliation check."""
    row = get_reconciliation(db, project_id=tenant_id, check_id=check_id)
    if row is None:
        raise HTTPException(
            status_code=404, detail="Outcome reconciliation check not found."
        )
    return _serialize_reconciliation(row)


@router.get("/by-call/{call_id}", response_model=list[OutcomeTypeView])
@limiter.limit("60/minute")
def get_outcomes_for_call(
    request: Request,
    call_id: str,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> list[OutcomeTypeView]:
    """All outcome events linked to a specific call."""
    views = get_call_outcomes(db, project_id=tenant_id, call_id=call_id)
    return [
        OutcomeTypeView(
            outcome_type=v.outcome_type,
            total_usd=v.amount_usd,
            count=1,
            avg_usd=v.amount_usd,
        )
        for v in views
    ]


@router.get("/replay/{run_id}", response_model=ReplaySavingsResponse)
@limiter.limit("30/minute")
def get_replay_savings(
    request: Request,
    run_id: str,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> ReplaySavingsResponse:
    """Compute the $ value of failures a replay run's candidate prompt would prevent."""
    savings = get_replay_prevented_savings(db, project_id=tenant_id, run_id=run_id)
    return ReplaySavingsResponse(
        run_id=run_id,
        prevented_outcome_cost_usd=savings,
        message=(
            f"This candidate prevents failures worth ${savings:,.2f} in linked outcome costs."
            if savings > 0
            else "No linked outcome events found for passing traces in this run."
        ),
    )


# ── Webhooks ──────────────────────────────────────────────────────────────────


@router.post("/webhooks/zendesk", status_code=200)
@limiter.limit("30/minute")
async def zendesk_webhook(
    request: Request,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> dict[str, str]:
    """Receive Zendesk ticket webhook and ingest escalations as outcome_events."""
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc

    fields = normalise_zendesk_ticket(payload)
    ingest_outcome(db, project_id=tenant_id, **fields)
    return {"status": "ok"}


@router.post("/webhooks/salesforce", status_code=200)
@limiter.limit("30/minute")
async def salesforce_webhook(
    request: Request,
    db: Session = Depends(get_db_session),
    tenant_id: str = Depends(require_tenant_id),
) -> dict[str, str]:
    """Receive Salesforce Opportunity stage-change and ingest churn as outcome_events."""
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc

    fields = normalise_salesforce_event(payload)
    ingest_outcome(db, project_id=tenant_id, **fields)
    return {"status": "ok"}
