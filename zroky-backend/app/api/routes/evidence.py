from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote, urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import ROLE_RANK
from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.core.limiter import limiter
from app.db.models import ActionIntent, OutcomeReconciliationCheck, RuntimePolicyDecision
from app.db.session import get_db_session
from app.schemas.evidence import (
    EvidenceManifestFilter,
    EvidenceLedgerCounts,
    EvidenceLedgerRecord,
    EvidenceLedgerResponse,
    EvidenceManifestRecord,
    EvidenceManifestResponse,
    EvidenceManifestScope,
    EvidenceManifestVerification,
)
from app.services.action_receipts import action_receipt_public_key_payload

router = APIRouter(prefix="/v1/evidence", tags=["evidence"])


@dataclass(frozen=True)
class _LedgerRow:
    action_id: str | None
    action_type: str
    agent_name: str
    call_id: str | None
    checked_at: datetime | None
    decision_id: str | None
    digest: str | None
    export_kind: str | None
    exportable: bool
    href_path: str
    id: str
    kind: str
    outcome_id: str | None
    source_label: str
    status: str
    system_ref: str | None
    title: str
    trace_id: str | None
    detail: str
    search_text: str


def _require_viewer(context: TenantContext) -> None:
    if ROLE_RANK[context.role] < ROLE_RANK["viewer"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Tenant role '{context.role}' does not allow this action.",
        )


def _loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _humanize(value: str | None) -> str:
    text = (value or "proof record").replace("_", " ").replace(".", " ").replace("-", " ").strip()
    return " ".join(part.capitalize() for part in text.split()) or "Proof Record"


def _row_status_for_intent(intent: ActionIntent) -> str:
    if intent.status in {"blocked", "denied", "rejected", "expired", "cancelled"}:
        return intent.status
    if intent.proof_status in {"mismatched", "not_verified"}:
        return intent.proof_status
    if intent.proof_status == "matched" and intent.receipt_status == "generated":
        return "matched"
    if intent.receipt_status in {"missing", "failed"}:
        return intent.receipt_status
    if intent.proof_status == "pending" or intent.receipt_status == "pending":
        return "pending"
    return intent.proof_status or intent.receipt_status or intent.status or "not_verified"


def _row_status_for_decision(decision: RuntimePolicyDecision, outcome: OutcomeReconciliationCheck | None) -> str:
    if outcome is not None and outcome.verdict:
        return outcome.verdict
    if decision.status in {"blocked", "denied", "rejected", "expired", "failed"}:
        return decision.status
    return "not_verified"


def _needs_verification(status_value: str) -> bool:
    return status_value in {"missing", "not_started", "not_verified", "pending"}


def _is_exception(status_value: str) -> bool:
    return status_value in {"mismatched", "failed", "signature_invalid"}


def _in_day_window(row: _LedgerRow, days: int, now: datetime) -> bool:
    if row.checked_at is None:
        return False
    checked_at = row.checked_at
    if checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=timezone.utc)
    return checked_at >= now - timedelta(days=days)


def _latest_by_date(items: list[OutcomeReconciliationCheck]) -> OutcomeReconciliationCheck | None:
    latest: OutcomeReconciliationCheck | None = None
    latest_time: datetime | None = None
    for item in items:
        current = item.checked_at or item.created_at
        if latest is None or (current is not None and (latest_time is None or current > latest_time)):
            latest = item
            latest_time = current
    return latest


def _dashboard_origin(request: Request, dashboard_origin: str | None) -> str:
    candidate = (dashboard_origin or request.headers.get("origin") or "").strip().rstrip("/")
    if not candidate:
        return ""
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def _absolute_href(origin: str, path: str) -> str:
    return f"{origin}{path}" if origin else path


def _in_date_scope(row: _LedgerRow, start_date: date | None, end_date: date | None) -> bool:
    if start_date is None and end_date is None:
        return True
    if row.checked_at is None:
        return False
    checked_date = row.checked_at.date()
    if start_date is not None and checked_date < start_date:
        return False
    return not (end_date is not None and checked_date > end_date)


def _matches_filter(row: _LedgerRow, filter_value: EvidenceManifestFilter) -> bool:
    if filter_value == "all":
        return True
    if filter_value == "matched":
        return row.status == "matched"
    if filter_value == "needs_verification":
        return _needs_verification(row.status)
    return _is_exception(row.status)


def _matches_search(row: _LedgerRow, search: str) -> bool:
    needle = search.strip().lower()
    if not needle:
        return True
    return needle in row.search_text.lower()


def _trace_context_for_intent(intent: ActionIntent) -> dict[str, Any]:
    canonical = _record(_loads(intent.canonical_intent_json, {}))
    return _record(canonical.get("trace_context"))


def _agent_name_for_intent(intent: ActionIntent) -> str:
    canonical = _record(_loads(intent.canonical_intent_json, {}))
    trace_context = _record(canonical.get("trace_context"))
    principal = _record(_loads(intent.principal_json, {}))
    return _string(trace_context.get("agent_name")) or _string(principal.get("id")) or "Protected agent"


def _title_for_intent(intent: ActionIntent) -> str:
    canonical = _record(_loads(intent.canonical_intent_json, {}))
    for value in (
        _record(canonical.get("summary")).get("title"),
        canonical.get("summary"),
        _record(canonical.get("purpose")).get("summary"),
        _record(canonical.get("resource")).get("label"),
    ):
        text = _string(value)
        if text:
            return text
    return _humanize(intent.action_type)


def _title_for_decision(decision: RuntimePolicyDecision) -> str:
    intended_action = _record(_loads(decision.intended_action_json, {}))
    for value in (intended_action.get("summary"), decision.tool_name, decision.action_type, decision.id):
        text = _string(value)
        if text:
            return text
    return "Guard-only action"


def _build_search_text(values: list[Any]) -> str:
    return " ".join(str(value) for value in values if value is not None)


def _build_manifest_rows(
    *,
    actions: list[ActionIntent],
    decisions: list[RuntimePolicyDecision],
    outcomes: list[OutcomeReconciliationCheck],
) -> list[_LedgerRow]:
    rows: list[_LedgerRow] = []
    action_decision_ids: set[str] = set()
    linked_outcome_ids: set[str] = set()
    decisions_by_id = {decision.id: decision for decision in decisions}
    outcomes_by_decision: dict[str, list[OutcomeReconciliationCheck]] = {}
    outcomes_by_idempotency: dict[str, list[OutcomeReconciliationCheck]] = {}

    for outcome in outcomes:
        if outcome.runtime_policy_decision_id:
            outcomes_by_decision.setdefault(outcome.runtime_policy_decision_id, []).append(outcome)
        if outcome.idempotency_key:
            outcomes_by_idempotency.setdefault(outcome.idempotency_key, []).append(outcome)

    for intent in actions:
        if intent.runtime_policy_decision_id:
            action_decision_ids.add(intent.runtime_policy_decision_id)
        decision = decisions_by_id.get(intent.runtime_policy_decision_id or "")
        outcome_candidates = [
            *outcomes_by_decision.get(intent.runtime_policy_decision_id or "", []),
            *outcomes_by_idempotency.get(intent.idempotency_key, []),
        ]
        outcome = _latest_by_date(outcome_candidates)
        if outcome:
            linked_outcome_ids.add(outcome.id)
        trace_context = _trace_context_for_intent(intent)
        trace_id = outcome.trace_id if outcome else decision.trace_id if decision else _string(trace_context.get("trace_id"))
        call_id = outcome.call_id if outcome else decision.call_id if decision else _string(trace_context.get("call_id"))
        status_value = _row_status_for_intent(intent)
        expected_block = status_value in {"blocked", "denied", "rejected", "expired", "cancelled"}
        title = _title_for_intent(intent)
        checked_at = outcome.checked_at if outcome else intent.created_at
        rows.append(
            _LedgerRow(
                action_id=intent.id,
                action_type=_humanize(intent.action_type),
                agent_name=_agent_name_for_intent(intent),
                call_id=call_id,
                checked_at=checked_at,
                decision_id=intent.runtime_policy_decision_id,
                digest=intent.intent_digest,
                export_kind=None if expected_block else "receipt",
                exportable=not expected_block and intent.receipt_status == "generated",
                href_path=f"/evidence?action_id={quote(intent.id)}",
                id=f"action:{intent.id}",
                kind="action_receipt",
                outcome_id=outcome.id if outcome else None,
                source_label=(
                    "Blocked action audit"
                    if expected_block
                    else "Action Receipt"
                    if intent.receipt_status == "generated"
                    else "Protected action record"
                ),
                status=status_value,
                system_ref=outcome.system_ref if outcome else None,
                title=title,
                trace_id=trace_id,
                detail=(
                    "Policy stopped execution; receipt and outcome proof are not expected."
                    if expected_block
                    else "Signed receipt available"
                    if intent.receipt_status == "generated"
                    else "Receipt not generated yet"
                ),
                search_text=_build_search_text([
                    intent.id,
                    intent.action_type,
                    call_id,
                    intent.intent_digest,
                    outcome.system_ref if outcome else None,
                    status_value,
                    title,
                    trace_id,
                ]),
            )
        )

    for decision in decisions:
        if decision.id in action_decision_ids:
            continue
        outcome = _latest_by_date(outcomes_by_decision.get(decision.id, []))
        if outcome:
            linked_outcome_ids.add(outcome.id)
        status_value = _row_status_for_decision(decision, outcome)
        title = _title_for_decision(decision)
        rows.append(
            _LedgerRow(
                action_id=None,
                action_type=_humanize(decision.action_type or decision.tool_name),
                agent_name=decision.agent_name or "Guard-only action",
                call_id=outcome.call_id if outcome else decision.call_id,
                checked_at=outcome.checked_at if outcome else decision.resolved_at or decision.created_at,
                decision_id=decision.id,
                digest=None,
                export_kind="evidence_pack",
                exportable=True,
                href_path=f"/evidence?decision_id={quote(decision.id)}",
                id=f"decision:{decision.id}",
                kind="orphan_decision",
                outcome_id=outcome.id if outcome else None,
                source_label="Guard-only Evidence Pack",
                status=status_value,
                system_ref=outcome.system_ref if outcome else decision.call_id or decision.trace_id,
                title=title,
                trace_id=outcome.trace_id if outcome else decision.trace_id,
                detail=(
                    "Runtime decision linked to outcome proof"
                    if outcome
                    else "Runtime decision has no linked outcome proof"
                ),
                search_text=_build_search_text([
                    decision.id,
                    decision.action_type,
                    decision.agent_name,
                    decision.call_id,
                    decision.tool_name,
                    outcome.system_ref if outcome else None,
                    status_value,
                    title,
                    decision.trace_id,
                ]),
            )
        )

    for outcome in outcomes:
        if outcome.id in linked_outcome_ids:
            continue
        status_value = outcome.verdict or "not_verified"
        title = outcome.system_ref or outcome.id
        rows.append(
            _LedgerRow(
                action_id=None,
                action_type=_humanize(outcome.action_type),
                agent_name="Unlinked outcome",
                call_id=outcome.call_id,
                checked_at=outcome.checked_at or outcome.created_at,
                decision_id=outcome.runtime_policy_decision_id,
                digest=None,
                export_kind=None,
                exportable=False,
                href_path="/outcomes",
                id=f"outcome:{outcome.id}",
                kind="unlinked_outcome",
                outcome_id=outcome.id,
                source_label="Unlinked outcome",
                status=status_value,
                system_ref=outcome.system_ref,
                title=title,
                trace_id=outcome.trace_id,
                detail="Not linked to an action intent in this evidence window",
                search_text=_build_search_text([
                    outcome.id,
                    outcome.action_type,
                    outcome.call_id,
                    outcome.connector_type,
                    outcome.system_ref,
                    outcome.trace_id,
                    status_value,
                    title,
                ]),
            )
        )

    rank = {"action_receipt": 0, "orphan_decision": 1, "unlinked_outcome": 2}
    return sorted(
        rows,
        key=lambda row: (
            rank.get(row.kind, 99),
            -(row.checked_at.timestamp() if row.checked_at else 0),
        ),
    )


def _ledger_record(row: _LedgerRow) -> EvidenceLedgerRecord:
    return EvidenceLedgerRecord(
        action_id=row.action_id,
        action_type=row.action_type,
        agent_name=row.agent_name,
        call_id=row.call_id,
        checked_at=row.checked_at,
        decision_id=row.decision_id,
        detail=row.detail,
        digest=row.digest,
        export_kind=row.export_kind,
        exportable=row.exportable,
        href=row.href_path,
        id=row.id,
        kind=row.kind,
        outcome_id=row.outcome_id,
        source_label=row.source_label,
        status=row.status,
        system_ref=row.system_ref,
        title=row.title,
        trace_id=row.trace_id,
    )


@router.get("/ledger", response_model=EvidenceLedgerResponse)
@limiter.limit("120/minute")
def get_evidence_ledger(
    request: Request,
    days: int = Query(default=7, ge=1, le=90),
    filter: EvidenceManifestFilter = Query(default="all"),
    search: str = Query(default="", max_length=200),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> EvidenceLedgerResponse:
    _require_viewer(context)
    actions = list(db.execute(select(ActionIntent).where(ActionIntent.project_id == context.tenant_id)).scalars())
    decisions = list(db.execute(select(RuntimePolicyDecision).where(RuntimePolicyDecision.project_id == context.tenant_id)).scalars())
    outcomes = list(
        db.execute(select(OutcomeReconciliationCheck).where(OutcomeReconciliationCheck.project_id == context.tenant_id)).scalars()
    )
    now = datetime.now(timezone.utc)
    scoped = [
        row
        for row in _build_manifest_rows(actions=actions, decisions=decisions, outcomes=outcomes)
        if _in_day_window(row, days, now)
    ]
    matching = [row for row in scoped if _matches_filter(row, filter) and _matches_search(row, search)]
    page = matching[offset : offset + limit]
    return EvidenceLedgerResponse(
        counts=EvidenceLedgerCounts(
            exceptions=sum(1 for row in scoped if _is_exception(row.status)),
            export_ready=sum(1 for row in scoped if row.exportable and row.status == "matched"),
            needs_verification=sum(1 for row in scoped if _needs_verification(row.status)),
            total=len(scoped),
        ),
        has_more=offset + len(page) < len(matching),
        items=[_ledger_record(row) for row in page],
        limit=limit,
        offset=offset,
        total_in_scope=len(scoped),
        total_matching=len(matching),
        window_days=days,
    )


@router.get("/manifest", response_model=EvidenceManifestResponse)
@limiter.limit("60/minute")
def get_evidence_manifest(
    request: Request,
    filter: EvidenceManifestFilter = Query(default="all"),
    search: str = Query(default="", max_length=200),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    days: int | None = Query(default=None, ge=1, le=90),
    dashboard_origin: str | None = Query(default=None, max_length=512),
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> EvidenceManifestResponse:
    _require_viewer(context)
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date.")

    actions = list(db.execute(select(ActionIntent).where(ActionIntent.project_id == context.tenant_id)).scalars())
    decisions = list(db.execute(select(RuntimePolicyDecision).where(RuntimePolicyDecision.project_id == context.tenant_id)).scalars())
    outcomes = list(
        db.execute(select(OutcomeReconciliationCheck).where(OutcomeReconciliationCheck.project_id == context.tenant_id)).scalars()
    )
    origin = _dashboard_origin(request, dashboard_origin)
    now = datetime.now(timezone.utc)
    rows = [
        row
        for row in _build_manifest_rows(actions=actions, decisions=decisions, outcomes=outcomes)
        if (days is None or _in_day_window(row, days, now))
        and _in_date_scope(row, start_date, end_date)
        and _matches_filter(row, filter)
        and _matches_search(row, search)
    ]
    public_key_url = str(
        action_receipt_public_key_payload().get("public_key_url") or "/.well-known/zroky/action-receipt-signing-key"
    )

    return EvidenceManifestResponse(
        artifact="zroky.evidence_manifest",
        schema_version="zroky.evidence_manifest.v1",
        generated_at=datetime.now(timezone.utc),
        project_id=context.tenant_id,
        scope=EvidenceManifestScope(
            filter=filter,
            search=search.strip() or None,
            start_date=start_date.isoformat() if start_date else None,
            end_date=end_date.isoformat() if end_date else None,
            total_records=len(rows),
            exportable_records=sum(1 for row in rows if row.exportable),
            non_exportable_records=sum(1 for row in rows if not row.exportable),
            window_days=days,
        ),
        verification=EvidenceManifestVerification(
            public_key_url=public_key_url,
            instructions=[
                "Use this manifest as an index, not as a signed evidence bundle.",
                "Export each referenced Action Receipt or Evidence Pack JSON before audit review.",
                "For Action Receipts, verify the Ed25519 signature over signed_payload using the published public key.",
                "For Evidence Packs, compare the evidence_hash in the exported proof with the value shown in Zroky.",
            ],
        ),
        records=[
            EvidenceManifestRecord(
                action_id=row.action_id,
                checked_at=row.checked_at,
                decision_id=row.decision_id,
                digest=row.digest,
                export_kind=row.export_kind,
                exportable=row.exportable,
                href=_absolute_href(origin, row.href_path),
                id=row.id,
                kind=row.kind,
                source_label=row.source_label,
                status=row.status,
                system_ref=row.system_ref,
                title=row.title,
                trace_id=row.trace_id,
            )
            for row in rows
        ],
    )
