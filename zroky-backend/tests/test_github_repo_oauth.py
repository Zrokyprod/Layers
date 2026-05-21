from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import User
from app.db.session import get_db_session, get_db_session_read
from app.main import app
from app.services.github_tokens import decrypt_github_token, encrypt_github_token
from app.services.security import issue_access_token

_AUTH_SECRET = "test-auth-secret-for-github-repo-oauth"


class _FakeGithubResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://api.github.com")
            response = httpx.Response(self.status_code, request=request, json=self._payload)
            raise httpx.HTTPStatusError("GitHub request failed", request=request, response=response)

    def json(self) -> dict:
        return self._payload


@pytest.fixture()
def client_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AUTH_JWT_SECRET", _AUTH_SECRET)
    monkeypatch.setenv("ALLOW_PROJECT_HEADER_CONTEXT", "true")
    monkeypatch.setenv("REQUIRE_PROVISIONING_TOKEN", "false")
    monkeypatch.setenv("GITHUB_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv("OAUTH_STATE_SECRET", "test-oauth-state-secret")
    monkeypatch.setenv("GITHUB_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))
    monkeypatch.setenv("GITHUB_PR_BOT_TOKEN", "gho_bot_fallback_token")
    get_settings.cache_clear()

    db_path = tmp_path / "test_github_repo_oauth.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)

    def override_get_db_session():
        session = testing_session_local()
        try:
            yield session
        finally:
            session.close()

    class _MockTaskResult:
        id = "task-test-github-repo-oauth"

    def _mock_delay(*_args, **_kwargs):
        return _MockTaskResult()

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_db_session_read] = override_get_db_session
    monkeypatch.setattr("app.api.routes.diagnosis.process_diagnosis.delay", _mock_delay)

    with TestClient(app) as client:
        yield client, testing_session_local

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    get_settings.cache_clear()


def _create_project(client: TestClient, *, owner_ref: str) -> str:
    response = client.post(
        "/v1/projects",
        json={"name": "GitHub Repo OAuth Project", "owner_ref": owner_ref},
    )
    assert response.status_code == 201
    return response.json()["project_id"]


def _auth_headers(
    session_factory,
    *,
    project_id: str,
    subject: str,
    email: str,
) -> dict[str, str]:
    with session_factory() as session:
        user = session.execute(select(User).where(User.subject == subject)).scalar_one_or_none()
        if user is None:
            user = User(subject=subject, email=email)
            session.add(user)
            session.commit()
            session.refresh(user)

        token = issue_access_token(
            user_id=user.id,
            email=user.email,
            subject=user.subject,
            expire_hours=72,
            secret=_AUTH_SECRET,
        )

    return {
        "X-Project-Id": project_id,
        "Authorization": f"Bearer {token}",
    }


def _oauth_state_from_start(client: TestClient, headers: dict[str, str]) -> str:
    start = client.get("/v1/settings/github/connect/start", headers=headers, follow_redirects=False)
    assert start.status_code in {302, 307}

    location = start.headers.get("location")
    assert location

    parsed = urlparse(location)
    params = parse_qs(parsed.query)
    assert params.get("scope")
    assert "repo" in params["scope"][0]
    assert params.get("state")
    return params["state"][0]


def test_github_connection_status_requires_authenticated_user(client_context) -> None:
    client, _ = client_context
    project_id = _create_project(client, owner_ref="owner-status-sub")

    response = client.get(
        "/v1/settings/github/connection",
        headers={"X-Project-Id": project_id},
    )
    assert response.status_code == 401


def test_github_connect_callback_persists_and_disconnects(client_context, monkeypatch: pytest.MonkeyPatch) -> None:
    client, session_factory = client_context
    subject = "email:owner-connect@example.com"
    project_id = _create_project(client, owner_ref=subject)
    headers = _auth_headers(
        session_factory,
        project_id=project_id,
        subject=subject,
        email="owner-connect@example.com",
    )

    oauth_state = _oauth_state_from_start(client, headers)

    monkeypatch.setattr(
        "app.api.routes.settings.httpx.post",
        lambda *args, **kwargs: _FakeGithubResponse(
            {
                "access_token": "ghu_user_repo_token_123",
                "scope": "repo,user:email",
                "token_type": "bearer",
            }
        ),
    )
    monkeypatch.setattr(
        "app.api.routes.settings.httpx.get",
        lambda *args, **kwargs: _FakeGithubResponse(
            {
                "id": 12345,
                "login": "octocat",
            }
        ),
    )

    callback = client.post(
        "/v1/settings/github/connect/callback",
        headers=headers,
        json={
            "code": "oauth-code",
            "state": oauth_state,
        },
    )
    assert callback.status_code == 200
    payload = callback.json()
    assert payload["connected"] is True
    assert payload["github_id"] == "12345"
    assert payload["github_login"] == "octocat"
    assert "repo" in payload["scopes"]

    with session_factory() as session:
        user = session.execute(select(User).where(User.subject == subject)).scalar_one()
    assert user.github_token_encrypted is not None
    assert user.github_token_encrypted != "ghu_user_repo_token_123"
    assert decrypt_github_token(user.github_token_encrypted) == "ghu_user_repo_token_123"

    disconnect = client.post("/v1/settings/github/disconnect", headers=headers)
    assert disconnect.status_code == 200
    assert disconnect.json()["connected"] is False


def test_generate_pr_prefers_connected_user_token(client_context, monkeypatch: pytest.MonkeyPatch) -> None:
    client, session_factory = client_context
    subject = "email:owner-pr-user@example.com"
    project_id = _create_project(client, owner_ref=subject)
    headers = _auth_headers(
        session_factory,
        project_id=project_id,
        subject=subject,
        email="owner-pr-user@example.com",
    )

    with session_factory() as session:
        user = session.execute(select(User).where(User.subject == subject)).scalar_one()
        user.github_token_encrypted = encrypt_github_token("ghu_user_token_for_pr")
        user.github_token_scopes = "repo user:email"
        session.add(user)
        session.commit()

    submit = client.post(
        "/v1/diagnosis/submit",
        headers=headers,
        json={
            "diagnosis_id": "diag-user-token-pr",
            "payload": {"provider": "openai", "model": "gpt-4o", "category": "RATE_LIMIT"},
        },
    )
    assert submit.status_code == 200

    captured: dict[str, str] = {}

    class _FakeGithubResult:
        branch_name = "zroky/fix/diag-user-token-pr"
        pull_request_number = 99
        pull_request_url = "https://github.com/acme/demo/pull/99"
        pull_request_title = "[ZROKY Fix] diag-user-token-pr"
        file_path = "zroky-generated-fixes/diag-user-token-pr.md"
        commit_sha = "sha-user-token-pr"

    def _fake_create_pull_request_with_patch(**kwargs):
        captured["token"] = kwargs["token"]
        return _FakeGithubResult()

    monkeypatch.setattr(
        "app.api.routes.diagnosis.create_pull_request_with_patch",
        _fake_create_pull_request_with_patch,
    )

    response = client.post(
        "/v1/diagnosis/diag-user-token-pr/generate-pr",
        headers=headers,
        json={
            "repository_owner": "acme",
            "repository_name": "demo",
            "base_branch": "main",
        },
    )
    assert response.status_code == 201
    assert response.json()["auth_source"] == "user_oauth"
    assert captured["token"] == "ghu_user_token_for_pr"


def test_generate_pr_falls_back_to_bot_token_when_user_not_connected(client_context, monkeypatch: pytest.MonkeyPatch) -> None:
    client, session_factory = client_context
    subject = "email:owner-pr-bot@example.com"
    project_id = _create_project(client, owner_ref=subject)
    headers = _auth_headers(
        session_factory,
        project_id=project_id,
        subject=subject,
        email="owner-pr-bot@example.com",
    )

    submit = client.post(
        "/v1/diagnosis/submit",
        headers=headers,
        json={
            "diagnosis_id": "diag-bot-token-pr",
            "payload": {"provider": "openai", "model": "gpt-4o", "category": "RATE_LIMIT"},
        },
    )
    assert submit.status_code == 200

    captured: dict[str, str] = {}

    class _FakeGithubResult:
        branch_name = "zroky/fix/diag-bot-token-pr"
        pull_request_number = 100
        pull_request_url = "https://github.com/acme/demo/pull/100"
        pull_request_title = "[ZROKY Fix] diag-bot-token-pr"
        file_path = "zroky-generated-fixes/diag-bot-token-pr.md"
        commit_sha = "sha-bot-token-pr"

    def _fake_create_pull_request_with_patch(**kwargs):
        captured["token"] = kwargs["token"]
        return _FakeGithubResult()

    monkeypatch.setattr(
        "app.api.routes.diagnosis.create_pull_request_with_patch",
        _fake_create_pull_request_with_patch,
    )

    response = client.post(
        "/v1/diagnosis/diag-bot-token-pr/generate-pr",
        headers=headers,
        json={
            "repository_owner": "acme",
            "repository_name": "demo",
            "base_branch": "main",
        },
    )
    assert response.status_code == 201
    assert response.json()["auth_source"] == "bot_token"
    assert captured["token"] == "gho_bot_fallback_token"


def test_generate_pr_returns_503_when_no_user_or_bot_token(
    client_context,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_PR_BOT_TOKEN", "")
    get_settings.cache_clear()

    try:
        client, session_factory = client_context
        subject = "email:owner-pr-no-token@example.com"
        project_id = _create_project(client, owner_ref=subject)
        headers = _auth_headers(
            session_factory,
            project_id=project_id,
            subject=subject,
            email="owner-pr-no-token@example.com",
        )

        submit = client.post(
            "/v1/diagnosis/submit",
            headers=headers,
            json={
                "diagnosis_id": "diag-no-token-pr",
                "payload": {"provider": "openai", "model": "gpt-4o", "category": "RATE_LIMIT"},
            },
        )
        assert submit.status_code == 200

        response = client.post(
            "/v1/diagnosis/diag-no-token-pr/generate-pr",
            headers=headers,
            json={
                "repository_owner": "acme",
                "repository_name": "demo",
                "base_branch": "main",
            },
        )
        assert response.status_code == 503
        assert "Connect GitHub in Settings" in response.json()["detail"]
    finally:
        get_settings.cache_clear()
