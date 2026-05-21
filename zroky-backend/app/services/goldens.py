"""
Goldens service — CRUD for `golden_sets` + `golden_traces` (Pilot tier).

Plan refs: §5.2 schema, §6.4 replay flow, §13 API surface.

A `GoldenSet` is a named collection of canonical traces owned by a project.
Each `GoldenTrace` pins one historical `Call` plus the expected output text,
expected token / cost / latency baselines, optional per-trace judge criteria,
and a weight used when the judge engine aggregates pass-rate.

Tenant scoping: every read + write goes through `project_id` so cross-tenant
access is impossible at the service layer (defence-in-depth on top of the
Postgres RLS policy enabled in migration 0049). Routes still enforce
`require_tenant_id` so the project id is always derived from the auth
context — callers cannot spoof it via request body.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Call, GoldenSet, GoldenTrace

logger = logging.getLogger(__name__)


# ── exceptions ───────────────────────────────────────────────────────────────


class GoldenSetNameConflict(Exception):
    """A golden set with the same name already exists for this project."""


# ── golden set CRUD ──────────────────────────────────────────────────────────


def create_golden_set(
    db: Session,
    *,
    project_id: str,
    name: str,
    description: str | None = None,
    judge_config_json: str | None = None,
) -> GoldenSet:
    """Create a golden set. Raises GoldenSetNameConflict if the (project_id,
    name) pair already exists."""
    name_norm = name.strip()
    if not name_norm:
        raise ValueError("name must be non-empty")

    now = datetime.now(timezone.utc)
    golden_set = GoldenSet(
        id=str(uuid4()),
        project_id=project_id,
        name=name_norm,
        description=description,
        judge_config_json=judge_config_json,
        created_at=now,
        updated_at=now,
    )
    db.add(golden_set)
    try:
        db.commit()
        db.refresh(golden_set)
    except IntegrityError as exc:
        db.rollback()
        raise GoldenSetNameConflict(
            f"golden set name {name_norm!r} already exists for project {project_id}"
        ) from exc
    return golden_set


def get_golden_set(
    db: Session, *, project_id: str, golden_set_id: str
) -> GoldenSet | None:
    return db.execute(
        select(GoldenSet).where(
            GoldenSet.project_id == project_id,
            GoldenSet.id == golden_set_id,
        )
    ).scalar_one_or_none()


def list_golden_sets(
    db: Session,
    *,
    project_id: str,
    limit: int = 20,
    before_created_at: datetime | None = None,
    before_id: str | None = None,
) -> list[GoldenSet]:
    """List golden sets for a project, newest-first by created_at.

    `before_created_at` + `before_id` form an opaque cursor: callers pass
    the last row from the prior page to retrieve the next page. The route
    layer encodes/decodes this as a base64 token.
    """
    conditions = [GoldenSet.project_id == project_id]
    if before_created_at is not None and before_id is not None:
        # strict less-than on (created_at, id) for stable pagination
        from sqlalchemy import and_, or_

        conditions.append(
            or_(
                GoldenSet.created_at < before_created_at,
                and_(
                    GoldenSet.created_at == before_created_at,
                    GoldenSet.id < before_id,
                ),
            )
        )

    rows = db.execute(
        select(GoldenSet)
        .where(*conditions)
        .order_by(GoldenSet.created_at.desc(), GoldenSet.id.desc())
        .limit(limit)
    ).scalars().all()
    return list(rows)


def update_golden_set(
    db: Session,
    *,
    project_id: str,
    golden_set_id: str,
    name: str | None = None,
    description: str | None = None,
    judge_config_json: str | None = None,
    clear_description: bool = False,
    clear_judge_config: bool = False,
) -> GoldenSet | None:
    """Partial update of a golden set. Pass `clear_*=True` to set the
    optional field back to NULL. Raises GoldenSetNameConflict on name clash.
    """
    golden_set = get_golden_set(
        db, project_id=project_id, golden_set_id=golden_set_id
    )
    if golden_set is None:
        return None

    if name is not None:
        name_norm = name.strip()
        if not name_norm:
            raise ValueError("name must be non-empty")
        golden_set.name = name_norm

    if clear_description:
        golden_set.description = None
    elif description is not None:
        golden_set.description = description

    if clear_judge_config:
        golden_set.judge_config_json = None
    elif judge_config_json is not None:
        golden_set.judge_config_json = judge_config_json

    golden_set.updated_at = datetime.now(timezone.utc)
    db.add(golden_set)
    try:
        db.commit()
        db.refresh(golden_set)
    except IntegrityError as exc:
        db.rollback()
        raise GoldenSetNameConflict(
            f"golden set name {golden_set.name!r} already exists for project {project_id}"
        ) from exc
    return golden_set


def delete_golden_set(
    db: Session, *, project_id: str, golden_set_id: str
) -> bool:
    """Delete a golden set and all its traces. Returns True if a row was
    deleted.

    Postgres enforces FK ON DELETE CASCADE on `golden_traces.golden_set_id`,
    but SQLite (used in unit tests) does not enforce FK constraints by
    default. To stay backend-agnostic we explicitly bulk-delete the child
    traces first in a single statement, then delete the parent.
    """
    from sqlalchemy import delete as sa_delete, update as sa_update

    from app.db.models import Project

    golden_set = get_golden_set(
        db, project_id=project_id, golden_set_id=golden_set_id
    )
    if golden_set is None:
        return False
    db.execute(
        sa_delete(GoldenTrace).where(
            GoldenTrace.project_id == project_id,
            GoldenTrace.golden_set_id == golden_set_id,
        )
    )
    # Module 9: clear any Project.default_golden_set_id that pointed at
    # this set so the dispatch endpoint stops resolving it. Scoped to
    # the same project_id (cross-project references should never exist
    # given application-layer enforcement, but bound to project to be
    # defensive).
    db.execute(
        sa_update(Project)
        .where(
            Project.id == project_id,
            Project.default_golden_set_id == golden_set_id,
        )
        .values(default_golden_set_id=None)
    )
    db.delete(golden_set)
    db.commit()
    return True


# ── golden trace CRUD ────────────────────────────────────────────────────────


def add_trace(
    db: Session,
    *,
    project_id: str,
    golden_set_id: str,
    call_id: str | None = None,
    expected_output_text: str | None = None,
    expected_tokens: int | None = None,
    expected_cost_usd: float | None = None,
    expected_latency_ms: int | None = None,
    criteria_json: str | None = None,
    weight: float = 1.0,
) -> GoldenTrace | None:
    """Add a trace to a golden set. Returns None if the parent set does not
    exist for the project. If `call_id` is provided, verifies the call
    belongs to the same project (defence-in-depth)."""
    parent = get_golden_set(
        db, project_id=project_id, golden_set_id=golden_set_id
    )
    if parent is None:
        return None

    if call_id is not None:
        call_row = db.execute(
            select(Call).where(Call.id == call_id, Call.project_id == project_id)
        ).scalar_one_or_none()
        if call_row is None:
            raise ValueError(
                f"call_id {call_id!r} not found for project {project_id}"
            )

    if weight <= 0:
        raise ValueError("weight must be > 0")

    now = datetime.now(timezone.utc)
    trace = GoldenTrace(
        id=str(uuid4()),
        golden_set_id=golden_set_id,
        project_id=project_id,
        call_id=call_id,
        expected_output_text=expected_output_text,
        expected_tokens=expected_tokens,
        expected_cost_usd=expected_cost_usd,
        expected_latency_ms=expected_latency_ms,
        criteria_json=criteria_json,
        weight=weight,
        created_at=now,
        updated_at=now,
    )
    db.add(trace)
    db.commit()
    db.refresh(trace)
    return trace


def list_traces(
    db: Session, *, project_id: str, golden_set_id: str
) -> list[GoldenTrace] | None:
    """List all traces in a golden set. Returns None if the set does not
    exist (so the route can 404 cleanly)."""
    parent = get_golden_set(
        db, project_id=project_id, golden_set_id=golden_set_id
    )
    if parent is None:
        return None
    rows = db.execute(
        select(GoldenTrace)
        .where(
            GoldenTrace.project_id == project_id,
            GoldenTrace.golden_set_id == golden_set_id,
        )
        .order_by(GoldenTrace.created_at.asc(), GoldenTrace.id.asc())
    ).scalars().all()
    return list(rows)


def get_trace(
    db: Session,
    *,
    project_id: str,
    golden_set_id: str,
    trace_id: str,
) -> GoldenTrace | None:
    return db.execute(
        select(GoldenTrace).where(
            GoldenTrace.project_id == project_id,
            GoldenTrace.golden_set_id == golden_set_id,
            GoldenTrace.id == trace_id,
        )
    ).scalar_one_or_none()


def remove_trace(
    db: Session,
    *,
    project_id: str,
    golden_set_id: str,
    trace_id: str,
) -> bool:
    """Remove a trace from a golden set. Returns True if a row was deleted."""
    trace = get_trace(
        db,
        project_id=project_id,
        golden_set_id=golden_set_id,
        trace_id=trace_id,
    )
    if trace is None:
        return False
    db.delete(trace)
    db.commit()
    return True


def count_traces(
    db: Session, *, project_id: str, golden_set_id: str
) -> int:
    """Cheap count helper used by list_golden_sets responses."""
    from sqlalchemy import func as sa_func

    result = db.execute(
        select(sa_func.count(GoldenTrace.id)).where(
            GoldenTrace.project_id == project_id,
            GoldenTrace.golden_set_id == golden_set_id,
        )
    ).scalar()
    return int(result or 0)
