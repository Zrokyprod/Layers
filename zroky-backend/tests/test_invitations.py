from pathlib import Path

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

    monkeypatch.setenv("REQUIRE_PROVISIONING_TOKEN", "true")
    monkeypatch.setenv("PROVISIONING_TOKEN", "top-secret")
    monkeypatch.setenv("JWT_SIGNING_KEY", signing_key)
    monkeypatch.setenv("JWT_ALGORITHMS", "HS256")
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

        list_response = client.get(
            f"/v1/invitations/projects/{project_id}/invitations",
            headers=auth_headers,
        )
        assert list_response.status_code == 200
        listed = list_response.json()
        assert any(item["invitation_id"] == created["invitation_id"] for item in listed)

        duplicate_response = client.post(
            f"/v1/invitations/projects/{project_id}/invitations",
            headers=auth_headers,
            json={"email": "new.teammate@zroky.local", "role": "member"},
        )
        assert duplicate_response.status_code == 409

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
    finally:
        get_settings.cache_clear()
