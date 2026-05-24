"""Sync-safe alert delivery to tenant Slack / Teams channels.

Called from Celery tasks (synchronous context). Uses httpx.post() directly
rather than the async helpers in slack_integration / teams_integration so it
can be invoked without an event loop.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.services.slack_integration import get_slack_install
from app.services.teams_integration import get_teams_install, decrypt_teams_webhook_url

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

    Returns a dict recording which channels were successfully notified:
        {"slack": True, "teams": False, ...}
    """
    if not categories:
        return {"slack": False, "teams": False}

    msg = _build_message(categories, agent_name, diagnosis_id)
    result: dict[str, bool] = {"slack": False, "teams": False}

    # ── Slack ──────────────────────────────────────────────────────────────────
    try:
        slack_install = get_slack_install(db, tenant_id)
        if slack_install and slack_install.webhook_url:
            result["slack"] = _post_sync(
                slack_install.webhook_url,
                {"text": msg},
            )
            if result["slack"]:
                logger.info(
                    "notification_dispatch: Slack delivered tenant=%s categories=%s",
                    tenant_id,
                    categories,
                )
    except Exception as exc:  # noqa: BLE001
        logger.error("notification_dispatch: Slack lookup failed tenant=%s: %s", tenant_id, exc)

    # ── Teams ──────────────────────────────────────────────────────────────────
    try:
        teams_install = get_teams_install(db, tenant_id)
        if teams_install:
            webhook_url = decrypt_teams_webhook_url(teams_install.webhook_url_encrypted)
            if webhook_url:
                result["teams"] = _post_sync(
                    webhook_url,
                    {"text": msg},
                )
                if result["teams"]:
                    logger.info(
                        "notification_dispatch: Teams delivered tenant=%s categories=%s",
                        tenant_id,
                        categories,
                    )
    except Exception as exc:  # noqa: BLE001
        logger.error("notification_dispatch: Teams lookup failed tenant=%s: %s", tenant_id, exc)

    return result
