import os

from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()
testing = os.environ.get("TESTING", "").strip().lower() in {"1", "true", "yes"}
broker_url = settings.effective_celery_broker_url
result_backend = settings.effective_celery_result_backend
if testing and not settings.CELERY_BROKER_URL:
    broker_url = "memory://"
if testing and not settings.CELERY_RESULT_BACKEND:
    result_backend = "cache+memory://"

retention_minute = min(max(int(settings.RETENTION_ENFORCEMENT_CRON_MINUTE), 0), 59)
retention_hour = min(max(int(settings.RETENTION_ENFORCEMENT_CRON_HOUR), 0), 23)
digest_dow = min(max(int(settings.DIGEST_GENERATE_CRON_DAY_OF_WEEK), 0), 6)
digest_hour = min(max(int(settings.DIGEST_GENERATE_CRON_HOUR), 0), 23)
beat_schedule: dict[str, dict] = {}

if settings.RETENTION_ENFORCEMENT_ENABLED:
    beat_schedule["retention-enforcement-daily"] = {
        "task": "app.worker.tasks.run_retention_enforcement",
        "schedule": crontab(minute=retention_minute, hour=retention_hour),
        "options": {"queue": "diagnosis_fast"},
    }

if settings.DIGEST_ENABLED:
    beat_schedule["weekly-digest-generate"] = {
        "task": "app.worker.tasks.generate_weekly_digests",
        "schedule": crontab(day_of_week=digest_dow, hour=digest_hour, minute=0),
        "options": {"queue": "diagnosis_fast"},
    }
    beat_schedule["weekly-digest-send"] = {
        "task": "app.worker.tasks.send_pending_digests",
        "schedule": crontab(minute="*/5"),
        "options": {"queue": "diagnosis_fast"},
    }

# Always enabled: scan active fix-watches for recurrences every 4 hours
beat_schedule["fix-watch-recurrence-check"] = {
    "task": "app.worker.tasks.notify_fix_watch_recurrences",
    "schedule": crontab(minute=0, hour="*/4"),
    "options": {"queue": "diagnosis_fast"},
}

beat_schedule["action-post-execution-sweep"] = {
    "task": "app.worker.tasks.process_action_post_execution_jobs",
    "schedule": max(5, int(settings.ACTION_POST_EXECUTION_SWEEP_INTERVAL_SECONDS)),
    "options": {"queue": "diagnosis_fast"},
}
beat_schedule["stale-action-execution-attempt-sweep"] = {
    "task": "app.worker.tasks.sweep_stale_action_execution_attempts",
    "schedule": max(30, int(settings.ACTION_EXECUTION_ATTEMPT_SWEEP_INTERVAL_SECONDS)),
    "options": {"queue": "diagnosis_fast"},
}

# Module 12 subscription lifecycle sweeps.
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

if (
    settings.BILLING_ENABLED
    and settings.BILLING_PROVIDER == "razorpay"
    and settings.BILLING_RAZORPAY_RECONCILE_ENABLED
):
    _razorpay_reconcile_interval = max(
        60,
        int(settings.BILLING_RAZORPAY_RECONCILE_INTERVAL_SECONDS),
    )
    beat_schedule["billing-razorpay-pending-reconcile"] = {
        "task": "app.worker.tasks.reconcile_pending_razorpay_orders",
        "schedule": _razorpay_reconcile_interval,
        "options": {"queue": "diagnosis_fast"},
    }

# Wedge 3: Judge Calibration.
if settings.JUDGE_CALIBRATION_ENABLED:
    _cal_hour = min(max(int(settings.JUDGE_CALIBRATION_CRON_HOUR), 0), 23)
    _cal_minute = min(max(int(settings.JUDGE_CALIBRATION_CRON_MINUTE), 0), 59)
    beat_schedule["judge-calibration-daily"] = {
        "task": "app.worker.tasks.run_judge_calibration_all_projects",
        "schedule": crontab(minute=_cal_minute, hour=_cal_hour),
        "options": {"queue": "diagnosis_fast"},
    }

# Wedge 2: Provider Drift Watch.
if settings.PROVIDER_DRIFT_WATCH_ENABLED:
    _drift_minute = min(max(int(settings.PROVIDER_DRIFT_WATCH_CRON_MINUTE), 0), 59)
    _drift_hour = min(max(int(settings.PROVIDER_DRIFT_WATCH_CRON_HOUR), 0), 23)
    beat_schedule["provider-drift-daily"] = {
        "task": "app.worker.tasks.run_provider_drift_watch",
        "schedule": crontab(minute=_drift_minute, hour=_drift_hour),
        "options": {"queue": "diagnosis_fast"},
    }

if settings.CLICKHOUSE_ENABLED:
    _ch_interval = max(10, int(settings.CLICKHOUSE_SYNC_INTERVAL_SECONDS))
    beat_schedule["clickhouse-sync"] = {
        "task": "app.worker.tasks.sync_clickhouse",
        "schedule": _ch_interval,
        "options": {"queue": "diagnosis_fast"},
    }

if settings.GATEWAY_INGEST_STREAM_ENABLED:
    _gateway_interval = max(1, int(settings.GATEWAY_INGEST_POLL_INTERVAL_SECONDS))
    beat_schedule["gateway-ingest-stream"] = {
        "task": "app.worker.tasks.consume_gateway_ingest_stream",
        "schedule": _gateway_interval,
        "options": {"queue": "diagnosis_fast"},
    }

if settings.DISCOVERY_ENABLED:
    _discovery_refresh_hour = min(max(int(settings.DISCOVERY_REFRESH_CRON_HOUR), 0), 23)
    _discovery_refresh_minute = min(max(int(settings.DISCOVERY_REFRESH_CRON_MINUTE), 0), 59)
    _discovery_scan_interval = max(60, int(settings.DISCOVERY_SCAN_INTERVAL_SECONDS))
    beat_schedule["discovery-baseline-refresh-daily"] = {
        "task": "app.worker.tasks.refresh_discovery_baselines",
        "schedule": crontab(
            minute=_discovery_refresh_minute,
            hour=_discovery_refresh_hour,
        ),
        "options": {"queue": "diagnosis_fast"},
    }
    beat_schedule["discovery-anomaly-scan"] = {
        "task": "app.worker.tasks.scan_discovery_anomalies",
        "schedule": _discovery_scan_interval,
        "options": {"queue": "diagnosis_fast"},
    }

celery_app = Celery(
    "zroky",
    broker=broker_url,
    backend=result_backend,
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
    task_soft_time_limit=300,
    task_time_limit=600,
    task_default_retry_delay=10,
    task_max_retries=3,
    task_routes={
        "app.worker.tasks.run_fast_diagnosis": {"queue": "diagnosis_fast"},
        "app.worker.tasks.run_pattern_diagnosis": {"queue": "diagnosis_pattern"},
    },
    broker_transport_options={
        "queue_order_strategy": "priority",
        "priority_steps": list(range(10)),
    },
    beat_schedule=beat_schedule,
)

celery_app.autodiscover_tasks(["app.worker"])
