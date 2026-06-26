from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Mapping

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models import ActionIntent, ActionReceipt, SourceMutationRecord
from app.services.protected_action_billing import (
    METER_SOURCE_MUTATIONS,
    reserve_usage_meter,
)


CLASS_MATCHED_RECEIPT = "matched_receipt"
CLASS_AUTHORIZED_EXTERNAL = "authorized_external"
CLASS_LEGACY_PATH = "legacy_path"
CLASS_UNMANAGED_AGENT_ACTION = "unmanaged_agent_action"
CLASS_POLICY_BYPASS = "policy_bypass"
CLASS_UNKNOWN_ACTOR = "unknown_actor"

BYPASS_CLASSIFICATIONS = {
    CLASS_UNMANAGED_AGENT_ACTION,
    CLASS_POLICY_BYPASS,
    CLASS_UNKNOWN_ACTOR,
}


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


def _bounded(value: Any, *, max_length: int) -> str | None:
    if value is None:
        return None
    rendered = str(value).strip()
    if not rendered:
        return None
    return rendered[:max_length]


def _normalize(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def _is_protected_action(action_type: str | None, metadata: Mapping[str, Any]) -> bool:
    if metadata.get("protected_action") is True or metadata.get("requires_zroky") is True:
        return True
    normalized = _normalize(action_type)
    return any(
        marker in normalized
        for marker in ("refund", "transfer", "payment", "delete", "send", "message", "email", "execute", "deploy", "update")
    )


def _find_receipt(
    db: Session,
    *,
    project_id: str,
    action_id: str | None,
    receipt_id: str | None,
    idempotency_key: str | None,
) -> ActionReceipt | None:
    if receipt_id:
        row = db.execute(
            select(ActionReceipt).where(
                ActionReceipt.project_id == project_id,
                ActionReceipt.id == receipt_id,
            )
        ).scalar_one_or_none()
        if row is not None:
            return row
    if action_id:
        row = db.execute(
            select(ActionReceipt).where(
                ActionReceipt.project_id == project_id,
                ActionReceipt.action_intent_id == action_id,
            )
        ).scalar_one_or_none()
        if row is not None:
            return row
    if idempotency_key:
        intent = db.execute(
            select(ActionIntent).where(
                ActionIntent.project_id == project_id,
                ActionIntent.idempotency_key == idempotency_key,
            )
        ).scalar_one_or_none()
        if intent is not None:
            return db.execute(
                select(ActionReceipt).where(
                    ActionReceipt.project_id == project_id,
                    ActionReceipt.action_intent_id == intent.id,
                )
            ).scalar_one_or_none()
    return None


def _classify_mutation(
    *,
    action_type: str | None,
    actor_type: str | None,
    metadata: Mapping[str, Any],
    receipt: ActionReceipt | None,
) -> str:
    if receipt is not None:
        return CLASS_MATCHED_RECEIPT
    if metadata.get("authorized_external") is True:
        return CLASS_AUTHORIZED_EXTERNAL
    if metadata.get("legacy_path") is True:
        return CLASS_LEGACY_PATH
    normalized_actor_type = _normalize(actor_type)
    if normalized_actor_type in {"agent", "ai_agent", "autonomous_agent", "service_agent"}:
        return CLASS_POLICY_BYPASS if _is_protected_action(action_type, metadata) else CLASS_UNMANAGED_AGENT_ACTION
    if _is_protected_action(action_type, metadata):
        return CLASS_POLICY_BYPASS
    return CLASS_UNKNOWN_ACTOR


def ingest_source_mutation(
    db: Session,
    *,
    project_id: str,
    source_system: str,
    mutation_id: str,
    action_type: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    system_ref: str | None = None,
    actor_type: str | None = None,
    actor_id: str | None = None,
    zroky_action_id: str | None = None,
    action_receipt_id: str | None = None,
    idempotency_key: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    occurred_at: datetime | None = None,
) -> SourceMutationRecord:
    existing = db.execute(
        select(SourceMutationRecord).where(
            SourceMutationRecord.project_id == project_id,
            SourceMutationRecord.source_system == source_system,
            SourceMutationRecord.mutation_id == mutation_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    reserve_usage_meter(db, project_id, METER_SOURCE_MUTATIONS)
    metadata_payload = dict(metadata or {})
    receipt = _find_receipt(
        db,
        project_id=project_id,
        action_id=zroky_action_id,
        receipt_id=action_receipt_id,
        idempotency_key=idempotency_key,
    )
    resolved_action_id = zroky_action_id or (receipt.action_intent_id if receipt is not None else None)
    resolved_receipt_id = receipt.id if receipt is not None else action_receipt_id
    classification = _classify_mutation(
        action_type=action_type,
        actor_type=actor_type,
        metadata=metadata_payload,
        receipt=receipt,
    )
    row = SourceMutationRecord(
        project_id=project_id,
        source_system=_bounded(source_system, max_length=64) or "unknown",
        mutation_id=_bounded(mutation_id, max_length=255) or "unknown",
        action_type=_bounded(action_type, max_length=64),
        resource_type=_bounded(resource_type, max_length=64),
        resource_id=_bounded(resource_id, max_length=255),
        system_ref=_bounded(system_ref, max_length=255),
        actor_type=_bounded(actor_type, max_length=64),
        actor_id=_bounded(actor_id, max_length=255),
        zroky_action_id=_bounded(resolved_action_id, max_length=36),
        action_receipt_id=_bounded(resolved_receipt_id, max_length=36),
        idempotency_key=_bounded(idempotency_key, max_length=255),
        classification=classification,
        metadata_json=_json_dumps(metadata_payload),
        occurred_at=occurred_at or _now(),
    )
    db.add(row)
    db.flush()
    return row


def list_source_mutations(
    db: Session,
    *,
    project_id: str,
    classification: str | None = None,
    unreceipted_only: bool = False,
    limit: int = 100,
) -> list[SourceMutationRecord]:
    query = select(SourceMutationRecord).where(SourceMutationRecord.project_id == project_id)
    if classification:
        query = query.where(SourceMutationRecord.classification == classification)
    if unreceipted_only:
        query = query.where(SourceMutationRecord.classification.in_(BYPASS_CLASSIFICATIONS))
    return list(
        db.execute(
            query.order_by(desc(SourceMutationRecord.occurred_at), desc(SourceMutationRecord.id)).limit(limit)
        ).scalars()
    )


def source_mutation_summary(
    db: Session,
    *,
    project_id: str,
) -> dict[str, int]:
    rows = db.execute(
        select(SourceMutationRecord.classification).where(SourceMutationRecord.project_id == project_id)
    ).scalars().all()
    counts = Counter(rows)
    return {
        "total": len(rows),
        "matched_receipt": counts[CLASS_MATCHED_RECEIPT],
        "authorized_external": counts[CLASS_AUTHORIZED_EXTERNAL],
        "legacy_path": counts[CLASS_LEGACY_PATH],
        "unmanaged_agent_action": counts[CLASS_UNMANAGED_AGENT_ACTION],
        "policy_bypass": counts[CLASS_POLICY_BYPASS],
        "unknown_actor": counts[CLASS_UNKNOWN_ACTOR],
        "unreceipted": sum(counts[item] for item in BYPASS_CLASSIFICATIONS),
    }


def source_mutation_to_dict(row: SourceMutationRecord) -> dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "source_system": row.source_system,
        "mutation_id": row.mutation_id,
        "action_type": row.action_type,
        "resource_type": row.resource_type,
        "resource_id": row.resource_id,
        "system_ref": row.system_ref,
        "actor_type": row.actor_type,
        "actor_id": row.actor_id,
        "zroky_action_id": row.zroky_action_id,
        "action_receipt_id": row.action_receipt_id,
        "idempotency_key": row.idempotency_key,
        "classification": row.classification,
        "metadata": _json_loads(row.metadata_json, {}),
        "occurred_at": row.occurred_at,
        "created_at": row.created_at,
    }
