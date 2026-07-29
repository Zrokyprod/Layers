"""Shared helpers for outcome reconciliation routes."""

import hashlib
import json
from typing import Any

from fastapi import HTTPException, status

from app.schemas.outcomes import (
    CustomerRecordReconciliationIngest,
    LedgerRefundReconciliationIngest,
    PostgresReadReconciliationIngest,
    SavedCustomerRecordReconciliationIngest,
    SavedGenericRestReconciliationIngest,
    SavedLedgerRefundReconciliationIngest,
    SavedPostgresReadReconciliationIngest,
)
from app.services.protected_action_billing import (
    ProtectedActionMeteringUnavailable,
    ProtectedActionQuotaExceeded,
    quota_error_detail,
)


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
