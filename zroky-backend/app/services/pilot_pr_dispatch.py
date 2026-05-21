"""
Pilot Tier-2 auto-PR dispatcher (ZROKY-TECHNICAL-PLAN-V2 §6.3 / §17.1 risk #1 / Module 10).

Composes the three pure modules into one decision pipeline:

    Anomaly + ReplayRun gate
            │
            ▼
    evaluate_tier2_dispatch()        (this module)
            │
            ├── policy gates (kill switch / tier2_enabled / action allow-list / daily cap)
            ├── entitlement check (pilot.tier2_pr_enabled)
            ├── replay-pass gate  (>= PILOT_TIER2_REPLAY_PASS_GATE)
            ├── payload generation              → pilot_pr_payload.build_pr_payload
            ├── idempotency lookup by (project_id, pr_fingerprint)
            ├── client.open_pr(payload)         → pilot_pr_client.GitHubPRClient
            └── pilot_actions row insert/update (status, pr_url, pr_fingerprint,
                                                 replay_run_id_gate, payload_json)

EVERY exit produces a row in `pilot_actions` so the audit trail is
complete — including the `skipped` / `failed` paths. The status
semantics:

    pending   → row reserved but client.open_pr not yet called
    applied   → client.open_pr succeeded; pr_url populated
    failed    → client.open_pr raised (transient or permanent)
    skipped   → policy gate denied (kill switch, cap, gate below threshold,
                 entitlement missing, unsupported action_type, etc.)
    reverted  → reserved for tier-1 only (per pilot.py REVERTIBLE_TIER)

`DispatchOutcome` is the single return value carrying both the row
and the decision reason — callers (worker tasks + admin retry routes)
log on it without re-running the dispatch.

Plan §17.1 risk #1: this module is the principal mitigation for
"autopilot tier-1 false positive". Even though the risk is named
Tier-1, the gate logic generalizes — for Tier-2 the same fail-CLOSED
posture applies: every unknown condition skips the action.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Anomaly, PilotAction, ReplayRun
from app.services.pilot import (
    REVERTIBLE_TIER,
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
from app.services.replay_runs import parse_summary

logger = logging.getLogger(__name__)


# ── outcome model ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DispatchOutcome:
    """Result of `evaluate_tier2_dispatch`.

    `decision` is one of:
        applied              client.open_pr returned a PR URL
        idempotent_hit       a prior action with the same fingerprint
                              already opened a PR — same row returned
        skipped_*            policy gate denied; reason in the suffix
        failed_*             open_pr raised; suffix denotes transient
                              vs. permanent
    """

    decision: str
    action: PilotAction
    payload: PRPayload | None = None
    reason: str = ""

    @property
    def is_applied(self) -> bool:
        return self.decision in {"applied", "idempotent_hit"}


# Decision tokens — kept as module-level strings so callers can `==`
# them without typos creeping in. The vocabulary is exhaustive — any
# code path returning a decision not in this set is a bug.
DECISION_APPLIED: str = "applied"
DECISION_IDEMPOTENT_HIT: str = "idempotent_hit"
DECISION_SKIPPED_ENTITLEMENT: str = "skipped_entitlement"
DECISION_SKIPPED_KILL_SWITCH: str = "skipped_kill_switch"
DECISION_SKIPPED_TIER_DISABLED: str = "skipped_tier_disabled"
DECISION_SKIPPED_ACTION_NOT_ALLOWED: str = "skipped_action_not_allowed"
DECISION_SKIPPED_DAILY_CAP: str = "skipped_daily_cap"
DECISION_SKIPPED_REPLAY_GATE: str = "skipped_replay_gate"
DECISION_SKIPPED_UNSUPPORTED: str = "skipped_unsupported_action"
DECISION_SKIPPED_INSUFFICIENT_EVIDENCE: str = "skipped_insufficient_evidence"
DECISION_FAILED_TRANSIENT: str = "failed_transient"
DECISION_FAILED_PERMANENT: str = "failed_permanent"


# ── public API ───────────────────────────────────────────────────────────────


def evaluate_tier2_dispatch(
    db: Session,
    *,
    anomaly: Anomaly,
    action_type: str,
    replay_run: ReplayRun,
    pr_client: GitHubPRClient | None = None,
    entitlement_check: Callable[[Session, str], bool] | None = None,
    now: datetime | None = None,
) -> DispatchOutcome:
    """Run the full Tier-2 decision pipeline. Always writes a
    `pilot_actions` row. Never raises — every exception is caught
    and mapped to a `failed_*` decision.

    Arguments:
      * `anomaly`            the anomaly motivating the action. Must
                              belong to the same project as `replay_run`.
      * `action_type`        must be in `SUPPORTED_TIER2_ACTIONS`.
      * `replay_run`         the replay run that gates this dispatch.
                              Pass-rate is computed from its
                              `summary_json` (pass_count /
                              trace_count_at_dispatch).
      * `pr_client`          override the default factory-resolved
                              backend. Tests pass a `DryRunPRClient`
                              they control directly.
      * `entitlement_check`  callable `(db, project_id) -> bool`
                              returning True when the org has
                              `pilot.tier2_pr_enabled`. Defaults to
                              the live entitlements_resolver. Lets
                              tests bypass without monkeypatching
                              the resolver module-wide.
      * `now`                inject for deterministic daily-cap tests.

    Returns:
      A `DispatchOutcome` whose `.action` is a fully-persisted row.
      The caller is expected to log on `.decision` and surface
      `.reason` to whatever audit pipe is appropriate.
    """
    now = now or datetime.now(timezone.utc)
    project_id = anomaly.project_id

    # ── 0) project-anomaly tenancy sanity check (defense-in-depth) ──
    if replay_run.project_id != project_id:
        return _persist_skip(
            db,
            project_id=project_id,
            anomaly_id=anomaly.id,
            action_type=action_type,
            decision=DECISION_FAILED_PERMANENT,
            reason=(
                "anomaly.project_id != replay_run.project_id — refusing "
                "to dispatch (cross-tenant guard)"
            ),
        )

    # ── 1) entitlement gate (plan §10.x — Pro+ only) ────────────────
    if not _check_entitlement(db, project_id, entitlement_check):
        return _persist_skip(
            db,
            project_id=project_id,
            anomaly_id=anomaly.id,
            action_type=action_type,
            decision=DECISION_SKIPPED_ENTITLEMENT,
            reason="pilot.tier2_pr_enabled is not granted for this org",
        )

    # ── 2) policy gates (kill switch / tier enabled / action allow / cap) ──
    policy = parse_policy_json(get_or_create_policy(db, project_id=project_id).policy_json)
    if policy.get("kill_switch") is True:
        return _persist_skip(
            db,
            project_id=project_id,
            anomaly_id=anomaly.id,
            action_type=action_type,
            decision=DECISION_SKIPPED_KILL_SWITCH,
            reason="pilot_policies.kill_switch is on",
        )
    if not policy.get("tier2_enabled"):
        return _persist_skip(
            db,
            project_id=project_id,
            anomaly_id=anomaly.id,
            action_type=action_type,
            decision=DECISION_SKIPPED_TIER_DISABLED,
            reason="pilot_policies.tier2_enabled is False",
        )
    allowed_actions = set(policy.get("tier2_actions", []) or [])
    if action_type not in allowed_actions:
        return _persist_skip(
            db,
            project_id=project_id,
            anomaly_id=anomaly.id,
            action_type=action_type,
            decision=DECISION_SKIPPED_ACTION_NOT_ALLOWED,
            reason=(
                f"action_type {action_type!r} not in policy.tier2_actions "
                f"({sorted(allowed_actions)})"
            ),
        )
    # action_type vocab guard — caller passed something the producer
    # cannot honour. Distinct from "not allowed by policy": this is
    # a developer mistake, not a customer config.
    if action_type not in SUPPORTED_TIER2_ACTIONS:
        return _persist_skip(
            db,
            project_id=project_id,
            anomaly_id=anomaly.id,
            action_type=action_type,
            decision=DECISION_SKIPPED_UNSUPPORTED,
            reason=(
                f"action_type {action_type!r} is not in "
                f"SUPPORTED_TIER2_ACTIONS ({sorted(SUPPORTED_TIER2_ACTIONS)})"
            ),
        )

    # Daily cap (real PRs only — dry_run rows do NOT count toward the
    # cap because the cap protects the customer's repo, not log noise).
    cap = _resolve_daily_cap(policy)
    today_count = _count_real_prs_today(db, project_id=project_id, now=now)
    if cap is not None and today_count >= cap:
        return _persist_skip(
            db,
            project_id=project_id,
            anomaly_id=anomaly.id,
            action_type=action_type,
            decision=DECISION_SKIPPED_DAILY_CAP,
            reason=f"daily cap reached ({today_count}/{cap})",
        )

    # ── 3) replay-pass gate (plan §17.1 risk #1) ────────────────────
    require_pass = bool(policy.get("tier2_require_replay_pass", True))
    if require_pass:
        pass_rate, denom = _replay_pass_rate(replay_run)
        threshold = _resolve_replay_gate()
        if denom == 0 or pass_rate < threshold:
            return _persist_skip(
                db,
                project_id=project_id,
                anomaly_id=anomaly.id,
                action_type=action_type,
                decision=DECISION_SKIPPED_REPLAY_GATE,
                reason=(
                    f"replay-pass rate {pass_rate:.3f} (n={denom}) below "
                    f"gate {threshold:.3f} on run {replay_run.id}"
                ),
                replay_run_id_gate=replay_run.id,
            )

    # ── 4) build payload (may raise InsufficientEvidence / Unsupported) ──
    try:
        payload = build_pr_payload(anomaly=anomaly, action_type=action_type)
    except UnsupportedActionTypeError as exc:
        # Already filtered above, but stays here for defense-in-depth
        # in case SUPPORTED_TIER2_ACTIONS drifts.
        return _persist_skip(
            db,
            project_id=project_id,
            anomaly_id=anomaly.id,
            action_type=action_type,
            decision=DECISION_SKIPPED_UNSUPPORTED,
            reason=str(exc),
            replay_run_id_gate=replay_run.id,
        )
    except InsufficientEvidenceError as exc:
        return _persist_skip(
            db,
            project_id=project_id,
            anomaly_id=anomaly.id,
            action_type=action_type,
            decision=DECISION_SKIPPED_INSUFFICIENT_EVIDENCE,
            reason=str(exc),
            replay_run_id_gate=replay_run.id,
        )

    # ── 5) idempotency by (project_id, pr_fingerprint) ──────────────
    existing = _find_existing_by_fingerprint(
        db, project_id=project_id, fingerprint=payload.fingerprint
    )
    if existing is not None:
        logger.info(
            "tier2_idempotent_hit project=%s action=%s fp=%s existing=%s",
            project_id, action_type, payload.fingerprint[:12], existing.id,
        )
        return DispatchOutcome(
            decision=DECISION_IDEMPOTENT_HIT,
            action=existing,
            payload=payload,
            reason=f"existing action {existing.id} already opened a PR for this patch",
        )

    # ── 6) reserve row (pending) BEFORE calling the network ─────────
    # Storing the payload + replay_run_id_gate up-front means even a
    # client crash leaves an auditable trail of "what we tried to do".
    action = PilotAction(
        id=str(uuid4()),
        project_id=project_id,
        anomaly_id=anomaly.id,
        tier=2,
        action_type=action_type,
        status="pending",
        payload_json=payload.to_json(),
        pr_fingerprint=payload.fingerprint,
        replay_run_id_gate=replay_run.id,
        audit_user=None,  # autopilot, not a human
    )
    db.add(action)
    db.commit()
    db.refresh(action)

    # ── 7) call the client ──────────────────────────────────────────
    client = pr_client or get_pr_client()
    try:
        result = client.open_pr(payload)
    except PRClientPermanentError as exc:
        action.status = "failed"
        db.add(action)
        db.commit()
        db.refresh(action)
        logger.error(
            "tier2_pr_permanent_failure project=%s action=%s reason=%s",
            project_id, action.id, exc,
        )
        return DispatchOutcome(
            decision=DECISION_FAILED_PERMANENT,
            action=action,
            payload=payload,
            reason=str(exc),
        )
    except PRClientError as exc:
        action.status = "failed"
        db.add(action)
        db.commit()
        db.refresh(action)
        logger.warning(
            "tier2_pr_transient_failure project=%s action=%s reason=%s",
            project_id, action.id, exc,
        )
        return DispatchOutcome(
            decision=DECISION_FAILED_TRANSIENT,
            action=action,
            payload=payload,
            reason=str(exc),
        )
    except Exception as exc:  # noqa: BLE001 — last-resort guard
        # Any other exception (programmer bug, missing dep) is permanent
        # from the dispatcher's POV — better to mark `failed` than let
        # Celery retry forever on the same bug.
        action.status = "failed"
        db.add(action)
        db.commit()
        db.refresh(action)
        logger.exception(
            "tier2_pr_unexpected_failure project=%s action=%s",
            project_id, action.id,
        )
        return DispatchOutcome(
            decision=DECISION_FAILED_PERMANENT,
            action=action,
            payload=payload,
            reason=f"unexpected exception: {exc!r}",
        )

    # ── 8) success: stamp applied + pr_url ──────────────────────────
    action.status = "applied"
    action.applied_at = now
    action.pr_url = result.pr_url
    db.add(action)
    db.commit()
    db.refresh(action)
    logger.info(
        "tier2_pr_applied project=%s action=%s pr_url=%s dry_run=%s",
        project_id, action.id, result.pr_url, result.dry_run,
    )
    return DispatchOutcome(
        decision=DECISION_APPLIED,
        action=action,
        payload=payload,
        reason=f"opened PR {result.pr_url}",
    )


# ── internals ────────────────────────────────────────────────────────────────


def _check_entitlement(
    db: Session,
    project_id: str,
    entitlement_check,
) -> bool:
    """Default entitlement check via the live resolver, with an
    injection point for tests. Resolver failure is treated as
    fail-CLOSED (no entitlement) — protects against an outage
    silently re-enabling auto-PR for everyone."""
    if entitlement_check is not None:
        try:
            return bool(entitlement_check(db, project_id))
        except Exception:
            logger.exception(
                "tier2_entitlement_check_failed_in_injection project=%s",
                project_id,
            )
            return False
    try:
        from app.services import entitlements_resolver

        return bool(entitlements_resolver.has(db, project_id, "pilot.tier2_pr_enabled"))
    except Exception:
        logger.exception(
            "tier2_entitlement_resolver_failed project=%s", project_id
        )
        return False


def _replay_pass_rate(run: ReplayRun) -> tuple[float, int]:
    """Compute the pass rate for a replay run from its summary_json.

    Returns (pass_rate, denominator) where denominator is the number
    of traces counted at dispatch time. A 0 denominator forces the
    gate to fail-CLOSED in the caller — we never approve a Tier-2
    based on a 0-trace replay.
    """
    summary = parse_summary(run.summary_json)
    denom = int(summary.get("trace_count_at_dispatch", 0) or 0)
    passes = int(summary.get("pass_count", 0) or 0)
    if denom <= 0:
        return 0.0, 0
    return passes / denom, denom


def _resolve_replay_gate() -> float:
    """Read the gate threshold from settings (with a sane fallback)."""
    from app.core.config import get_settings

    settings = get_settings()
    try:
        return float(getattr(settings, "PILOT_TIER2_REPLAY_PASS_GATE", 0.95))
    except (TypeError, ValueError):
        return 0.95


def _resolve_daily_cap(policy: dict[str, Any]) -> int | None:
    """Daily cap defaults to the global `PILOT_TIER2_DAILY_PR_CAP`.
    `policy_json` does not expose a Tier-2 cap field yet (plan §6.3
    schema only includes `tier1_daily_cap`); when that field is
    added later, this helper picks it up automatically.
    A cap of 0 disables Tier-2 entirely; a negative or missing value
    falls back to settings. None == unlimited."""
    from app.core.config import get_settings

    settings = get_settings()
    raw = policy.get("tier2_daily_cap")
    if isinstance(raw, bool):  # bool ⊂ int in Python — reject explicitly
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
    """Count `applied` tier-2 rows in the trailing 24 hours whose
    `pr_url` is NOT a `dry-run://` or `recording://` sentinel.

    Implemented in Python over the row list rather than as a CASE
    expression because (a) the daily cap is small, and (b) SQLite
    in tests doesn't optimize LIKE-with-leading-wildcard. The
    `(project_id, created_at)` index makes the SELECT fast.
    """
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
    """Return the most recent applied/pending action with the given
    fingerprint. Failed/skipped rows are NOT considered idempotent
    matches — a previous failure should not block a retry from
    opening a fresh PR (the user explicitly retried)."""
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
    anomaly_id: str,
    action_type: str,
    decision: str,
    reason: str,
    replay_run_id_gate: str | None = None,
) -> DispatchOutcome:
    """Insert a `skipped` (or `failed_permanent`) tier-2 row with the
    decision encoded in `payload_json.skip_reason`. Keeps the audit
    trail uniform — every dispatch attempt produces a row, regardless
    of whether the client was ever called."""
    status = "failed" if decision.startswith("failed_") else "skipped"
    payload_blob = json.dumps(
        {"decision": decision, "skip_reason": reason},
        separators=(",", ":"),
    )
    action = PilotAction(
        id=str(uuid4()),
        project_id=project_id,
        anomaly_id=anomaly_id,
        tier=2,
        action_type=action_type,
        status=status,
        payload_json=payload_blob,
        replay_run_id_gate=replay_run_id_gate,
        audit_user=None,
    )
    db.add(action)
    db.commit()
    db.refresh(action)
    logger.info(
        "tier2_dispatch_skipped project=%s action=%s decision=%s reason=%s",
        project_id, action.id, decision, reason,
    )
    return DispatchOutcome(
        decision=decision, action=action, payload=None, reason=reason
    )


# ── retry / cancel helpers used by the admin routes ──────────────────────────


class TierActionStateError(ValueError):
    """Raised when the caller asks for a state transition the row's
    current status doesn't allow (e.g. cancel an already-applied
    action). Routes map this to 409 Conflict."""


def cancel_pilot_action(
    db: Session,
    *,
    project_id: str,
    action_id: str,
    audit_user: str | None,
) -> PilotAction | None:
    """Mark a `pending` tier-2 row as `skipped` with a human-authored
    reason. Other statuses raise `TierActionStateError`. Returns None
    when the row doesn't exist for this tenant.

    Why we don't allow cancelling `applied`: the PR is already live
    on the customer's repo; "cancelling" would have to close that PR,
    which is the GitHub client's responsibility, not this row's
    state machine. A separate Tier-1-style revert path will land
    when the GitHub-App impl is wired in.
    """
    action = db.execute(
        select(PilotAction).where(
            PilotAction.project_id == project_id,
            PilotAction.id == action_id,
        )
    ).scalar_one_or_none()
    if action is None:
        return None
    if action.tier == REVERTIBLE_TIER:
        raise TierActionStateError(
            "tier-1 actions are reverted via /revert, not /cancel"
        )
    if action.status != "pending":
        raise TierActionStateError(
            f"action status is {action.status!r}; only 'pending' rows can be cancelled"
        )
    action.status = "skipped"
    if audit_user is not None:
        action.audit_user = audit_user
    db.add(action)
    db.commit()
    db.refresh(action)
    logger.info(
        "tier2_action_cancelled project=%s action=%s by=%s",
        project_id, action_id, audit_user,
    )
    return action
