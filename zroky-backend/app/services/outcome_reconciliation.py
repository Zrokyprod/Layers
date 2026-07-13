"""Outcome reconciliation against system-of-record evidence.

This is intentionally separate from ``outcome_attribution``. Attribution answers
"what did a failure cost?" Reconciliation answers "did the claimed real-world
action actually happen correctly?"
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol
from uuid import uuid4

from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from app.db.models import OutcomeReconciliationCheck
from app.services.proof_connector_manifest import (
    PROOF_MATCHED,
    PROOF_MISMATCHED,
    PROOF_PARTIAL,
    PROOF_PENDING,
    PROOF_UNVERIFIABLE,
    evaluate_proof_manifest,
    proof_status_from_metadata,
    proof_status_to_outcome_verdict,
    public_manifest_summary,
)
from app.services.protected_action_billing import (
    METER_VERIFICATION_CHECKS,
    reserve_usage_meter,
)


VERDICT_MATCHED = "matched"
VERDICT_MISMATCHED = "mismatched"
VERDICT_NOT_VERIFIED = "not_verified"
VALID_VERDICTS = frozenset({VERDICT_MATCHED, VERDICT_MISMATCHED, VERDICT_NOT_VERIFIED})

VERIFICATION_VERIFIED = "verified"
VERIFICATION_MATCHED = "matched"
VERIFICATION_MISMATCHED = "mismatched"
VERIFICATION_PENDING = "pending"
VERIFICATION_UNVERIFIABLE = "unverifiable"
VERIFICATION_PARTIAL = PROOF_PARTIAL
VERIFICATION_CANCELLED = "cancelled"
VALID_VERIFICATION_STATUSES = frozenset(
    {
        VERIFICATION_VERIFIED,
        VERIFICATION_MATCHED,
        VERIFICATION_MISMATCHED,
        VERIFICATION_PENDING,
        VERIFICATION_UNVERIFIABLE,
        VERIFICATION_PARTIAL,
        VERIFICATION_CANCELLED,
    }
)

PROOF_REASON_NO_CONNECTOR = "no_connector"
PROOF_REASON_RUNNER_OFFLINE = "runner_offline"
PROOF_REASON_NO_SOR_TRACE = "no_sor_trace"
PROOF_REASON_SOR_UNREACHABLE = "sor_unreachable"
PROOF_REASON_FIELD_MISMATCH = "field_mismatch"
PROOF_REASON_REQUIRED_EVIDENCE_MISSING = "required_evidence_missing"

_PENDING_EXPIRE_AS_UNVERIFIABLE = {
    PROOF_REASON_SOR_UNREACHABLE,
    PROOF_REASON_NO_CONNECTOR,
    PROOF_REASON_RUNNER_OFFLINE,
}

DEFAULT_MATCH_FIELDS = (
    "status",
    "amount_minor",
    "amount_major",
    "amount",
    "amount_usd",
    "currency",
    "customer_id",
    "account_id",
    "order_id",
    "invoice_id",
    "payment_id",
    "refund_id",
    "recipient_id",
    "email",
    "email_status",
    "ledger_entry_id",
)


@dataclass(frozen=True)
class SourceRecord:
    record: dict[str, Any] | None
    record_found: bool | None = None
    metadata: dict[str, Any] | None = None


class SystemOfRecordConnector(Protocol):
    connector_type: str

    def fetch(self) -> SourceRecord:
        """Return the source-of-record row used for reconciliation."""


@dataclass(frozen=True)
class ApiRecordConnector:
    """Connector for customer-supplied source-of-record records.

    This is not a synthetic verifier: the caller must supply the actual row read
    from their ledger/CRM/DB/email provider, and the check remains
    ``not_verified`` when that evidence is absent.
    """

    record: dict[str, Any] | None
    record_found: bool | None = None
    connector_type: str = "api_record"

    def fetch(self) -> SourceRecord:
        return SourceRecord(record=self.record, record_found=self.record_found)


@dataclass(frozen=True)
class ReconciliationComparison:
    verdict: str
    reason: str
    compared_fields: list[dict[str, Any]]
    mismatches: list[dict[str, Any]]
    missing_fields: list[str]

    def to_json(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "reason": self.reason,
            "compared_fields": self.compared_fields,
            "mismatches": self.mismatches,
            "missing_fields": self.missing_fields,
        }


@dataclass(frozen=True)
class ReconciliationSummary:
    window_days: int
    total: int
    matched: int
    mismatched: int
    not_verified: int
    verified: int = 0
    pending: int = 0
    unverifiable: int = 0
    partial: int = 0
    cancelled: int = 0


@dataclass(frozen=True)
class PendingProofSweepResult:
    expired: int
    due_for_reverify: int
    expired_check_ids: list[str]
    due_check_ids: list[str]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, default=str)


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _bounded(value: str | None, *, max_length: int) -> str | None:
    if value is None:
        return None
    rendered = str(value).strip()
    if not rendered:
        return None
    return rendered[:max_length]


def _as_dict(value: Mapping[str, Any] | dict[str, Any] | None) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _flatten(record: Mapping[str, Any], *, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for raw_key, value in record.items():
        key = str(raw_key)
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, Mapping):
            out.update(_flatten(value, prefix=path))
        else:
            out[path] = value
    return out


def _field_value(record: Mapping[str, Any], field: str) -> tuple[bool, Any]:
    if not field:
        return False, None
    current: Any = record
    for part in field.split("."):
        if not isinstance(current, Mapping) or part not in current:
            break
        current = current[part]
    else:
        return True, current

    flattened = _flatten(record)
    for path, value in flattened.items():
        if path.split(".")[-1] == field:
            return True, value
    return False, None


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _values_equal(claimed: Any, actual: Any) -> bool:
    claimed_decimal = _decimal(claimed)
    actual_decimal = _decimal(actual)
    if claimed_decimal is not None and actual_decimal is not None:
        return claimed_decimal == actual_decimal
    return str(claimed).strip().lower() == str(actual).strip().lower()


def _default_fields(claimed: Mapping[str, Any], actual: Mapping[str, Any]) -> list[str]:
    claimed_keys = {path.split(".")[-1] for path in _flatten(claimed)}
    actual_keys = {path.split(".")[-1] for path in _flatten(actual)}
    return [
        field
        for field in DEFAULT_MATCH_FIELDS
        if field in claimed_keys or field in actual_keys
    ]


def compare_claim_to_actual(
    *,
    claimed: Mapping[str, Any],
    actual: Mapping[str, Any] | None,
    actual_record_found: bool | None = None,
    match_fields: list[str] | None = None,
) -> ReconciliationComparison:
    claimed_dict = _as_dict(claimed)
    actual_dict = _as_dict(actual)

    if actual_record_found is False:
        return ReconciliationComparison(
            verdict=VERDICT_MISMATCHED,
            reason="system_of_record_record_missing",
            compared_fields=[],
            mismatches=[],
            missing_fields=[],
        )
    if not actual_dict:
        return ReconciliationComparison(
            verdict=VERDICT_NOT_VERIFIED,
            reason="system_of_record_missing",
            compared_fields=[],
            mismatches=[],
            missing_fields=[],
        )

    fields = [field.strip() for field in (match_fields or []) if field.strip()]
    if not fields:
        fields = _default_fields(claimed_dict, actual_dict)
    if not fields:
        return ReconciliationComparison(
            verdict=VERDICT_NOT_VERIFIED,
            reason="no_comparable_fields",
            compared_fields=[],
            mismatches=[],
            missing_fields=[],
        )

    compared: list[dict[str, Any]] = []
    mismatches: list[dict[str, Any]] = []
    missing: list[str] = []
    for field in fields:
        claimed_present, claimed_value = _field_value(claimed_dict, field)
        actual_present, actual_value = _field_value(actual_dict, field)
        if not claimed_present or not actual_present:
            missing.append(field)
            continue
        matched = _values_equal(claimed_value, actual_value)
        row = {
            "field": field,
            "claimed": claimed_value,
            "actual": actual_value,
            "matched": matched,
        }
        compared.append(row)
        if not matched:
            mismatches.append(row)

    if mismatches:
        return ReconciliationComparison(
            verdict=VERDICT_MISMATCHED,
            reason="field_mismatch",
            compared_fields=compared,
            mismatches=mismatches,
            missing_fields=missing,
        )
    if missing or not compared:
        return ReconciliationComparison(
            verdict=VERDICT_NOT_VERIFIED,
            reason="actual_fields_missing" if missing else "no_comparable_fields",
            compared_fields=compared,
            mismatches=[],
            missing_fields=missing,
        )
    return ReconciliationComparison(
        verdict=VERDICT_MATCHED,
        reason="all_compared_fields_matched",
        compared_fields=compared,
        mismatches=[],
        missing_fields=[],
    )


def _connector_retryable(metadata: Mapping[str, Any] | None) -> bool:
    connector = _as_dict(metadata)
    retryable = connector.get("retryable")
    if retryable is True:
        return True
    try:
        status_code = int(connector.get("http_status"))
    except (TypeError, ValueError):
        return False
    return status_code >= 500


def _legacy_proof_status(
    *,
    comparison: ReconciliationComparison,
    metadata_payload: Mapping[str, Any],
) -> str:
    if comparison.verdict == VERDICT_MATCHED:
        return PROOF_MATCHED
    if comparison.verdict == VERDICT_MISMATCHED:
        return PROOF_MISMATCHED
    connector_metadata = _as_dict(metadata_payload.get("connector"))
    if _connector_retryable(connector_metadata):
        return PROOF_PENDING
    return PROOF_UNVERIFIABLE


def _legacy_proof_reason_code(
    *,
    comparison: ReconciliationComparison,
    source: SourceRecord,
    metadata_payload: Mapping[str, Any],
) -> str:
    not_verified_reason = _bounded(
        str(metadata_payload.get("not_verified_reason") or ""),
        max_length=255,
    )
    if not_verified_reason == "connector_not_configured":
        return PROOF_REASON_NO_CONNECTOR
    if not_verified_reason and not_verified_reason.startswith("execution_"):
        return PROOF_REASON_RUNNER_OFFLINE
    connector_metadata = _as_dict(metadata_payload.get("connector"))
    if _connector_retryable(connector_metadata):
        return PROOF_REASON_SOR_UNREACHABLE
    error_code = str(connector_metadata.get("error_code") or "").strip()
    if error_code and error_code != "system_record_missing":
        return PROOF_REASON_SOR_UNREACHABLE
    if source.record_found is False or comparison.reason == "system_of_record_record_missing":
        return PROOF_REASON_NO_SOR_TRACE
    if comparison.reason == "field_mismatch":
        return PROOF_REASON_FIELD_MISMATCH
    if comparison.reason in {"actual_fields_missing", "no_comparable_fields"}:
        return PROOF_REASON_REQUIRED_EVIDENCE_MISSING
    return _bounded(comparison.reason or comparison.verdict, max_length=64) or "unknown"


def _proof_status_for_display(
    *,
    row: OutcomeReconciliationCheck,
    metadata: Mapping[str, Any],
) -> str | None:
    row_status = _bounded(row.proof_status, max_length=32)
    if row_status:
        proof = _as_dict(metadata.get("proof"))
        if row_status == PROOF_MATCHED and not proof:
            return VERIFICATION_VERIFIED
        return row_status
    return proof_status_from_metadata(metadata)


def proof_status_for_check(row: OutcomeReconciliationCheck) -> str:
    metadata = _json_loads(row.metadata_json, {}) or {}
    if not isinstance(metadata, Mapping):
        metadata = {}
    row_status = _bounded(row.proof_status, max_length=32)
    if row_status:
        return row_status
    metadata_status = proof_status_from_metadata(metadata)
    if metadata_status:
        return metadata_status
    if row.verdict == VERDICT_MATCHED:
        return PROOF_MATCHED
    if row.verdict == VERDICT_MISMATCHED:
        return PROOF_MISMATCHED
    if row.verdict == VERDICT_NOT_VERIFIED:
        connector = _as_dict(metadata.get("connector"))
        if _connector_retryable(connector):
            return PROOF_PENDING
        return PROOF_UNVERIFIABLE
    return PROOF_UNVERIFIABLE


def intent_proof_status_for_check(row: OutcomeReconciliationCheck) -> str:
    status = proof_status_for_check(row)
    if status == PROOF_MATCHED:
        return VERDICT_MATCHED
    if status in {PROOF_MISMATCHED, PROOF_PARTIAL}:
        return VERDICT_MISMATCHED
    if status == PROOF_PENDING:
        return PROOF_PENDING
    return VERDICT_NOT_VERIFIED


def proof_reason_code_for_check(row: OutcomeReconciliationCheck) -> str | None:
    reason = _bounded(row.proof_reason_code, max_length=64)
    if reason:
        return reason
    metadata = _json_loads(row.metadata_json, {}) or {}
    if isinstance(metadata, Mapping):
        proof = _as_dict(metadata.get("proof"))
        reason = _bounded(str(proof.get("reason") or ""), max_length=64)
        if reason:
            return reason
    return _bounded(row.reason, max_length=64)


def reconcile_outcome(
    db: Session,
    *,
    project_id: str,
    claimed: Mapping[str, Any],
    connector: SystemOfRecordConnector,
    call_id: str | None = None,
    trace_id: str | None = None,
    runtime_policy_decision_id: str | None = None,
    action_intent_id: str | None = None,
    action_type: str | None = None,
    system_ref: str | None = None,
    amount_usd: float | None = None,
    currency: str | None = None,
    match_fields: list[str] | None = None,
    idempotency_key: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    proof_manifest: Mapping[str, Any] | None = None,
    checked_at: datetime | None = None,
) -> OutcomeReconciliationCheck:
    checked_time = checked_at or _now()
    if idempotency_key:
        existing = db.execute(
            select(OutcomeReconciliationCheck).where(
                OutcomeReconciliationCheck.project_id == project_id,
                OutcomeReconciliationCheck.idempotency_key == idempotency_key,
            )
        ).scalar_one_or_none()
        if existing is not None:
            if action_intent_id and existing.action_intent_id is None:
                existing.action_intent_id = _bounded(action_intent_id, max_length=36)
                db.add(existing)
                db.commit()
                db.refresh(existing)
            from app.services.outcome_mismatch_response import create_or_get_mismatch_response

            create_or_get_mismatch_response(
                db,
                check=existing,
                action_intent_id=action_intent_id,
            )
            return existing

    reserve_usage_meter(db, project_id, METER_VERIFICATION_CHECKS)
    source = connector.fetch()
    metadata_payload = _as_dict(metadata)
    if source.metadata:
        metadata_payload.setdefault("connector", _as_dict(source.metadata))
    if match_fields:
        metadata_payload.setdefault("match_fields", match_fields)
    proof_status: str
    proof_reason_code: str
    proof_observed_at: datetime | None = None
    proof_deadline_at: datetime | None = None
    proof_next_check_at: datetime | None = None
    if proof_manifest:
        proof = evaluate_proof_manifest(
            claimed=claimed,
            actual=source.record,
            actual_record_found=source.record_found,
            connector_metadata=source.metadata,
            manifest=proof_manifest,
            checked_at=checked_time,
        )
        comparison = ReconciliationComparison(
            verdict=proof_status_to_outcome_verdict(proof.status),
            reason=proof.reason,
            compared_fields=[field.to_json() for field in proof.fields],
            mismatches=proof.mismatches,
            missing_fields=proof.missing_fields,
        )
        metadata_payload.setdefault("proof", proof.to_json())
        manifest_summary = public_manifest_summary(proof_manifest)
        if manifest_summary:
            metadata_payload.setdefault("proof_manifest", manifest_summary)
        proof_status = proof.status
        proof_reason_code = proof.reason_code
        proof_observed_at = proof.observed_at
        proof_deadline_at = proof.deadline_at
        proof_next_check_at = proof.next_check_at if proof.status == PROOF_PENDING else None
    else:
        comparison = compare_claim_to_actual(
            claimed=claimed,
            actual=source.record,
            actual_record_found=source.record_found,
            match_fields=match_fields,
        )
        proof_status = _legacy_proof_status(
            comparison=comparison,
            metadata_payload=metadata_payload,
        )
        proof_reason_code = _legacy_proof_reason_code(
            comparison=comparison,
            source=source,
            metadata_payload=metadata_payload,
        )
        if metadata_payload.get("cancelled") is True or str(metadata_payload.get("status") or "").strip().lower() == "cancelled":
            proof_status = VERIFICATION_CANCELLED
            proof_reason_code = "cancelled"

    row = OutcomeReconciliationCheck(
        id=str(uuid4()),
        project_id=project_id,
        call_id=_bounded(call_id, max_length=64),
        trace_id=_bounded(trace_id, max_length=128),
        runtime_policy_decision_id=_bounded(runtime_policy_decision_id, max_length=36),
        action_intent_id=_bounded(action_intent_id, max_length=36),
        action_type=_bounded(action_type, max_length=64),
        connector_type=_bounded(connector.connector_type, max_length=64)
        or "api_record",
        system_ref=_bounded(system_ref, max_length=255),
        verdict=comparison.verdict,
        reason=_bounded(comparison.reason, max_length=255),
        amount_usd=amount_usd,
        currency=_bounded(currency, max_length=3),
        claimed_json=_json_dumps(_as_dict(claimed)),
        actual_json=_json_dumps(source.record) if source.record is not None else None,
        comparison_json=_json_dumps(comparison.to_json()),
        idempotency_key=_bounded(idempotency_key, max_length=255),
        metadata_json=_json_dumps(metadata_payload) if metadata_payload else None,
        proof_status=_bounded(proof_status, max_length=32),
        proof_reason_code=_bounded(proof_reason_code, max_length=64),
        proof_observed_at=proof_observed_at,
        proof_deadline_at=proof_deadline_at,
        proof_next_check_at=proof_next_check_at,
        checked_at=checked_time,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    from app.services.outcome_mismatch_response import create_or_get_mismatch_response

    create_or_get_mismatch_response(
        db,
        check=row,
        action_intent_id=action_intent_id,
    )
    return row


def list_reconciliations(
    db: Session,
    *,
    project_id: str,
    verdict: str | None = None,
    call_id: str | None = None,
    since: datetime | None = None,
    limit: int = 50,
) -> list[OutcomeReconciliationCheck]:
    query = select(OutcomeReconciliationCheck).where(
        OutcomeReconciliationCheck.project_id == project_id
    )
    if verdict:
        if verdict not in VALID_VERDICTS:
            raise ValueError(
                f"verdict must be one of: {', '.join(sorted(VALID_VERDICTS))}"
            )
        query = query.where(OutcomeReconciliationCheck.verdict == verdict)
    if call_id:
        query = query.where(OutcomeReconciliationCheck.call_id == call_id)
    if since:
        query = query.where(OutcomeReconciliationCheck.checked_at >= since)
    return list(
        db.execute(
            query.order_by(
                desc(OutcomeReconciliationCheck.checked_at),
                desc(OutcomeReconciliationCheck.id),
            ).limit(limit)
        ).scalars()
    )


def get_reconciliation(
    db: Session,
    *,
    project_id: str,
    check_id: str,
) -> OutcomeReconciliationCheck | None:
    return db.execute(
        select(OutcomeReconciliationCheck).where(
            OutcomeReconciliationCheck.project_id == project_id,
            OutcomeReconciliationCheck.id == check_id,
        )
    ).scalar_one_or_none()


def get_reconciliation_summary(
    db: Session,
    *,
    project_id: str,
    days: int = 30,
) -> ReconciliationSummary:
    since = _now() - timedelta(days=days)
    rows = db.execute(
        select(
            OutcomeReconciliationCheck.verdict,
            func.count(OutcomeReconciliationCheck.id),
        )
        .where(
            OutcomeReconciliationCheck.project_id == project_id,
            OutcomeReconciliationCheck.checked_at >= since,
        )
        .group_by(OutcomeReconciliationCheck.verdict)
    ).all()
    counts = {verdict: int(count or 0) for verdict, count in rows}
    matched = counts.get(VERDICT_MATCHED, 0)
    mismatched = counts.get(VERDICT_MISMATCHED, 0)
    not_verified = counts.get(VERDICT_NOT_VERIFIED, 0)
    proof_rows = db.execute(
        select(
            OutcomeReconciliationCheck.proof_status,
            func.count(OutcomeReconciliationCheck.id),
        )
        .where(
            OutcomeReconciliationCheck.project_id == project_id,
            OutcomeReconciliationCheck.checked_at >= since,
        )
        .group_by(OutcomeReconciliationCheck.proof_status)
    ).all()
    verification_counts = {
        status: 0
        for status in VALID_VERIFICATION_STATUSES
    }
    for raw_status, count in proof_rows:
        status = _bounded(raw_status, max_length=32)
        if status in verification_counts:
            verification_counts[status] += int(count or 0)
    legacy_matched_without_column = db.execute(
        select(func.count(OutcomeReconciliationCheck.id)).where(
            OutcomeReconciliationCheck.project_id == project_id,
            OutcomeReconciliationCheck.checked_at >= since,
            OutcomeReconciliationCheck.proof_status.is_(None),
            OutcomeReconciliationCheck.verdict == VERDICT_MATCHED,
        )
    ).scalar_one()
    verification_counts[VERIFICATION_VERIFIED] += int(legacy_matched_without_column or 0)
    return ReconciliationSummary(
        window_days=days,
        total=matched + mismatched + not_verified,
        matched=matched,
        mismatched=mismatched,
        not_verified=not_verified,
        verified=verification_counts[VERIFICATION_VERIFIED]
        + verification_counts[VERIFICATION_MATCHED],
        pending=verification_counts[VERIFICATION_PENDING],
        unverifiable=verification_counts[VERIFICATION_UNVERIFIABLE],
        partial=verification_counts[VERIFICATION_PARTIAL],
        cancelled=verification_counts[VERIFICATION_CANCELLED],
    )


def verification_status_for_check(row: OutcomeReconciliationCheck) -> str:
    metadata = _json_loads(row.metadata_json, {}) or {}
    if isinstance(metadata, Mapping):
        proof_status = _proof_status_for_display(row=row, metadata=metadata)
        if proof_status is not None:
            return proof_status
        proof_status = proof_status_from_metadata(metadata)
        if proof_status is not None:
            return proof_status
        if metadata.get("cancelled") is True or str(metadata.get("status") or "").strip().lower() == "cancelled":
            return VERIFICATION_CANCELLED
        connector = metadata.get("connector")
        if isinstance(connector, Mapping):
            status_code = connector.get("http_status")
            retryable = connector.get("retryable")
            try:
                status_code_int = int(status_code)
            except (TypeError, ValueError):
                status_code_int = None
            if retryable is True or (status_code_int is not None and status_code_int >= 500):
                return VERIFICATION_PENDING

    if row.verdict == VERDICT_MATCHED:
        return VERIFICATION_VERIFIED
    if row.verdict == VERDICT_MISMATCHED:
        return VERIFICATION_MISMATCHED
    if row.verdict == VERDICT_NOT_VERIFIED:
        if row.reason in {"system_of_record_missing", "actual_fields_missing", "no_comparable_fields"}:
            return VERIFICATION_UNVERIFIABLE
        return VERIFICATION_PENDING
    return VERIFICATION_UNVERIFIABLE


REVERIFY_CONNECTORS = {
    "customer_record_api",
    "generic_rest_api",
    "hubspot_crm",
    "jira_issue",
    "ledger_refund_api",
    "netsuite_finance",
    "postgres_read",
    "razorpay_refund",
    "salesforce_crm",
    "stripe_refund",
    "zendesk_ticket",
    "zoho_crm",
}


def reverify_connector_for_check(row: OutcomeReconciliationCheck) -> str | None:
    connector_type = (row.connector_type or "").strip().lower()
    return connector_type if connector_type in REVERIFY_CONNECTORS else None


def list_pending_reconciliations_due(
    db: Session,
    *,
    project_id: str | None = None,
    now: datetime | None = None,
    limit: int = 100,
) -> list[OutcomeReconciliationCheck]:
    current = now or _now()
    query = select(OutcomeReconciliationCheck).where(
        OutcomeReconciliationCheck.proof_status == PROOF_PENDING,
        OutcomeReconciliationCheck.proof_next_check_at.is_not(None),
        OutcomeReconciliationCheck.proof_next_check_at <= current,
        OutcomeReconciliationCheck.connector_type.in_(REVERIFY_CONNECTORS),
        or_(
            OutcomeReconciliationCheck.proof_deadline_at.is_(None),
            OutcomeReconciliationCheck.proof_deadline_at >= current,
        ),
    )
    if project_id:
        query = query.where(OutcomeReconciliationCheck.project_id == project_id)
    return list(
        db.execute(
            query.order_by(
                OutcomeReconciliationCheck.proof_next_check_at,
                OutcomeReconciliationCheck.id,
            ).limit(max(1, min(limit, 1000)))
        ).scalars()
    )


def sweep_pending_reconciliation_checks(
    db: Session,
    *,
    project_id: str | None = None,
    now: datetime | None = None,
    limit: int = 100,
) -> PendingProofSweepResult:
    current = now or _now()
    expired_query = select(OutcomeReconciliationCheck).where(
        OutcomeReconciliationCheck.proof_status == PROOF_PENDING,
        OutcomeReconciliationCheck.proof_deadline_at.is_not(None),
        OutcomeReconciliationCheck.proof_deadline_at < current,
    )
    if project_id:
        expired_query = expired_query.where(OutcomeReconciliationCheck.project_id == project_id)
    expired_rows = list(
        db.execute(
            expired_query.order_by(
                OutcomeReconciliationCheck.proof_deadline_at,
                OutcomeReconciliationCheck.id,
            ).limit(max(1, min(limit, 1000)))
        ).scalars()
    )

    expired_ids: list[str] = []
    for row in expired_rows:
        reason = proof_reason_code_for_check(row) or PROOF_REASON_NO_SOR_TRACE
        if reason in _PENDING_EXPIRE_AS_UNVERIFIABLE:
            row.proof_status = PROOF_UNVERIFIABLE
            row.verdict = VERDICT_NOT_VERIFIED
            row.reason = _bounded(reason, max_length=255)
        else:
            row.proof_status = PROOF_MISMATCHED
            row.verdict = VERDICT_MISMATCHED
            row.reason = _bounded(reason, max_length=255)
        row.proof_reason_code = _bounded(reason, max_length=64)
        row.proof_next_check_at = None
        row.checked_at = current
        metadata = _json_loads(row.metadata_json, {}) or {}
        if not isinstance(metadata, Mapping):
            metadata = {}
        metadata_payload = dict(metadata)
        proof = _as_dict(metadata_payload.get("proof"))
        proof.update(
            {
                "status": row.proof_status,
                "reason": reason,
                "next_check_at": None,
                "resolved_at": current.isoformat(),
                "point_in_time": True,
            }
        )
        metadata_payload["proof"] = proof
        row.metadata_json = _json_dumps(metadata_payload)
        db.add(row)
        expired_ids.append(row.id)
    if expired_ids:
        db.commit()
        from app.services.outcome_mismatch_response import create_or_get_mismatch_response

        for row in expired_rows:
            create_or_get_mismatch_response(
                db,
                check=row,
                action_intent_id=row.action_intent_id,
            )

    due_rows = list_pending_reconciliations_due(
        db,
        project_id=project_id,
        now=current,
        limit=limit,
    )
    return PendingProofSweepResult(
        expired=len(expired_ids),
        due_for_reverify=len(due_rows),
        expired_check_ids=expired_ids,
        due_check_ids=[row.id for row in due_rows],
    )


def reconciliation_to_dict(row: OutcomeReconciliationCheck) -> dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "call_id": row.call_id,
        "trace_id": row.trace_id,
        "runtime_policy_decision_id": row.runtime_policy_decision_id,
        "action_type": row.action_type,
        "connector_type": row.connector_type,
        "reverify_connector": reverify_connector_for_check(row),
        "system_ref": row.system_ref,
        "verdict": row.verdict,
        "verification_status": verification_status_for_check(row),
        "proof_status": proof_status_for_check(row),
        "proof_reason_code": proof_reason_code_for_check(row),
        "reason": row.reason,
        "amount_usd": float(row.amount_usd) if row.amount_usd is not None else None,
        "currency": row.currency,
        "claimed": _json_loads(row.claimed_json, {}),
        "actual": _json_loads(row.actual_json, None),
        "comparison": _json_loads(row.comparison_json, {}),
        "idempotency_key": row.idempotency_key,
        "metadata": _json_loads(row.metadata_json, None),
        "proof_observed_at": row.proof_observed_at,
        "proof_deadline_at": row.proof_deadline_at,
        "proof_next_check_at": row.proof_next_check_at,
        "checked_at": row.checked_at,
        "created_at": row.created_at,
    }
