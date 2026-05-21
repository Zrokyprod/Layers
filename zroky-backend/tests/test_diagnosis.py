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


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    get_settings.cache_clear()
    db_path = tmp_path / "test_diagnosis.db"
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
        id = "task-test-1"

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


def test_submit_requires_tenant_context_header(client: TestClient) -> None:
    response = client.post(
        "/v1/diagnosis/submit",
        json={
            "diagnosis_id": "diag-1",
            "payload": {"prompt": "test"},
        },
    )
    assert response.status_code == 401


def test_submit_and_get_status(client: TestClient) -> None:
    headers = {"X-Project-Id": "proj-1"}

    submit_response = client.post(
        "/v1/diagnosis/submit",
        headers=headers,
        json={
            "diagnosis_id": "diag-1",
            "payload": {"prompt": "test"},
        },
    )
    assert submit_response.status_code == 200
    submit_payload = submit_response.json()
    assert submit_payload["status"] == "queued"
    assert submit_payload["task_id"] == "task-test-1"

    status_response = client.get("/v1/diagnosis/diag-1", headers=headers)
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["tenant_id"] == "proj-1"
    assert status_payload["diagnosis_id"] == "diag-1"


def test_legacy_status_path_rejects_tenant_mismatch(client: TestClient) -> None:
    submit_response = client.post(
        "/v1/diagnosis/submit",
        headers={"X-Project-Id": "proj-1"},
        json={
            "diagnosis_id": "diag-legacy",
            "payload": {"prompt": "test"},
        },
    )
    assert submit_response.status_code == 200

    response = client.get(
        "/v1/diagnosis/proj-other/diag-legacy",
        headers={"X-Project-Id": "proj-1"},
    )
    assert response.status_code == 403


def test_project_header_can_be_disabled(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALLOW_PROJECT_HEADER_CONTEXT", "false")
    get_settings.cache_clear()

    try:
        response = client.post(
            "/v1/diagnosis/submit",
            headers={"X-Project-Id": "proj-header-only"},
            json={
                "diagnosis_id": "diag-no-header-trust",
                "payload": {"prompt": "test"},
            },
        )
        assert response.status_code == 401
    finally:
        get_settings.cache_clear()


def test_submit_with_jwt_project_claim(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALLOW_PROJECT_HEADER_CONTEXT", "false")
    monkeypatch.setenv("JWT_SIGNING_KEY", "jwt-secret-for-tests-minimum-32-bytes-2026")
    monkeypatch.setenv("JWT_ALGORITHMS", "HS256")
    get_settings.cache_clear()

    try:
        token = jwt.encode(
            {
                "sub": "user-1",
                "project_id": "proj-jwt-1",
            },
            "jwt-secret-for-tests-minimum-32-bytes-2026",
            algorithm="HS256",
        )

        submit_response = client.post(
            "/v1/diagnosis/submit",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "diagnosis_id": "diag-jwt-1",
                "payload": {"prompt": "test"},
            },
        )
        assert submit_response.status_code == 200

        status_response = client.get(
            "/v1/diagnosis/diag-jwt-1",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert status_response.status_code == 200
        assert status_response.json()["tenant_id"] == "proj-jwt-1"
    finally:
        get_settings.cache_clear()


def test_jwt_multi_project_requires_selection_header(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALLOW_PROJECT_HEADER_CONTEXT", "false")
    monkeypatch.setenv("JWT_SIGNING_KEY", "jwt-secret-for-tests-minimum-32-bytes-2026")
    monkeypatch.setenv("JWT_ALGORITHMS", "HS256")
    get_settings.cache_clear()

    try:
        token = jwt.encode(
            {
                "sub": "user-2",
                "projects": ["proj-a", "proj-b"],
            },
            "jwt-secret-for-tests-minimum-32-bytes-2026",
            algorithm="HS256",
        )

        missing_selector = client.post(
            "/v1/diagnosis/submit",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "diagnosis_id": "diag-jwt-selector-missing",
                "payload": {"prompt": "test"},
            },
        )
        assert missing_selector.status_code == 400

        invalid_selector = client.post(
            "/v1/diagnosis/submit",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Project-Id": "proj-c",
            },
            json={
                "diagnosis_id": "diag-jwt-selector-invalid",
                "payload": {"prompt": "test"},
            },
        )
        assert invalid_selector.status_code == 403

        valid_selector = client.post(
            "/v1/diagnosis/submit",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Project-Id": "proj-b",
            },
            json={
                "diagnosis_id": "diag-jwt-selector-valid",
                "payload": {"prompt": "test"},
            },
        )
        assert valid_selector.status_code == 200
    finally:
        get_settings.cache_clear()


def test_submit_with_jwt_enforced_membership(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALLOW_PROJECT_HEADER_CONTEXT", "false")
    monkeypatch.setenv("JWT_SIGNING_KEY", "jwt-secret-for-tests-minimum-32-bytes-2026")
    monkeypatch.setenv("JWT_ALGORITHMS", "HS256")
    monkeypatch.setenv("ENFORCE_JWT_PROJECT_MEMBERSHIP", "true")
    get_settings.cache_clear()

    try:
        project_response = client.post(
            "/v1/projects",
            json={"name": "JWT Secure Project", "owner_ref": "member-sub-1"},
        )
        assert project_response.status_code == 201
        project_id = project_response.json()["project_id"]

        token = jwt.encode(
            {
                "sub": "member-sub-1",
                "project_id": project_id,
            },
            "jwt-secret-for-tests-minimum-32-bytes-2026",
            algorithm="HS256",
        )

        submit_response = client.post(
            "/v1/diagnosis/submit",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "diagnosis_id": "diag-jwt-membership-allow",
                "payload": {"prompt": "test"},
            },
        )
        assert submit_response.status_code == 200
    finally:
        get_settings.cache_clear()


def test_submit_with_jwt_enforced_membership_rejects_non_member(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALLOW_PROJECT_HEADER_CONTEXT", "false")
    monkeypatch.setenv("JWT_SIGNING_KEY", "jwt-secret-for-tests-minimum-32-bytes-2026")
    monkeypatch.setenv("JWT_ALGORITHMS", "HS256")
    monkeypatch.setenv("ENFORCE_JWT_PROJECT_MEMBERSHIP", "true")
    get_settings.cache_clear()

    try:
        project_response = client.post(
            "/v1/projects",
            json={"name": "JWT Reject Project"},
        )
        assert project_response.status_code == 201
        project_id = project_response.json()["project_id"]

        token = jwt.encode(
            {
                "sub": "member-sub-2",
                "project_id": project_id,
            },
            "jwt-secret-for-tests-minimum-32-bytes-2026",
            algorithm="HS256",
        )

        submit_response = client.post(
            "/v1/diagnosis/submit",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "diagnosis_id": "diag-jwt-membership-deny",
                "payload": {"prompt": "test"},
            },
        )
        assert submit_response.status_code == 403
    finally:
        get_settings.cache_clear()


def test_jwt_viewer_role_cannot_submit_but_can_read_status(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALLOW_PROJECT_HEADER_CONTEXT", "false")
    monkeypatch.setenv("JWT_SIGNING_KEY", "jwt-secret-for-tests-minimum-32-bytes-2026")
    monkeypatch.setenv("JWT_ALGORITHMS", "HS256")
    monkeypatch.setenv("ENFORCE_JWT_PROJECT_MEMBERSHIP", "true")
    get_settings.cache_clear()

    try:
        project_response = client.post(
            "/v1/projects",
            json={"name": "Viewer Role Project", "owner_ref": "owner-role-sub"},
        )
        assert project_response.status_code == 201
        project_id = project_response.json()["project_id"]

        membership_response = client.post(
            f"/v1/projects/{project_id}/memberships",
            json={
                "subject": "viewer-role-sub",
                "role": "viewer",
                "is_active": True,
            },
        )
        assert membership_response.status_code == 200

        owner_token = jwt.encode(
            {
                "sub": "owner-role-sub",
                "project_id": project_id,
            },
            "jwt-secret-for-tests-minimum-32-bytes-2026",
            algorithm="HS256",
        )
        seed_submit = client.post(
            "/v1/diagnosis/submit",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "diagnosis_id": "diag-viewer-readonly",
                "payload": {"prompt": "seed"},
            },
        )
        assert seed_submit.status_code == 200

        viewer_token = jwt.encode(
            {
                "sub": "viewer-role-sub",
                "project_id": project_id,
            },
            "jwt-secret-for-tests-minimum-32-bytes-2026",
            algorithm="HS256",
        )
        viewer_submit = client.post(
            "/v1/diagnosis/submit",
            headers={"Authorization": f"Bearer {viewer_token}"},
            json={
                "diagnosis_id": "diag-viewer-denied-submit",
                "payload": {"prompt": "no-write"},
            },
        )
        assert viewer_submit.status_code == 403

        viewer_status = client.get(
            "/v1/diagnosis/diag-viewer-readonly",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert viewer_status.status_code == 200
    finally:
        get_settings.cache_clear()


def test_submit_diagnosis_feedback(client: TestClient) -> None:
    headers = {"X-Project-Id": "proj-feedback-1"}
    submit = client.post(
        "/v1/diagnosis/submit",
        headers=headers,
        json={
            "diagnosis_id": "diag-feedback-1",
            "payload": {"prompt": "test"},
        },
    )
    assert submit.status_code == 200

    feedback = client.post(
        "/v1/diagnosis/diag-feedback-1/feedback",
        headers=headers,
        json={
            "was_helpful": False,
            "developer_note": "  this diagnosis missed provider context  ",
        },
    )
    assert feedback.status_code == 201
    payload = feedback.json()
    assert payload["tenant_id"] == "proj-feedback-1"
    assert payload["diagnosis_id"] == "diag-feedback-1"
    assert payload["was_helpful"] is False
    assert payload["developer_note"] == "this diagnosis missed provider context"


def test_fix_watch_returns_not_started_until_resolved(client: TestClient) -> None:
    headers = {"X-Project-Id": "proj-fix-watch-0"}
    submit = client.post(
        "/v1/diagnosis/submit",
        headers=headers,
        json={
            "diagnosis_id": "diag-fix-watch-0",
            "payload": {"prompt": "watch"},
        },
    )
    assert submit.status_code == 200

    fix_watch = client.get("/v1/diagnosis/diag-fix-watch-0/fix-watch", headers=headers)
    assert fix_watch.status_code == 200
    payload = fix_watch.json()
    assert payload["status"] == "not_started"
    assert payload["recurrence_count"] == 0


def test_resolve_starts_fix_watch(client: TestClient) -> None:
    headers = {"X-Project-Id": "proj-fix-watch-1"}
    submit = client.post(
        "/v1/diagnosis/submit",
        headers=headers,
        json={
            "diagnosis_id": "diag-fix-watch-1",
            "payload": {
                "prompt": "watch",
                "category": "RATE_LIMIT",
            },
        },
    )
    assert submit.status_code == 200

    resolve = client.post("/v1/diagnosis/diag-fix-watch-1/resolve", headers=headers)
    assert resolve.status_code == 200
    resolve_payload = resolve.json()
    assert resolve_payload["status"] == "active"
    assert "RATE_LIMIT" in resolve_payload["target_categories"]

    fix_watch = client.get("/v1/diagnosis/diag-fix-watch-1/fix-watch", headers=headers)
    assert fix_watch.status_code == 200
    fix_payload = fix_watch.json()
    assert fix_payload["status"] == "active"
    assert fix_payload["recurrence_count"] == 0


def test_fix_watch_detects_recurrence(client: TestClient) -> None:
    headers = {"X-Project-Id": "proj-fix-watch-2"}
    submit = client.post(
        "/v1/diagnosis/submit",
        headers=headers,
        json={
            "diagnosis_id": "diag-fix-watch-2",
            "payload": {
                "prompt": "watch",
                "category": "RATE_LIMIT",
            },
        },
    )
    assert submit.status_code == 200

    resolve = client.post("/v1/diagnosis/diag-fix-watch-2/resolve", headers=headers)
    assert resolve.status_code == 200

    recurrence = client.post(
        "/v1/diagnosis/submit",
        headers=headers,
        json={
            "diagnosis_id": "diag-fix-watch-2-recurrence",
            "payload": {
                "prompt": "watch",
                "category": "RATE_LIMIT",
            },
        },
    )
    assert recurrence.status_code == 200

    fix_watch = client.get("/v1/diagnosis/diag-fix-watch-2/fix-watch", headers=headers)
    assert fix_watch.status_code == 200
    fix_payload = fix_watch.json()
    assert fix_payload["status"] == "recurrence_detected"
    assert fix_payload["recurrence_count"] >= 1
    assert fix_payload["last_recurrence_at"] is not None


def test_create_and_read_diagnosis_share_link(client: TestClient) -> None:
    headers = {"X-Project-Id": "proj-share-1"}
    submit = client.post(
        "/v1/diagnosis/submit",
        headers=headers,
        json={
            "diagnosis_id": "diag-share-1",
            "payload": {"prompt": "share me"},
        },
    )
    assert submit.status_code == 200

    share_create = client.post("/v1/diagnosis/diag-share-1/share", headers=headers)
    assert share_create.status_code == 201
    share_payload = share_create.json()
    assert share_payload["token"].startswith("zroky_share_live_")

    share_read = client.get(f"/v1/diagnosis/share/{share_payload['token']}")
    assert share_read.status_code == 200
    read_payload = share_read.json()
    assert read_payload["diagnosis_id"] == "diag-share-1"
    assert read_payload["tenant_id"] == "proj-share-1"
    assert read_payload["read_only"] is True


def test_expired_diagnosis_share_link_returns_gone(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("READ_ONLY_SHARE_TOKEN_TTL_SECONDS", "-1")
    get_settings.cache_clear()

    try:
        headers = {"X-Project-Id": "proj-share-expired-1"}
        submit = client.post(
            "/v1/diagnosis/submit",
            headers=headers,
            json={
                "diagnosis_id": "diag-share-expired-1",
                "payload": {"prompt": "expired"},
            },
        )
        assert submit.status_code == 200

        share_create = client.post("/v1/diagnosis/diag-share-expired-1/share", headers=headers)
        assert share_create.status_code == 201
        share_token = share_create.json()["token"]

        share_read = client.get(f"/v1/diagnosis/share/{share_token}")
        assert share_read.status_code == 410
    finally:
        get_settings.cache_clear()


def test_project_admin_can_revoke_share_link_viewer_cannot(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REQUIRE_PROVISIONING_TOKEN", "true")
    monkeypatch.setenv("PROVISIONING_TOKEN", "top-secret")
    monkeypatch.setenv("ALLOW_PROJECT_HEADER_CONTEXT", "false")
    monkeypatch.setenv("JWT_SIGNING_KEY", "jwt-secret-for-tests-minimum-32-bytes-2026")
    monkeypatch.setenv("JWT_ALGORITHMS", "HS256")
    monkeypatch.setenv("ENFORCE_JWT_PROJECT_MEMBERSHIP", "true")
    get_settings.cache_clear()

    try:
        create_project = client.post(
            "/v1/projects",
            headers={"X-Zroky-Admin-Token": "top-secret"},
            json={"name": "Share Revoke Project", "owner_ref": "owner-share-sub"},
        )
        assert create_project.status_code == 201
        project_id = create_project.json()["project_id"]

        owner_token = jwt.encode(
            {
                "sub": "owner-share-sub",
                "project_id": project_id,
            },
            "jwt-secret-for-tests-minimum-32-bytes-2026",
            algorithm="HS256",
        )
        submit = client.post(
            "/v1/diagnosis/submit",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={
                "diagnosis_id": "diag-share-revoke-1",
                "payload": {"prompt": "seed"},
            },
        )
        assert submit.status_code == 200

        create_share = client.post(
            "/v1/diagnosis/diag-share-revoke-1/share",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert create_share.status_code == 201
        share_payload = create_share.json()

        membership = client.post(
            f"/v1/projects/{project_id}/memberships",
            headers={"X-Zroky-Admin-Token": "top-secret"},
            json={
                "subject": "viewer-share-sub",
                "role": "viewer",
                "is_active": True,
            },
        )
        assert membership.status_code == 200

        viewer_token = jwt.encode(
            {
                "sub": "viewer-share-sub",
                "project_id": project_id,
            },
            "jwt-secret-for-tests-minimum-32-bytes-2026",
            algorithm="HS256",
        )
        viewer_revoke = client.post(
            f"/v1/projects/{project_id}/diagnosis-shares/{share_payload['share_id']}/revoke",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert viewer_revoke.status_code == 403

        owner_revoke = client.post(
            f"/v1/projects/{project_id}/diagnosis-shares/{share_payload['share_id']}/revoke",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert owner_revoke.status_code == 200
        assert owner_revoke.json()["revoked"] is True

        share_read = client.get(f"/v1/diagnosis/share/{share_payload['token']}")
        assert share_read.status_code == 410
    finally:
        get_settings.cache_clear()


def test_generate_pr_creates_link_and_lists_prs(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_PR_BOT_TOKEN", "bot-token-test")
    get_settings.cache_clear()

    try:
        headers = {"X-Project-Id": "proj-generate-pr-1"}
        submit = client.post(
            "/v1/diagnosis/submit",
            headers=headers,
            json={
                "diagnosis_id": "diag-generate-pr-1",
                "payload": {
                    "provider": "openai",
                    "model": "gpt-4o",
                    "category": "RATE_LIMIT",
                },
            },
        )
        assert submit.status_code == 200

        class _FakeGithubResult:
            branch_name = "zroky/fix/diag-generate-pr-1"
            pull_request_number = 17
            pull_request_url = "https://github.com/acme/demo/pull/17"
            pull_request_title = "[ZROKY Fix] diag-generate-pr-1"
            file_path = "zroky-generated-fixes/diag-generate-pr-1.md"
            commit_sha = "abc123def456"

        monkeypatch.setattr(
            "app.api.routes.diagnosis.create_pull_request_with_patch",
            lambda **_kwargs: _FakeGithubResult(),
        )

        response = client.post(
            "/v1/diagnosis/diag-generate-pr-1/generate-pr",
            headers=headers,
            json={
                "repository_owner": "acme",
                "repository_name": "demo",
                "base_branch": "main",
            },
        )
        assert response.status_code == 201
        payload = response.json()
        assert payload["diagnosis_id"] == "diag-generate-pr-1"
        assert payload["auth_source"] == "bot_token"
        assert payload["repository_owner"] == "acme"
        assert payload["repository_name"] == "demo"
        assert payload["pull_request_number"] == 17
        assert payload["pull_request_url"] == "https://github.com/acme/demo/pull/17"

        list_response = client.get(
            "/v1/diagnosis/diag-generate-pr-1/prs",
            headers=headers,
        )
        assert list_response.status_code == 200
        rows = list_response.json()
        assert len(rows) == 1
        assert rows[0]["pull_request_url"] == "https://github.com/acme/demo/pull/17"
    finally:
        get_settings.cache_clear()


def test_generate_pr_requires_repository_when_not_configured(client: TestClient) -> None:
    headers = {"X-Project-Id": "proj-generate-pr-2"}
    submit = client.post(
        "/v1/diagnosis/submit",
        headers=headers,
        json={
            "diagnosis_id": "diag-generate-pr-2",
            "payload": {"provider": "openai", "model": "gpt-4o"},
        },
    )
    assert submit.status_code == 200

    response = client.post(
        "/v1/diagnosis/diag-generate-pr-2/generate-pr",
        headers=headers,
        json={},
    )
    assert response.status_code == 422


def test_enterprise_audit_logs_capture_required_actions(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_PR_BOT_TOKEN", "bot-token-test")
    get_settings.cache_clear()

    try:
        headers = {"X-Project-Id": "proj-audit-feed-1"}
        submit = client.post(
            "/v1/diagnosis/submit",
            headers=headers,
            json={
                "diagnosis_id": "diag-audit-feed-1",
                "payload": {
                    "provider": "openai",
                    "model": "gpt-4o",
                    "category": "RATE_LIMIT",
                },
            },
        )
        assert submit.status_code == 200

        viewed = client.get("/v1/calls/diag-audit-feed-1", headers=headers)
        assert viewed.status_code == 200

        fix_copied = client.post("/v1/diagnosis/diag-audit-feed-1/fix-copied", headers=headers)
        assert fix_copied.status_code == 201
        assert fix_copied.json()["action"] == "fix_copied"

        class _FakeGithubResult:
            branch_name = "zroky/fix/diag-audit-feed-1"
            pull_request_number = 23
            pull_request_url = "https://github.com/acme/demo/pull/23"
            pull_request_title = "[ZROKY Fix] diag-audit-feed-1"
            file_path = "zroky-generated-fixes/diag-audit-feed-1.md"
            commit_sha = "feed123abc456"

        monkeypatch.setattr(
            "app.api.routes.diagnosis.create_pull_request_with_patch",
            lambda **_kwargs: _FakeGithubResult(),
        )

        generated_pr = client.post(
            "/v1/diagnosis/diag-audit-feed-1/generate-pr",
            headers=headers,
            json={
                "repository_owner": "acme",
                "repository_name": "demo",
                "base_branch": "main",
            },
        )
        assert generated_pr.status_code == 201

        resolved = client.post("/v1/diagnosis/diag-audit-feed-1/resolve", headers=headers)
        assert resolved.status_code == 200

        feed = client.get("/v1/analytics/activity-feed?limit=25&offset=0", headers=headers)
        assert feed.status_code == 200
        items = feed.json()["items"]
        actions = {item["action"] for item in items}

        assert "diagnosis_viewed" in actions
        assert "fix_copied" in actions
        assert "pr_generated" in actions
        assert "resolved" in actions
    finally:
        get_settings.cache_clear()
