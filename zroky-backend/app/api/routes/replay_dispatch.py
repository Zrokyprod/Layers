"""
/v1/replay/dispatch — GitHub-Action-friendly replay dispatch surface
(ZROKY-TECHNICAL-PLAN-V2 §6.4 Module 9).

This is the surface the `zroky/regression-ci@v1` GitHub Action POSTs
to. Compared to the lower-level `POST /v1/goldens/{id}/run` endpoint,
this surface:

  * Accepts an OPTIONAL `golden_set_id`. When omitted, the project's
    `default_golden_set_id` (added in migration 0060) is resolved.
    A 422 is returned if neither is provided.
  * Always returns a `summary_url` for the GitHub Action to post as the
    PR check `details_url`.
  * Honors idempotency on `(project_id, golden_set_id, git_sha)` exactly
    like the goldens-router endpoint — this is implemented in
    `app.services.replay_runs.dispatch_replay_run` so both surfaces
    share the same horizon rules.

Auth model: same as the rest of the Pilot tier — tenant-scoped via
`require_tenant_id` (which accepts both API-key and JWT auth) and
plan-gated via `require_entitlement("pilot.autopilot_enabled")` at the
router level so customers on Free / Watch-only get a 402.
"""
from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.entitlements import require_entitlement
from app.api.dependencies.tenant import require_tenant_id
from app.core.limiter import limiter
from app.db.models import Project
from app.db.session import get_db_session
from app.services.goldens import get_golden_set
from app.services.replay_runs import (
    VALID_TRIGGERS,
    build_summary_url,
    dispatch_replay_run,
    was_idempotent_hit,
)

router = APIRouter(
    prefix="/v1/replay",
    dependencies=[Depends(require_entitlement("pilot.autopilot_enabled"))],
)
logger = logging.getLogger(__name__)


# ── schemas ──────────────────────────────────────────────────────────────────


class ReplayDispatchRequest(BaseModel):
    """Inbound payload for `POST /v1/replay/dispatch`.

    All fields are optional because the GitHub Action's most common
    invocation looks like::

        POST /v1/replay/dispatch
        Authorization: Bearer <project-api-key>
        { "git_sha": "abc123", "branch_name": "feature/foo", "pr_number": 42 }

    The project's default golden set is resolved server-side when
    `golden_set_id` is omitted.
    """

    golden_set_id: str | None = None
    # `trigger` defaults to "github" here (vs "manual" on the
    # goldens-router endpoint) because the only callers of this
    # surface are CI integrations.
    trigger: str = "github"
    git_sha: str | None = None
    branch_name: str | None = None
    pr_number: int | None = None
    commit_message: str | None = None
    # Option A (honesty fix) — see GoldenRunRequest for full rationale.
    # CI callers can set these to test a candidate prompt/model coming
    # from a PR diff; the dispatcher rejects them when
    # REPLAY_REAL_LLM_ENABLED is False.
    candidate_prompt_override: str | None = None
    candidate_model_override: str | None = None


class ReplayDispatchResponse(BaseModel):
    id: str
    project_id: str
    golden_set_id: str
    trigger: str
    git_sha: str | None
    status: str
    created_at: datetime
    summary_url: str
    # True when the dispatch hit the (project_id, golden_set_id,
    # git_sha) idempotency window and the response refers to a
    # pre-existing run.
    idempotent: bool = False


# ── helpers ──────────────────────────────────────────────────────────────────


def _resolve_default_golden_set_id(
    db: Session, *, project_id: str
) -> str | None:
    """Return `projects.default_golden_set_id` for the tenant, or None.

    Reads only the column we need (avoids triggering relationship
    loaders on the Project model) and tolerates a missing project row
    by returning None — the caller maps that to a 422 with a
    diagnostic message.
    """
    row = db.execute(
        select(Project.default_golden_set_id).where(Project.id == project_id)
    ).first()
    if row is None:
        return None
    return row[0]


# ── route ────────────────────────────────────────────────────────────────────


@router.post(
    "/dispatch",
    response_model=ReplayDispatchResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit("30/minute")
def dispatch_replay(
    request: Request,
    body: ReplayDispatchRequest | None = None,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> ReplayDispatchResponse:
    """Dispatch a replay run via the GitHub-Action-friendly surface.

    Resolution order for the target golden set:
      1) explicit `golden_set_id` in the body (must belong to the tenant)
      2) project's `default_golden_set_id` (Module 9 / migration 0060)

    Returns 422 when neither is available, 404 when the resolved set
    no longer exists for the tenant, and 202 on accept.
    """
    payload = body or ReplayDispatchRequest()

    if payload.trigger not in VALID_TRIGGERS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"trigger must be one of {sorted(VALID_TRIGGERS)}",
        )

    # ── resolve target set ───────────────────────────────────────────
    target_set_id = payload.golden_set_id
    if not target_set_id:
        target_set_id = _resolve_default_golden_set_id(
            db, project_id=tenant_id
        )
    if not target_set_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "No golden_set_id provided and project has no "
                "default_golden_set_id configured."
            ),
        )

    # When the caller passed an explicit set, validate tenancy up-front
    # so the 404 fires before we even reach the service. The service
    # would also return None on a missing set, but this gives a more
    # precise log line.
    if payload.golden_set_id is not None:
        if get_golden_set(
            db, project_id=tenant_id, golden_set_id=target_set_id
        ) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Golden set not found",
            )

    # ── dispatch ─────────────────────────────────────────────────────
    try:
        run = dispatch_replay_run(
            db,
            project_id=tenant_id,
            golden_set_id=target_set_id,
            trigger=payload.trigger,
            git_sha=payload.git_sha,
            branch_name=payload.branch_name,
            pr_number=payload.pr_number,
            commit_message=payload.commit_message,
            candidate_prompt_override=payload.candidate_prompt_override,
            candidate_model_override=payload.candidate_model_override,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    if run is None:
        # Stale default_golden_set_id pointer (set was deleted between
        # the project read and the service call). Map to 422 because
        # the project config is at fault, not the request.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Resolved golden set no longer exists. Update the "
                "project's default_golden_set_id."
            ),
        )

    is_idempotent = was_idempotent_hit(run)

    # Enqueue the Celery executor task — same contract as
    # `POST /v1/goldens/{id}/run`. Skip on idempotent hit because the
    # original dispatch already enqueued.
    if not is_idempotent:
        try:
            from app.worker.tasks import process_replay_run

            process_replay_run.apply_async(
                args=(tenant_id, run.id),
                queue="diagnosis_pattern",
                countdown=2,
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "replay_dispatch.enqueue_failed run=%s — row remains pending",
                run.id,
                exc_info=True,
            )

    logger.info(
        "replay_dispatch project=%s run=%s set=%s sha=%s idempotent=%s",
        tenant_id,
        run.id,
        target_set_id,
        payload.git_sha,
        is_idempotent,
    )

    return ReplayDispatchResponse(
        id=run.id,
        project_id=run.project_id,
        golden_set_id=run.golden_set_id,
        trigger=run.trigger,
        git_sha=run.git_sha,
        status=run.status,
        created_at=run.created_at,
        summary_url=build_summary_url(run),
        idempotent=is_idempotent,
    )
