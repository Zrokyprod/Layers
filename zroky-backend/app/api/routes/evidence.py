from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import quote, urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.authorization import ROLE_RANK
from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.core.limiter import limiter
from app.db.models import ActionIntent, FinalEvidenceBundle, OutcomeReconciliationCheck, RuntimePolicyDecision
from app.db.session import get_db_session
from app.schemas.evidence import (
    EvidenceManifestFilter,
    EvidenceManifestRecord,
    EvidenceManifestResponse,
    EvidenceManifestScope,
    EvidenceManifestVerification,
)
from app.services.action_receipts import (
    SIGNATURE_ALGORITHM,
    _ed25519_private_key,
    _ed25519_signature,
    action_receipt_public_key_payload,
    verify_receipt_json_with_public_key,
)
from app.services.privacy import mask_value

router = APIRouter(prefix="/v1/evidence", tags=["evidence"])

FINAL_EVIDENCE_BUNDLE_SCHEMA_VERSION = "zroky.final_evidence_bundle.v1"
FINAL_EVIDENCE_BUNDLE_SECTIONS = {
    "intent": dict,
    "policy": dict,
    "observations": list,
    "snapshot": dict,
    "incident": dict,
    "recovery": dict,
}


class FinalEvidenceBundleCreateRequest(BaseModel):
    environment: str = Field(default="production", min_length=1, max_length=64)
    subject_type: str = Field(min_length=1, max_length=64)
    subject_id: str = Field(min_length=1, max_length=36)
    bundle: dict[str, Any]


class FinalEvidenceBundleResponse(BaseModel):
    id: str
    project_id: str
    environment: str
    subject_type: str
    subject_id: str
    bundle_digest: str
    bundle: dict[str, Any]
    signature: dict[str, Any] | None
    created_at: datetime


class FinalEvidenceBundleVerificationResponse(BaseModel):
    bundle_id: str
    bundle_digest: str
    verification_status: str
    digest_valid: bool
    signature_valid: bool
    algorithm: str | None
    key_id: str | None


def _digest_json(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def _normalize_final_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(bundle)
    schema_version = normalized.setdefault("schema_version", FINAL_EVIDENCE_BUNDLE_SCHEMA_VERSION)
    if schema_version != FINAL_EVIDENCE_BUNDLE_SCHEMA_VERSION:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported evidence bundle schema_version.")
    for key, expected_type in FINAL_EVIDENCE_BUNDLE_SECTIONS.items():
        if not isinstance(normalized.get(key), expected_type):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Evidence bundle requires {key}.")
    return normalized


def _final_bundle_signature(*, bundle_json: str, bundle_digest: str) -> dict[str, Any]:
    private_key, key_id = _ed25519_private_key()
    public_key = action_receipt_public_key_payload()["public_key"]
    return {
        "schema_version": "zroky.final_evidence_signature.v1",
        "envelope": "dsse-like",
        "payload_type": "application/vnd.zroky.final-evidence-bundle+json",
        "payload_digest": f"sha256:{bundle_digest}",
        "algorithm": SIGNATURE_ALGORITHM,
        "key_id": key_id,
        "public_key": public_key,
        "signature": _ed25519_signature(bundle_json, private_key),
        "signed_payload": "bundle_json",
    }


def _final_bundle_response(row: FinalEvidenceBundle) -> FinalEvidenceBundleResponse:
    return FinalEvidenceBundleResponse(
        id=row.id,
        project_id=row.project_id,
        environment=row.environment,
        subject_type=row.subject_type,
        subject_id=row.subject_id,
        bundle_digest=row.bundle_digest,
        bundle=json.loads(row.bundle_json),
        signature=json.loads(row.signature_json) if row.signature_json else None,
        created_at=row.created_at,
    )


@dataclass(frozen=True)
class _LedgerRow:
    action_id: str | None
    checked_at: datetime | None
    decision_id: str | None
    digest: str | None
    export_kind: str | None
    exportable: bool
    href_path: str
    id: str
    kind: str
    source_label: str
    status: str
    system_ref: str | None
    title: str
    trace_id: str | None
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
    return status_value in {"mismatched", "failed", "signature_invalid", "blocked", "denied", "rejected", "expired"}


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
        title = _title_for_intent(intent)
        checked_at = outcome.checked_at if outcome else intent.created_at
        rows.append(
            _LedgerRow(
                action_id=intent.id,
                checked_at=checked_at,
                decision_id=intent.runtime_policy_decision_id,
                digest=intent.intent_digest,
                export_kind="receipt",
                exportable=intent.receipt_status == "generated",
                href_path=f"/evidence?action_id={quote(intent.id)}",
                id=f"action:{intent.id}",
                kind="action_receipt",
                source_label="Action Receipt",
                status=status_value,
                system_ref=outcome.system_ref if outcome else None,
                title=title,
                trace_id=trace_id,
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
                checked_at=outcome.checked_at if outcome else decision.resolved_at or decision.created_at,
                decision_id=decision.id,
                digest=None,
                export_kind="evidence_pack",
                exportable=True,
                href_path=f"/evidence?decision_id={quote(decision.id)}",
                id=f"decision:{decision.id}",
                kind="orphan_decision",
                source_label="Guard-only Evidence Pack",
                status=status_value,
                system_ref=outcome.system_ref if outcome else decision.call_id or decision.trace_id,
                title=title,
                trace_id=outcome.trace_id if outcome else decision.trace_id,
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
                checked_at=outcome.checked_at or outcome.created_at,
                decision_id=outcome.runtime_policy_decision_id,
                digest=None,
                export_kind=None,
                exportable=False,
                href_path="/outcomes",
                id=f"outcome:{outcome.id}",
                kind="unlinked_outcome",
                source_label="Unlinked outcome",
                status=status_value,
                system_ref=outcome.system_ref,
                title=title,
                trace_id=outcome.trace_id,
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


@router.post("/bundles", response_model=FinalEvidenceBundleResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("60/minute")
def create_final_evidence_bundle(
    request: Request,
    body: FinalEvidenceBundleCreateRequest,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> FinalEvidenceBundleResponse:
    _require_viewer(context)
    redacted = mask_value(_normalize_final_bundle(body.bundle))
    bundle_json = json.dumps(redacted, sort_keys=True, separators=(",", ":"), default=str)
    bundle_digest = _digest_json(redacted)
    row = FinalEvidenceBundle(
        project_id=context.tenant_id,
        environment=body.environment.strip().lower(),
        subject_type=body.subject_type,
        subject_id=body.subject_id,
        bundle_digest=bundle_digest,
        bundle_json=bundle_json,
        signature_json=json.dumps(
            _final_bundle_signature(bundle_json=bundle_json, bundle_digest=bundle_digest),
            sort_keys=True,
            separators=(",", ":"),
        ),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _final_bundle_response(row)


@router.get("/bundles/{bundle_id}", response_model=FinalEvidenceBundleResponse)
@limiter.limit("120/minute")
def get_final_evidence_bundle(
    request: Request,
    bundle_id: str,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> FinalEvidenceBundleResponse:
    _require_viewer(context)
    row = db.execute(
        select(FinalEvidenceBundle).where(
            FinalEvidenceBundle.id == bundle_id,
            FinalEvidenceBundle.project_id == context.tenant_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence bundle not found.")
    return _final_bundle_response(row)


@router.get("/bundles/{bundle_id}/verify", response_model=FinalEvidenceBundleVerificationResponse)
@limiter.limit("120/minute")
def verify_final_evidence_bundle(
    request: Request,
    bundle_id: str,
    context: TenantContext = Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> FinalEvidenceBundleVerificationResponse:
    _require_viewer(context)
    row = db.execute(
        select(FinalEvidenceBundle).where(
            FinalEvidenceBundle.id == bundle_id,
            FinalEvidenceBundle.project_id == context.tenant_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence bundle not found.")
    bundle = json.loads(row.bundle_json)
    signature = json.loads(row.signature_json or "{}")
    digest_valid = _digest_json(bundle) == row.bundle_digest
    signature_valid = verify_receipt_json_with_public_key(
        receipt_json=row.bundle_json,
        signature=str(signature.get("signature") or ""),
        public_key=str(signature.get("public_key") or ""),
    )
    return FinalEvidenceBundleVerificationResponse(
        bundle_id=row.id,
        bundle_digest=row.bundle_digest,
        verification_status="pass" if digest_valid and signature_valid else "fail",
        digest_valid=digest_valid,
        signature_valid=signature_valid,
        algorithm=signature.get("algorithm"),
        key_id=signature.get("key_id"),
    )


@router.get("/manifest", response_model=EvidenceManifestResponse)
@limiter.limit("60/minute")
def get_evidence_manifest(
    request: Request,
    filter: EvidenceManifestFilter = Query(default="all"),
    search: str = Query(default="", max_length=200),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
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
    rows = [
        row
        for row in _build_manifest_rows(actions=actions, decisions=decisions, outcomes=outcomes)
        if _in_date_scope(row, start_date, end_date) and _matches_filter(row, filter) and _matches_search(row, search)
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
