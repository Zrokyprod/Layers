from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import ActionExecutionAttempt, ActionIntent, ActionPostExecutionJob
from app.services.action_receipts import generate_action_receipt
from app.services.action_timeline import record_action_timeline_event
from app.services.outcome_reconciliation import ApiRecordConnector, reconcile_outcome
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
)
from app.services.zoho_oauth import resolve_zoho_crm_bearer_token


JOB_VERIFY_OUTCOME = "verify_outcome"
JOB_GENERATE_RECEIPT = "generate_receipt"
JOB_TYPES = frozenset({JOB_VERIFY_OUTCOME, JOB_GENERATE_RECEIPT})

JOB_PENDING = "pending"
JOB_CLAIMED = "claimed"
JOB_RUNNING = "running"
JOB_SUCCEEDED = "succeeded"
JOB_RETRYING = "retrying"
JOB_DEAD = "dead"

PROOF_NOT_STARTED = "not_started"
PROOF_PENDING = "pending"
PROOF_MATCHED = "matched"
PROOF_MISMATCHED = "mismatched"
PROOF_NOT_VERIFIED = "not_verified"

RECEIPT_MISSING = "missing"
RECEIPT_PENDING = "pending"
RECEIPT_GENERATED = "generated"
RECEIPT_FAILED = "failed"

DEFAULT_JOB_MAX_ATTEMPTS = 3
DEFAULT_JOB_LEASE_SECONDS = 300


class ActionPostExecutionError(ValueError):
    pass


@dataclass(frozen=True)
class ProcessedPostExecutionJob:
    job: ActionPostExecutionJob
    result: dict[str, Any]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True, default=str)


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[str] | None:
    if not isinstance(value, list | tuple):
        return None
    out = [str(item).strip() for item in value if str(item).strip()]
    return out or None


def _text(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _connector_alias(value: Any) -> str | None:
    raw = _text(value)
    if raw is None:
        return None
    key = raw.lower().replace("-", "_")
    aliases = {
        "ledger_refund": LEDGER_REFUND_CONNECTOR_TYPE,
        "ledger_refund_api": LEDGER_REFUND_CONNECTOR_TYPE,
        "payment_refund": LEDGER_REFUND_CONNECTOR_TYPE,
        "stripe": STRIPE_REFUND_CONNECTOR_TYPE,
        "stripe_refund": STRIPE_REFUND_CONNECTOR_TYPE,
        "stripe_refunds": STRIPE_REFUND_CONNECTOR_TYPE,
        "razorpay": RAZORPAY_REFUND_CONNECTOR_TYPE,
        "razorpay_refund": RAZORPAY_REFUND_CONNECTOR_TYPE,
        "razorpay_refunds": RAZORPAY_REFUND_CONNECTOR_TYPE,
        "customer_record": CUSTOMER_RECORD_CONNECTOR_TYPE,
        "customer_record_api": CUSTOMER_RECORD_CONNECTOR_TYPE,
        "crm_record": CUSTOMER_RECORD_CONNECTOR_TYPE,
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
        "zendesk": ZENDESK_TICKET_CONNECTOR_TYPE,
        "zendesk_ticket": ZENDESK_TICKET_CONNECTOR_TYPE,
        "netsuite": NETSUITE_FINANCE_CONNECTOR_TYPE,
        "netsuite_finance": NETSUITE_FINANCE_CONNECTOR_TYPE,
        "netsuite_record": NETSUITE_FINANCE_CONNECTOR_TYPE,
        "finance_record": NETSUITE_FINANCE_CONNECTOR_TYPE,
        "procurement_record": NETSUITE_FINANCE_CONNECTOR_TYPE,
        "generic_rest": GENERIC_REST_CONNECTOR_TYPE,
        "generic_rest_api": GENERIC_REST_CONNECTOR_TYPE,
        "ticket_status": GENERIC_REST_CONNECTOR_TYPE,
        "email_delivery": GENERIC_REST_CONNECTOR_TYPE,
        "github_ci": GENERIC_REST_CONNECTOR_TYPE,
        "webhook_callback": GENERIC_REST_CONNECTOR_TYPE,
        "postgres": POSTGRES_READ_CONNECTOR_TYPE,
        "postgres_read": POSTGRES_READ_CONNECTOR_TYPE,
    }
    return aliases.get(key, key)


def _plan_document(attempt: ActionExecutionAttempt) -> dict[str, Any]:
    return _as_dict(_json_loads(attempt.plan_json, {}))


def _runner_plan(attempt: ActionExecutionAttempt) -> dict[str, Any]:
    return _as_dict(_plan_document(attempt).get("execution_plan"))


def _result_summary(attempt: ActionExecutionAttempt) -> dict[str, Any]:
    return _as_dict(_json_loads(attempt.result_summary_json, {}))


def _trace_context(intent: ActionIntent) -> dict[str, Any]:
    return _as_dict(_json_loads(intent.trace_context_json, {}))


def _base_metadata(
    *,
    intent: ActionIntent,
    attempt: ActionExecutionAttempt,
    job: ActionPostExecutionJob,
    connector_type: str | None = None,
) -> dict[str, Any]:
    payload = {
        "source": "action_post_execution_worker",
        "proof_mode": "backend_auto",
        "action_id": intent.id,
        "execution_attempt_id": attempt.id,
        "post_execution_job_id": job.id,
        "execution_status": attempt.status,
    }
    if connector_type:
        payload["connector_kind"] = connector_type
    return payload


def enqueue_action_post_execution_job(
    db: Session,
    *,
    project_id: str,
    action_id: str,
    attempt_id: str,
    job_type: str,
    payload: Mapping[str, Any] | None = None,
    max_attempts: int = DEFAULT_JOB_MAX_ATTEMPTS,
    available_at: datetime | None = None,
) -> ActionPostExecutionJob:
    if job_type not in JOB_TYPES:
        raise ActionPostExecutionError(f"Unsupported post-execution job type: {job_type}.")
    existing = db.execute(
        select(ActionPostExecutionJob).where(
            ActionPostExecutionJob.project_id == project_id,
            ActionPostExecutionJob.action_intent_id == action_id,
            ActionPostExecutionJob.execution_attempt_id == attempt_id,
            ActionPostExecutionJob.job_type == job_type,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    row = ActionPostExecutionJob(
        id=str(uuid4()),
        project_id=project_id,
        action_intent_id=action_id,
        execution_attempt_id=attempt_id,
        job_type=job_type,
        status=JOB_PENDING,
        payload_json=_json_dumps(payload or {}),
        max_attempts=max(1, int(max_attempts)),
        available_at=available_at or _now(),
    )
    db.add(row)
    db.flush()
    return row


def enqueue_post_execution_verification(
    db: Session,
    *,
    project_id: str,
    action_id: str,
    attempt_id: str,
    actor: str | None = None,
) -> ActionPostExecutionJob:
    intent = db.execute(
        select(ActionIntent).where(ActionIntent.project_id == project_id, ActionIntent.id == action_id)
    ).scalar_one()
    intent.proof_status = PROOF_PENDING
    intent.receipt_status = RECEIPT_PENDING
    db.add(intent)
    job = enqueue_action_post_execution_job(
        db,
        project_id=project_id,
        action_id=action_id,
        attempt_id=attempt_id,
        job_type=JOB_VERIFY_OUTCOME,
        payload={"trigger": "execution_finished"},
    )
    record_action_timeline_event(
        db,
        project_id=project_id,
        action_id=action_id,
        event_type="post_execution_queued",
        payload={
            "job_id": job.id,
            "job_type": job.job_type,
            "execution_attempt_id": attempt_id,
            "proof_status": intent.proof_status,
            "receipt_status": intent.receipt_status,
        },
        actor=actor,
    )
    return job


def _claim_next_job(
    db: Session,
    *,
    worker_id: str,
    lease_seconds: int = DEFAULT_JOB_LEASE_SECONDS,
    now: datetime | None = None,
) -> ActionPostExecutionJob | None:
    current = now or _now()
    query = (
        select(ActionPostExecutionJob)
        .where(
            or_(
                and_(
                    ActionPostExecutionJob.status.in_((JOB_PENDING, JOB_RETRYING)),
                    ActionPostExecutionJob.available_at <= current,
                ),
                and_(
                    ActionPostExecutionJob.status.in_((JOB_CLAIMED, JOB_RUNNING)),
                    ActionPostExecutionJob.lease_expires_at.is_not(None),
                    ActionPostExecutionJob.lease_expires_at <= current,
                ),
            )
        )
        .order_by(ActionPostExecutionJob.available_at.asc(), ActionPostExecutionJob.created_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    row = db.execute(query).scalar_one_or_none()
    if row is None:
        return None
    row.status = JOB_RUNNING
    row.claimed_by = worker_id[:128]
    row.claimed_at = current
    row.lease_expires_at = current + timedelta(seconds=max(30, int(lease_seconds)))
    row.attempt_count = int(row.attempt_count or 0) + 1
    row.updated_at = current
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _verification_context(intent: ActionIntent, attempt: ActionExecutionAttempt) -> dict[str, Any]:
    runner_plan = _runner_plan(attempt)
    result = _result_summary(attempt)
    target = _as_dict(runner_plan.get("target"))
    arguments = _as_dict(runner_plan.get("arguments"))
    verification = _as_dict(runner_plan.get("verification"))
    adapter_contract = _as_dict(runner_plan.get("adapter_contract"))
    claimed = _as_dict(verification.get("claimed")) or _as_dict(result.get("claimed"))
    if not claimed:
        claimed = {
            **target,
            **arguments,
        }
        for key in ("provider_ref", "status", "delivery_status", "record_ref", "customer_id", "refund_id"):
            if key in result and key not in claimed:
                claimed[key] = result[key]
    match_fields = (
        _as_list(verification.get("match_fields"))
        or _as_list(result.get("match_fields"))
        or [key for key, value in claimed.items() if value is not None][:20]
        or None
    )
    connector_type = _connector_alias(
        verification.get("connector")
        or verification.get("source_of_record")
        or adapter_contract.get("verification_connector")
    )
    return {
        "runner_plan": runner_plan,
        "result": result,
        "target": target,
        "arguments": arguments,
        "verification": verification,
        "adapter_contract": adapter_contract,
        "claimed": claimed,
        "match_fields": match_fields,
        "connector_type": connector_type,
        "trace": _trace_context(intent),
    }


def _reconcile_not_verified(
    db: Session,
    *,
    intent: ActionIntent,
    attempt: ActionExecutionAttempt,
    job: ActionPostExecutionJob,
    context: Mapping[str, Any],
    connector_type: str,
    reason: str,
) -> Any:
    trace = _as_dict(context.get("trace"))
    claimed = _as_dict(context.get("claimed"))
    metadata = {
        **_base_metadata(intent=intent, attempt=attempt, job=job, connector_type=connector_type),
        "not_verified_reason": reason,
    }
    return reconcile_outcome(
        db,
        project_id=intent.project_id,
        claimed=claimed,
        connector=ApiRecordConnector(record=None, record_found=None, connector_type=connector_type),
        call_id=_text(trace.get("call_id")),
        trace_id=_text(trace.get("trace_id")),
        runtime_policy_decision_id=intent.runtime_policy_decision_id,
        action_type=intent.action_type,
        system_ref=_text(context.get("system_ref")) or f"zroky:{intent.id}:{attempt.id}",
        amount_usd=_float(claimed.get("amount_usd")),
        currency=_text(claimed.get("currency")),
        match_fields=_as_list(context.get("match_fields")),
        idempotency_key=f"action-post-exec:{intent.id}:{attempt.id}:verify",
        metadata=metadata,
    )


def _saved_connector_for_context(
    *,
    db: Session,
    intent: ActionIntent,
    context: Mapping[str, Any],
) -> tuple[Any | None, str, str | None]:
    settings = get_settings()
    connector_type = _connector_alias(context.get("connector_type")) or GENERIC_REST_CONNECTOR_TYPE
    verification = _as_dict(context.get("verification"))
    target = _as_dict(context.get("target"))
    result = _as_dict(context.get("result"))
    claimed = _as_dict(context.get("claimed"))
    config = get_connector_config(db, project_id=intent.project_id, connector_type=connector_type)
    if config is None or not config.is_active:
        return None, connector_type, "connector_not_configured"

    if connector_type == LEDGER_REFUND_CONNECTOR_TYPE:
        refund_id = _text(verification.get("refund_id"), target.get("refund_id"), claimed.get("refund_id"), result.get("refund_id"))
        if refund_id is None:
            return None, connector_type, "refund_id_missing"
        bearer_token = decrypt_connector_bearer_token(config, project_id=intent.project_id)
        return (
            build_ledger_refund_connector(
                config,
                refund_id=refund_id,
                bearer_token=bearer_token,
                timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
                max_attempts=settings.OUTCOME_CONNECTOR_MAX_ATTEMPTS,
                allow_private_hosts=settings.OUTCOME_CONNECTOR_ALLOW_PRIVATE_HOSTS,
            ),
            connector_type,
            None,
        )

    if connector_type == STRIPE_REFUND_CONNECTOR_TYPE:
        refund_id = _text(verification.get("refund_id"), target.get("refund_id"), claimed.get("refund_id"), result.get("refund_id"))
        if refund_id is None:
            return None, connector_type, "stripe_refund_id_missing"
        bearer_token = decrypt_connector_bearer_token(config, project_id=intent.project_id)
        return (
            build_stripe_refund_connector(
                config,
                refund_id=refund_id,
                bearer_token=bearer_token,
                timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
                max_attempts=settings.OUTCOME_CONNECTOR_MAX_ATTEMPTS,
            ),
            connector_type,
            None,
        )

    if connector_type == RAZORPAY_REFUND_CONNECTOR_TYPE:
        refund_id = _text(
            verification.get("refund_id"),
            verification.get("razorpay_refund_id"),
            target.get("refund_id"),
            target.get("razorpay_refund_id"),
            claimed.get("refund_id"),
            claimed.get("razorpay_refund_id"),
            result.get("refund_id"),
            result.get("razorpay_refund_id"),
        )
        if refund_id is None:
            return None, connector_type, "razorpay_refund_id_missing"
        key_secret = decrypt_connector_bearer_token(config, project_id=intent.project_id)
        return (
            build_razorpay_refund_connector(
                config,
                refund_id=refund_id,
                key_secret=key_secret,
                timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
                max_attempts=settings.OUTCOME_CONNECTOR_MAX_ATTEMPTS,
            ),
            connector_type,
            None,
        )

    if connector_type == CUSTOMER_RECORD_CONNECTOR_TYPE:
        customer_id = _text(verification.get("customer_id"), target.get("customer_id"), claimed.get("customer_id"), result.get("customer_id"))
        if customer_id is None:
            return None, connector_type, "customer_id_missing"
        bearer_token = decrypt_connector_bearer_token(config, project_id=intent.project_id)
        return (
            build_customer_record_connector(
                config,
                customer_id=customer_id,
                bearer_token=bearer_token,
                timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
                max_attempts=settings.OUTCOME_CONNECTOR_MAX_ATTEMPTS,
                allow_private_hosts=settings.OUTCOME_CONNECTOR_ALLOW_PRIVATE_HOSTS,
            ),
            connector_type,
            None,
        )

    if connector_type == HUBSPOT_CRM_CONNECTOR_TYPE:
        record_ref = _text(
            verification.get("record_ref"),
            verification.get("contact_id"),
            verification.get("email"),
            target.get("record_ref"),
            target.get("contact_id"),
            target.get("email"),
            claimed.get("record_ref"),
            claimed.get("hs_object_id"),
            claimed.get("hubspot_id"),
            claimed.get("email"),
            result.get("record_ref"),
            result.get("provider_ref"),
        )
        if record_ref is None:
            return None, connector_type, "hubspot_record_ref_missing"
        bearer_token = decrypt_connector_bearer_token(config, project_id=intent.project_id)
        return (
            build_hubspot_crm_connector(
                config,
                record_ref=record_ref,
                bearer_token=bearer_token,
                timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
                max_attempts=settings.OUTCOME_CONNECTOR_MAX_ATTEMPTS,
            ),
            connector_type,
            None,
        )

    if connector_type == ZENDESK_TICKET_CONNECTOR_TYPE:
        record_ref = _text(
            verification.get("record_ref"),
            verification.get("ticket_id"),
            target.get("record_ref"),
            target.get("ticket_id"),
            target.get("support_ticket_id"),
            claimed.get("record_ref"),
            claimed.get("ticket_id"),
            result.get("record_ref"),
            result.get("ticket_id"),
            result.get("provider_ref"),
        )
        if record_ref is None:
            return None, connector_type, "zendesk_ticket_ref_missing"
        bearer_token = decrypt_connector_bearer_token(config, project_id=intent.project_id)
        return (
            build_zendesk_ticket_connector(
                config,
                record_ref=record_ref,
                bearer_token=bearer_token,
                timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
                max_attempts=settings.OUTCOME_CONNECTOR_MAX_ATTEMPTS,
            ),
            connector_type,
            None,
        )

    if connector_type == JIRA_ISSUE_CONNECTOR_TYPE:
        record_ref = _text(
            verification.get("record_ref"),
            verification.get("jira_issue_key"),
            verification.get("issue_key"),
            verification.get("ticket_id"),
            target.get("record_ref"),
            target.get("jira_issue_key"),
            target.get("issue_key"),
            target.get("ticket_id"),
            target.get("support_ticket_id"),
            claimed.get("record_ref"),
            claimed.get("jira_issue_key"),
            claimed.get("issue_key"),
            claimed.get("ticket_id"),
            result.get("record_ref"),
            result.get("jira_issue_key"),
            result.get("issue_key"),
            result.get("ticket_id"),
            result.get("provider_ref"),
        )
        if record_ref is None:
            return None, connector_type, "jira_issue_ref_missing"
        bearer_token = decrypt_connector_bearer_token(config, project_id=intent.project_id)
        return (
            build_jira_issue_connector(
                config,
                record_ref=record_ref,
                bearer_token=bearer_token,
                timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
                max_attempts=settings.OUTCOME_CONNECTOR_MAX_ATTEMPTS,
            ),
            connector_type,
            None,
        )

    if connector_type == SALESFORCE_CRM_CONNECTOR_TYPE:
        object_type = _text(
            verification.get("object_type"),
            verification.get("salesforce_object"),
            target.get("object_type"),
            target.get("salesforce_object"),
            target.get("resource_type"),
            claimed.get("object_type"),
            claimed.get("salesforce_object"),
            result.get("object_type"),
            result.get("salesforce_object"),
        ) or "Account"
        record_ref = _text(
            verification.get("record_ref"),
            verification.get("salesforce_id"),
            target.get("record_ref"),
            target.get("salesforce_id"),
            target.get("resource_ref"),
            claimed.get("record_ref"),
            claimed.get("salesforce_id"),
            claimed.get("Id"),
            result.get("record_ref"),
            result.get("salesforce_id"),
            result.get("provider_ref"),
        )
        if record_ref is None:
            return None, connector_type, "salesforce_record_ref_missing"
        bearer_token = decrypt_connector_bearer_token(config, project_id=intent.project_id)
        return (
            build_salesforce_crm_connector(
                config,
                object_type=object_type,
                record_ref=record_ref,
                bearer_token=bearer_token,
                timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
                max_attempts=settings.OUTCOME_CONNECTOR_MAX_ATTEMPTS,
            ),
            connector_type,
            None,
        )

    if connector_type == ZOHO_CRM_CONNECTOR_TYPE:
        module_name = _text(
            verification.get("module_name"),
            verification.get("zoho_module"),
            target.get("module_name"),
            target.get("zoho_module"),
            target.get("resource_type"),
            claimed.get("module_name"),
            claimed.get("zoho_module"),
            result.get("module_name"),
            result.get("zoho_module"),
        ) or "Contacts"
        record_ref = _text(
            verification.get("record_ref"),
            verification.get("zoho_record_id"),
            target.get("record_ref"),
            target.get("zoho_record_id"),
            target.get("resource_ref"),
            claimed.get("record_ref"),
            claimed.get("zoho_record_id"),
            claimed.get("id"),
            result.get("record_ref"),
            result.get("zoho_record_id"),
            result.get("provider_ref"),
        )
        if record_ref is None:
            return None, connector_type, "zoho_record_ref_missing"
        bearer_token = resolve_zoho_crm_bearer_token(
            config,
            project_id=intent.project_id,
            settings=settings,
        )
        return (
            build_zoho_crm_connector(
                config,
                module_name=module_name,
                record_ref=record_ref,
                bearer_token=bearer_token,
                timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
                max_attempts=settings.OUTCOME_CONNECTOR_MAX_ATTEMPTS,
            ),
            connector_type,
            None,
        )

    if connector_type == NETSUITE_FINANCE_CONNECTOR_TYPE:
        record_type = _text(
            verification.get("record_type"),
            verification.get("netsuite_record_type"),
            target.get("record_type"),
            target.get("netsuite_record_type"),
            target.get("resource_type"),
            claimed.get("record_type"),
            claimed.get("netsuite_record_type"),
            result.get("record_type"),
            result.get("netsuite_record_type"),
        ) or "vendorBill"
        record_ref = _text(
            verification.get("record_ref"),
            verification.get("netsuite_record_id"),
            target.get("record_ref"),
            target.get("netsuite_record_id"),
            target.get("resource_ref"),
            claimed.get("record_ref"),
            claimed.get("netsuite_record_id"),
            claimed.get("id"),
            result.get("record_ref"),
            result.get("netsuite_record_id"),
            result.get("provider_ref"),
        )
        if record_ref is None:
            return None, connector_type, "netsuite_record_ref_missing"
        bearer_token = decrypt_connector_bearer_token(
            config, project_id=intent.project_id
        )
        return (
            build_netsuite_finance_connector(
                config,
                record_type=record_type,
                record_ref=record_ref,
                bearer_token=bearer_token,
                timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
                max_attempts=settings.OUTCOME_CONNECTOR_MAX_ATTEMPTS,
            ),
            connector_type,
            None,
        )

    if connector_type == POSTGRES_READ_CONNECTOR_TYPE:
        if not config.read_query:
            return None, connector_type, "postgres_read_query_missing"
        database_url = decrypt_connector_database_url(config, project_id=intent.project_id)
        if not database_url:
            return None, connector_type, "postgres_database_url_missing"
        params = verification.get("params") if isinstance(verification.get("params"), Mapping) else result.get("params")
        return (
            build_postgres_read_connector(
                config,
                database_url=database_url,
                params=_as_dict(params),
                timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
                allow_private_hosts=settings.OUTCOME_CONNECTOR_ALLOW_PRIVATE_HOSTS,
            ),
            connector_type,
            None,
        )

    record_ref = _text(
        verification.get("record_ref"),
        target.get("record_ref"),
        target.get("resource_ref"),
        claimed.get("record_ref"),
        result.get("record_ref"),
        result.get("provider_ref"),
    )
    if record_ref is None:
        return None, GENERIC_REST_CONNECTOR_TYPE, "record_ref_missing"
    bearer_token = decrypt_connector_bearer_token(config, project_id=intent.project_id)
    return (
        build_generic_rest_connector(
            config,
            record_ref=record_ref,
            bearer_token=bearer_token,
            timeout_seconds=settings.OUTCOME_CONNECTOR_TIMEOUT_SECONDS,
            max_attempts=settings.OUTCOME_CONNECTOR_MAX_ATTEMPTS,
            allow_private_hosts=settings.OUTCOME_CONNECTOR_ALLOW_PRIVATE_HOSTS,
        ),
        GENERIC_REST_CONNECTOR_TYPE,
        None,
    )


def _run_verify_job(db: Session, job: ActionPostExecutionJob) -> dict[str, Any]:
    intent = db.execute(
        select(ActionIntent).where(ActionIntent.project_id == job.project_id, ActionIntent.id == job.action_intent_id)
    ).scalar_one()
    attempt = db.execute(
        select(ActionExecutionAttempt).where(
            ActionExecutionAttempt.project_id == job.project_id,
            ActionExecutionAttempt.id == job.execution_attempt_id,
        )
    ).scalar_one()
    context = _verification_context(intent, attempt)
    connector_type = _connector_alias(context.get("connector_type")) or GENERIC_REST_CONNECTOR_TYPE

    if attempt.status != "succeeded":
        outcome = _reconcile_not_verified(
            db,
            intent=intent,
            attempt=attempt,
            job=job,
            context=context,
            connector_type="action_execution_terminal",
            reason=f"execution_{attempt.status}",
        )
    else:
        try:
            connector, connector_type, missing_reason = _saved_connector_for_context(
                db=db,
                intent=intent,
                context=context,
            )
        except Exception as exc:  # noqa: BLE001
            connector = None
            missing_reason = exc.__class__.__name__
        if connector is None:
            outcome = _reconcile_not_verified(
                db,
                intent=intent,
                attempt=attempt,
                job=job,
                context=context,
                connector_type=connector_type,
                reason=missing_reason or "connector_unavailable",
            )
        else:
            trace = _as_dict(context.get("trace"))
            claimed = _as_dict(context.get("claimed"))
            metadata = _base_metadata(intent=intent, attempt=attempt, job=job, connector_type=connector_type)
            try:
                outcome = reconcile_outcome(
                    db,
                    project_id=intent.project_id,
                    claimed=claimed,
                    connector=connector,
                    call_id=_text(trace.get("call_id")),
                    trace_id=_text(trace.get("trace_id")),
                    runtime_policy_decision_id=intent.runtime_policy_decision_id,
                    action_type=intent.action_type,
                    system_ref=_text(context.get("system_ref"), _as_dict(context.get("verification")).get("system_ref"))
                    or f"{connector_type}:{intent.id}",
                    amount_usd=_float(claimed.get("amount_usd")),
                    currency=_text(claimed.get("currency")),
                    match_fields=_as_list(context.get("match_fields")),
                    idempotency_key=f"action-post-exec:{intent.id}:{attempt.id}:verify",
                    metadata=metadata,
                )
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                intent = db.execute(
                    select(ActionIntent).where(
                        ActionIntent.project_id == job.project_id,
                        ActionIntent.id == job.action_intent_id,
                    )
                ).scalar_one()
                attempt = db.execute(
                    select(ActionExecutionAttempt).where(
                        ActionExecutionAttempt.project_id == job.project_id,
                        ActionExecutionAttempt.id == job.execution_attempt_id,
                    )
                ).scalar_one()
                context = _verification_context(intent, attempt)
                outcome = _reconcile_not_verified(
                    db,
                    intent=intent,
                    attempt=attempt,
                    job=job,
                    context=context,
                    connector_type=connector_type,
                    reason=f"connector_exception:{exc.__class__.__name__}",
                )

    intent = db.execute(
        select(ActionIntent).where(ActionIntent.project_id == job.project_id, ActionIntent.id == job.action_intent_id)
    ).scalar_one()
    intent.proof_status = outcome.verdict
    intent.receipt_status = RECEIPT_PENDING
    db.add(intent)
    receipt_job = enqueue_action_post_execution_job(
        db,
        project_id=job.project_id,
        action_id=job.action_intent_id,
        attempt_id=job.execution_attempt_id,
        job_type=JOB_GENERATE_RECEIPT,
        payload={
            "trigger": "verification_completed",
            "outcome_reconciliation_id": outcome.id,
            "verdict": outcome.verdict,
        },
    )
    record_action_timeline_event(
        db,
        project_id=job.project_id,
        action_id=job.action_intent_id,
        event_type="verification_completed",
        payload={
            "job_id": job.id,
            "outcome_reconciliation_id": outcome.id,
            "verdict": outcome.verdict,
            "receipt_job_id": receipt_job.id,
        },
        actor=job.claimed_by,
    )
    return {
        "status": "verified",
        "outcome_reconciliation_id": outcome.id,
        "verdict": outcome.verdict,
        "receipt_job_id": receipt_job.id,
    }


def _resolve_verify_job_as_not_verified(
    db: Session,
    *,
    job: ActionPostExecutionJob,
    reason: str,
) -> dict[str, Any]:
    intent = db.execute(
        select(ActionIntent).where(ActionIntent.project_id == job.project_id, ActionIntent.id == job.action_intent_id)
    ).scalar_one()
    attempt = db.execute(
        select(ActionExecutionAttempt).where(
            ActionExecutionAttempt.project_id == job.project_id,
            ActionExecutionAttempt.id == job.execution_attempt_id,
        )
    ).scalar_one()
    context = _verification_context(intent, attempt)
    connector_type = _connector_alias(context.get("connector_type")) or GENERIC_REST_CONNECTOR_TYPE
    outcome = _reconcile_not_verified(
        db,
        intent=intent,
        attempt=attempt,
        job=job,
        context=context,
        connector_type=connector_type,
        reason=reason,
    )
    intent = db.execute(
        select(ActionIntent).where(ActionIntent.project_id == job.project_id, ActionIntent.id == job.action_intent_id)
    ).scalar_one()
    intent.proof_status = PROOF_NOT_VERIFIED
    intent.receipt_status = RECEIPT_PENDING
    db.add(intent)
    receipt_job = enqueue_action_post_execution_job(
        db,
        project_id=job.project_id,
        action_id=job.action_intent_id,
        attempt_id=job.execution_attempt_id,
        job_type=JOB_GENERATE_RECEIPT,
        payload={
            "trigger": "verification_dead_resolved_not_verified",
            "outcome_reconciliation_id": outcome.id,
            "verdict": outcome.verdict,
            "reason": reason,
        },
    )
    record_action_timeline_event(
        db,
        project_id=job.project_id,
        action_id=job.action_intent_id,
        event_type="verification_completed",
        payload={
            "job_id": job.id,
            "outcome_reconciliation_id": outcome.id,
            "verdict": outcome.verdict,
            "receipt_job_id": receipt_job.id,
            "reason": reason,
        },
        actor=job.claimed_by,
    )
    return {
        "status": "dead_resolved_not_verified",
        "outcome_reconciliation_id": outcome.id,
        "verdict": outcome.verdict,
        "receipt_job_id": receipt_job.id,
    }


def _run_receipt_job(db: Session, job: ActionPostExecutionJob) -> dict[str, Any]:
    generated = generate_action_receipt(
        db,
        project_id=job.project_id,
        action_id=job.action_intent_id,
        actor=job.claimed_by,
    )
    intent = db.execute(
        select(ActionIntent).where(ActionIntent.project_id == job.project_id, ActionIntent.id == job.action_intent_id)
    ).scalar_one()
    intent.receipt_status = RECEIPT_GENERATED
    db.add(intent)
    return {
        "status": "receipt_generated",
        "receipt_id": generated.row.id,
        "created": generated.created,
    }


def _mark_job_succeeded(db: Session, job: ActionPostExecutionJob, result: Mapping[str, Any]) -> ActionPostExecutionJob:
    current = _now()
    job.status = JOB_SUCCEEDED
    job.result_json = _json_dumps(result)
    job.error_message = None
    job.completed_at = current
    job.lease_expires_at = None
    job.updated_at = current
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _mark_job_failed(db: Session, job: ActionPostExecutionJob, exc: Exception) -> ActionPostExecutionJob:
    job_id = job.id
    db.rollback()
    job = db.execute(select(ActionPostExecutionJob).where(ActionPostExecutionJob.id == job_id)).scalar_one()
    current = _now()
    terminal = int(job.attempt_count or 0) >= int(job.max_attempts or DEFAULT_JOB_MAX_ATTEMPTS)
    job.status = JOB_DEAD if terminal else JOB_RETRYING
    job.error_message = str(exc)[:2000]
    job.available_at = current + timedelta(seconds=min(300, 2 ** max(0, int(job.attempt_count or 1))))
    job.lease_expires_at = None
    job.updated_at = current
    if terminal and job.job_type == JOB_GENERATE_RECEIPT:
        intent = db.execute(
            select(ActionIntent).where(ActionIntent.project_id == job.project_id, ActionIntent.id == job.action_intent_id)
        ).scalar_one_or_none()
        if intent is not None:
            intent.receipt_status = RECEIPT_FAILED
            db.add(intent)
    if terminal and job.job_type == JOB_VERIFY_OUTCOME:
        try:
            result = _resolve_verify_job_as_not_verified(
                db,
                job=job,
                reason=f"verify_job_dead:{exc.__class__.__name__}",
            )
            job = db.execute(select(ActionPostExecutionJob).where(ActionPostExecutionJob.id == job_id)).scalar_one()
            job.result_json = _json_dumps(result)
        except Exception as fallback_exc:  # noqa: BLE001
            job = db.execute(select(ActionPostExecutionJob).where(ActionPostExecutionJob.id == job_id)).scalar_one()
            job.error_message = f"{str(exc)[:1000]}; fail_closed_resolution_error={fallback_exc.__class__.__name__}:{str(fallback_exc)[:500]}"
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def process_action_post_execution_job(
    db: Session,
    *,
    job_id: str,
) -> ProcessedPostExecutionJob:
    job = db.execute(select(ActionPostExecutionJob).where(ActionPostExecutionJob.id == job_id)).scalar_one()
    try:
        if job.job_type == JOB_VERIFY_OUTCOME:
            result = _run_verify_job(db, job)
        elif job.job_type == JOB_GENERATE_RECEIPT:
            result = _run_receipt_job(db, job)
        else:
            raise ActionPostExecutionError(f"Unsupported post-execution job type: {job.job_type}.")
    except Exception as exc:  # noqa: BLE001
        failed = _mark_job_failed(db, job, exc)
        return ProcessedPostExecutionJob(failed, {"status": failed.status, "error": str(exc)})
    succeeded = _mark_job_succeeded(db, job, result)
    return ProcessedPostExecutionJob(succeeded, result)


def process_next_action_post_execution_job(
    db: Session,
    *,
    worker_id: str = "action-post-execution-worker",
    lease_seconds: int = DEFAULT_JOB_LEASE_SECONDS,
) -> ProcessedPostExecutionJob | None:
    job = _claim_next_job(db, worker_id=worker_id, lease_seconds=lease_seconds)
    if job is None:
        return None
    return process_action_post_execution_job(db, job_id=job.id)


def process_action_post_execution_jobs(
    db: Session,
    *,
    worker_id: str = "action-post-execution-worker",
    limit: int = 25,
) -> dict[str, Any]:
    processed: list[dict[str, Any]] = []
    for _ in range(max(1, int(limit))):
        item = process_next_action_post_execution_job(db, worker_id=worker_id)
        if item is None:
            break
        processed.append(
            {
                "job_id": item.job.id,
                "job_type": item.job.job_type,
                "status": item.job.status,
                "result": item.result,
            }
        )
    return {
        "processed": len(processed),
        "jobs": processed,
    }


def sweep_stale_execution_attempts(
    db: Session,
    *,
    stale_after_seconds: int = 600,
    limit: int = 50,
    actor: str = "action-stale-attempt-sweeper",
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or _now()
    cutoff = current - timedelta(seconds=max(1, int(stale_after_seconds)))
    rows = list(
        db.execute(
            select(ActionExecutionAttempt)
            .where(
                ActionExecutionAttempt.status.in_(("planned", "dispatched", "running")),
                ActionExecutionAttempt.updated_at <= cutoff,
            )
            .order_by(ActionExecutionAttempt.updated_at.asc(), ActionExecutionAttempt.created_at.asc())
            .limit(max(1, int(limit)))
            .with_for_update(skip_locked=True)
        ).scalars()
    )
    resolved: list[dict[str, Any]] = []
    if not rows:
        return {"resolved": 0, "attempts": resolved}

    from app.services.action_runner import finish_execution_attempt

    for attempt in rows:
        previous_status = attempt.status
        previous_updated_at = attempt.updated_at
        finish_execution_attempt(
            db,
            project_id=attempt.project_id,
            action_id=attempt.action_intent_id,
            attempt_id=attempt.id,
            final_status="ambiguous",
            result_summary={
                "stale_execution": {
                    "resolved_by": actor,
                    "previous_status": previous_status,
                    "stale_after_seconds": max(1, int(stale_after_seconds)),
                    "stale_cutoff": cutoff.isoformat(),
                    "last_updated_at": previous_updated_at.isoformat() if previous_updated_at is not None else None,
                }
            },
            error_message="Execution attempt timed out before runner reported a terminal status.",
            actor=actor,
        )
        resolved.append(
            {
                "execution_attempt_id": attempt.id,
                "action_intent_id": attempt.action_intent_id,
                "previous_status": previous_status,
            }
        )

    db.commit()
    return {
        "resolved": len(resolved),
        "attempts": resolved,
    }
