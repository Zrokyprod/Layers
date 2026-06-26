"""Sync-safe alert delivery to tenant Slack channels.

Called from Celery tasks (synchronous context). Uses httpx.post() directly
rather than the async helpers in slack_integration so it can be invoked without
an event loop.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ProjectAlert
from app.services.slack_integration import decrypt_slack_webhook_url, get_slack_install
from app.services.slack_approvals import build_runtime_policy_approval_slack_payload
from app.services.slack_judgment import (
    build_ci_gate_failed_alert_payload,
    build_judgment_alert_payload,
    build_new_issue_alert_payload,
    build_replay_failed_alert_payload,
    build_replay_verified_alert_payload,
)

logger = logging.getLogger(__name__)

_SEVERITY_EMOJI: dict[str, str] = {
    "LOOP_DETECTED": "🔁",
    "COST_SPIKE": "💸",
    "AUTH_FAILURE": "🔐",
    "RATE_LIMIT": "🚦",
    "TOKEN_OVERFLOW": "📦",
    "PROVIDER_ERROR": "⚡",
    "LATENCY_SPIKE": "🐢",
}

_DEFAULT_EMOJI = "🚨"


def _build_message(
    categories: list[str],
    agent_name: str | None,
    diagnosis_id: str | None,
) -> str:
    emojis = " ".join(_SEVERITY_EMOJI.get(c, _DEFAULT_EMOJI) for c in categories)
    cats = ", ".join(categories) if categories else "Unknown"
    agent = agent_name or "unknown agent"
    lines = [f"{emojis} *Zroky Alert — {cats}*", f"Agent: `{agent}`"]
    if diagnosis_id:
        lines.append(f"Diagnosis ID: `{diagnosis_id}`")
    lines.append("→ Open your Zroky dashboard to view the issue and suggested fix.")
    return "\n".join(lines)


def _post_sync(url: str, payload: dict[str, Any]) -> bool:
    """Fire-and-forget synchronous HTTP POST to a webhook URL."""
    try:
        resp = httpx.post(url, json=payload, timeout=5)
        if not (200 <= resp.status_code < 300):
            logger.warning(
                "notification_dispatch: webhook returned %s for %s",
                resp.status_code,
                url[:60],
            )
            return False
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("notification_dispatch: POST failed for %s: %s", url[:60], exc)
        return False


def _alert_context_for_slack(
    db: Session,
    *,
    tenant_id: str,
    diagnosis_id: str | None,
    categories: list[str],
) -> dict[str, str]:
    diagnosis = (diagnosis_id or "").strip()
    normalized_categories = sorted({category.strip().upper() for category in categories if category.strip()})
    if not diagnosis or not normalized_categories:
        return {}
    try:
        rows = db.execute(
            select(ProjectAlert).where(
                ProjectAlert.tenant_id == tenant_id,
                ProjectAlert.diagnosis_id == diagnosis,
                ProjectAlert.category.in_(normalized_categories),
            )
        ).scalars().all()
    except Exception as exc:  # noqa: BLE001
        logger.debug(
            "notification_dispatch: alert context lookup failed tenant=%s diagnosis=%s: %s",
            tenant_id,
            diagnosis,
            exc,
        )
        return {}
    rows = list(rows)
    if not rows:
        return {}
    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    selected = sorted(
        rows,
        key=lambda row: (
            severity_rank.get(str(row.severity or "").lower(), 99),
            row.created_at,
            row.id,
        ),
    )[0]
    return {
        "alert_id": str(selected.id),
        "alert_title": str(selected.title or "").strip(),
        "severity": str(selected.severity or "").strip(),
    }


def dispatch_slack_payload_to_tenant_channel(
    db: Session,
    tenant_id: str,
    payload: dict[str, Any],
    *,
    event_name: str,
) -> bool:
    """Deliver one Slack-only event payload to the tenant install."""
    try:
        slack_install = get_slack_install(db, tenant_id)
        if not slack_install or not slack_install.webhook_url:
            return False
        webhook_url = decrypt_slack_webhook_url(slack_install.webhook_url)
        if not webhook_url:
            return False
        delivered = _post_sync(webhook_url, payload)
        if delivered:
            logger.info(
                "notification_dispatch: Slack event delivered tenant=%s event=%s",
                tenant_id,
                event_name,
            )
        return delivered
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "notification_dispatch: Slack event lookup failed tenant=%s event=%s: %s",
            tenant_id,
            event_name,
            exc,
        )
        return False


def dispatch_new_issue_slack_alert(
    db: Session,
    *,
    tenant_id: str,
    issue_id: str,
    failure_code: str,
    severity: str | None,
    agent_name: str | None,
    diagnosis_id: str | None,
    call_id: str | None,
) -> bool:
    return dispatch_slack_payload_to_tenant_channel(
        db,
        tenant_id,
        build_new_issue_alert_payload(
            issue_id=issue_id,
            failure_code=failure_code,
            severity=severity,
            agent_name=agent_name,
            diagnosis_id=diagnosis_id,
            call_id=call_id,
        ),
        event_name="new_issue",
    )


def dispatch_replay_slack_alert(
    db: Session,
    *,
    tenant_id: str,
    run_id: str,
    status: str,
    trigger: str | None,
    git_sha: str | None,
    summary: dict[str, Any],
) -> bool:
    run_status = str(status or "").strip().lower()
    if summary.get("verified_fix") is True:
        return dispatch_slack_payload_to_tenant_channel(
            db,
            tenant_id,
            build_replay_verified_alert_payload(
                run_id=run_id,
                source_issue_id=_optional_str(summary.get("source_issue_id")),
                source_call_id=_optional_str(summary.get("source_call_id")),
                failure_code=_optional_str(summary.get("source_issue_failure_code")),
                verification_status=_optional_str(summary.get("verification_status")),
                git_sha=git_sha,
            ),
            event_name="replay_verified",
        )

    if run_status not in {"fail", "error"}:
        return False

    is_ci_gate = str(trigger or "").strip().lower() == "github"
    if is_ci_gate:
        return dispatch_slack_payload_to_tenant_channel(
            db,
            tenant_id,
            build_ci_gate_failed_alert_payload(
                run_id=run_id,
                status=run_status,
                git_sha=git_sha,
                source_issue_id=_optional_str(summary.get("source_issue_id")),
                failure_code=_optional_str(summary.get("source_issue_failure_code")),
                regressed_count=_optional_int(summary.get("regressed_count") or summary.get("fail_count")),
                error_count=_optional_int(summary.get("error_count")),
                trace_count=_optional_int(summary.get("trace_count") or summary.get("trace_count_executed")),
                regression_rate=_optional_float(summary.get("regression_rate")),
                threshold=_optional_float(summary.get("threshold")),
            ),
            event_name="ci_gate_failed",
        )

    return dispatch_slack_payload_to_tenant_channel(
        db,
        tenant_id,
        build_replay_failed_alert_payload(
            run_id=run_id,
            status=run_status,
            source_issue_id=_optional_str(summary.get("source_issue_id")),
            source_call_id=_optional_str(summary.get("source_call_id")),
            failure_code=_optional_str(summary.get("source_issue_failure_code")),
            verification_status=_optional_str(summary.get("verification_status")),
            fail_count=_optional_int(summary.get("fail_count")),
            error_count=_optional_int(summary.get("error_count")),
            git_sha=git_sha,
        ),
        event_name="replay_failed",
    )


def dispatch_ci_gate_failed_slack_alert(
    db: Session,
    *,
    tenant_id: str,
    run_id: str,
    status: str,
    git_sha: str | None,
    report: dict[str, Any],
) -> bool:
    run_status = str(status or report.get("verdict") or "").strip().lower()
    if run_status not in {"fail", "error"}:
        return False
    return dispatch_slack_payload_to_tenant_channel(
        db,
        tenant_id,
        build_ci_gate_failed_alert_payload(
            run_id=run_id,
            status=run_status,
            git_sha=git_sha,
            regressed_count=_optional_int(report.get("regressed_count")),
            error_count=_optional_int(report.get("error_count")),
            trace_count=_optional_int(report.get("trace_count")),
            regression_rate=_optional_float(report.get("regression_rate")),
            threshold=_optional_float(report.get("threshold")),
        ),
        event_name="ci_gate_failed",
    )


def dispatch_runtime_policy_approval_slack_request(
    db: Session,
    *,
    tenant_id: str,
    decision: Any,
) -> bool:
    return dispatch_slack_payload_to_tenant_channel(
        db,
        tenant_id,
        build_runtime_policy_approval_slack_payload(decision),
        event_name="runtime_policy_approval",
    )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def dispatch_alert_to_tenant_channels(
    db: Session,
    tenant_id: str,
    categories: list[str],
    agent_name: str | None = None,
    diagnosis_id: str | None = None,
) -> dict[str, bool]:
    """Deliver an alert to all connected channels for the given tenant.

    Synchronous and exception-safe — a delivery failure never propagates to
    the calling Celery task.

    Returns a dict recording whether Slack was successfully notified:
        {"slack": True}
    """
    if not categories:
        return {"slack": False}

    alert_context = _alert_context_for_slack(
        db,
        tenant_id=tenant_id,
        diagnosis_id=diagnosis_id,
        categories=categories,
    )
    msg = _build_message(categories, agent_name, diagnosis_id)
    result: dict[str, bool] = {"slack": False}

    # ── Slack ──────────────────────────────────────────────────────────────────
    try:
        slack_install = get_slack_install(db, tenant_id)
        if slack_install and slack_install.webhook_url:
            webhook_url = decrypt_slack_webhook_url(slack_install.webhook_url)
            if webhook_url:
                result["slack"] = _post_sync(
                    webhook_url,
                    build_judgment_alert_payload(
                        text=msg,
                        categories=categories,
                        agent_name=agent_name,
                        diagnosis_id=diagnosis_id,
                        severity=alert_context.get("severity"),
                        alert_id=alert_context.get("alert_id"),
                        alert_title=alert_context.get("alert_title"),
                    ),
                )
                if result["slack"]:
                    logger.info(
                        "notification_dispatch: Slack delivered tenant=%s categories=%s",
                        tenant_id,
                        categories,
                    )
    except Exception as exc:  # noqa: BLE001
        logger.error("notification_dispatch: Slack lookup failed tenant=%s: %s", tenant_id, exc)

    return result
