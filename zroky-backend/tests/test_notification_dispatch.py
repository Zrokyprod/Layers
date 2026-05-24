"""Tests for app/services/notification_dispatch.py"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.notification_dispatch import dispatch_alert_to_tenant_channels, _build_message


# ── _build_message ────────────────────────────────────────────────────────────

def test_build_message_includes_categories_and_agent():
    msg = _build_message(["LOOP_DETECTED", "COST_SPIKE"], "checkout-agent", "diag-001")
    assert "LOOP_DETECTED" in msg
    assert "COST_SPIKE" in msg
    assert "checkout-agent" in msg
    assert "diag-001" in msg


def test_build_message_unknown_category_uses_default_emoji():
    msg = _build_message(["TOTALLY_NEW_CATEGORY"], "my-agent", None)
    assert "🚨" in msg
    assert "TOTALLY_NEW_CATEGORY" in msg


def test_build_message_no_diagnosis_id_omits_line():
    msg = _build_message(["AUTH_FAILURE"], "agent", None)
    assert "Diagnosis ID" not in msg


# ── Slack delivery ────────────────────────────────────────────────────────────

def test_slack_delivered_when_install_present():
    db = MagicMock()
    mock_install = MagicMock()
    mock_install.webhook_url = "https://hooks.slack.com/T123/B456/secret"

    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("app.services.notification_dispatch.get_slack_install", return_value=mock_install), \
         patch("app.services.notification_dispatch.get_teams_install", return_value=None), \
         patch("httpx.post", return_value=mock_response) as mock_post:

        result = dispatch_alert_to_tenant_channels(
            db=db,
            tenant_id="tenant-abc",
            categories=["LOOP_DETECTED"],
            agent_name="my-agent",
            diagnosis_id="d-001",
        )

    assert result["slack"] is True
    assert result["teams"] is False
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert call_args[0][0] == "https://hooks.slack.com/T123/B456/secret"
    assert "LOOP_DETECTED" in call_args[1]["json"]["text"]


def test_slack_skipped_when_no_install():
    db = MagicMock()

    with patch("app.services.notification_dispatch.get_slack_install", return_value=None), \
         patch("app.services.notification_dispatch.get_teams_install", return_value=None), \
         patch("httpx.post") as mock_post:

        result = dispatch_alert_to_tenant_channels(
            db=db, tenant_id="tenant-abc", categories=["COST_SPIKE"], agent_name=None
        )

    assert result["slack"] is False
    mock_post.assert_not_called()


def test_slack_skipped_when_install_has_no_webhook_url():
    db = MagicMock()
    mock_install = MagicMock()
    mock_install.webhook_url = None

    with patch("app.services.notification_dispatch.get_slack_install", return_value=mock_install), \
         patch("app.services.notification_dispatch.get_teams_install", return_value=None), \
         patch("httpx.post") as mock_post:

        result = dispatch_alert_to_tenant_channels(
            db=db, tenant_id="tenant-abc", categories=["AUTH_FAILURE"], agent_name="agent"
        )

    assert result["slack"] is False
    mock_post.assert_not_called()


# ── Teams delivery ────────────────────────────────────────────────────────────

def test_teams_delivered_when_install_present():
    db = MagicMock()
    mock_install = MagicMock()
    mock_install.webhook_url_encrypted = "encrypted-blob"
    decrypted_url = "https://outlook.office.com/webhook/xxx"

    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("app.services.notification_dispatch.get_slack_install", return_value=None), \
         patch("app.services.notification_dispatch.get_teams_install", return_value=mock_install), \
         patch("app.services.notification_dispatch.decrypt_teams_webhook_url", return_value=decrypted_url), \
         patch("httpx.post", return_value=mock_response) as mock_post:

        result = dispatch_alert_to_tenant_channels(
            db=db,
            tenant_id="tenant-xyz",
            categories=["COST_SPIKE"],
            agent_name="billing-agent",
        )

    assert result["teams"] is True
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert call_args[0][0] == decrypted_url


def test_teams_skipped_when_no_install():
    db = MagicMock()

    with patch("app.services.notification_dispatch.get_slack_install", return_value=None), \
         patch("app.services.notification_dispatch.get_teams_install", return_value=None), \
         patch("httpx.post") as mock_post:

        result = dispatch_alert_to_tenant_channels(
            db=db, tenant_id="tenant-xyz", categories=["RATE_LIMIT"], agent_name=None
        )

    assert result["teams"] is False
    mock_post.assert_not_called()


# ── Exception safety ──────────────────────────────────────────────────────────

def test_exception_in_slack_post_is_swallowed():
    db = MagicMock()
    mock_install = MagicMock()
    mock_install.webhook_url = "https://hooks.slack.com/broken"

    import httpx as _httpx
    with patch("app.services.notification_dispatch.get_slack_install", return_value=mock_install), \
         patch("app.services.notification_dispatch.get_teams_install", return_value=None), \
         patch("httpx.post", side_effect=_httpx.ConnectError("timeout")):

        # Must not raise
        result = dispatch_alert_to_tenant_channels(
            db=db, tenant_id="tenant-abc", categories=["LOOP_DETECTED"], agent_name="agent"
        )

    assert result["slack"] is False


def test_empty_categories_returns_false_without_posting():
    db = MagicMock()

    with patch("httpx.post") as mock_post:
        result = dispatch_alert_to_tenant_channels(
            db=db, tenant_id="tenant-abc", categories=[], agent_name="agent"
        )

    assert result == {"slack": False, "teams": False}
    mock_post.assert_not_called()
