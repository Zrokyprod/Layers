from __future__ import annotations

import hashlib
import hmac
import json
import base64
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import (
    ActionContractVersion,
    ActionExecutionAttempt,
    ActionIntent,
    Agent,
    ActionReceipt,
    OutcomeReconciliationCheck,
    RuntimePolicyDecision,
)
from app.services.action_kernel import ActionIntentNotFound, get_action_intent
from app.services.action_runner import execution_attempt_plan
from app.services.action_timeline import (
    action_timeline_event_payload,
    list_action_timeline,
    record_action_timeline_event,
)
from app.services.evidence_pack import build_runtime_policy_evidence_pack
from app.services.outcome_reconciliation import verification_status_for_check
from app.services.protected_action_billing import (
    METER_ACTION_RECEIPTS,
    reserve_usage_meter,
)


SCHEMA_VERSION = "zroky.action_receipt.v1"
SIGNATURE_ALGORITHM = "Ed25519"
LEGACY_HMAC_SIGNATURE_ALGORITHM = "HMAC-SHA256"
DEV_SIGNING_SECRET = "dev-action-receipt-signing-secret-minimum-32-bytes"
DEV_ED25519_PRIVATE_KEY_BYTES = hashlib.sha256(b"zroky:dev-action-receipt-ed25519:v1").digest()


class ActionReceiptError(ValueError):
    pass


class ActionReceiptNotFound(ActionReceiptError):
    pass


class ActionReceiptSigningError(ActionReceiptError):
    pass


@dataclass(frozen=True)
class GeneratedActionReceipt:
    row: ActionReceipt
    created: bool


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True, default=str)


def _sha256_digest(canonical_payload: str) -> str:
    return f"sha256:{hashlib.sha256(canonical_payload.encode('utf-8')).hexdigest()}"


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _signing_key_id() -> str:
    return get_settings().ACTION_RECEIPT_SIGNING_KEY_ID


def _decode_ed25519_private_key(value: str) -> bytes:
    cleaned = value.strip()
    if not cleaned:
        raise ActionReceiptSigningError("ACTION_RECEIPT_ED25519_PRIVATE_KEY is required to sign receipts.")
    if "BEGIN" in cleaned:
        private_key = serialization.load_pem_private_key(cleaned.encode("utf-8"), password=None)
        if not isinstance(private_key, Ed25519PrivateKey):
            raise ActionReceiptSigningError("ACTION_RECEIPT_ED25519_PRIVATE_KEY must be an Ed25519 private key.")
        return private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
    try:
        raw = base64.b64decode(cleaned, validate=True)
    except Exception as exc:
        raise ActionReceiptSigningError(
            "ACTION_RECEIPT_ED25519_PRIVATE_KEY must be base64 raw Ed25519 seed bytes or PEM."
        ) from exc
    if len(raw) != 32:
        raise ActionReceiptSigningError("ACTION_RECEIPT_ED25519_PRIVATE_KEY must decode to 32 bytes.")
    return raw


def _ed25519_private_key() -> tuple[Ed25519PrivateKey, str]:
    settings = get_settings()
    private_key_value = (settings.ACTION_RECEIPT_ED25519_PRIVATE_KEY or "").strip()
    if private_key_value:
        raw_private_key = _decode_ed25519_private_key(private_key_value)
    else:
        if settings.APP_ENV.strip().lower() == "production":
            raise ActionReceiptSigningError(
                "ACTION_RECEIPT_ED25519_PRIVATE_KEY is required to sign independently verifiable receipts."
            )
        raw_private_key = DEV_ED25519_PRIVATE_KEY_BYTES
    return Ed25519PrivateKey.from_private_bytes(raw_private_key), settings.ACTION_RECEIPT_SIGNING_KEY_ID


def _hmac_signature(canonical_payload: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), canonical_payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _legacy_signing_secret() -> str:
    settings = get_settings()
    secret = (settings.ACTION_RECEIPT_SIGNING_SECRET or "").strip()
    if not secret and settings.APP_ENV.strip().lower() != "production":
        secret = DEV_SIGNING_SECRET
    return secret


def _ed25519_signature(canonical_payload: str, private_key: Ed25519PrivateKey) -> str:
    signature = private_key.sign(canonical_payload.encode("utf-8"))
    return base64.b64encode(signature).decode("ascii")


def _ed25519_public_key_b64(private_key: Ed25519PrivateKey) -> str:
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(public_bytes).decode("ascii")


def action_receipt_public_key_payload() -> dict[str, Any]:
    private_key, key_id = _ed25519_private_key()
    return {
        "key_id": key_id,
        "algorithm": SIGNATURE_ALGORITHM,
        "public_key": _ed25519_public_key_b64(private_key),
        "public_key_encoding": "base64-raw-ed25519",
        "canonicalization": "json-sort-keys-separators-comma-colon",
        "signed_payload": "receipt_json",
    }


def verify_receipt_json_with_public_key(
    *,
    receipt_json: str,
    signature: str,
    public_key: str,
) -> bool:
    try:
        public_key_bytes = base64.b64decode(public_key.strip(), validate=True)
        signature_bytes = base64.b64decode(signature.strip(), validate=True)
        verifier = Ed25519PublicKey.from_public_bytes(public_key_bytes)
        verifier.verify(signature_bytes, receipt_json.encode("utf-8"))
        return True
    except (AttributeError, TypeError, ValueError, InvalidSignature):
        return False


def _contract_to_receipt(row: ActionContractVersion | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "contract_version": f"{row.contract_key}/{row.version}",
        "action_type": row.action_type,
        "operation_kind": row.operation_kind,
        "domain_family": row.domain_family,
        "schema_digest": row.schema_digest,
        "risk_class": row.risk_class,
        "connector_family": row.connector_family,
        "status": row.status,
    }


def _policy_decision_to_receipt(row: RuntimePolicyDecision | None) -> dict[str, Any] | None:
    if row is None:
        return None
    request = _json_loads(row.request_json, {})
    policy_snapshot = _json_loads(row.policy_snapshot_json, {})
    return {
        "id": row.id,
        "decision": row.decision,
        "status": row.status,
        "reasons": _json_loads(row.reasons_json, []),
        "policy_snapshot": policy_snapshot,
        "policy_resolution": policy_snapshot.get("_runtime_policy_resolution") if isinstance(policy_snapshot, dict) else None,
        "approval_scope_hash": row.approval_scope_hash,
        "approval_id": request.get("approval_id") if isinstance(request, dict) else None,
        "resolved_by": row.resolved_by,
        "resolved_at": _iso(row.resolved_at),
        "consumed_at": _iso(row.consumed_at),
        "consumed_by_decision_id": row.consumed_by_decision_id,
        "required_approval_count": row.required_approval_count,
        "approval_count": row.approval_count,
        "approver_subjects": _json_loads(row.approver_subjects_json, []),
        "created_at": _iso(row.created_at),
    }


def _execution_attempt_to_receipt(row: ActionExecutionAttempt | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "runner_id": row.runner_id,
        "attempt_number": row.attempt_number,
        "status": row.status,
        "idempotency_key": row.idempotency_key,
        "credential_ref": row.credential_ref,
        "plan_digest": row.plan_digest,
        "plan": execution_attempt_plan(row),
        "protected_credential_returned": row.protected_credential_returned,
        "started_at": _iso(row.started_at),
        "finished_at": _iso(row.finished_at),
        "created_at": _iso(row.created_at),
    }


def _outcome_to_receipt(row: OutcomeReconciliationCheck) -> dict[str, Any]:
    return {
        "id": row.id,
        "verdict": row.verdict,
        "verification_status": verification_status_for_check(row),
        "reason": row.reason,
        "connector_type": row.connector_type,
        "system_ref": row.system_ref,
        "idempotency_key": row.idempotency_key,
        "checked_at": _iso(row.checked_at),
    }


def _latest_execution_attempt(
    db: Session,
    *,
    project_id: str,
    action_id: str,
) -> ActionExecutionAttempt | None:
    return db.execute(
        select(ActionExecutionAttempt)
        .where(
            ActionExecutionAttempt.project_id == project_id,
            ActionExecutionAttempt.action_intent_id == action_id,
        )
        .order_by(desc(ActionExecutionAttempt.created_at), desc(ActionExecutionAttempt.attempt_number))
        .limit(1)
    ).scalar_one_or_none()


def _outcomes_for_decision(
    db: Session,
    *,
    project_id: str,
    decision: RuntimePolicyDecision | None,
) -> list[OutcomeReconciliationCheck]:
    if decision is None:
        return []
    filters: list[Any] = [OutcomeReconciliationCheck.runtime_policy_decision_id == decision.id]
    if decision.call_id:
        filters.append(OutcomeReconciliationCheck.call_id == decision.call_id)
    if decision.trace_id:
        filters.append(OutcomeReconciliationCheck.trace_id == decision.trace_id)
    return list(
        db.execute(
            select(OutcomeReconciliationCheck)
            .where(OutcomeReconciliationCheck.project_id == project_id, or_(*filters))
            .order_by(OutcomeReconciliationCheck.checked_at.asc(), OutcomeReconciliationCheck.id.asc())
        ).scalars()
    )


def _receipt_status(intent: ActionIntent, attempt: ActionExecutionAttempt | None, outcomes: list[OutcomeReconciliationCheck]) -> str:
    statuses = {verification_status_for_check(row) for row in outcomes}
    if "mismatched" in statuses:
        return "mismatched"
    if "verified" in statuses:
        return "verified"
    if "pending" in statuses:
        return "pending"
    if "unverifiable" in statuses:
        return "unverifiable"
    if "cancelled" in statuses:
        return "cancelled"
    if attempt is not None and attempt.status in {"failed", "ambiguous", "cancelled"}:
        return attempt.status
    if intent.status in {"denied", "expired"}:
        return intent.status
    if attempt is not None:
        return attempt.status
    return intent.status


def _build_receipt_core(
    db: Session,
    *,
    project_id: str,
    action_id: str,
    generated_at: datetime,
) -> dict[str, Any]:
    intent = get_action_intent(db, project_id=project_id, action_id=action_id)
    agent = db.get(Agent, intent.agent_id) if intent.agent_id else None
    contract = db.get(ActionContractVersion, intent.contract_version_id)
    decision = None
    if intent.runtime_policy_decision_id:
        decision = db.execute(
            select(RuntimePolicyDecision).where(
                RuntimePolicyDecision.project_id == project_id,
                RuntimePolicyDecision.id == intent.runtime_policy_decision_id,
            )
        ).scalar_one_or_none()
    attempt = _latest_execution_attempt(db, project_id=project_id, action_id=action_id)
    outcomes = _outcomes_for_decision(db, project_id=project_id, decision=decision)
    evidence_pack = None
    if decision is not None:
        evidence_pack = build_runtime_policy_evidence_pack(db, project_id=project_id, decision_id=decision.id)
    timeline = list_action_timeline(db, project_id=project_id, action_id=action_id)
    evidence_hash = evidence_pack.get("evidence_hash") if evidence_pack else None
    return {
        "schema_version": SCHEMA_VERSION,
        "project_id": project_id,
        "action_id": intent.id,
        "environment": intent.environment,
        "final_status": _receipt_status(intent, attempt, outcomes),
        "generated_at": _iso(generated_at),
        "action_contract": _contract_to_receipt(contract),
        "intent": {
            "agent_id": intent.agent_id,
            "agent_profile": {
                "id": agent.id,
                "display_name": agent.name,
                "slug": agent.slug,
                "runtime_path": agent.runtime_path,
                "environment": agent.environment,
            } if agent is not None and agent.project_id == project_id else None,
            "contract_version": f"{intent.contract_key}/{intent.contract_version}",
            "action_type": intent.action_type,
            "operation_kind": intent.operation_kind,
            "idempotency_key": intent.idempotency_key,
            "intent_digest": intent.intent_digest,
            "canonical_intent": _json_loads(intent.canonical_intent_json, {}),
            "principal": _json_loads(intent.principal_json, {}),
            "actor_chain": _json_loads(intent.actor_chain_json, []),
            "purpose": _json_loads(intent.purpose_json, {}),
            "resource": _json_loads(intent.resource_json, {}),
            "parameters": _json_loads(intent.parameters_json, {}),
            "verification_profile": intent.verification_profile,
            "created_at": _iso(intent.created_at),
            "decided_at": _iso(intent.decided_at),
            "authorized_at": _iso(intent.authorized_at),
        },
        "policy_decision": _policy_decision_to_receipt(decision),
        "runner_execution": _execution_attempt_to_receipt(attempt),
        "verification": {
            "status": _receipt_status(intent, attempt, outcomes),
            "outcomes": [_outcome_to_receipt(row) for row in outcomes],
        },
        "evidence": {
            "hash_algorithm": "sha256",
            "evidence_hash": evidence_hash,
        },
        "timeline": [
            {
                "id": row.id,
                "event_type": row.event_type,
                "event_digest": row.event_digest,
                "actor": row.actor,
                "payload": action_timeline_event_payload(row),
                "created_at": _iso(row.created_at),
            }
            for row in timeline
        ],
    }


def get_action_receipt(db: Session, *, project_id: str, action_id: str) -> ActionReceipt:
    row = db.execute(
        select(ActionReceipt).where(
            ActionReceipt.project_id == project_id,
            ActionReceipt.action_intent_id == action_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise ActionReceiptNotFound("Action receipt not found.")
    return row


def generate_action_receipt(
    db: Session,
    *,
    project_id: str,
    action_id: str,
    actor: str | None = None,
) -> GeneratedActionReceipt:
    try:
        existing = get_action_receipt(db, project_id=project_id, action_id=action_id)
    except ActionReceiptNotFound:
        existing = None
    if existing is not None:
        return GeneratedActionReceipt(existing, created=False)

    generated_at = _now()
    core = _build_receipt_core(db, project_id=project_id, action_id=action_id, generated_at=generated_at)
    canonical = _canonical_json(core)
    receipt_digest = _sha256_digest(canonical)
    private_key, key_id = _ed25519_private_key()
    signature = _ed25519_signature(canonical, private_key)
    reserve_usage_meter(db, project_id, METER_ACTION_RECEIPTS)
    row = ActionReceipt(
        project_id=project_id,
        action_intent_id=action_id,
        receipt_digest=receipt_digest,
        receipt_json=canonical,
        evidence_hash=core["evidence"]["evidence_hash"],
        signature_algorithm=SIGNATURE_ALGORITHM,
        signature=signature,
        signing_key_id=key_id,
        generated_at=generated_at,
    )
    db.add(row)
    db.flush()
    record_action_timeline_event(
        db,
        project_id=project_id,
        action_id=action_id,
        event_type="receipt_generated",
        payload={
            "receipt_id": row.id,
            "receipt_digest": receipt_digest,
            "signature_algorithm": SIGNATURE_ALGORITHM,
            "signing_key_id": key_id,
        },
        actor=actor,
    )
    return GeneratedActionReceipt(row, created=True)


def action_receipt_payload(row: ActionReceipt) -> dict[str, Any]:
    payload = _json_loads(row.receipt_json, {})
    if not isinstance(payload, dict):
        payload = {}
    public_key_payload = None
    if row.signature_algorithm == SIGNATURE_ALGORITHM:
        public_key_payload = action_receipt_public_key_payload()
    return {
        **payload,
        "receipt_id": row.id,
        "receipt_digest": row.receipt_digest,
        "signature": {
            "algorithm": row.signature_algorithm,
            "value": row.signature,
            "key_id": row.signing_key_id,
            "public_key": public_key_payload["public_key"] if public_key_payload else None,
            "public_key_encoding": public_key_payload["public_key_encoding"] if public_key_payload else None,
        },
    }


def verify_action_receipt_signature(row: ActionReceipt) -> bool:
    if row.signature_algorithm == SIGNATURE_ALGORITHM:
        public_key = action_receipt_public_key_payload()["public_key"]
        return verify_receipt_json_with_public_key(
            receipt_json=row.receipt_json,
            signature=row.signature,
            public_key=public_key,
        )
    if row.signature_algorithm == LEGACY_HMAC_SIGNATURE_ALGORITHM:
        secret = _legacy_signing_secret()
        if not secret:
            return False
        expected = _hmac_signature(row.receipt_json, secret)
        return hmac.compare_digest(expected, row.signature)
    return False
