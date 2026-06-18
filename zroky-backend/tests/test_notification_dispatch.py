"""Tests for app/services/notification_dispatch.py."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.notification_dispatch import _build_message, dispatch_alert_to_tenant_channels


def test_build_message_includes_categories_and_agent():
    msg = _build_message(["LOOP_DETECTED", "COST_SPIKE"], "checkout-agent", "diag-001")
    assert "LOOP_DETECTED" in msg
    assert "COST_SPIKE" in msg
    assert "checkout-agent" in msg
    assert "diag-001" in msg


def test_build_message_unknown_category_uses_default_emoji():
    msg = _build_message(["TOTALLY_NEW_CATEGORY"], "my-agent", None)
    assert "TOTALLY_NEW_CATEGORY" in msg


def test_build_message_no_diagnosis_id_omits_line():
    msg = _build_message(["AUTH_FAILURE"], "agent", None)
    assert "Diagnosis ID" not in msg


def test_slack_delivered_when_install_present():
    db = MagicMock()
    mock_install = MagicMock()
    mock_install.webhook_url = "https://hooks.slack.com/T123/B456/secret"

    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("app.services.notification_dispatch.get_slack_install", return_value=mock_install), \
         patch("httpx.post", return_value=mock_response) as mock_post:
        result = dispatch_alert_to_tenant_channels(
            db=db,
            tenant_id="tenant-abc",
            categories=["LOOP_DETECTED"],
            agent_name="my-agent",
            diagnosis_id="d-001",
        )

    assert result == {"slack": True}
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert call_args[0][0] == "https://hooks.slack.com/T123/B456/secret"
    assert "LOOP_DETECTED" in call_args[1]["json"]["text"]


def test_slack_skipped_when_no_install():
    db = MagicMock()

    with patch("app.services.notification_dispatch.get_slack_install", return_value=None), \
         patch("httpx.post") as mock_post:
        result = dispatch_alert_to_tenant_channels(
            db=db, tenant_id="tenant-abc", categories=["COST_SPIKE"], agent_name=None
        )

    assert result == {"slack": False}
    mock_post.assert_not_called()


def test_slack_skipped_when_install_has_no_webhook_url():
    db = MagicMock()
    mock_install = MagicMock()
    mock_install.webhook_url = None

    with patch("app.services.notification_dispatch.get_slack_install", return_value=mock_install), \
         patch("httpx.post") as mock_post:
        result = dispatch_alert_to_tenant_channels(
            db=db, tenant_id="tenant-abc", categories=["AUTH_FAILURE"], agent_name="agent"
        )

    assert result == {"slack": False}
    mock_post.assert_not_called()


def test_exception_in_slack_post_is_swallowed():
    db = MagicMock()
    mock_install = MagicMock()
    mock_install.webhook_url = "https://hooks.slack.com/broken"

    import httpx as _httpx

    with patch("app.services.notification_dispatch.get_slack_install", return_value=mock_install), \
         patch("httpx.post", side_effect=_httpx.ConnectError("timeout")):
        result = dispatch_alert_to_tenant_channels(
            db=db, tenant_id="tenant-abc", categories=["LOOP_DETECTED"], agent_name="agent"
        )

    assert result == {"slack": False}


def test_empty_categories_returns_false_without_posting():
    db = MagicMock()

    with patch("httpx.post") as mock_post:
        result = dispatch_alert_to_tenant_channels(
            db=db, tenant_id="tenant-abc", categories=[], agent_name="agent"
        )

    assert result == {"slack": False}
    mock_post.assert_not_called()
