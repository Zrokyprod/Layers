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
        "proof_manifest": _as_dict(
            verification.get("proof_manifest") or verification.get("proof")
        ),
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


__all__ = [name for name in globals() if not name.startswith("__")]
