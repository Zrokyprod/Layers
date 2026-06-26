from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import DiagnosisJob, Project, ProjectAlert, RuntimePolicyAuditEvent, RuntimePolicyDecision, TenantSlackInstall
from app.db.session import get_db_session, get_db_session_read
from app.main import app
from app.services.ask import AskAnswer
from app.services.alerts import auto_send_pending_alerts_to_slack
from app.services.slack_approvals import slack_approval_value
from app.services.slack_integration import decrypt_slack_webhook_url, encrypt_slack_webhook_url
from app.services.slack_judgment import (
    build_judgment_alert_payload,
    verify_slack_signature,
)

_SECRET = "slack-signing-secret"
_TS = "1893456000"


@pytest.fixture()
def client_ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SLACK_SIGNING_SECRET", _SECRET)
    monkeypatch.setenv("FRONTEND_URL", "https://dashboard.test")
    get_settings.cache_clear()

    db_path = tmp_path / "test_slack_judgment.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    testing_session_local = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        future=True,
    )
    Base.metadata.create_all(bind=engine)

    def override_get_db_session():
        session = testing_session_local()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_db_session_read] = override_get_db_session

    with TestClient(app) as test_client:
        yield test_client, testing_session_local

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    get_settings.cache_clear()


def _seed_slack_install(
    session,
    *,
    project_id: str = "proj-slack",
    team_id: str = "T123",
    channel_id: str = "C123",
    approval_user_ids: list[str] | None = None,
) -> None:
    session.add(Project(id=project_id, name=f"Project {project_id}"))
    session.add(
        TenantSlackInstall(
            tenant_id=project_id,
            team_id=team_id,
            team_name="Acme",
            access_token_encrypted="encrypted-token",
            webhook_url="https://hooks.slack.com/services/test",
            channel_id=channel_id,
            channel_name="#alerts",
            bot_user_id="B123",
            scope="incoming-webhook,commands",
            approval_user_ids_json=json.dumps(approval_user_ids if approval_user_ids is not None else ["U777"]),
            installed_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    session.commit()


def _seed_project(session, project_id: str = "proj-slack") -> None:
    session.add(Project(id=project_id, name=f"Project {project_id}"))
    session.commit()


def _seed_completed_diagnosis_job(
    session,
    *,
    project_id: str,
    diagnosis_id: str,
    category: str,
    root_cause: str = "Agent failure detected.",
    agent_name: str = "refund-agent",
) -> None:
    session.add(
        DiagnosisJob(
            tenant_id=project_id,
            diagnosis_id=diagnosis_id,
            status="completed",
            payload_json=json.dumps({"agent_name": agent_name}, separators=(",", ":")),
            result_json=json.dumps(
                {
                    "diagnoses": [
                        {
                            "category": category,
                            "root_cause": root_cause,
                            "evidence": {"category": category, "agent_name": agent_name},
                        }
                    ]
                },
                separators=(",", ":"),
            ),
        )
    )
    session.commit()


def _signed_headers(
    body: bytes,
    *,
    timestamp: str | None = None,
    secret: str = _SECRET,
) -> dict[str, str]:
    timestamp = timestamp or str(int(time.time()))
    base = b"v0:" + timestamp.encode("utf-8") + b":" + body
    signature = "v0=" + hmac.new(secret.encode("utf-8"), base, hashlib.sha256).hexdigest()
    return {
        "content-type": "application/x-www-form-urlencoded",
        "x-slack-request-timestamp": timestamp,
        "x-slack-signature": signature,
    }


def _post_signed(client: TestClient, path: str, fields: dict[str, str]):
    body = urlencode(fields).encode("utf-8")
    return client.post(path, content=body, headers=_signed_headers(body))


def _seed_pending_runtime_policy_decision(
    session,
    *,
    project_id: str = "proj-slack",
    decision_id: str = "decision-slack-approval",
    approval_scope_hash: str = "scope-slack-approval",
    expires_at: datetime | None = None,
    required_approval_count: int = 1,
) -> tuple[str, str]:
    row = RuntimePolicyDecision(
        id=decision_id,
        project_id=project_id,
        trace_id="trace-slack-approval",
        agent_name="refund-agent",
        role="operator",
        action_type="refund",
        tool_name="refund_payment",
        decision="requires_approval",
        status="pending_approval",
        reasons_json=json.dumps(["refund requires human approval"]),
        request_json=json.dumps(
            {
                "tool_args": {
                    "intent_digest": "sha256:intent-slack-approval",
                    "resource": {"id": "rf_slack"},
                    "parameters": {"amount_minor": 75000, "currency": "USD"},
                }
            },
            separators=(",", ":"),
        ),
        policy_snapshot_json="{}",
        intended_action_json="{}",
        trace_context_json="{}",
        policy_hit_json="{}",
        business_impact_json="{}",
        approval_scope_hash=approval_scope_hash,
        required_approval_count=required_approval_count,
        approval_count=0,
        approver_subjects_json="[]",
        expires_at=expires_at,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row.id, slack_approval_value(row)


def _post_slack_action(
    client: TestClient,
    *,
    action_id: str,
    value: str,
    user_id: str = "U777",
    username: str = "finance-lead",
):
    payload = {
        "team": {"id": "T123"},
        "channel": {"id": "C123"},
        "user": {"id": user_id, "username": username},
        "actions": [{"action_id": action_id, "value": value}],
    }
    return _post_signed(
        client,
        "/v1/integrations/slack/actions",
        {"payload": json.dumps(payload, separators=(",", ":"))},
    )


def test_slack_status_is_disconnected_without_credentials(client_ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    client, session_local = client_ctx
    for key in (
        "SLACK_CLIENT_ID",
        "SLACK_CLIENT_SECRET",
        "SLACK_TOKEN_ENCRYPTION_KEY",
        "GITHUB_TOKEN_ENCRYPTION_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    with session_local() as session:
        _seed_project(session, "proj-no-slack")

    response = client.get(
        "/v1/integrations/slack/status",
        headers={"X-Project-Id": "proj-no-slack"},
    )

    assert response.status_code == 200
    assert response.json()["connected"] is False
    assert response.json()["scopes"] == []


def test_slack_install_reports_missing_oauth_config(client_ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    client, session_local = client_ctx
    monkeypatch.delenv("SLACK_CLIENT_ID", raising=False)
    monkeypatch.delenv("SLACK_CLIENT_SECRET", raising=False)
    get_settings.cache_clear()
    with session_local() as session:
        _seed_project(session, "proj-oauth-missing")

    response = client.post(
        "/v1/integrations/slack/install",
        headers={"X-Project-Id": "proj-oauth-missing"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Slack OAuth is not configured on this server."


def test_slack_install_reports_missing_token_encryption_key(
    client_ctx,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, session_local = client_ctx
    monkeypatch.setenv("SLACK_CLIENT_ID", "client-123")
    monkeypatch.setenv("SLACK_CLIENT_SECRET", "secret-123")
    monkeypatch.delenv("SLACK_TOKEN_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN_ENCRYPTION_KEY", raising=False)
    get_settings.cache_clear()
    with session_local() as session:
        _seed_project(session, "proj-encryption-missing")

    response = client.post(
        "/v1/integrations/slack/install",
        headers={"X-Project-Id": "proj-encryption-missing"},
    )

    assert response.status_code == 503
    assert "SLACK_TOKEN_ENCRYPTION_KEY is not configured" in response.json()["detail"]


def test_slack_oauth_callback_stores_install(client_ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    client, session_local = client_ctx
    monkeypatch.setenv("SLACK_CLIENT_ID", "client-123")
    monkeypatch.setenv("SLACK_CLIENT_SECRET", "secret-123")
    monkeypatch.setenv("SLACK_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))
    monkeypatch.setenv("OAUTH_STATE_SECRET", "state-secret")
    monkeypatch.setenv("SLACK_OAUTH_REDIRECT_URL", "http://testserver/v1/integrations/slack/callback")
    monkeypatch.setenv("FRONTEND_URL", "https://dashboard.test")
    get_settings.cache_clear()
    with session_local() as session:
        _seed_project(session, "proj-oauth")

    start = client.post(
        "/v1/integrations/slack/install",
        headers={"X-Project-Id": "proj-oauth"},
    )
    assert start.status_code == 200
    state = parse_qs(urlparse(start.json()["authorization_url"]).query)["state"][0]

    slack_payload = {
        "ok": True,
        "access_token": "xoxb-test-token",
        "team": {"id": "T999", "name": "Acme"},
        "incoming_webhook": {
            "url": "https://hooks.slack.com/services/test",
            "channel_id": "C999",
            "channel": "alerts",
        },
        "bot_user_id": "B999",
        "scope": "incoming-webhook,commands",
        "authed_user": {"id": "UINSTALLER"},
    }
    with patch("app.api.routes.integrations._exchange_slack_code", return_value=slack_payload):
        callback = client.get(
            "/v1/integrations/slack/callback",
            params={"code": "code-123", "state": state},
            follow_redirects=False,
        )

    assert callback.status_code in {302, 303, 307}
    assert callback.headers["location"] == "https://dashboard.test/settings/integrations/slack?connected=1"
    with session_local() as session:
        install = session.get(TenantSlackInstall, "proj-oauth")
        if install is None:
            install = session.query(TenantSlackInstall).filter_by(tenant_id="proj-oauth").one()
        assert install.team_id == "T999"
        assert install.channel_name == "alerts"
        assert install.webhook_url != "https://hooks.slack.com/services/test"
        assert install.webhook_url.startswith("fernet:")
        assert decrypt_slack_webhook_url(install.webhook_url) == "https://hooks.slack.com/services/test"
        assert json.loads(install.approval_user_ids_json) == ["UINSTALLER"]


def test_slack_test_message_without_install_is_cleanly_blocked(client_ctx) -> None:
    client, session_local = client_ctx
    with session_local() as session:
        _seed_project(session, "proj-test-unconnected")

    response = client.post(
        "/v1/integrations/slack/test",
        headers={"X-Project-Id": "proj-test-unconnected"},
        json={"text": "hello"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Slack is not connected for this project."


def test_slack_test_message_posts_to_installed_webhook(client_ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    client, session_local = client_ctx
    calls: list[dict[str, object]] = []

    class _Response:
        status_code = 200

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json):
            calls.append({"url": url, "json": json})
            return _Response()

    with session_local() as session:
        _seed_slack_install(session, project_id="proj-test-connected")

    monkeypatch.setattr("app.services.slack_integration.httpx.AsyncClient", _Client)
    response = client.post(
        "/v1/integrations/slack/test",
        headers={"X-Project-Id": "proj-test-connected"},
        json={"text": "custom test"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "message": "Slack test message sent."}
    assert calls == [
        {
            "url": "https://hooks.slack.com/services/test",
            "json": {"text": "custom test"},
        }
    ]


def test_alert_channel_test_posts_to_installed_slack(client_ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    client, session_local = client_ctx
    calls: list[dict[str, object]] = []

    class _Response:
        status_code = 200

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json):
            calls.append({"url": url, "json": json})
            return _Response()

    with session_local() as session:
        _seed_slack_install(session, project_id="proj-alert-slack-connected")

    monkeypatch.setattr("app.services.slack_integration.httpx.AsyncClient", _Client)
    response = client.post(
        "/v1/alerts/channel-test",
        headers={"X-Project-Id": "proj-alert-slack-connected"},
        json={"channel": "slack"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "channel": "slack",
        "status": "sent",
        "message": "Slack alert channel test sent.",
    }
    assert calls == [
        {
            "url": "https://hooks.slack.com/services/test",
            "json": {
                "text": "Zroky alert channel test: Slack notifications are connected for this project.",
            },
        }
    ]


def test_alert_channel_test_blocks_slack_without_install(client_ctx) -> None:
    client, session_local = client_ctx
    with session_local() as session:
        _seed_project(session, "proj-alert-slack-missing")

    response = client.post(
        "/v1/alerts/channel-test",
        headers={"X-Project-Id": "proj-alert-slack-missing"},
        json={"channel": "slack"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Slack is not connected for this project."


def test_auto_slack_delivery_marks_project_alert_sent(client_ctx) -> None:
    _, session_local = client_ctx

    class _Response:
        status_code = 200

    with session_local() as session:
        _seed_slack_install(session, project_id="proj-auto-slack")
        session.add(
            ProjectAlert(
                tenant_id="proj-auto-slack",
                diagnosis_id="diag-auto-slack",
                category="LOOP_DETECTED",
                severity="critical",
                status="OPEN",
                source="diagnosis_engine",
                title="Refund agent loop detected.",
                evidence_json="{}",
            )
        )
        session.commit()

        with patch("httpx.post", return_value=_Response()) as mock_post:
            result = auto_send_pending_alerts_to_slack(
                session,
                tenant_id="proj-auto-slack",
                diagnosis_id="diag-auto-slack",
                categories=["LOOP_DETECTED"],
                agent_name="refund-agent",
            )

        alert = session.query(ProjectAlert).filter_by(tenant_id="proj-auto-slack").one()

    assert result == {"attempted": 1, "slack": True, "status": "sent"}
    assert alert.slack_delivery_status == "sent"
    assert alert.slack_delivery_attempted_at is not None
    assert alert.slack_delivery_error is None
    mock_post.assert_called_once()
    payload = mock_post.call_args.kwargs["json"]
    assert payload["text"] == "Critical alert: Refund agent loop detected."
    assert "LOOP_DETECTED" in str(payload["blocks"])
    assert "Open approval" in str(payload["blocks"])


def test_auto_slack_delivery_marks_project_alert_not_connected(client_ctx) -> None:
    _, session_local = client_ctx
    with session_local() as session:
        _seed_project(session, "proj-auto-slack-missing")
        session.add(
            ProjectAlert(
                tenant_id="proj-auto-slack-missing",
                diagnosis_id="diag-auto-slack-missing",
                category="COST_SPIKE",
                severity="high",
                status="OPEN",
                source="diagnosis_engine",
                title="Cost spike detected.",
                evidence_json="{}",
            )
        )
        session.commit()

        with patch("httpx.post") as mock_post:
            result = auto_send_pending_alerts_to_slack(
                session,
                tenant_id="proj-auto-slack-missing",
                diagnosis_id="diag-auto-slack-missing",
                categories=["COST_SPIKE"],
                agent_name="billing-agent",
            )

        alert = session.query(ProjectAlert).filter_by(tenant_id="proj-auto-slack-missing").one()

    assert result == {"attempted": 1, "slack": False, "status": "not_connected"}
    assert alert.slack_delivery_status == "not_connected"
    assert alert.slack_delivery_attempted_at is not None
    assert alert.slack_delivery_error == "Slack is not connected for this project."
    mock_post.assert_not_called()


def test_auto_slack_delivery_skips_non_actionable_alerts(client_ctx) -> None:
    _, session_local = client_ctx
    with session_local() as session:
        _seed_slack_install(session, project_id="proj-auto-slack-low")
        session.add(
            ProjectAlert(
                tenant_id="proj-auto-slack-low",
                diagnosis_id="diag-auto-slack-low",
                category="INFO_SIGNAL",
                severity="low",
                status="OPEN",
                source="diagnosis_engine",
                title="Low severity informational signal.",
                evidence_json="{}",
            )
        )
        session.commit()

        with patch("httpx.post") as mock_post:
            result = auto_send_pending_alerts_to_slack(
                session,
                tenant_id="proj-auto-slack-low",
                diagnosis_id="diag-auto-slack-low",
                categories=["INFO_SIGNAL"],
                agent_name="info-agent",
            )

        alert = session.query(ProjectAlert).filter_by(tenant_id="proj-auto-slack-low").one()

    assert result == {"attempted": 0, "slack": False, "status": "skipped"}
    assert alert.slack_delivery_status == "not_attempted"
    assert alert.slack_delivery_attempted_at is None
    mock_post.assert_not_called()


def test_alert_list_lazy_sync_auto_sends_high_alert_once(client_ctx) -> None:
    client, session_local = client_ctx

    class _Response:
        status_code = 200

    with session_local() as session:
        _seed_slack_install(session, project_id="proj-list-auto-slack")
        _seed_completed_diagnosis_job(
            session,
            project_id="proj-list-auto-slack",
            diagnosis_id="diag-list-auto-slack",
            category="LOOP_DETECTED",
            root_cause="Refund agent loop detected.",
        )

    headers = {"X-Project-Id": "proj-list-auto-slack"}
    with patch("httpx.post", return_value=_Response()) as mock_post:
        first = client.get("/v1/alerts", headers=headers)

        assert first.status_code == 200
        body = first.json()
        assert body["total"] == 1
        alert_id = body["items"][0]["alert_id"]
        assert body["items"][0]["severity"] == "high"
        assert body["items"][0]["slack_delivery_status"] == "sent"
        assert body["items"][0]["slack_delivery_attempted_at"] is not None
        mock_post.assert_called_once()

        second = client.get("/v1/alerts", headers=headers)
        detail = client.get(f"/v1/alerts/{alert_id}", headers=headers)

    assert second.status_code == 200
    assert detail.status_code == 200
    assert detail.json()["slack_delivery_status"] == "sent"
    mock_post.assert_called_once()


def test_alert_list_lazy_sync_marks_high_alert_not_connected_without_slack(client_ctx) -> None:
    client, session_local = client_ctx
    with session_local() as session:
        _seed_project(session, "proj-list-auto-slack-missing")
        _seed_completed_diagnosis_job(
            session,
            project_id="proj-list-auto-slack-missing",
            diagnosis_id="diag-list-auto-slack-missing",
            category="COST_SPIKE",
            root_cause="Cost spike detected.",
            agent_name="billing-agent",
        )

    with patch("httpx.post") as mock_post:
        response = client.get(
            "/v1/alerts",
            headers={"X-Project-Id": "proj-list-auto-slack-missing"},
        )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["severity"] == "high"
    assert item["slack_delivery_status"] == "not_connected"
    assert item["slack_delivery_attempted_at"] is not None
    assert item["slack_delivery_error"] == "Slack is not connected for this project."
    mock_post.assert_not_called()


def test_alert_list_lazy_sync_marks_high_alert_failed_when_webhook_fails(client_ctx) -> None:
    client, session_local = client_ctx

    class _Response:
        status_code = 500

    with session_local() as session:
        _seed_slack_install(session, project_id="proj-list-auto-slack-fail")
        _seed_completed_diagnosis_job(
            session,
            project_id="proj-list-auto-slack-fail",
            diagnosis_id="diag-list-auto-slack-fail",
            category="AUTH_FAILURE",
            root_cause="Auth failure detected.",
            agent_name="auth-agent",
        )

    with patch("httpx.post", return_value=_Response()) as mock_post:
        response = client.get(
            "/v1/alerts",
            headers={"X-Project-Id": "proj-list-auto-slack-fail"},
        )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["severity"] == "high"
    assert item["slack_delivery_status"] == "failed"
    assert item["slack_delivery_attempted_at"] is not None
    assert item["slack_delivery_error"] == "Slack webhook delivery failed."
    mock_post.assert_called_once()


def test_alert_list_lazy_sync_skips_low_severity_slack_notification(client_ctx) -> None:
    client, session_local = client_ctx
    with session_local() as session:
        _seed_slack_install(session, project_id="proj-list-auto-slack-low")
        _seed_completed_diagnosis_job(
            session,
            project_id="proj-list-auto-slack-low",
            diagnosis_id="diag-list-auto-slack-low",
            category="SCHEMA_VIOLATION",
            root_cause="Schema validation failed.",
            agent_name="schema-agent",
        )

    with patch("httpx.post") as mock_post:
        response = client.get(
            "/v1/alerts",
            headers={"X-Project-Id": "proj-list-auto-slack-low"},
        )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["severity"] == "low"
    assert item["slack_delivery_status"] == "not_attempted"
    assert item["slack_delivery_attempted_at"] is None
    mock_post.assert_not_called()


def test_retry_slack_delivery_resends_failed_alert(client_ctx) -> None:
    client, session_local = client_ctx

    class _Response:
        status_code = 200

    with session_local() as session:
        _seed_slack_install(session, project_id="proj-retry-slack")
        alert = ProjectAlert(
            tenant_id="proj-retry-slack",
            diagnosis_id="diag-retry-slack",
            category="LOOP_DETECTED",
            severity="critical",
            status="OPEN",
            source="diagnosis_engine",
            title="Refund agent loop detected.",
            evidence_json="{}",
            slack_delivery_status="failed",
            slack_delivery_attempted_at=datetime.now(timezone.utc),
            slack_delivery_error="Slack webhook delivery failed.",
        )
        session.add(alert)
        session.commit()
        alert_id = alert.id

    with patch("httpx.post", return_value=_Response()) as mock_post:
        response = client.post(
            f"/v1/alerts/{alert_id}/retry-slack",
            headers={"X-Project-Id": "proj-retry-slack"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["slack_delivery_status"] == "sent"
    assert body["slack_delivery_error"] is None
    mock_post.assert_called_once()


def test_retry_slack_delivery_marks_not_connected_when_slack_missing(client_ctx) -> None:
    client, session_local = client_ctx
    with session_local() as session:
        _seed_project(session, "proj-retry-slack-missing")
        alert = ProjectAlert(
            tenant_id="proj-retry-slack-missing",
            diagnosis_id="diag-retry-slack-missing",
            category="COST_SPIKE",
            severity="high",
            status="OPEN",
            source="diagnosis_engine",
            title="Cost spike detected.",
            evidence_json="{}",
            slack_delivery_status="failed",
            slack_delivery_attempted_at=datetime.now(timezone.utc),
            slack_delivery_error="Slack webhook delivery failed.",
        )
        session.add(alert)
        session.commit()
        alert_id = alert.id

    with patch("httpx.post") as mock_post:
        response = client.post(
            f"/v1/alerts/{alert_id}/retry-slack",
            headers={"X-Project-Id": "proj-retry-slack-missing"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["slack_delivery_status"] == "not_connected"
    assert body["slack_delivery_error"] == "Slack is not connected for this project."
    mock_post.assert_not_called()


def test_retry_slack_delivery_rejects_low_severity_alert(client_ctx) -> None:
    client, session_local = client_ctx
    with session_local() as session:
        _seed_slack_install(session, project_id="proj-retry-slack-low")
        alert = ProjectAlert(
            tenant_id="proj-retry-slack-low",
            diagnosis_id="diag-retry-slack-low",
            category="INFO_SIGNAL",
            severity="low",
            status="OPEN",
            source="diagnosis_engine",
            title="Low severity signal.",
            evidence_json="{}",
            slack_delivery_status="failed",
            slack_delivery_attempted_at=datetime.now(timezone.utc),
            slack_delivery_error="Slack webhook delivery failed.",
        )
        session.add(alert)
        session.commit()
        alert_id = alert.id

    response = client.post(
        f"/v1/alerts/{alert_id}/retry-slack",
        headers={"X-Project-Id": "proj-retry-slack-low"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Only high and critical alerts can retry Slack notification."


def test_slack_test_message_decrypts_stored_webhook(client_ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    client, session_local = client_ctx
    calls: list[dict[str, object]] = []
    monkeypatch.setenv("SLACK_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))
    get_settings.cache_clear()

    class _Response:
        status_code = 200

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json):
            calls.append({"url": url, "json": json})
            return _Response()

    with session_local() as session:
        _seed_slack_install(session, project_id="proj-test-encrypted")
        install = session.query(TenantSlackInstall).filter_by(tenant_id="proj-test-encrypted").one()
        install.webhook_url = encrypt_slack_webhook_url("https://hooks.slack.com/services/encrypted")
        session.commit()

    monkeypatch.setattr("app.services.slack_integration.httpx.AsyncClient", _Client)
    response = client.post(
        "/v1/integrations/slack/test",
        headers={"X-Project-Id": "proj-test-encrypted"},
        json={"text": "custom test"},
    )

    assert response.status_code == 200
    assert calls == [
        {
            "url": "https://hooks.slack.com/services/encrypted",
            "json": {"text": "custom test"},
        }
    ]


def test_slack_test_message_reports_webhook_failure(client_ctx, monkeypatch: pytest.MonkeyPatch) -> None:
    client, session_local = client_ctx

    class _Response:
        status_code = 500

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json):
            return _Response()

    with session_local() as session:
        _seed_slack_install(session, project_id="proj-test-failure")

    monkeypatch.setattr("app.services.slack_integration.httpx.AsyncClient", _Client)
    response = client.post(
        "/v1/integrations/slack/test",
        headers={"X-Project-Id": "proj-test-failure"},
        json={"text": "custom test"},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "Slack test message failed."


def test_verify_slack_signature_accepts_current_signed_body() -> None:
    body = b"team_id=T123&text=help"
    headers = _signed_headers(body, timestamp=_TS)

    assert verify_slack_signature(
        _SECRET,
        headers["x-slack-request-timestamp"],
        body,
        headers["x-slack-signature"],
        now=int(_TS),
    )


def test_verify_slack_signature_rejects_tampered_body() -> None:
    body = b"team_id=T123&text=help"
    headers = _signed_headers(body, timestamp=_TS)

    assert not verify_slack_signature(
        _SECRET,
        headers["x-slack-request-timestamp"],
        b"team_id=T123&text=changed",
        headers["x-slack-signature"],
        now=int(_TS),
    )


def test_slack_command_runs_ask_judgment_for_resolved_install(client_ctx) -> None:
    client, session_local = client_ctx
    with session_local() as session:
        _seed_slack_install(session)

    answer = AskAnswer(
        answer="issue-schema is a schema violation on refund-agent.",
        suggested_actions=["Open the evidence trace", "Add replay coverage"],
        confidence=0.75,
        intent="failure",
        evidence=[
            {
                "kind": "issue",
                "id": "issue-schema",
                "label": "This issue",
                "href": "/approvals?issue_id=issue-schema",
            }
        ],
        used_llm=False,
    )
    with patch("app.services.slack_judgment.answer_question", return_value=answer) as mocked:
        response = _post_signed(
            client,
            "/v1/integrations/slack/command",
            {
                "team_id": "T123",
                "channel_id": "C123",
                "user_id": "U123",
                "command": "/judgment",
                "text": "investigate issue-schema",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["response_type"] == "ephemeral"
    assert "schema violation" in body["text"]
    assert any(block.get("type") == "actions" for block in body["blocks"])

    mocked.assert_called_once()
    assert mocked.call_args.kwargs["project_id"] == "proj-slack"
    assert mocked.call_args.kwargs["context"] == {"issue_id": "issue-schema"}
    assert "root cause" in mocked.call_args.kwargs["question"]


def test_slack_command_rejects_bad_signature(client_ctx) -> None:
    client, session_local = client_ctx
    with session_local() as session:
        _seed_slack_install(session)

    body = urlencode({"team_id": "T123", "channel_id": "C123", "text": "help"}).encode()
    headers = _signed_headers(body)
    headers["x-slack-signature"] = "v0=bad"

    response = client.post(
        "/v1/integrations/slack/command",
        content=body,
        headers=headers,
    )

    assert response.status_code == 401


def test_slack_command_reports_ambiguous_workspace(client_ctx) -> None:
    client, session_local = client_ctx
    with session_local() as session:
        _seed_slack_install(session, project_id="proj-one", team_id="T999", channel_id="C1")
        _seed_slack_install(session, project_id="proj-two", team_id="T999", channel_id="C2")

    response = _post_signed(
        client,
        "/v1/integrations/slack/command",
        {"team_id": "T999", "channel_id": "C3", "text": "why did agent checkout fail today?"},
    )

    assert response.status_code == 200
    assert "multiple Zroky projects" in response.json()["text"]


def test_slack_action_runs_root_cause_question(client_ctx) -> None:
    client, session_local = client_ctx
    with session_local() as session:
        _seed_slack_install(session)

    answer = AskAnswer(
        answer="The likely root cause is unstable tool selection.",
        suggested_actions=["Tighten tool descriptions"],
        confidence=0.7,
        intent="failure",
        evidence=[],
        used_llm=False,
    )
    payload = {
        "team": {"id": "T123"},
        "channel": {"id": "C123"},
        "actions": [
            {
                "action_id": "judgment_root_cause",
                "value": json.dumps(
                    {
                        "categories": ["TOOL_SELECTION_WRONG"],
                        "agent_name": "checkout-agent",
                        "diagnosis_id": "diag-123",
                    },
                    separators=(",", ":"),
                ),
            }
        ],
    }
    with patch("app.services.slack_judgment.answer_question", return_value=answer) as mocked:
        response = _post_signed(
            client,
            "/v1/integrations/slack/actions",
            {"payload": json.dumps(payload, separators=(",", ":"))},
        )

    assert response.status_code == 200
    assert "root cause" in response.json()["text"]
    assert mocked.call_args.kwargs["project_id"] == "proj-slack"
    assert "TOOL_SELECTION_WRONG" in mocked.call_args.kwargs["question"]
    assert mocked.call_args.kwargs["context"] == {}


def test_slack_action_approves_signed_runtime_policy_decision(client_ctx) -> None:
    client, session_local = client_ctx
    with session_local() as session:
        _seed_slack_install(session)
        decision_id, value = _seed_pending_runtime_policy_decision(session)

    response = _post_slack_action(
        client,
        action_id="runtime_policy_approve",
        value=value,
    )

    assert response.status_code == 200, response.text
    assert response.json()["text"] == "Approval accepted. Zroky can now continue the protected action."
    with session_local() as session:
        row = session.get(RuntimePolicyDecision, decision_id)
        assert row.status == "approved"
        assert row.decision == "allow"
        assert row.resolved_by == "slack:U777"
        assert row.approval_count == 1
        assert json.loads(row.approver_subjects_json) == ["slack:U777"]
        events = session.query(RuntimePolicyAuditEvent).filter_by(decision_id=decision_id).all()
        assert [event.event_type for event in events] == ["approved"]


def test_slack_action_rejects_stale_signed_approval_scope(client_ctx) -> None:
    client, session_local = client_ctx
    with session_local() as session:
        _seed_slack_install(session)
        decision_id, value = _seed_pending_runtime_policy_decision(
            session,
            approval_scope_hash="scope-before-action-edit",
        )
        row = session.get(RuntimePolicyDecision, decision_id)
        row.approval_scope_hash = "scope-after-action-edit"
        session.add(row)
        session.commit()

    response = _post_slack_action(
        client,
        action_id="runtime_policy_approve",
        value=value,
    )

    assert response.status_code == 200, response.text
    assert "stale" in response.json()["text"]
    with session_local() as session:
        row = session.get(RuntimePolicyDecision, decision_id)
        assert row.status == "pending_approval"
        assert row.approval_count == 0
        assert json.loads(row.approver_subjects_json) == []


def test_slack_action_rejects_user_outside_approval_allowlist(client_ctx) -> None:
    client, session_local = client_ctx
    with session_local() as session:
        _seed_slack_install(session, approval_user_ids=["U777"])
        decision_id, value = _seed_pending_runtime_policy_decision(session)

    response = _post_slack_action(
        client,
        action_id="runtime_policy_approve",
        value=value,
        user_id="U999",
        username="unapproved-user",
    )

    assert response.status_code == 200, response.text
    assert "not authorized" in response.json()["text"]
    with session_local() as session:
        row = session.get(RuntimePolicyDecision, decision_id)
        assert row.status == "pending_approval"
        assert row.approval_count == 0


def test_slack_action_expires_stale_approval_with_audit(client_ctx) -> None:
    client, session_local = client_ctx
    with session_local() as session:
        _seed_slack_install(session)
        decision_id, value = _seed_pending_runtime_policy_decision(
            session,
            decision_id="decision-slack-expired",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )

    response = _post_slack_action(
        client,
        action_id="runtime_policy_approve",
        value=value,
    )

    assert response.status_code == 200, response.text
    assert "expired" in response.json()["text"]
    with session_local() as session:
        row = session.get(RuntimePolicyDecision, decision_id)
        assert row.status == "expired"
        assert row.decision == "block"
        assert row.resolved_by == "slack:U777"
        events = session.query(RuntimePolicyAuditEvent).filter_by(decision_id=decision_id).all()
        assert [event.event_type for event in events] == ["expired"]


def test_judgment_alert_payload_includes_investigation_buttons() -> None:
    with patch("app.services.slack_judgment.get_settings") as get_settings:
        get_settings.return_value.FRONTEND_URL = "https://zroky.com"
        payload = build_judgment_alert_payload(
            text="Zroky Alert - LOOP_DETECTED",
            categories=["LOOP_DETECTED"],
            agent_name="checkout-agent",
            diagnosis_id="diag-001",
            severity="critical",
            alert_id="alert-001",
            alert_title="Checkout agent loop detected.",
        )

    actions = [block for block in payload["blocks"] if block.get("type") == "actions"][0]
    action_ids = [element["action_id"] for element in actions["elements"] if "action_id" in element]
    assert action_ids == ["judgment_investigate", "judgment_root_cause", "judgment_similar"]
    assert "LOOP_DETECTED" in actions["elements"][0]["value"]
    assert payload["text"] == "Critical alert: Checkout agent loop detected."
    labels = [element["text"]["text"] for element in actions["elements"]]
    assert labels == ["Ask judgment", "Root cause", "Similar cases", "Open approval", "View evidence"]
    urls = [element["url"] for element in actions["elements"] if "url" in element]
    assert urls == [
        "https://zroky.com/approvals?alert_id=alert-001",
        "https://zroky.com/evidence?alert_id=alert-001",
    ]
