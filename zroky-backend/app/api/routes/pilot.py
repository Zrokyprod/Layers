"""
/v1/pilot/* — Pilot-tier autopilot surface.

API surface per ZROKY-TECHNICAL-PLAN-V2 §13 (4 endpoints):

  GET  /v1/pilot/actions                cursor-paginated; filters by
                                        status, tier, action_type, anomaly_id
  POST /v1/pilot/actions/{id}/revert    200; 404 if missing; 409 if not
                                        applied OR not tier-1
  GET  /v1/pilot/policy                 returns current policy
                                        (seeds the §6.3 default on first read)
  PUT  /v1/pilot/policy                 validates body; upserts; returns row

Entitlements plan-gate (402 Payment Required) — Module 6 attaches
`require_entitlement("pilot.autopilot_enabled")` at the router level
so every endpoint here is gated uniformly per plan §10.x.
"""
from __future__ import annotations

import base64
import json
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.entitlements import require_entitlement
from app.api.dependencies.tenant import require_tenant_context, require_tenant_id
from app.core.limiter import limiter
from app.db.session import get_db_session
from app.db.models import Anomaly, PilotAction, ReplayRun
from app.services.pilot import (
    DEFAULT_POLICY,
    PilotActionRevertError,
    PolicyValidationError,
    VALID_ACTION_STATUSES,
    VALID_TIERS,
    get_or_create_policy,
    get_pilot_action,
    list_pilot_actions,
    parse_policy_json,
    revert_pilot_action,
    upsert_policy,
)
from app.services.pilot_pr_dispatch import (
    TierActionStateError,
    cancel_pilot_action,
    evaluate_tier2_dispatch,
)

router = APIRouter(
    prefix="/v1/pilot",
    dependencies=[Depends(require_entitlement("pilot.autopilot_enabled"))],
)
logger = logging.getLogger(__name__)

_DEFAULT_LIMIT = 20
_MAX_LIMIT = 100


# ── schemas ──────────────────────────────────────────────────────────────────


class PilotActionResponse(BaseModel):
    id: str
    project_id: str
    anomaly_id: str
    tier: int
    action_type: str
    status: str
    payload_json: str | None
    applied_at: datetime | None
    reverted_at: datetime | None
    audit_user: str | None
    # Module 10 — Tier-2 columns (migration 0061). Always NULL on
    # tier-1 / tier-3 rows.
    pr_url: str | None = None
    pr_fingerprint: str | None = None
    replay_run_id_gate: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PilotActionListResponse(BaseModel):
    items: list[PilotActionResponse]
    next_cursor: str | None
    total_in_page: int


class PilotPolicyPayload(BaseModel):
    """Strongly-typed mirror of the policy_json schema (plan §6.3).

    Defaults intentionally mirror `services.pilot.DEFAULT_POLICY` so a
    caller can omit any field and have it default to the canonical value.
    """

    tier1_enabled: bool = Field(default=DEFAULT_POLICY["tier1_enabled"])
    tier1_actions: list[str] = Field(
        default_factory=lambda: list(DEFAULT_POLICY["tier1_actions"])
    )
    tier1_min_confidence: float = Field(
        default=DEFAULT_POLICY["tier1_min_confidence"], ge=0.0, le=1.0
    )
    tier1_max_blast_radius: str = Field(
        default=DEFAULT_POLICY["tier1_max_blast_radius"], min_length=1
    )
    tier1_daily_cap: int = Field(
        default=DEFAULT_POLICY["tier1_daily_cap"], ge=0
    )
    tier2_enabled: bool = Field(default=DEFAULT_POLICY["tier2_enabled"])
    tier2_actions: list[str] = Field(
        default_factory=lambda: list(DEFAULT_POLICY["tier2_actions"])
    )
    tier2_require_replay_pass: bool = Field(
        default=DEFAULT_POLICY["tier2_require_replay_pass"]
    )
    # Module 10 — per-project Tier-2 daily PR cap. None = fall back to
    # the global PILOT_TIER2_DAILY_PR_CAP setting (10 by default).
    tier2_daily_cap: int | None = Field(
        default=DEFAULT_POLICY["tier2_daily_cap"], ge=0
    )
    tier3_alert_channels: list[str] = Field(
        default_factory=lambda: list(DEFAULT_POLICY["tier3_alert_channels"])
    )
    kill_switch: bool = Field(default=DEFAULT_POLICY["kill_switch"])


class PilotPolicyResponse(BaseModel):
    id: str
    project_id: str
    policy: PilotPolicyPayload
    updated_by: str | None
    created_at: datetime
    updated_at: datetime


# ── helpers ──────────────────────────────────────────────────────────────────


def _encode_cursor(created_at: datetime, action_id: str) -> str:
    payload = json.dumps(
        {"t": created_at.isoformat(), "id": action_id}, separators=(",", ":")
    )
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, str] | None:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        return datetime.fromisoformat(payload["t"]), str(payload["id"])
    except Exception:
        return None


def _to_policy_response(policy) -> PilotPolicyResponse:
    parsed = parse_policy_json(policy.policy_json)
    return PilotPolicyResponse(
        id=policy.id,
        project_id=policy.project_id,
        policy=PilotPolicyPayload(**parsed),
        updated_by=policy.updated_by,
        created_at=policy.created_at,
        updated_at=policy.updated_at,
    )


# ── routes: actions ──────────────────────────────────────────────────────────


@router.get("/actions", response_model=PilotActionListResponse)
@limiter.limit("60/minute")
def list_actions(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    tier: int | None = Query(default=None, ge=1, le=3),
    action_type: str | None = Query(default=None),
    anomaly_id: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> PilotActionListResponse:
    if status_filter is not None and status_filter not in VALID_ACTION_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "status must be one of: "
                + ", ".join(sorted(VALID_ACTION_STATUSES))
            ),
        )

    before_created_at: datetime | None = None
    before_id: str | None = None
    if cursor:
        decoded = _decode_cursor(cursor)
        if decoded is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid cursor value.",
            )
        before_created_at, before_id = decoded

    rows = list_pilot_actions(
        db,
        project_id=tenant_id,
        status=status_filter,
        tier=tier,
        action_type=action_type,
        anomaly_id=anomaly_id,
        limit=limit + 1,
        before_created_at=before_created_at,
        before_id=before_id,
    )
    has_next = len(rows) > limit
    page = rows[:limit]

    next_cursor: str | None = None
    if has_next and page:
        last = page[-1]
        next_cursor = _encode_cursor(last.created_at, last.id)

    return PilotActionListResponse(
        items=[PilotActionResponse.model_validate(r) for r in page],
        next_cursor=next_cursor,
        total_in_page=len(page),
    )


@router.post(
    "/actions/{action_id}/revert",
    response_model=PilotActionResponse,
)
@limiter.limit("30/minute")
def revert_action(
    request: Request,
    action_id: str,
    context=Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> PilotActionResponse:
    """Mark a tier-1 applied action as reverted. The actual config
    rollback is handled by a downstream worker (deferred to a later
    module). Returns 409 if the action is not in `applied` state or is
    not tier-1."""
    try:
        action = revert_pilot_action(
            db,
            project_id=context.tenant_id,
            action_id=action_id,
            audit_user=context.subject,
        )
    except PilotActionRevertError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    if action is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pilot action not found",
        )
    return PilotActionResponse.model_validate(action)


# ── routes: tier-2 cancel + retry (Module 10) ────────────────────────────────


@router.post(
    "/actions/{action_id}/cancel",
    response_model=PilotActionResponse,
)
@limiter.limit("30/minute")
def cancel_action(
    request: Request,
    action_id: str,
    context=Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> PilotActionResponse:
    """Cancel a `pending` tier-2 action — the founder console uses
    this to intervene before the auto-PR opens.

    Returns:
      404 if the action does not exist for this tenant.
      409 if the action is tier-1 (use /revert) or not in 'pending'
          state (already applied / failed / skipped).
    """
    try:
        action = cancel_pilot_action(
            db,
            project_id=context.tenant_id,
            action_id=action_id,
            audit_user=context.subject,
        )
    except TierActionStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    if action is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pilot action not found",
        )
    return PilotActionResponse.model_validate(action)


class PilotActionRetryResponse(PilotActionResponse):
    """Augments the action with the dispatcher decision so the
    founder console can render "Retry skipped — same gate failed"
    without re-fetching the action row."""

    decision: str
    reason: str


@router.post(
    "/actions/{action_id}/retry",
    response_model=PilotActionRetryResponse,
)
@limiter.limit("12/minute")
def retry_action(
    request: Request,
    action_id: str,
    context=Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> PilotActionRetryResponse:
    """Re-dispatch a previously `failed` or `skipped` Tier-2 action.

    Reads the original anomaly + replay_run_id_gate off the action
    row and re-runs `evaluate_tier2_dispatch` from scratch. Because
    the dispatcher always writes a fresh row, this never mutates the
    original action; the response describes the *new* action.

    Requires the original action to be tier-2 and in one of the
    non-applied terminal states. Tier-1 retries flow through the
    Tier-1 revert/apply worker (not this endpoint).

    Returns:
      404 if the original action doesn't exist for the tenant.
      409 if the action is tier != 2 or already in pending/applied.
      422 if the original action is missing the gate evidence
          (replay_run_id_gate is NULL) — happens on actions skipped
          BEFORE the gate was checked (e.g. entitlement gate).
    """
    original = get_pilot_action(
        db, project_id=context.tenant_id, action_id=action_id
    )
    if original is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pilot action not found",
        )
    if original.tier != 2:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="only tier-2 actions are retried via /retry",
        )
    if original.status not in ("failed", "skipped"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"original action status is {original.status!r}; "
                "only 'failed' or 'skipped' rows can be retried"
            ),
        )
    if not original.replay_run_id_gate:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "original action was skipped before the replay gate was "
                "evaluated (no replay_run_id_gate on file) — re-dispatch "
                "manually with a fresh replay run"
            ),
        )

    # Re-load the anomaly + replay run to feed the dispatcher. Cross-
    # tenant rows are filtered by project_id at the SELECT level.
    anomaly = db.execute(
        select(Anomaly).where(
            Anomaly.id == original.anomaly_id,
            Anomaly.project_id == context.tenant_id,
        )
    ).scalar_one_or_none()
    replay_run = db.execute(
        select(ReplayRun).where(
            ReplayRun.id == original.replay_run_id_gate,
            ReplayRun.project_id == context.tenant_id,
        )
    ).scalar_one_or_none()
    if anomaly is None or replay_run is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "anomaly or replay_run referenced by the original action "
                "no longer exists — cannot retry"
            ),
        )

    outcome = evaluate_tier2_dispatch(
        db,
        anomaly=anomaly,
        action_type=original.action_type,
        replay_run=replay_run,
    )
    base = PilotActionResponse.model_validate(outcome.action).model_dump()
    return PilotActionRetryResponse(
        **base,
        decision=outcome.decision,
        reason=outcome.reason,
    )


# ── routes: policy ───────────────────────────────────────────────────────────


@router.get("/policy", response_model=PilotPolicyResponse)
@limiter.limit("60/minute")
def get_policy(
    request: Request,
    tenant_id: str = Depends(require_tenant_id),
    db: Session = Depends(get_db_session),
) -> PilotPolicyResponse:
    """Return the project's pilot policy. First read seeds the §6.3
    canonical default so the dashboard always has a row to render."""
    policy = get_or_create_policy(db, project_id=tenant_id)
    return _to_policy_response(policy)


@router.put("/policy", response_model=PilotPolicyResponse)
@limiter.limit("12/minute")
def put_policy(
    request: Request,
    body: PilotPolicyPayload,
    context=Depends(require_tenant_context),
    db: Session = Depends(get_db_session),
) -> PilotPolicyResponse:
    """Replace the project's pilot policy. Pydantic enforces the simple
    type + range constraints (booleans, ge=0, ≤1, etc.); the service
    layer re-validates and trims string entries before persisting."""
    try:
        policy = upsert_policy(
            db,
            project_id=context.tenant_id,
            payload=body.model_dump(),
            updated_by=context.subject,
        )
    except PolicyValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _to_policy_response(policy)
