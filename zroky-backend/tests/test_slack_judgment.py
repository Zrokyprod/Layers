from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
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
from app.db.models import Project, TenantSlackInstall
from app.db.session import get_db_session, get_db_session_read
from app.main import app
from app.services.ask import AskAnswer
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
            installed_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    session.commit()


def _seed_project(session, project_id: str = "proj-slack") -> None:
    session.add(Project(id=project_id, name=f"Project {project_id}"))
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
                "href": "/issues/issue-schema",
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


def test_judgment_alert_payload_includes_investigation_buttons() -> None:
    payload = build_judgment_alert_payload(
        text="Zroky Alert - LOOP_DETECTED",
        categories=["LOOP_DETECTED"],
        agent_name="checkout-agent",
        diagnosis_id="diag-001",
    )

    actions = [block for block in payload["blocks"] if block.get("type") == "actions"][0]
    action_ids = [element["action_id"] for element in actions["elements"]]
    assert action_ids == ["judgment_investigate", "judgment_root_cause", "judgment_similar"]
    assert "LOOP_DETECTED" in actions["elements"][0]["value"]
