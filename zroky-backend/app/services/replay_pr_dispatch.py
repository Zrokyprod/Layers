"""
Replay-driven auto-fix PR dispatcher (Module 10 advanced).

Composes `replay_fix_engine.analyze_and_generate_fix` with the existing
Tier-2 PR infrastructure (pilot_pr_payload + pilot_pr_client) to produce
and open a fix PR when a replay run with overrides fails.

Gates (fail-CLOSED):
  1. Entitlement: pilot.autofix_pr_enabled (Enterprise only)
  2. Policy: kill_switch, tier2_enabled, action allow-list, daily cap
  3. Replay run must have status=fail|error and replay_mode=real_llm
  4. Fix engine must produce a suggestion with confidence >= floor

Idempotency: by (project_id, pr_fingerprint) via pilot_actions.
Audit trail: every dispatch attempt writes a pilot_actions row.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Anomaly,
    PilotAction,
    ReplayRun,
)
from app.services.pilot import (
    get_or_create_policy,
    parse_policy_json,
)
from app.services.pilot_pr_client import (
    GitHubPRClient,
    PRClientError,
    PRClientPermanentError,
    get_pr_client,
)
from app.services.pilot_pr_payload import (
    InsufficientEvidenceError,
    PRPayload,
    SUPPORTED_TIER2_ACTIONS,
    UnsupportedActionTypeError,
    build_pr_payload,
)
from app.services.replay_fix_engine import (
    FixSuggestion,
    _FIX_CONFIDENCE_FLOOR,
    analyze_and_generate_fix,
)
from app.services.replay_runs import (
    REPLAY_MODE_REAL_LLM,
    parse_summary,
)

logger = logging.getLogger(__name__)


# ── outcome model ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ReplayFixOutcome:
    """Result of `dispatch_replay_fix_pr`."""

    decision: str
    action: PilotAction
    payload: PRPayload | None = None
    fix_suggestion: FixSuggestion | None = None
    reason: str = ""

    @property
    def is_applied(self) -> bool:
        return self.decision in {"applied", "idempotent_hit"}


# Decision tokens
_DECISION_APPLIED = "applied"
_DECISION_IDEMPOTENT_HIT = "idempotent_hit"
_DECISION_SKIPPED_ENTITLEMENT = "skipped_entitlement"
_DECISION_SKIPPED_KILL_SWITCH = "skipped_kill_switch"
_DECISION_SKIPPED_TIER_DISABLED = "skipped_tier_disabled"
_DECISION_SKIPPED_NOT_REAL_LLM = "skipped_not_real_llm"
_DECISION_SKIPPED_NO_FIX = "skipped_no_fix"
_DECISION_SKIPPED_LOW_CONFIDENCE = "skipped_low_confidence"
_DECISION_SKIPPED_ACTION_NOT_ALLOWED = "skipped_action_not_allowed"
_DECISION_SKIPPED_DAILY_CAP = "skipped_daily_cap"
_DECISION_FAILED_TRANSIENT = "failed_transient"
_DECISION_FAILED_PERMANENT = "failed_permanent"


# ── public API ────────────────────────────────────────────────────────────────


def dispatch_replay_fix_pr(
    db: Session,
    *,
    replay_run: ReplayRun,
    pr_client: GitHubPRClient | None = None,
    entitlement_check: Callable[[Session, str], bool] | None = None,
    now: datetime | None = None,
) -> ReplayFixOutcome:
    """Run the full replay-driven auto-fix dispatch pipeline.

    Always writes a ``pilot_actions`` row. Never raises.
    """
    now = now or datetime.now(timezone.utc)
    project_id = replay_run.project_id

    # ── 1) entitlement gate (Enterprise only) ──────────────────────
    if not _check_entitlement(db, project_id, entitlement_check):
        action = _persist_skip(
            db,
            project_id=project_id,
            run_id=replay_run.id,
            decision=_DECISION_SKIPPED_ENTITLEMENT,
            reason="pilot.autofix_pr_enabled is not granted for this org",
            now=now,
        )
        return ReplayFixOutcome(
            decision=_DECISION_SKIPPED_ENTITLEMENT,
            action=action,
            reason="pilot.autofix_pr_enabled is not granted for this org",
        )

    # ── 2) policy gates ────────────────────────────────────────────
    policy = parse_policy_json(get_or_create_policy(db, project_id=project_id).policy_json)
    if policy.get("kill_switch") is True:
        action = _persist_skip(
            db, project_id=project_id, run_id=replay_run.id,
            decision=_DECISION_SKIPPED_KILL_SWITCH,
            reason="pilot_policies.kill_switch is on", now=now,
        )
        return ReplayFixOutcome(
            decision=_DECISION_SKIPPED_KILL_SWITCH, action=action,
            reason="pilot_policies.kill_switch is on",
        )
    if not policy.get("tier2_enabled"):
        action = _persist_skip(
            db, project_id=project_id, run_id=replay_run.id,
            decision=_DECISION_SKIPPED_TIER_DISABLED,
            reason="pilot_policies.tier2_enabled is False", now=now,
        )
        return ReplayFixOutcome(
            decision=_DECISION_SKIPPED_TIER_DISABLED, action=action,
            reason="pilot_policies.tier2_enabled is False",
        )

    # ── 3) replay mode gate ─────────────────────────────────────────
    summary = parse_summary(replay_run.summary_json)
    replay_mode = summary.get("replay_mode", "stub")
    if replay_mode != REPLAY_MODE_REAL_LLM:
        action = _persist_skip(
            db, project_id=project_id, run_id=replay_run.id,
            decision=_DECISION_SKIPPED_NOT_REAL_LLM,
            reason=f"replay_mode={replay_mode!r} != real_llm (no override to fix)",
            now=now,
        )
        return ReplayFixOutcome(
            decision=_DECISION_SKIPPED_NOT_REAL_LLM, action=action,
            reason=f"replay_mode={replay_mode!r} != real_llm",
        )

    # ── 4) fix engine ───────────────────────────────────────────────
    candidate_prompt_override = summary.get("candidate_prompt_override")
    candidate_model_override = summary.get("candidate_model_override")
    fix = analyze_and_generate_fix(
        db,
        replay_run=replay_run,
        candidate_prompt_override=candidate_prompt_override,
        candidate_model_override=candidate_model_override,
    )
    if fix is None:
        action = _persist_skip(
            db, project_id=project_id, run_id=replay_run.id,
            decision=_DECISION_SKIPPED_NO_FIX,
            reason="fix engine returned no suggestion", now=now,
        )
        return ReplayFixOutcome(
            decision=_DECISION_SKIPPED_NO_FIX, action=action,
            reason="fix engine returned no suggestion",
        )
    if fix.confidence < _FIX_CONFIDENCE_FLOOR:
        action = _persist_skip(
            db, project_id=project_id, run_id=replay_run.id,
            decision=_DECISION_SKIPPED_LOW_CONFIDENCE,
            reason=f"fix confidence {fix.confidence:.2f} below floor {_FIX_CONFIDENCE_FLOOR}",
            now=now,
        )
        return ReplayFixOutcome(
            decision=_DECISION_SKIPPED_LOW_CONFIDENCE, action=action,
            fix_suggestion=fix,
            reason=f"fix confidence {fix.confidence:.2f} below floor {_FIX_CONFIDENCE_FLOOR}",
        )

    # ── 5) action type gate ─────────────────────────────────────────
    action_type = "replay_prompt_fix" if fix.fix_type in {"prompt_tweak", "prompt_revert"} else "replay_model_fix"
    allowed_actions = set(policy.get("tier2_actions", []) or [])
    if action_type not in allowed_actions:
        action = _persist_skip(
            db, project_id=project_id, run_id=replay_run.id,
            decision=_DECISION_SKIPPED_ACTION_NOT_ALLOWED,
            reason=f"action_type {action_type!r} not in policy.tier2_actions", now=now,
        )
        return ReplayFixOutcome(
            decision=_DECISION_SKIPPED_ACTION_NOT_ALLOWED, action=action,
            fix_suggestion=fix,
            reason=f"action_type {action_type!r} not in policy.tier2_actions",
        )
    if action_type not in SUPPORTED_TIER2_ACTIONS:
        action = _persist_skip(
            db, project_id=project_id, run_id=replay_run.id,
            decision=_DECISION_SKIPPED_ACTION_NOT_ALLOWED,
            reason=f"action_type {action_type!r} not in SUPPORTED_TIER2_ACTIONS", now=now,
        )
        return ReplayFixOutcome(
            decision=_DECISION_SKIPPED_ACTION_NOT_ALLOWED, action=action,
            fix_suggestion=fix,
            reason=f"action_type {action_type!r} not in SUPPORTED_TIER2_ACTIONS",
        )

    # ── 6) daily cap ──────────────────────────────────────────────
    cap = _resolve_daily_cap(policy)
    today_count = _count_real_prs_today(db, project_id=project_id, now=now)
    if cap is not None and today_count >= cap:
        action = _persist_skip(
            db, project_id=project_id, run_id=replay_run.id,
            decision=_DECISION_SKIPPED_DAILY_CAP,
            reason=f"daily cap reached ({today_count}/{cap})", now=now,
        )
        return ReplayFixOutcome(
            decision=_DECISION_SKIPPED_DAILY_CAP, action=action,
            fix_suggestion=fix,
            reason=f"daily cap reached ({today_count}/{cap})",
        )

    # ── 7) build payload ────────────────────────────────────────────
    # We need a synthetic Anomaly row to satisfy the existing payload
    # builder interface. We create it in-memory (not persisted).
    synthetic_anomaly = Anomaly(
        id=f"replay-{replay_run.id[:20]}",
        project_id=project_id,
        detector="replay_fix_engine",
        severity="high",
        occurrence_count=1,
        fingerprint=None,
        evidence_json=json.dumps(fix.evidence, separators=(",", ":")),
    )
    try:
        payload = build_pr_payload(anomaly=synthetic_anomaly, action_type=action_type)
    except (UnsupportedActionTypeError, InsufficientEvidenceError) as exc:
        action = _persist_skip(
            db, project_id=project_id, run_id=replay_run.id,
            decision=_DECISION_SKIPPED_NO_FIX,
            reason=str(exc), now=now,
        )
        return ReplayFixOutcome(
            decision=_DECISION_SKIPPED_NO_FIX, action=action,
            fix_suggestion=fix, reason=str(exc),
        )

    # ── 8) idempotency ────────────────────────────────────────────
    existing = _find_existing_by_fingerprint(
        db, project_id=project_id, fingerprint=payload.fingerprint
    )
    if existing is not None:
        return ReplayFixOutcome(
            decision=_DECISION_IDEMPOTENT_HIT,
            action=existing,
            payload=payload,
            fix_suggestion=fix,
            reason=f"existing action {existing.id} already opened a PR for this patch",
        )

    # ── 9) reserve row + open PR ────────────────────────────────────
    action = PilotAction(
        id=str(uuid4()),
        project_id=project_id,
        anomaly_id=synthetic_anomaly.id,
        tier=2,
        action_type=action_type,
        status="pending",
        payload_json=payload.to_json(),
        pr_fingerprint=payload.fingerprint,
        replay_run_id_gate=replay_run.id,
        audit_user=None,
    )
    db.add(action)
    db.commit()
    db.refresh(action)

    client = pr_client or get_pr_client()
    try:
        result = client.open_pr(payload)
    except PRClientPermanentError as exc:
        action.status = "failed"
        db.add(action)
        db.commit()
        db.refresh(action)
        return ReplayFixOutcome(
            decision=_DECISION_FAILED_PERMANENT,
            action=action,
            payload=payload,
            fix_suggestion=fix,
            reason=str(exc),
        )
    except PRClientError as exc:
        action.status = "failed"
        db.add(action)
        db.commit()
        db.refresh(action)
        return ReplayFixOutcome(
            decision=_DECISION_FAILED_TRANSIENT,
            action=action,
            payload=payload,
            fix_suggestion=fix,
            reason=str(exc),
        )
    except Exception as exc:  # noqa: BLE001
        action.status = "failed"
        db.add(action)
        db.commit()
        db.refresh(action)
        return ReplayFixOutcome(
            decision=_DECISION_FAILED_PERMANENT,
            action=action,
            payload=payload,
            fix_suggestion=fix,
            reason=f"unexpected exception: {exc!r}",
        )

    # ── 10) success ─────────────────────────────────────────────────
    action.status = "applied"
    action.applied_at = now
    action.pr_url = result.pr_url
    db.add(action)
    db.commit()
    db.refresh(action)
    logger.info(
        "replay_fix_pr_applied project=%s action=%s pr_url=%s dry_run=%s",
        project_id, action.id, result.pr_url, result.dry_run,
    )
    return ReplayFixOutcome(
        decision=_DECISION_APPLIED,
        action=action,
        payload=payload,
        fix_suggestion=fix,
        reason=f"opened PR {result.pr_url}",
    )


# ── internals ───────────────────────────────────────────────────────────────


def _check_entitlement(
    db: Session,
    project_id: str,
    entitlement_check,
) -> bool:
    if entitlement_check is not None:
        try:
            return bool(entitlement_check(db, project_id))
        except Exception:
            logger.exception("autofix_entitlement_check_failed project=%s", project_id)
            return False
    try:
        from app.services import entitlements_resolver
        return bool(entitlements_resolver.has(db, project_id, "pilot.autofix_pr_enabled"))
    except Exception:
        logger.exception("autofix_entitlement_resolver_failed project=%s", project_id)
        return False


def _resolve_daily_cap(policy: dict[str, Any]) -> int | None:
    from app.core.config import get_settings
    settings = get_settings()
    raw = policy.get("tier2_daily_cap")
    if isinstance(raw, bool):
        raw = None
    if isinstance(raw, int) and raw >= 0:
        return raw
    fallback = getattr(settings, "PILOT_TIER2_DAILY_PR_CAP", 10)
    try:
        cap = int(fallback)
    except (TypeError, ValueError):
        return 10
    return cap if cap >= 0 else 10


def _count_real_prs_today(
    db: Session, *, project_id: str, now: datetime
) -> int:
    since = now - timedelta(hours=24)
    rows = db.execute(
        select(PilotAction).where(
            PilotAction.project_id == project_id,
            PilotAction.tier == 2,
            PilotAction.status == "applied",
            PilotAction.created_at >= since,
        )
    ).scalars().all()
    real_count = 0
    for row in rows:
        url = row.pr_url or ""
        if url.startswith("dry-run://") or url.startswith("recording://"):
            continue
        real_count += 1
    return real_count


def _find_existing_by_fingerprint(
    db: Session, *, project_id: str, fingerprint: str
) -> PilotAction | None:
    return db.execute(
        select(PilotAction)
        .where(
            PilotAction.project_id == project_id,
            PilotAction.pr_fingerprint == fingerprint,
            PilotAction.status.in_(("applied", "pending")),
        )
        .order_by(PilotAction.created_at.desc(), PilotAction.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def _persist_skip(
    db: Session,
    *,
    project_id: str,
    run_id: str,
    decision: str,
    reason: str,
    now: datetime,
) -> PilotAction:
    status = "failed" if decision.startswith("failed_") else "skipped"
    payload_blob = json.dumps(
        {"decision": decision, "skip_reason": reason},
        separators=(",", ":"),
    )
    action = PilotAction(
        id=str(uuid4()),
        project_id=project_id,
        anomaly_id=f"replay-{run_id[:20]}",
        tier=2,
        action_type="replay_prompt_fix",
        status=status,
        payload_json=payload_blob,
        replay_run_id_gate=run_id,
        audit_user=None,
    )
    db.add(action)
    db.commit()
    db.refresh(action)
    logger.info(
        "replay_fix_dispatch_skipped project=%s action=%s decision=%s reason=%s",
        project_id, action.id, decision, reason,
    )
    return action
