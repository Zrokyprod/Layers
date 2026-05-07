from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

retention_minute = min(max(int(settings.RETENTION_ENFORCEMENT_CRON_MINUTE), 0), 59)
retention_hour = min(max(int(settings.RETENTION_ENFORCEMENT_CRON_HOUR), 0), 23)
exchange_refresh_minutes = min(max(int(settings.EXCHANGE_RATE_REFRESH_INTERVAL_MINUTES), 5), 60)
weekly_email_dow = min(max(int(settings.WEEKLY_IMPACT_EMAIL_CRON_DAY_OF_WEEK), 0), 6)
weekly_email_hour = min(max(int(settings.WEEKLY_IMPACT_EMAIL_CRON_HOUR), 0), 23)
beat_schedule: dict[str, dict] = {}
if settings.RETENTION_ENFORCEMENT_ENABLED:
    beat_schedule["retention-enforcement-daily"] = {
        "task": "app.worker.tasks.run_retention_enforcement",
        "schedule": crontab(minute=retention_minute, hour=retention_hour),
        "options": {"queue": "diagnosis_fast"},
    }
if settings.EXCHANGE_RATE_ENABLE_LIVE_FETCH:
    beat_schedule["exchange-rate-refresh"] = {
        "task": "app.worker.tasks.refresh_exchange_rate_cache",
        "schedule": crontab(minute=f"*/{exchange_refresh_minutes}"),
        "options": {"queue": "diagnosis_fast"},
    }
if settings.WEEKLY_IMPACT_EMAIL_ENABLED:
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
