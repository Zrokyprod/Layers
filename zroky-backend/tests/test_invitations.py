from pathlib import Path
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db_session, get_db_session_read
from app.main import app


@pytest.fixture()
def client(tmp_path: Path):
    get_settings.cache_clear()
    db_path = tmp_path / "test_invitations.db"
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

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_db_session_read] = override_get_db_session

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    get_settings.cache_clear()


def test_project_invitation_create_list_duplicate_and_revoke(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signing_key = "jwt-secret-for-tests-minimum-32-bytes-2026"
    owner_subject = "owner-invite-sub"
    sent_messages: list[dict[str, object]] = []

    def fake_send_email(to, subject, html_body, *, plain_body=None):
        sent_messages.append(
            {
                "to": to,
                "subject": subject,
                "html_body": html_body,
                "plain_body": plain_body,
            }
        )
        return True

    monkeypatch.setenv("REQUIRE_PROVISIONING_TOKEN", "true")
    monkeypatch.setenv("PROVISIONING_TOKEN", "top-secret")
    monkeypatch.setenv("JWT_SIGNING_KEY", signing_key)
    monkeypatch.setenv("JWT_ALGORITHMS", "HS256")
    monkeypatch.setenv("FRONTEND_URL", "https://app.example.com")
    monkeypatch.setattr("app.api.routes.invitations.send_email", fake_send_email)
    get_settings.cache_clear()

    try:
        project_response = client.post(
            "/v1/projects",
            headers={"X-Zroky-Admin-Token": "top-secret"},
            json={"name": "Invite Project", "owner_ref": owner_subject},
        )
        assert project_response.status_code == 201
        project_id = project_response.json()["project_id"]

        token = jwt.encode(
            {
                "sub": owner_subject,
                "project_id": project_id,
            },
            signing_key,
            algorithm="HS256",
        )
        auth_headers = {"Authorization": f"Bearer {token}"}

        membership_response = client.post(
            f"/v1/projects/{project_id}/memberships",
            headers=auth_headers,
            json={
                "subject": owner_subject,
                "email": "Owner@Zroky.Local",
                "role": "owner",
                "is_active": True,
            },
        )
        assert membership_response.status_code == 200

        existing_member_response = client.post(
            f"/v1/invitations/projects/{project_id}/invitations",
            headers=auth_headers,
            json={"email": " owner@zroky.local ", "role": "member"},
        )
        assert existing_member_response.status_code == 409
        assert (
            existing_member_response.json()["detail"]
            == "This user is already an active project member."
        )

        create_response = client.post(
            f"/v1/invitations/projects/{project_id}/invitations",
            headers=auth_headers,
            json={"email": "New.Teammate@Zroky.Local", "role": "member"},
        )
        assert create_response.status_code == 201
        created = create_response.json()
        assert created["project_id"] == project_id
        assert created["email"] == "new.teammate@zroky.local"
        assert created["role"] == "member"
        assert created["accepted_at"] is None
        assert created["revoked_at"] is None
        assert created["email_sent"] is True
        assert sent_messages[-1]["to"] == ["new.teammate@zroky.local"]
        plain_body = str(sent_messages[-1]["plain_body"])
        accept_url = next(line.removeprefix("Accept invitation: ") for line in plain_body.splitlines() if line.startswith("Accept invitation: "))
        parsed_accept_url = urlparse(accept_url)
        assert parsed_accept_url.scheme == "https"
        assert parsed_accept_url.netloc == "app.example.com"
        assert parsed_accept_url.path == "/invite/accept"
        original_token = parse_qs(parsed_accept_url.query)["token"][0]

        list_response = client.get(
            f"/v1/invitations/projects/{project_id}/invitations",
            headers=auth_headers,
        )
        assert list_response.status_code == 200
        listed = list_response.json()
        assert any(item["invitation_id"] == created["invitation_id"] for item in listed)
        assert next(item for item in listed if item["invitation_id"] == created["invitation_id"])["email_sent"] is None

        duplicate_response = client.post(
            f"/v1/invitations/projects/{project_id}/invitations",
            headers=auth_headers,
            json={"email": "new.teammate@zroky.local", "role": "member"},
        )
        assert duplicate_response.status_code == 409

        resend_response = client.post(
            f"/v1/invitations/projects/{project_id}/invitations/{created['invitation_id']}/resend",
            headers=auth_headers,
        )
        assert resend_response.status_code == 200
        assert resend_response.json()["email_sent"] is True
        resent_plain_body = str(sent_messages[-1]["plain_body"])
        resent_accept_url = next(
            line.removeprefix("Accept invitation: ")
            for line in resent_plain_body.splitlines()
            if line.startswith("Accept invitation: ")
        )
        resent_token = parse_qs(urlparse(resent_accept_url).query)["token"][0]
        assert resent_token != original_token

        old_token_response = client.post(
            "/v1/invitations/accept",
            headers=auth_headers,
            json={"token": original_token},
        )
        assert old_token_response.status_code == 200
        assert old_token_response.json() == {
            "success": False,
            "message": "Invalid or expired invitation token.",
            "project_id": None,
            "membership_id": None,
        }

        revoke_response = client.delete(
            f"/v1/invitations/projects/{project_id}/invitations/{created['invitation_id']}",
            headers=auth_headers,
        )
        assert revoke_response.status_code == 200

        revoked_list_response = client.get(
            f"/v1/invitations/projects/{project_id}/invitations",
            headers=auth_headers,
        )
        assert revoked_list_response.status_code == 200
        revoked = next(
            item for item in revoked_list_response.json() if item["invitation_id"] == created["invitation_id"]
        )
        assert revoked["revoked_at"] is not None

        reinvite_response = client.post(
            f"/v1/invitations/projects/{project_id}/invitations",
            headers=auth_headers,
            json={"email": "new.teammate@zroky.local", "role": "viewer"},
        )
        assert reinvite_response.status_code == 201
        assert reinvite_response.json()["invitation_id"] == created["invitation_id"]
        assert reinvite_response.json()["role"] == "viewer"
        assert reinvite_response.json()["revoked_at"] is None
    finally:
        get_settings.cache_clear()


def test_invitation_acceptance_is_idempotent(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signing_key = "jwt-secret-for-tests-minimum-32-bytes-2026"
    owner_subject = "owner-accept-sub"
    sent_messages: list[str] = []

    def fake_send_email(to, subject, html_body, *, plain_body=None):
        del to, subject, html_body
        sent_messages.append(str(plain_body))
        return True

    monkeypatch.setenv("REQUIRE_PROVISIONING_TOKEN", "true")
    monkeypatch.setenv("PROVISIONING_TOKEN", "top-secret")
    monkeypatch.setenv("JWT_SIGNING_KEY", signing_key)
    monkeypatch.setenv("JWT_ALGORITHMS", "HS256")
    monkeypatch.setenv("FRONTEND_URL", "https://app.example.com")
    monkeypatch.setattr("app.api.routes.invitations.send_email", fake_send_email)
    get_settings.cache_clear()

    try:
        project_id = client.post(
            "/v1/projects",
            headers={"X-Zroky-Admin-Token": "top-secret"},
            json={"name": "Accept Project", "owner_ref": owner_subject},
        ).json()["project_id"]
        owner_headers = {
            "Authorization": f"Bearer {jwt.encode({'sub': owner_subject, 'project_id': project_id}, signing_key, algorithm='HS256')}"
        }
        created = client.post(
            f"/v1/invitations/projects/{project_id}/invitations",
            headers=owner_headers,
            json={"email": "accept@example.com", "role": "member"},
        )
        assert created.status_code == 201
        accept_url = next(
            line.removeprefix("Accept invitation: ")
            for line in sent_messages[-1].splitlines()
            if line.startswith("Accept invitation: ")
        )
        raw_token = parse_qs(urlparse(accept_url).query)["token"][0]

        registered = client.post(
            "/v1/auth/register",
            json={
                "email": "accept@example.com",
                "password": "secureaccept123",
                "confirm_password": "secureaccept123",
            },
        )
        assert registered.status_code == 201
        invitee_headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}

        first_accept = client.post(
            "/v1/invitations/accept",
            headers=invitee_headers,
            json={"token": raw_token},
        )
        assert first_accept.status_code == 200
        assert first_accept.json()["success"] is True
        assert first_accept.json()["project_id"] == project_id

        retry_accept = client.post(
            "/v1/invitations/accept",
            headers=invitee_headers,
            json={"token": raw_token},
        )
        assert retry_accept.status_code == 200, retry_accept.json()
        assert retry_accept.json()["success"] is True
        assert retry_accept.json()["membership_id"] == first_accept.json()["membership_id"]
    finally:
        get_settings.cache_clear()


def test_admin_cannot_manage_owner_invitations(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signing_key = "jwt-secret-for-tests-minimum-32-bytes-2026"
    owner_subject = "owner-invitation-authority"
    admin_subject = "admin-invitation-authority"

    monkeypatch.setenv("REQUIRE_PROVISIONING_TOKEN", "true")
    monkeypatch.setenv("PROVISIONING_TOKEN", "top-secret")
    monkeypatch.setenv("JWT_SIGNING_KEY", signing_key)
    monkeypatch.setenv("JWT_ALGORITHMS", "HS256")
    monkeypatch.setattr("app.api.routes.invitations.send_email", lambda *_args, **_kwargs: True)
    get_settings.cache_clear()

    try:
        project_id = client.post(
            "/v1/projects",
            headers={"X-Zroky-Admin-Token": "top-secret"},
            json={"name": "Invitation Authority Project", "owner_ref": owner_subject},
        ).json()["project_id"]
        owner_headers = {
            "Authorization": f"Bearer {jwt.encode({'sub': owner_subject, 'project_id': project_id}, signing_key, algorithm='HS256')}"
        }
        admin_headers = {
            "Authorization": f"Bearer {jwt.encode({'sub': admin_subject, 'project_id': project_id}, signing_key, algorithm='HS256')}"
        }

        admin_membership = client.post(
            f"/v1/projects/{project_id}/memberships",
            headers=owner_headers,
            json={"subject": admin_subject, "email": "admin@example.com", "role": "admin"},
        )
        assert admin_membership.status_code == 200

        denied_create = client.post(
            f"/v1/invitations/projects/{project_id}/invitations",
            headers=admin_headers,
            json={"email": "owner-candidate@example.com", "role": "owner"},
        )
        assert denied_create.status_code == 403

        owner_create = client.post(
            f"/v1/invitations/projects/{project_id}/invitations",
            headers=owner_headers,
            json={"email": "owner-candidate@example.com", "role": "owner"},
        )
        assert owner_create.status_code == 201
        invitation_id = owner_create.json()["invitation_id"]

        denied_resend = client.post(
            f"/v1/invitations/projects/{project_id}/invitations/{invitation_id}/resend",
            headers=admin_headers,
        )
        assert denied_resend.status_code == 403

        denied_revoke = client.delete(
            f"/v1/invitations/projects/{project_id}/invitations/{invitation_id}",
            headers=admin_headers,
        )
        assert denied_revoke.status_code == 403

        owner_revoke = client.delete(
            f"/v1/invitations/projects/{project_id}/invitations/{invitation_id}",
            headers=owner_headers,
        )
        assert owner_revoke.status_code == 200
    finally:
        get_settings.cache_clear()
