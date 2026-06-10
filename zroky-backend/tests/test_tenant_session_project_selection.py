from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.api.dependencies.authorization import require_project_role
from app.api.dependencies.tenant import _resolve_project_from_bearer
from app.api.routes.auth import list_current_user_projects
from app.core.config import get_settings
from app.db.base import Base
from app.db.models import Project, ProjectMembership, User
from app.services.security import issue_access_token


AUTH_SECRET = "session-project-selection-secret"


@pytest.fixture()
def db_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AUTH_JWT_SECRET", AUTH_SECRET)
    monkeypatch.setenv("JWT_ISSUER", "")
    monkeypatch.setenv("JWT_AUDIENCE", "")
    monkeypatch.setenv("ALLOW_PROJECT_HEADER_CONTEXT", "false")
    get_settings.cache_clear()

    engine = create_engine(
        f"sqlite:///{tmp_path / 'tenant-selection.db'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        get_settings.cache_clear()


def _request(token: str, selected_project_id: str | None = None) -> Request:
    headers = [(b"authorization", f"Bearer {token}".encode("utf-8"))]
    if selected_project_id:
        headers.append((b"x-project-id", selected_project_id.encode("utf-8")))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": headers,
        }
    )


def _seed_user_projects(db_session, *, memberships: list[tuple[str, str]]) -> tuple[User, str]:
    user = User(subject="user:multi-project", email="multi@example.com", is_active=True)
    db_session.add(user)
    db_session.flush()

    for project_id, role in memberships:
        db_session.add(Project(id=project_id, name=project_id, owner_ref=user.subject, is_active=True))
        db_session.flush()
        db_session.add(
            ProjectMembership(
                project_id=project_id,
                user_id=user.id,
                role=role,
                is_active=True,
            )
        )
    db_session.commit()

    token = issue_access_token(
        user_id=user.id,
        email=user.email,
        subject=user.subject,
        expire_hours=1,
        secret=AUTH_SECRET,
    )
    return user, token


def test_single_project_session_keeps_frictionless_resolution(db_session) -> None:
    _, token = _seed_user_projects(db_session, memberships=[("proj_single", "owner")])

    context = _resolve_project_from_bearer(_request(token), None, db_session)

    assert context is not None
    assert context.tenant_id == "proj_single"
    assert context.role == "owner"


def test_multi_project_session_requires_explicit_project_selection(db_session) -> None:
    _, token = _seed_user_projects(
        db_session,
        memberships=[("proj_first", "owner"), ("proj_second", "member")],
    )

    with pytest.raises(HTTPException) as error:
        _resolve_project_from_bearer(_request(token), None, db_session)

    assert error.value.status_code == 400
    assert error.value.detail["code"] == "project_selection_required"


def test_multi_project_session_honors_valid_selected_project(db_session) -> None:
    _, token = _seed_user_projects(
        db_session,
        memberships=[("proj_first", "owner"), ("proj_second", "member")],
    )

    context = _resolve_project_from_bearer(_request(token), "proj_second", db_session)

    assert context is not None
    assert context.tenant_id == "proj_second"
    assert context.role == "member"


def test_session_selected_project_requires_membership(db_session) -> None:
    _, token = _seed_user_projects(db_session, memberships=[("proj_allowed", "owner")])
    db_session.add(Project(id="proj_forbidden", name="Forbidden", is_active=True))
    db_session.commit()

    with pytest.raises(HTTPException) as error:
        _resolve_project_from_bearer(_request(token), "proj_forbidden", db_session)

    assert error.value.status_code == 403


def test_current_user_projects_lists_active_memberships_without_tenant_context(db_session) -> None:
    user, token = _seed_user_projects(
        db_session,
        memberships=[("proj_b", "viewer"), ("proj_a", "admin")],
    )
    inactive_project = Project(id="proj_inactive", name="Inactive", owner_ref=user.subject, is_active=False)
    db_session.add(inactive_project)
    db_session.add(
        ProjectMembership(
            project_id="proj_inactive",
            user_id=user.id,
            role="owner",
            is_active=True,
        )
    )
    db_session.commit()

    projects = list_current_user_projects(authorization=f"Bearer {token}", db=db_session)

    assert [project.project_id for project in projects] == ["proj_a", "proj_b"]
    assert projects[0].project_name == "proj_a"
    assert projects[0].role == "admin"


def test_project_role_guard_accepts_internal_session_when_path_matches_selected_project(db_session) -> None:
    _, token = _seed_user_projects(
        db_session,
        memberships=[("proj_first", "owner"), ("proj_second", "admin")],
    )
    guard = require_project_role("admin")

    tenant_id = guard(
        request=_request(token, selected_project_id="proj_second"),
        project_id="proj_second",
        db=db_session,
    )

    assert tenant_id == "proj_second"


def test_project_role_guard_rejects_selected_project_path_mismatch(db_session) -> None:
    _, token = _seed_user_projects(
        db_session,
        memberships=[("proj_first", "owner"), ("proj_second", "admin")],
    )
    guard = require_project_role("admin")

    with pytest.raises(HTTPException) as error:
        guard(
            request=_request(token, selected_project_id="proj_first"),
            project_id="proj_second",
            db=db_session,
        )

    assert error.value.status_code == 403
    assert error.value.detail == "Selected project does not match requested project."
