from app.worker._internal.tasks_common import *
from app.worker._internal.tasks_utils import *

@celery_app.task(
    name="app.worker.tasks.expire_trials", queue="diagnosis_fast"
)
def expire_trials(limit: int | None = None) -> dict:
    """Beat task: downgrade `trialing` subscriptions whose `trial_end`
    has passed AND that have no provider subscription. See
    `services.subscription_lifecycle.sweep_expired_trials` for the
    eligibility contract.

    Returns a summary dict so beat logs surface counts.
    """
    from app.services.subscription_lifecycle import sweep_expired_trials

    settings = get_settings()
    if not settings.BILLING_LIFECYCLE_SWEEP_ENABLED:
        logger.info("expire_trials: BILLING_LIFECYCLE_SWEEP_ENABLED=false â€” skipping")
        return {"skipped": True, "reason": "BILLING_LIFECYCLE_SWEEP_ENABLED=false"}

    effective_limit = (
        int(limit)
        if limit is not None and limit > 0
        else int(settings.BILLING_LIFECYCLE_SWEEP_LIMIT)
    )

    session = SessionLocal()
    try:
        result = sweep_expired_trials(session, limit=effective_limit)
        logger.info(
            "expire_trials.completed",
            extra={
                "event": "subscription_lifecycle",
                "task": "expire_trials",
                "examined": result.examined,
                "transitioned": result.transitioned,
                "failed": result.failed,
            },
        )
        # Strip per-row transitions from the dict to keep the Celery
        # result envelope small. Operators read counts from logs.
        out = result.to_dict()
        out.pop("transitions", None)
        return out
    finally:
        session.close()


@celery_app.task(
    name="app.worker.tasks.expire_past_due_grace", queue="diagnosis_fast"
)
def expire_past_due_grace(
    grace_days: int | None = None,
    limit: int | None = None,
) -> dict:
    """Beat task: hard-downgrade `past_due` subscriptions whose
    `current_period_end + grace_days` has passed. See
    `services.subscription_lifecycle.sweep_expired_past_due_grace`
    for the eligibility contract.

    grace_days defaults to BILLING_PAST_DUE_GRACE_DAYS (locked at 7
    per plan Â§11.4 binding); the kwarg exists so an operator can run
    a one-off sweep with a longer window during a provider incident.
    """
    from app.services.subscription_lifecycle import sweep_expired_past_due_grace

    settings = get_settings()
    if not settings.BILLING_LIFECYCLE_SWEEP_ENABLED:
        logger.info(
            "expire_past_due_grace: BILLING_LIFECYCLE_SWEEP_ENABLED=false â€” skipping"
        )
        return {"skipped": True, "reason": "BILLING_LIFECYCLE_SWEEP_ENABLED=false"}

    effective_grace = (
        int(grace_days)
        if grace_days is not None and grace_days >= 0
        else int(settings.BILLING_PAST_DUE_GRACE_DAYS)
    )
    effective_limit = (
        int(limit)
        if limit is not None and limit > 0
        else int(settings.BILLING_LIFECYCLE_SWEEP_LIMIT)
    )

    session = SessionLocal()
    try:
        result = sweep_expired_past_due_grace(
            session, grace_days=effective_grace, limit=effective_limit,
        )
        logger.info(
            "expire_past_due_grace.completed",
            extra={
                "event": "subscription_lifecycle",
                "task": "expire_past_due_grace",
                "grace_days": effective_grace,
                "examined": result.examined,
                "transitioned": result.transitioned,
                "failed": result.failed,
            },
        )
        out = result.to_dict()
        out.pop("transitions", None)
        return out
    finally:
        session.close()


@celery_app.task(
    name="app.worker.tasks.reconcile_pending_razorpay_orders", queue="diagnosis_fast"
)
def reconcile_pending_razorpay_orders(limit: int | None = None) -> dict:
    """Beat task: recover paid Razorpay orders still pending locally."""
    from app.services.razorpay_reconciliation import (
        reconcile_pending_razorpay_orders as reconcile_orders,
    )

    settings = get_settings()
    if not settings.BILLING_ENABLED:
        logger.info("reconcile_pending_razorpay_orders: BILLING_ENABLED=false - skipping")
        return {"skipped": True, "reason": "BILLING_ENABLED=false"}
    if settings.BILLING_PROVIDER != "razorpay":
        logger.info(
            "reconcile_pending_razorpay_orders: BILLING_PROVIDER=%s - skipping",
            settings.BILLING_PROVIDER,
        )
        return {"skipped": True, "reason": "BILLING_PROVIDER is not razorpay"}
    if not settings.BILLING_RAZORPAY_RECONCILE_ENABLED:
        logger.info(
            "reconcile_pending_razorpay_orders: BILLING_RAZORPAY_RECONCILE_ENABLED=false - skipping"
        )
        return {
            "skipped": True,
            "reason": "BILLING_RAZORPAY_RECONCILE_ENABLED=false",
        }

    effective_limit = (
        int(limit)
        if limit is not None and limit > 0
        else int(settings.BILLING_RAZORPAY_RECONCILE_LIMIT)
    )
    session = SessionLocal()
    try:
        result = reconcile_orders(session, limit=effective_limit)
        logger.info(
            "reconcile_pending_razorpay_orders.completed",
            extra={
                "event": "razorpay_reconciliation",
                "task": "reconcile_pending_razorpay_orders",
                "examined": result.examined,
                "activated": result.activated,
                "skipped": result.skipped,
                "failed": result.failed,
            },
        )
        out = result.to_dict()
        out.pop("records", None)
        return out
    finally:
        session.close()


__all__ = [name for name in globals() if not name.startswith("__")]
