"""
Subscription lifecycle automation (Module 12; plan section 11.4).

Closes the gap between the Stripe-event-driven state machine and the
non-event-driven transitions that section 11.4 binds:

  * Trial expiry (no-card 14-day Pro trial)
        Stripe does not fire any event when our application-managed
        trial elapses. Without a sweeper a `trialing` row keeps Pro
        entitlements forever.

  * Past-due grace expiry
        Stripe's dunning sequence (typically 4 retries over ~21 days)
        eventually emits `customer.subscription.deleted`, but section
        11.4 binds a 7-day grace cap so the customer experience is
        bounded. We hard-downgrade at 7d regardless of Stripe's
        retry timeline.

Both transitions are pull-driven: a Celery beat task calls into this
module hourly. The service layer ships pure helpers (no Celery
imports) so tests can drive the same code paths directly.

Eligibility filters — locked decisions:

  * Trial expiry: `status='trialing'` AND `trial_end < now()` AND
    `stripe_sub_id IS NULL`.
        The `stripe_sub_id IS NULL` predicate restricts the sweep to
        application-managed (no-card) trials. Customers with a real
        Stripe subscription transition through Stripe's
        `customer.subscription.updated` event — sweeping them here
        would race against the webhook (and `_is_stale_event` in
        `stripe_sync` would then block the legitimate post-webhook
        upgrade for paid customers).

  * Past-due grace expiry: `status='past_due'` AND
    `current_period_end + grace_days < now()`.
        These rows ALL have `stripe_sub_id` set (they paid before).
        On hard-downgrade we clear `stripe_sub_id` so a delayed
        `invoice.paid` for the old subscription cannot resurrect the
        customer (the invoice handler looks up by stripe_sub_id and
        will simply find no row).

Audit trail: every state transition writes one `audit_log_admin` row
with `actor_role='system'`, `action='subscription.auto_downgrade_*'`,
and `before_json` / `after_json` snapshots of the affected fields.
The Founder Console (Module 13) reads this for support investigations.

Idempotency: the eligibility filters guarantee re-entry safety. Once a
row is transitioned, the next sweep finds no eligible rows for that
subscription. Concurrent sweep runs (rare) are bounded by
`status` flip — the second run sees the new state and skips.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditLogAdmin, Subscription
from app.services.billing_plans import DEFAULT_PLAN_CODE
from app.services.entitlements import (
    clear_trial_entitlements,
    seed_plan_entitlements,
)

logger = logging.getLogger(__name__)


# ── result envelopes ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TransitionRecord:
    """One subscription state transition produced by a sweep run."""
    subscription_id: str
    org_id: str
    reason: str  # 'trial_expired' | 'past_due_grace_expired'
    before: dict[str, Any]
    after: dict[str, Any]


@dataclass
class SweepResult:
    """Aggregated outcome of one sweep invocation. Mutable so the
    Celery wrapper can serialize counts directly without extra mapping."""
    examined: int = 0
    transitioned: int = 0
    failed: int = 0
    transitions: list[TransitionRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "examined": self.examined,
            "transitioned": self.transitioned,
            "failed": self.failed,
            "transitions": [
                {
                    "subscription_id": t.subscription_id,
                    "org_id": t.org_id,
                    "reason": t.reason,
                    "before": t.before,
                    "after": t.after,
                }
                for t in self.transitions
            ],
        }


# ── helpers ─────────────────────────────────────────────────────────────────


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _snapshot(sub: Subscription) -> dict[str, Any]:
    """Capture the audit-relevant fields. ISO-format datetimes so the
    JSON round-trips cleanly through `audit_log_admin.before_json`."""
    return {
        "plan_code": sub.plan_code,
        "status": sub.status,
        "stripe_sub_id": sub.stripe_sub_id,
        "stripe_customer_id": sub.stripe_customer_id,
        "current_period_end": (
            sub.current_period_end.isoformat()
            if sub.current_period_end is not None else None
        ),
        "trial_end": (
            sub.trial_end.isoformat() if sub.trial_end is not None else None
        ),
        "sla_tier": sub.sla_tier,
    }


def _write_audit(
    db: Session,
    *,
    sub: Subscription,
    action: str,
    before: dict[str, Any],
    after: dict[str, Any],
) -> None:
    """Append one `audit_log_admin` row for a sweep transition. Never
    raises — the audit write happens AFTER the subscription mutation
    has been staged but BEFORE commit, so a failure here would roll
    back the transition too. We use `actor_role='system'` per the
    enum vocabulary; `actor_user_id=NULL` because no human triggered
    this."""
    db.add(AuditLogAdmin(
        id=str(uuid4()),
        actor_user_id=None,
        actor_role="system",
        action=action,
        target_type="subscription",
        target_id=sub.id,
        before_json=json.dumps(before, separators=(",", ":"), sort_keys=True),
        after_json=json.dumps(after, separators=(",", ":"), sort_keys=True),
    ))


# ── trial expiry ────────────────────────────────────────────────────────────


def _select_expired_trial_subs(
    db: Session, *, now: datetime, limit: int
) -> list[Subscription]:
    """Eligibility query for the trial-expiry sweep. The `stripe_sub_id
    IS NULL` filter is the locked-decision boundary that prevents this
    task from racing the Stripe webhook on paid customers."""
    return list(db.execute(
        select(Subscription)
        .where(Subscription.status == "trialing")
        .where(Subscription.trial_end.is_not(None))
        .where(Subscription.trial_end < now)
        .where(Subscription.stripe_sub_id.is_(None))
        .order_by(Subscription.trial_end.asc())
        .limit(limit)
    ).scalars().all())


def sweep_expired_trials(
    db: Session, *, limit: int = 500, now: datetime | None = None
) -> SweepResult:
    """Walk subscriptions in `trialing` whose `trial_end` has passed
    AND that have no Stripe subscription, downgrading each to free.

    Caller owns the Session lifecycle. We commit per-row so a failure
    on one row does not roll back successful transitions on others.
    Returns a SweepResult so the caller can emit metrics / logs.

    Args:
      db:    request- or task-scoped Session.
      limit: cap on rows examined per call (default 500). Bounds the
             worst-case execution time of one sweep tick.
      now:   injectable clock for tests.
    """
    if limit < 1:
        raise ValueError("limit must be >= 1")
    current = now if now is not None else _now()
    result = SweepResult()

    rows = _select_expired_trial_subs(db, now=current, limit=limit)
    result.examined = len(rows)

    for sub in rows:
        try:
            transition = _transition_to_free(
                db, sub=sub,
                action="subscription.auto_downgrade_trial",
                reason="trial_expired",
                clear_stripe_sub_id=False,  # already NULL by filter
            )
            result.transitioned += 1
            result.transitions.append(transition)
            logger.info(
                "subscription_lifecycle.trial_expired org=%s sub=%s",
                transition.org_id, transition.subscription_id,
            )
        except Exception as exc:  # noqa: BLE001 — record + skip
            db.rollback()
            result.failed += 1
            logger.exception(
                "subscription_lifecycle.trial_sweep_failed sub=%s err=%s",
                sub.id, exc,
            )

    return result


# ── past-due grace expiry ───────────────────────────────────────────────────


def _select_expired_past_due_subs(
    db: Session, *, now: datetime, grace_days: int, limit: int
) -> list[Subscription]:
    """Eligibility for the past-due grace sweep. We require
    `current_period_end IS NOT NULL` because rows where the period
    end is unset (rare — incomplete signups that never paid) cannot
    have a deterministic grace window and should not be hard-downgraded
    by a clock-based sweep."""
    from datetime import timedelta
    cutoff = now - timedelta(days=grace_days)
    return list(db.execute(
        select(Subscription)
        .where(Subscription.status == "past_due")
        .where(Subscription.current_period_end.is_not(None))
        .where(Subscription.current_period_end < cutoff)
        .order_by(Subscription.current_period_end.asc())
        .limit(limit)
    ).scalars().all())


def sweep_expired_past_due_grace(
    db: Session,
    *,
    grace_days: int = 7,
    limit: int = 500,
    now: datetime | None = None,
) -> SweepResult:
    """Walk subscriptions in `past_due` whose `current_period_end` is
    older than `grace_days`, hard-downgrading each to free.

    Per plan section 11.4: 7-day grace then hard-downgrade. The
    `stripe_sub_id` is cleared on transition so a delayed Stripe
    `invoice.paid` event for the old subscription cannot resurrect
    the customer (the handler looks up by stripe_sub_id and finds
    nothing).
    """
    if grace_days < 0:
        raise ValueError("grace_days must be >= 0")
    if limit < 1:
        raise ValueError("limit must be >= 1")
    current = now if now is not None else _now()
    result = SweepResult()

    rows = _select_expired_past_due_subs(
        db, now=current, grace_days=grace_days, limit=limit,
    )
    result.examined = len(rows)

    for sub in rows:
        try:
            transition = _transition_to_free(
                db, sub=sub,
                action="subscription.auto_downgrade_past_due",
                reason="past_due_grace_expired",
                clear_stripe_sub_id=True,
            )
            result.transitioned += 1
            result.transitions.append(transition)
            logger.info(
                "subscription_lifecycle.past_due_expired org=%s sub=%s",
                transition.org_id, transition.subscription_id,
            )
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            result.failed += 1
            logger.exception(
                "subscription_lifecycle.past_due_sweep_failed sub=%s err=%s",
                sub.id, exc,
            )

    return result


# ── shared transition helper ────────────────────────────────────────────────


def _transition_to_free(
    db: Session,
    *,
    sub: Subscription,
    action: str,
    reason: str,
    clear_stripe_sub_id: bool,
) -> TransitionRecord:
    """Move a subscription row to (`free`, `active`) state, re-seed
    `source='plan'` entitlements as the free template, and drop any
    lingering trial overlay. Writes one audit row per call.

    `clear_stripe_sub_id` exists so the trial-expiry path (no Stripe
    sub) can leave the column alone while the past-due-grace path
    actively clears it to defang stale `invoice.paid` events.

    Commits on success. On any internal error the caller is expected
    to roll back — we don't try/except here because the orchestrators
    above already do, with the per-row isolation that matters for
    cohort sweeps.
    """
    before = _snapshot(sub)

    sub.plan_code = DEFAULT_PLAN_CODE  # 'free'
    sub.status = "active"
    sub.trial_end = None
    if clear_stripe_sub_id:
        sub.stripe_sub_id = None
    # Note: sla_tier is intentionally NOT reset. A customer who
    # lapses keeps their SLA-tier history for refund-eligibility
    # audits per plan §11.4. Founder Console is the only writer.
    db.add(sub)

    # Re-seed plan entitlements + clear any stale trial overlay.
    # commit=False — we batch the audit write into the same txn.
    seed_plan_entitlements(
        db, org_id=sub.org_id, plan_code=DEFAULT_PLAN_CODE, commit=False,
    )
    clear_trial_entitlements(db, org_id=sub.org_id, commit=False)

    after = _snapshot(sub)
    _write_audit(db, sub=sub, action=action, before=before, after=after)

    db.commit()
    db.refresh(sub)

    # Resolver cache invalidation — the entitlement writers were
    # called with commit=False so they skipped the cache hook. Now
    # that we have committed, drop the cached merged dict so the
    # next has()/get() call sees the fresh state.
    try:
        from app.services.entitlements_resolver import invalidate
        invalidate(sub.org_id)
    except Exception:  # noqa: BLE001 — never propagate from cache hook
        logger.exception(
            "subscription_lifecycle.cache_invalidate_failed org=%s",
            sub.org_id,
        )

    return TransitionRecord(
        subscription_id=sub.id,
        org_id=sub.org_id,
        reason=reason,
        before=before,
        after=after,
    )


__all__ = [
    "TransitionRecord",
    "SweepResult",
    "sweep_expired_trials",
    "sweep_expired_past_due_grace",
]
