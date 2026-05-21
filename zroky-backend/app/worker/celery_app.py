from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

retention_minute = min(max(int(settings.RETENTION_ENFORCEMENT_CRON_MINUTE), 0), 59)
retention_hour = min(max(int(settings.RETENTION_ENFORCEMENT_CRON_HOUR), 0), 23)
weekly_email_dow = min(max(int(settings.WEEKLY_IMPACT_EMAIL_CRON_DAY_OF_WEEK), 0), 6)
weekly_email_hour = min(max(int(settings.WEEKLY_IMPACT_EMAIL_CRON_HOUR), 0), 23)
beat_schedule: dict[str, dict] = {}
if settings.RETENTION_ENFORCEMENT_ENABLED:
    beat_schedule["retention-enforcement-daily"] = {
        "task": "app.worker.tasks.run_retention_enforcement",
        "schedule": crontab(minute=retention_minute, hour=retention_hour),
        "options": {"queue": "diagnosis_fast"},
    }
if settings.WEEKLY_IMPACT_EMAIL_ENABLED:
    # Legacy single-stage path — kept for one release behind the
    # WEEKLY_IMPACT_EMAIL_ENABLED flag. New deployments should set
    # DIGEST_ENABLED instead. Tasks are mutually exclusive: deployments
    # that flip both on get duplicate emails, so the README/CHANGELOG
    # for Module 11 explicitly calls out the rotation.
    beat_schedule["weekly-impact-email"] = {
        "task": "app.worker.tasks.send_weekly_impact_emails",
        "schedule": crontab(
            day_of_week=weekly_email_dow,
            hour=weekly_email_hour,
            minute=0,
        ),
        "options": {"queue": "diagnosis_fast"},
    }

# Always enabled: scan active fix-watches for recurrences every 4 hours
beat_schedule["fix-watch-recurrence-check"] = {
    "task": "app.worker.tasks.notify_fix_watch_recurrences",
    "schedule": crontab(minute=0, hour="*/4"),
    "options": {"queue": "diagnosis_fast"},
}

# Module 12 — subscription lifecycle sweeps. Hourly cadence, offset
# from :00 to dodge the top-of-hour herd from other beat tasks. The
# two sweeps share a minute because they query disjoint row sets
# (status='trialing' vs status='past_due') and never contend.
if settings.BILLING_LIFECYCLE_SWEEP_ENABLED:
    _lifecycle_minute = min(max(int(settings.BILLING_LIFECYCLE_SWEEP_MINUTE), 0), 59)
    beat_schedule["billing-lifecycle-trial-expiry"] = {
        "task": "app.worker.tasks.expire_trials",
        "schedule": crontab(minute=_lifecycle_minute),
        "options": {"queue": "diagnosis_fast"},
    }
    beat_schedule["billing-lifecycle-past-due-grace"] = {
        "task": "app.worker.tasks.expire_past_due_grace",
        "schedule": crontab(minute=_lifecycle_minute),
        "options": {"queue": "diagnosis_fast"},
    }

# Wedge 3 — Judge Calibration (daily per-project sweep)
if settings.JUDGE_CALIBRATION_ENABLED:
    _cal_hour = min(max(int(settings.JUDGE_CALIBRATION_CRON_HOUR), 0), 23)
    _cal_minute = min(max(int(settings.JUDGE_CALIBRATION_CRON_MINUTE), 0), 59)
    beat_schedule["judge-calibration-daily"] = {
        "task": "app.worker.tasks.run_judge_calibration_all_projects",
        "schedule": crontab(minute=_cal_minute, hour=_cal_hour),
        "options": {"queue": "diagnosis_fast"},
    }

# Wedge 2 — Provider Drift Watch (daily at 04:00 UTC)
if settings.PROVIDER_DRIFT_WATCH_ENABLED:
    _drift_minute = min(max(int(settings.PROVIDER_DRIFT_WATCH_CRON_MINUTE), 0), 59)
    _drift_hour = min(max(int(settings.PROVIDER_DRIFT_WATCH_CRON_HOUR), 0), 23)
    beat_schedule["provider-drift-daily"] = {
        "task": "app.worker.tasks.run_provider_drift_watch",
        "schedule": crontab(minute=_drift_minute, hour=_drift_hour),
        "options": {"queue": "diagnosis_fast"},
    }

# ClickHouse sync — only scheduled when CLICKHOUSE_ENABLED is true
if settings.CLICKHOUSE_ENABLED:
    _ch_interval = max(10, int(settings.CLICKHOUSE_SYNC_INTERVAL_SECONDS))
    beat_schedule["clickhouse-sync"] = {
        "task": "app.worker.tasks.sync_clickhouse",
        "schedule": _ch_interval,
        "options": {"queue": "diagnosis_fast"},
    }

celery_app = Celery(
    "zroky",
    broker=settings.effective_celery_broker_url,
    backend=settings.effective_celery_result_backend,
)

celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_default_queue="diagnosis_fast",
    # Timeouts: prevent runaway tasks from hogging workers
    task_soft_time_limit=300,
    task_time_limit=600,
    # Retry policy: exponential back-off with a hard ceiling
    task_default_retry_delay=10,
    task_max_retries=3,
    # Dead-letter queue for permanently failed tasks
    task_routes={
        "app.worker.tasks.run_fast_diagnosis": {"queue": "diagnosis_fast"},
        "app.worker.tasks.run_pattern_diagnosis": {"queue": "diagnosis_pattern"},
    },
    # Broker/DLQ: route failed messages to a dead-letter exchange so they can be inspected
    broker_transport_options={
        "queue_order_strategy": "priority",
        "priority_steps": list(range(10)),
    },
    beat_schedule=beat_schedule,
)

celery_app.autodiscover_tasks(["app.worker"])
