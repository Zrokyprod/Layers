"""Thin email and Slack dispatcher.

All public functions are no-ops when credentials are not configured,
allowing the caller to invoke them unconditionally without guarding.
"""
from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Sequence

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def send_email(
    to: Sequence[str],
    subject: str,
    html_body: str,
    *,
    plain_body: str | None = None,
) -> bool:
    """Send an HTML email via SMTP.

    Returns True on success, False when SMTP is not configured or on error.
    The call is always safe to make — missing config is a no-op.
    """
    settings = get_settings()
    recipients = [r for r in to if r and r.strip()]
    if not settings.SMTP_HOST or not recipients:
        logger.debug("send_email: SMTP not configured or no recipients — skipping")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.ALERTS_FROM_EMAIL
        msg["To"] = ", ".join(recipients)

        if plain_body:
            msg.attach(MIMEText(plain_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.ALERTS_FROM_EMAIL, recipients, msg.as_string())

        logger.info("send_email: sent to %d recipients subject=%r", len(recipients), subject)
        return True

    except Exception as exc:  # noqa: BLE001
        logger.error("send_email failed: %s", exc)
        return False


def send_slack_message(text: str, blocks: list | None = None) -> bool:
    """Post a message to the configured Slack Incoming Webhook.

    Returns True on success, False when not configured or on error.
    """
    settings = get_settings()
    if not settings.SLACK_WEBHOOK_URL:
        logger.debug("send_slack_message: SLACK_WEBHOOK_URL not configured — skipping")
        return False

    payload: dict = {"text": text}
    if blocks:
        payload["blocks"] = blocks

    try:
        resp = httpx.post(str(settings.SLACK_WEBHOOK_URL), json=payload, timeout=5)
        resp.raise_for_status()
        logger.info("send_slack_message: posted successfully")
        return True

    except Exception as exc:  # noqa: BLE001
        logger.error("send_slack_message failed: %s", exc)
        return False
