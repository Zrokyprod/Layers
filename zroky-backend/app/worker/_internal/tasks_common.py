import json
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from sqlalchemy import and_, func, select
from sqlalchemy.orm import load_only, selectinload

from app.core.config import get_settings
from app.realtime.publisher import publish_diagnosis, publish_loop_alert, publish_auth_failure_alert, publish_rate_limit_alert, publish_cost_spike
from app.db.models import AuditLog, Call, DiagnosisFixWatch, DiagnosisJob, Project, ProjectDashboardConfig, ReplayRun
from app.db.session import SessionLocal, set_db_tenant_context
from app.observability.metrics import (
    record_diagnosis_job,
    record_diagnosis_rule_hits,
    record_retention_rows,
    record_retention_run,
)
from app.services.alerts import (
    auto_send_pending_alerts_to_slack,
    sync_alerts_from_jobs,
)
from app.services.diagnosis_engine import (
    build_diagnosis_result,
    evaluate_fast_rules,
    evaluate_pattern_rules,
)
from app.services.fix_adoption import (
    calibrate_resolved_fix_confidence,
    ensure_fix_event_prerequisites,
    evaluate_fix_regressions,
    evaluate_pending_fix_resolutions,
    record_fix_event,
)
from app.services.fix_identity import extract_fix_id_from_result, safe_json_object as _fix_safe_json_object
from app.services.loop_pattern_cache import mark_loop_detected_fired, summarize_loop_from_cache
from app.services.loop_signals import (
    DEFAULT_LOOP_WINDOW_SIZE,
    normalize_loop_text,
    output_signal,
    output_similarity_score,
    summarize_tool_lifecycle,
)
from app.services.privacy import mask_error_message, mask_payload, mask_value
from app.services.retention import (
    DEFAULT_RETENTION_DAYS,
    normalize_retention_days,
    purge_project_retention_data,
)
from app.worker.celery_app import celery_app
from app.worker.idempotency import idempotency_guard
from app.services.email_sender import send_email, send_slack_message
from app.services.digest_engine import (
    generate_weekly_digest,
    list_pending_digests,
    mark_digest_sent,
    monday_of,
    parse_summary_json,
    render_plain,
    resolve_recipient_emails,
)
logger = logging.getLogger(__name__)

LOOP_REPEAT_THRESHOLD = 5
LOOP_REPEAT_WINDOW_SECONDS = 90
LOOP_TOOL_WINDOW_SECONDS = 120
LOOP_COOLDOWN_SECONDS = 600
LOOP_PROGRESS_MIN_EVENTS = 3
LOOP_EVIDENCE_SAMPLE_LIMIT = 5
LOOP_REPEAT_SCAN_LIMIT = 64
LOOP_PROGRESS_SCAN_LIMIT = 96
LOOP_COOLDOWN_SCAN_LIMIT = 128
LOOP_WINDOW_SIZE = DEFAULT_LOOP_WINDOW_SIZE
TERMINAL_DIAGNOSIS_STATUSES = {"done", "completed", "failed", "dead_lettered"}
SUCCESS_DIAGNOSIS_STATUSES = {"done", "completed"}
REQUEUEABLE_DIAGNOSIS_STATUSES = {"pending", "queued", "retrying", "enqueue_failed"}



__all__ = [name for name in globals() if not name.startswith("__")]
