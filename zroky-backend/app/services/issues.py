"""
Issues service — upsert and query helpers for the denormalized `issues` table.

The `issues` table is a fast-read denormalized view grouped by
(project_id, failure_code, prompt_fingerprint, agent_name).
Rows are created/updated by the incremental issues worker and queried
by the GET /v1/issues API.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Issue

logger = logging.getLogger(__name__)

_OPEN = "open"
_RESOLVED = "resolved"
_IGNORED = "ignored"
VALID_STATUSES = frozenset({_OPEN, _RESOLVED, _IGNORED})


# ── upsert ────────────────────────────────────────────────────────────────────

def _derive_severity(failure_code: str, occurrence_count: int, blast_radius_usd: float) -> str:
    """Heuristic severity: critical / high / medium / low."""
    if failure_code in ("AUTH_FAILURE", "COST_SPIKE") or blast_radius_usd >= 10.0:
        return "critical"
    if failure_code in ("LOOP_DETECTED", "TOKEN_OVERFLOW") or occurrence_count >= 10:
        return "high"
    if occurrence_count >= 3 or blast_radius_usd >= 1.0:
        return "medium"
    return "low"


def upsert_issue(
    db: Session,
    *,
    project_id: str,
    failure_code: str,
    prompt_fingerprint: str | None,
    agent_name: str | None,
    call_id: str,
    diagnosis_id: str,
    occurred_at: datetime,
    call_cost_usd: float = 0.0,
    evidence: dict[str, Any] | None = None,
) -> Issue:
    """Upsert a grouped issue row.

    On INSERT: creates a new open issue with occurrence_count=1.
    On CONFLICT (group key): increments occurrence_count, refreshes
    last_seen_at and sample_* columns.  If the issue was resolved it
    is re-opened automatically.

    Falls back to a SELECT + UPDATE on databases that do not support
    ON CONFLICT (e.g., SQLite used in tests).
    """
    now = datetime.now(timezone.utc)
    evidence_json = json.dumps(evidence, separators=(",", ":")) if evidence else None

    if db.bind is not None and db.bind.dialect.name == "postgresql":
        return _upsert_postgresql(
            db,
            project_id=project_id,
            failure_code=failure_code,
            prompt_fingerprint=prompt_fingerprint,
            agent_name=agent_name,
            call_id=call_id,
            diagnosis_id=diagnosis_id,
            occurred_at=occurred_at,
            call_cost_usd=call_cost_usd,
            evidence_json=evidence_json,
            now=now,
        )
    return _upsert_portable(
        db,
        project_id=project_id,
        failure_code=failure_code,
        prompt_fingerprint=prompt_fingerprint,
        agent_name=agent_name,
        call_id=call_id,
        diagnosis_id=diagnosis_id,
        occurred_at=occurred_at,
        call_cost_usd=call_cost_usd,
        evidence_json=evidence_json,
        now=now,
    )


def _upsert_postgresql(
    db: Session,
    *,
    project_id: str,
    failure_code: str,
    prompt_fingerprint: str | None,
    agent_name: str | None,
    call_id: str,
    diagnosis_id: str,
    occurred_at: datetime,
    call_cost_usd: float,
    evidence_json: str | None,
    now: datetime,
) -> Issue:
    new_count = Issue.occurrence_count + 1
    new_blast = Issue.blast_radius_usd + call_cost_usd
    stmt = (
        pg_insert(Issue)
        .values(
            id=str(uuid4()),
            project_id=project_id,
            failure_code=failure_code,
            prompt_fingerprint=prompt_fingerprint,
            agent_name=agent_name,
            status=_OPEN,
            occurrence_count=1,
            blast_radius_usd=call_cost_usd,
            first_seen_at=occurred_at,
            last_seen_at=occurred_at,
            sample_call_id=call_id,
            sample_diagnosis_id=diagnosis_id,
            sample_evidence_json=evidence_json,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_update(
            constraint="ux_issues_group_key",
            set_={
                "occurrence_count": new_count,
                "blast_radius_usd": new_blast,
                "last_seen_at": occurred_at,
                "sample_call_id": call_id,
                "sample_diagnosis_id": diagnosis_id,
                "sample_evidence_json": evidence_json,
                "status": _OPEN,
                "resolved_at": None,
                "updated_at": now,
            },
        )
        .returning(Issue.id)
    )
    result = db.execute(stmt)
    db.commit()
    issue_id = result.scalar_one()
    issue = db.execute(select(Issue).where(Issue.id == issue_id)).scalar_one()
    issue.severity = _derive_severity(failure_code, issue.occurrence_count, float(issue.blast_radius_usd or 0))
    db.commit()
    return issue


def _upsert_portable(
    db: Session,
    *,
    project_id: str,
    failure_code: str,
    prompt_fingerprint: str | None,
    agent_name: str | None,
    call_id: str,
    diagnosis_id: str,
    occurred_at: datetime,
    call_cost_usd: float,
    evidence_json: str | None,
    now: datetime,
) -> Issue:
    existing = db.execute(
        select(Issue).where(
            Issue.project_id == project_id,
            Issue.failure_code == failure_code,
            Issue.prompt_fingerprint == prompt_fingerprint,
            Issue.agent_name == agent_name,
        )
    ).scalar_one_or_none()

    if existing is not None:
        existing.occurrence_count = (existing.occurrence_count or 0) + 1
        existing.blast_radius_usd = float(existing.blast_radius_usd or 0) + call_cost_usd
        existing.last_seen_at = occurred_at
        existing.sample_call_id = call_id
        existing.sample_diagnosis_id = diagnosis_id
        existing.sample_evidence_json = evidence_json
        existing.status = _OPEN
        existing.resolved_at = None
        existing.severity = _derive_severity(failure_code, existing.occurrence_count, float(existing.blast_radius_usd or 0))
        existing.updated_at = now
        db.add(existing)
        try:
            db.commit()
            db.refresh(existing)
        except Exception:
            db.rollback()
            raise
        return existing

    issue = Issue(
        id=str(uuid4()),
        project_id=project_id,
        failure_code=failure_code,
        prompt_fingerprint=prompt_fingerprint,
        agent_name=agent_name,
        status=_OPEN,
        occurrence_count=1,
        blast_radius_usd=call_cost_usd,
        severity=_derive_severity(failure_code, 1, call_cost_usd),
        first_seen_at=occurred_at,
        last_seen_at=occurred_at,
        sample_call_id=call_id,
        sample_diagnosis_id=diagnosis_id,
        sample_evidence_json=evidence_json,
        created_at=now,
        updated_at=now,
    )
    db.add(issue)
    try:
        db.commit()
        db.refresh(issue)
    except IntegrityError:
        db.rollback()
        return _upsert_portable(
            db,
            project_id=project_id,
            failure_code=failure_code,
            prompt_fingerprint=prompt_fingerprint,
            agent_name=agent_name,
            call_id=call_id,
            diagnosis_id=diagnosis_id,
            occurred_at=occurred_at,
            call_cost_usd=call_cost_usd,
            evidence_json=evidence_json,
            now=now,
        )
    return issue


# ── resolve ───────────────────────────────────────────────────────────────────

def resolve_issue(
    db: Session,
    *,
    project_id: str,
    issue_id: str,
    fix_id: str | None = None,
    resolution_source: str = "manual",
) -> Issue | None:
    """Mark an issue as resolved. Returns the updated issue or None if not found."""
    issue = db.execute(
        select(Issue).where(Issue.project_id == project_id, Issue.id == issue_id)
    ).scalar_one_or_none()
    if issue is None:
        return None
    now = datetime.now(timezone.utc)
    issue.status = _RESOLVED
    issue.resolved_at = now
    issue.resolution_source = resolution_source
    if fix_id:
        issue.last_fix_id = fix_id
    issue.updated_at = now
    db.add(issue)
    db.commit()
    db.refresh(issue)
    return issue


# ── ignore ────────────────────────────────────────────────────────────────────

def ignore_issue(
    db: Session,
    *,
    project_id: str,
    issue_id: str,
) -> Issue | None:
    """Mark an open issue as ignored. Returns the updated issue or None if not found."""
    issue = db.execute(
        select(Issue).where(Issue.project_id == project_id, Issue.id == issue_id)
    ).scalar_one_or_none()
    if issue is None:
        return None
    now = datetime.now(timezone.utc)
    issue.status = _IGNORED
    issue.updated_at = now
    db.add(issue)
    db.commit()
    db.refresh(issue)
    return issue
