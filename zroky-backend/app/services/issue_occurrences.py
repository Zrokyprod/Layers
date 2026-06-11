from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import IssueOccurrence
from app.services.privacy import mask_value


@dataclass(frozen=True)
class IssueOccurrenceStats:
    occurrence_count: int
    affected_trace_count: int
    affected_user_count: int


def occurrence_key(*, call_id: str | None, diagnosis_id: str | None) -> str:
    call = (call_id or "").strip()
    if call:
        return f"call:{call}"
    diagnosis = (diagnosis_id or "").strip()
    if diagnosis:
        return f"diagnosis:{diagnosis}"
    return f"generated:{uuid4()}"


def occurrence_exists(
    db: Session,
    *,
    project_id: str,
    issue_id: str,
    key: str,
) -> bool:
    return (
        db.execute(
            select(IssueOccurrence.id).where(
                IssueOccurrence.project_id == project_id,
                IssueOccurrence.issue_id == issue_id,
                IssueOccurrence.occurrence_key == key,
            )
        ).scalar_one_or_none()
        is not None
    )


def record_issue_occurrence(
    db: Session,
    *,
    project_id: str,
    issue_id: str,
    key: str,
    failure_code: str,
    detector: str,
    occurred_at: datetime,
    call_id: str | None = None,
    diagnosis_id: str | None = None,
    trace_id: str | None = None,
    user_id: str | None = None,
    grouping_signature: str | None = None,
    evidence: dict[str, Any] | None = None,
) -> IssueOccurrence:
    existing = db.execute(
        select(IssueOccurrence).where(
            IssueOccurrence.project_id == project_id,
            IssueOccurrence.issue_id == issue_id,
            IssueOccurrence.occurrence_key == key,
        )
    ).scalar_one_or_none()

    evidence_json = (
        json.dumps(mask_value(evidence), separators=(",", ":"), default=str)
        if evidence
        else None
    )
    now = datetime.now(timezone.utc)
    if existing is not None:
        existing.failure_code = failure_code
        existing.detector = detector
        existing.call_id = call_id or existing.call_id
        existing.diagnosis_id = diagnosis_id or existing.diagnosis_id
        existing.trace_id = trace_id or existing.trace_id
        existing.user_id = user_id or existing.user_id
        existing.grouping_signature = grouping_signature or existing.grouping_signature
        existing.occurred_at = occurred_at
        if evidence_json is not None:
            existing.evidence_json = evidence_json
        existing.updated_at = now
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing

    row = IssueOccurrence(
        id=str(uuid4()),
        project_id=project_id,
        issue_id=issue_id,
        occurrence_key=key,
        call_id=call_id or None,
        diagnosis_id=diagnosis_id or None,
        trace_id=trace_id or None,
        user_id=user_id or None,
        failure_code=failure_code,
        detector=detector,
        grouping_signature=grouping_signature or None,
        occurred_at=occurred_at,
        evidence_json=evidence_json,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def issue_occurrence_stats(
    db: Session,
    *,
    project_id: str,
    issue_id: str,
) -> IssueOccurrenceStats:
    rows = db.execute(
        select(
            func.count(IssueOccurrence.id),
            func.count(func.distinct(IssueOccurrence.trace_id)),
            func.count(func.distinct(IssueOccurrence.user_id)),
        ).where(
            IssueOccurrence.project_id == project_id,
            IssueOccurrence.issue_id == issue_id,
        )
    ).one()
    occurrence_count = int(rows[0] or 0)
    trace_count = int(rows[1] or 0)
    user_count = int(rows[2] or 0)
    return IssueOccurrenceStats(
        occurrence_count=occurrence_count,
        affected_trace_count=max(trace_count, occurrence_count),
        affected_user_count=user_count,
    )
