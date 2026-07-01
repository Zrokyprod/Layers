from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.core.config import get_settings
from app.db.session import get_db_session, get_db_session_read
from app.main import app


TEST_JWT_SIGNING_KEY = "jwt-secret-for-tests-minimum-32-bytes-2026"


def _project_auth_headers(project_id: str, subject: str) -> dict[str, str]:
    token = jwt.encode(
        {
            "sub": subject,
            "project_id": project_id,
        },
        TEST_JWT_SIGNING_KEY,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    get_settings.cache_clear()
    monkeypatch.setenv("REQUIRE_PROVISIONING_TOKEN", "false")
    monkeypatch.setenv("PROVISIONING_TOKEN", "top-secret")
    monkeypatch.setenv("JWT_SIGNING_KEY", TEST_JWT_SIGNING_KEY)
    monkeypatch.setenv("JWT_ALGORITHMS", "HS256")
    get_settings.cache_clear()
    db_path = tmp_path / "test_projects.db"
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
        id = "task-test-project-key"

    def _mock_delay(*_args, **_kwargs):
        return _MockTaskResult()

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_db_session_read] = override_get_db_session
    monkeypatch.setattr("app.api.routes.diagnosis.process_diagnosis.delay", _mock_delay)

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    get_settings.cache_clear()


def test_project_and_api_key_flow(client: TestClient) -> None:
    project_response = client.post(
        "/v1/projects",
        json={"name": "Acme Project", "owner_ref": "owner-1"},
    )
    assert project_response.status_code == 201
    project_payload = project_response.json()
    project_id = project_payload["project_id"]
    assert project_id.startswith("proj_")

    key_response = client.post(
        f"/v1/projects/{project_id}/api-keys",
        headers=_project_auth_headers(project_id, "owner-1"),
        json={"name": "primary"},
    )
    assert key_response.status_code == 201
    key_payload = key_response.json()
    assert key_payload["project_id"] == project_id
    assert key_payload["api_key"].startswith("zk_live_")

    submit_response = client.post(
        "/v1/diagnosis/submit",
        headers={"X-Api-Key": key_payload["api_key"]},
        json={
            "diagnosis_id": "diag-key-1",
            "payload": {"prompt": "hello"},
        },
    )
    assert submit_response.status_code == 200

    status_response = client.get(
        "/v1/diagnosis/diag-key-1",
        headers={"X-Api-Key": key_payload["api_key"]},
    )
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["tenant_id"] == project_id

    rename_response = client.patch(
        "/v1/settings/project",
        headers=_project_auth_headers(project_id, "owner-1"),
        json={"name": "Acme Verified Actions"},
    )
    assert rename_response.status_code == 200
    assert rename_response.json()["name"] == "Acme Verified Actions"

    settings_response = client.get(
        "/v1/settings/project",
        headers=_project_auth_headers(project_id, "owner-1"),
    )
    assert settings_response.status_code == 200
    assert settings_response.json()["name"] == "Acme Verified Actions"


def test_invalid_api_key_rejected(client: TestClient) -> None:
    response = client.post(
        "/v1/diagnosis/submit",
        headers={"X-Api-Key": "zk_live_invalid"},
        json={
            "diagnosis_id": "diag-invalid-key",
            "payload": {"prompt": "hello"},
        },
    )
    assert response.status_code == 401


def test_default_api_key_name_is_zroky_api(client: TestClient) -> None:
    project_response = client.post(
        "/v1/projects",
        json={"name": "Default Key Project", "owner_ref": "default-key-owner"},
    )
    assert project_response.status_code == 201
    project_id = project_response.json()["project_id"]

    key_response = client.post(
        f"/v1/projects/{project_id}/api-keys",
        headers=_project_auth_headers(project_id, "default-key-owner"),
        json={},
    )
    assert key_response.status_code == 201
    assert key_response.json()["name"] == "Zroky API"


def test_api_key_expiry_scope_and_rotation_flow(client: TestClient) -> None:
    project_response = client.post(
        "/v1/projects",
        json={"name": "Rotating Key Project", "owner_ref": "rotation-owner"},
    )
    assert project_response.status_code == 201
    project_id = project_response.json()["project_id"]
    auth_headers = _project_auth_headers(project_id, "rotation-owner")

    key_response = client.post(
        f"/v1/projects/{project_id}/api-keys",
        headers=auth_headers,
        json={"name": "rotatable", "expires_in_days": 30, "scopes": ["project:member"]},
    )
    assert key_response.status_code == 201
    key_payload = key_response.json()
    assert key_payload["scopes"] == ["project:member"]
    assert key_payload["expires_at"] is not None

    rotate_response = client.post(
        f"/v1/projects/{project_id}/api-keys/{key_payload['key_id']}/rotate",
        headers=auth_headers,
    )
    assert rotate_response.status_code == 200
    rotated_payload = rotate_response.json()
    assert rotated_payload["api_key"].startswith("zk_live_")
    assert rotated_payload["rotated_from_key_id"] == key_payload["key_id"]
    assert rotated_payload["scopes"] == ["project:member"]

    keys_response = client.get(f"/v1/projects/{project_id}/api-keys", headers=auth_headers)
    assert keys_response.status_code == 200
    keys = keys_response.json()
    old_key = next(item for item in keys if item["key_id"] == key_payload["key_id"])
    assert old_key["revoked"] is True


def test_revoked_api_key_blocked(client: TestClient) -> None:
    project_response = client.post(
        "/v1/projects",
        json={"name": "Revocation Project", "owner_ref": "revocation-owner"},
    )
    assert project_response.status_code == 201
    project_id = project_response.json()["project_id"]
    auth_headers = _project_auth_headers(project_id, "revocation-owner")

    key_response = client.post(
        f"/v1/projects/{project_id}/api-keys",
        headers=auth_headers,
        json={"name": "revokable"},
    )
    assert key_response.status_code == 201
    key_payload = key_response.json()

    revoke_response = client.post(
        f"/v1/projects/{project_id}/api-keys/{key_payload['key_id']}/revoke",
        headers=auth_headers,
    )
    assert revoke_response.status_code == 200
    assert revoke_response.json()["revoked"] is True

    response = client.post(
        "/v1/diagnosis/submit",
        headers={"X-Api-Key": key_payload["api_key"]},
        json={
            "diagnosis_id": "diag-after-revoke",
            "payload": {"prompt": "hello"},
        },
    )
    assert response.status_code == 401


def test_provisioning_token_guard_when_enabled(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REQUIRE_PROVISIONING_TOKEN", "true")
    monkeypatch.setenv("PROVISIONING_TOKEN", "top-secret")
    get_settings.cache_clear()

    try:
        unauthorized = client.post("/v1/projects", json={"name": "No Token Project"})
        assert unauthorized.status_code == 401

        authorized = client.post(
            "/v1/projects",
            headers={"X-Zroky-Admin-Token": "top-secret"},
            json={"name": "Authorized Project"},
        )
        assert authorized.status_code == 201
    finally:
        get_settings.cache_clear()


def test_provisioning_allows_admin_jwt_when_enabled(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REQUIRE_PROVISIONING_TOKEN", "true")
    monkeypatch.setenv("PROVISIONING_TOKEN", "top-secret")
    monkeypatch.setenv("ALLOW_JWT_PROVISIONING_ACCESS", "true")
    monkeypatch.setenv("JWT_SIGNING_KEY", "jwt-secret-for-tests-minimum-32-bytes-2026")
    monkeypatch.setenv("JWT_ALGORITHMS", "HS256")
    monkeypatch.setenv("JWT_ADMIN_ROLE", "zroky_admin")
    get_settings.cache_clear()

    try:
        admin_token = jwt.encode(
            {
                "sub": "admin-1",
                "roles": ["zroky_admin"],
            },
            "jwt-secret-for-tests-minimum-32-bytes-2026",
            algorithm="HS256",
        )

        response = client.post(
            "/v1/projects",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "JWT Admin Project"},
        )
        assert response.status_code == 201
    finally:
        get_settings.cache_clear()


def test_provisioning_rejects_non_admin_jwt_when_token_required(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REQUIRE_PROVISIONING_TOKEN", "true")
    monkeypatch.setenv("PROVISIONING_TOKEN", "top-secret")
    monkeypatch.setenv("ALLOW_JWT_PROVISIONING_ACCESS", "true")
    monkeypatch.setenv("JWT_SIGNING_KEY", "jwt-secret-for-tests-minimum-32-bytes-2026")
    monkeypatch.setenv("JWT_ALGORITHMS", "HS256")
    monkeypatch.setenv("JWT_ADMIN_ROLE", "zroky_admin")
    get_settings.cache_clear()

    try:
        user_token = jwt.encode(
            {
                "sub": "user-1",
                "roles": ["member"],
            },
            "jwt-secret-for-tests-minimum-32-bytes-2026",
            algorithm="HS256",
        )

        response = client.post(
            "/v1/projects",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"name": "JWT Member Project"},
        )
        assert response.status_code == 401
    finally:
        get_settings.cache_clear()


def test_provisioning_open_mode_ignores_invalid_bearer(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REQUIRE_PROVISIONING_TOKEN", "false")
    monkeypatch.setenv("ALLOW_JWT_PROVISIONING_ACCESS", "true")
    monkeypatch.setenv("JWT_SIGNING_KEY", "jwt-secret-for-tests-minimum-32-bytes-2026")
    monkeypatch.setenv("JWT_ALGORITHMS", "HS256")
    get_settings.cache_clear()

    try:
        response = client.post(
            "/v1/projects",
            headers={"Authorization": "Bearer definitely-not-a-jwt"},
            json={"name": "Open Mode Project"},
        )
        assert response.status_code == 201
    finally:
        get_settings.cache_clear()


def test_project_role_guard_requires_auth_when_global_provisioning_is_open(client: TestClient) -> None:
    project_response = client.post(
        "/v1/projects",
        json={"name": "Open Provisioning Scoped Project"},
    )
    assert project_response.status_code == 201
    project_id = project_response.json()["project_id"]

    anonymous_response = client.post(
        f"/v1/projects/{project_id}/api-keys",
        json={"name": "anonymous-key"},
    )
    assert anonymous_response.status_code == 401

    strict_token_response = client.post(
        f"/v1/projects/{project_id}/api-keys",
        headers={"X-Zroky-Admin-Token": "top-secret"},
        json={"name": "operator-key"},
    )
    assert strict_token_response.status_code == 201

    admin_token = jwt.encode(
        {
            "sub": "admin-open-mode",
            "roles": ["zroky_admin"],
        },
        TEST_JWT_SIGNING_KEY,
        algorithm="HS256",
    )
    strict_jwt_response = client.post(
        f"/v1/projects/{project_id}/api-keys",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "admin-jwt-key"},
    )
    assert strict_jwt_response.status_code == 201


def test_project_creation_bootstraps_owner_membership(client: TestClient) -> None:
    project_response = client.post(
        "/v1/projects",
        json={"name": "Owner Bootstrap Project", "owner_ref": "owner-sub-1"},
    )
    assert project_response.status_code == 201
    project_id = project_response.json()["project_id"]

    memberships_response = client.get(
        f"/v1/projects/{project_id}/memberships",
        headers=_project_auth_headers(project_id, "owner-sub-1"),
    )
    assert memberships_response.status_code == 200
    memberships = memberships_response.json()
    assert len(memberships) == 1
    assert memberships[0]["subject"] == "owner-sub-1"
    assert memberships[0]["role"] == "owner"
    assert memberships[0]["is_active"] is True


def test_upsert_project_membership(client: TestClient) -> None:
    project_response = client.post(
        "/v1/projects",
        json={"name": "Membership Project"},
    )
    assert project_response.status_code == 201
    project_id = project_response.json()["project_id"]
    auth_headers = {"X-Zroky-Admin-Token": "top-secret"}

    first_upsert = client.post(
        f"/v1/projects/{project_id}/memberships",
        headers=auth_headers,
        json={
            "subject": "member-sub-1",
            "email": "member@example.com",
            "role": "member",
            "is_active": True,
        },
    )
    assert first_upsert.status_code == 200
    assert first_upsert.json()["role"] == "member"

    second_upsert = client.post(
        f"/v1/projects/{project_id}/memberships",
        headers=auth_headers,
        json={
            "subject": "member-sub-1",
            "email": "member@example.com",
            "role": "admin",
            "is_active": True,
        },
    )
    assert second_upsert.status_code == 200
    assert second_upsert.json()["role"] == "admin"

    list_response = client.get(f"/v1/projects/{project_id}/memberships", headers=auth_headers)
    assert list_response.status_code == 200
    memberships = list_response.json()
    assert len(memberships) == 1
    assert memberships[0]["subject"] == "member-sub-1"
    assert memberships[0]["role"] == "admin"


def test_project_scoped_route_allows_owner_membership_without_provisioning_token(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REQUIRE_PROVISIONING_TOKEN", "true")
    monkeypatch.setenv("PROVISIONING_TOKEN", "top-secret")
    monkeypatch.setenv("JWT_SIGNING_KEY", "jwt-secret-for-tests-minimum-32-bytes-2026")
    monkeypatch.setenv("JWT_ALGORITHMS", "HS256")
    get_settings.cache_clear()

    try:
        create_project_response = client.post(
            "/v1/projects",
            headers={"X-Zroky-Admin-Token": "top-secret"},
            json={"name": "Scoped Owner Project", "owner_ref": "owner-sub-9"},
        )
        assert create_project_response.status_code == 201
        project_id = create_project_response.json()["project_id"]

        owner_token = jwt.encode(
            {
                "sub": "owner-sub-9",
                "project_id": project_id,
            },
            "jwt-secret-for-tests-minimum-32-bytes-2026",
            algorithm="HS256",
        )

        key_create_response = client.post(
            f"/v1/projects/{project_id}/api-keys",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"name": "owner-managed-key"},
        )
        assert key_create_response.status_code == 201
    finally:
        get_settings.cache_clear()


def test_project_scoped_route_rejects_viewer_membership_for_admin_actions(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REQUIRE_PROVISIONING_TOKEN", "true")
    monkeypatch.setenv("PROVISIONING_TOKEN", "top-secret")
    monkeypatch.setenv("JWT_SIGNING_KEY", "jwt-secret-for-tests-minimum-32-bytes-2026")
    monkeypatch.setenv("JWT_ALGORITHMS", "HS256")
    get_settings.cache_clear()

    try:
        create_project_response = client.post(
            "/v1/projects",
            headers={"X-Zroky-Admin-Token": "top-secret"},
            json={"name": "Scoped Viewer Project", "owner_ref": "owner-sub-10"},
        )
        assert create_project_response.status_code == 201
        project_id = create_project_response.json()["project_id"]

        membership_response = client.post(
            f"/v1/projects/{project_id}/memberships",
            headers={"X-Zroky-Admin-Token": "top-secret"},
            json={
                "subject": "viewer-sub-10",
                "role": "viewer",
                "is_active": True,
            },
        )
        assert membership_response.status_code == 200

        viewer_token = jwt.encode(
            {
                "sub": "viewer-sub-10",
                "project_id": project_id,
            },
            "jwt-secret-for-tests-minimum-32-bytes-2026",
            algorithm="HS256",
        )

        key_create_response = client.post(
            f"/v1/projects/{project_id}/api-keys",
            headers={"Authorization": f"Bearer {viewer_token}"},
            json={"name": "viewer-denied-key"},
        )
        assert key_create_response.status_code == 403
    finally:
        get_settings.cache_clear()
