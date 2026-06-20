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

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.db.models import OutcomeReconciliationCheck


VERDICT_MATCHED = "matched"
VERDICT_MISMATCHED = "mismatched"
VERDICT_NOT_VERIFIED = "not_verified"
VALID_VERDICTS = frozenset({VERDICT_MATCHED, VERDICT_MISMATCHED, VERDICT_NOT_VERIFIED})

DEFAULT_MATCH_FIELDS = (
    "status",
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
    return [field for field in DEFAULT_MATCH_FIELDS if field in claimed_keys or field in actual_keys]


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


def reconcile_outcome(
    db: Session,
    *,
    project_id: str,
    claimed: Mapping[str, Any],
    connector: SystemOfRecordConnector,
    call_id: str | None = None,
    trace_id: str | None = None,
    runtime_policy_decision_id: str | None = None,
    action_type: str | None = None,
    system_ref: str | None = None,
    amount_usd: float | None = None,
    currency: str | None = None,
    match_fields: list[str] | None = None,
    idempotency_key: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    checked_at: datetime | None = None,
) -> OutcomeReconciliationCheck:
    if idempotency_key:
        existing = db.execute(
            select(OutcomeReconciliationCheck).where(
                OutcomeReconciliationCheck.project_id == project_id,
                OutcomeReconciliationCheck.idempotency_key == idempotency_key,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

    source = connector.fetch()
    comparison = compare_claim_to_actual(
        claimed=claimed,
        actual=source.record,
        actual_record_found=source.record_found,
        match_fields=match_fields,
    )
    metadata_payload = _as_dict(metadata)
    if match_fields:
        metadata_payload.setdefault("match_fields", match_fields)

    row = OutcomeReconciliationCheck(
        id=str(uuid4()),
        project_id=project_id,
        call_id=_bounded(call_id, max_length=64),
        trace_id=_bounded(trace_id, max_length=128),
        runtime_policy_decision_id=_bounded(runtime_policy_decision_id, max_length=36),
        action_type=_bounded(action_type, max_length=64),
        connector_type=_bounded(connector.connector_type, max_length=64) or "api_record",
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
        checked_at=checked_at or _now(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_reconciliations(
    db: Session,
    *,
    project_id: str,
    verdict: str | None = None,
    call_id: str | None = None,
    limit: int = 50,
) -> list[OutcomeReconciliationCheck]:
    query = select(OutcomeReconciliationCheck).where(
        OutcomeReconciliationCheck.project_id == project_id
    )
    if verdict:
        if verdict not in VALID_VERDICTS:
            raise ValueError(f"verdict must be one of: {', '.join(sorted(VALID_VERDICTS))}")
        query = query.where(OutcomeReconciliationCheck.verdict == verdict)
    if call_id:
        query = query.where(OutcomeReconciliationCheck.call_id == call_id)
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
        select(OutcomeReconciliationCheck.verdict, func.count(OutcomeReconciliationCheck.id))
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
    return ReconciliationSummary(
        window_days=days,
        total=matched + mismatched + not_verified,
        matched=matched,
        mismatched=mismatched,
        not_verified=not_verified,
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
        "system_ref": row.system_ref,
        "verdict": row.verdict,
        "reason": row.reason,
        "amount_usd": float(row.amount_usd) if row.amount_usd is not None else None,
        "currency": row.currency,
        "claimed": _json_loads(row.claimed_json, {}),
        "actual": _json_loads(row.actual_json, None),
        "comparison": _json_loads(row.comparison_json, {}),
        "idempotency_key": row.idempotency_key,
        "metadata": _json_loads(row.metadata_json, None),
        "checked_at": row.checked_at,
        "created_at": row.created_at,
    }
