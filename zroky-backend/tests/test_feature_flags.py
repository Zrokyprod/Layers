from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app


@pytest.fixture()
def client(tmp_path: Path):
    db_path = tmp_path / "feature_flags.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()
        engine.dispose()


def _set_tenant(project_id: str) -> None:
    app.dependency_overrides[require_tenant_context] = lambda: TenantContext(
        tenant_id=project_id,
        role="owner",
        subject="owner@example.com",
    )


def _set_owner_auth(monkeypatch: pytest.MonkeyPatch, token: str = "owner-token") -> dict[str, str]:
    monkeypatch.setenv("REQUIRE_PROVISIONING_TOKEN", "false")
    monkeypatch.setenv("PROVISIONING_TOKEN", token)
    get_settings.cache_clear()
    return {"x-zroky-admin-token": token}


def test_owner_feature_flag_crud_and_tenant_resolution(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    owner_headers = _set_owner_auth(monkeypatch)

    created = client.post(
        "/v1/feature-flags/admin",
        headers=owner_headers,
        json={
            "key": "admin_console_v2",
            "description": "Enable the new owner admin console.",
            "enabled_globally": False,
        },
    )
    assert created.status_code == 201
    flag = created.json()
    assert flag["key"] == "admin_console_v2"
    assert flag["enabled_globally"] is False

    listed = client.get("/v1/feature-flags/admin", headers=owner_headers)
    assert listed.status_code == 200
    assert [item["key"] for item in listed.json()["items"]] == ["admin_console_v2"]

    updated = client.put(
        f"/v1/feature-flags/admin/{flag['id']}",
        headers=owner_headers,
        json={
            "enabled_globally": False,
            "add_enabled_tenants": ["proj_enabled"],
            "add_disabled_tenants": ["proj_disabled"],
        },
    )
    assert updated.status_code == 200
    assert updated.json()["enabled_tenants"] == ["proj_enabled"]
    assert updated.json()["disabled_tenants"] == ["proj_disabled"]

    _set_tenant("proj_enabled")
    enabled_view = client.get("/v1/feature-flags/tenant")
    assert enabled_view.status_code == 200
    assert enabled_view.json()["flags"]["admin_console_v2"] is True

    _set_tenant("proj_disabled")
    disabled_view = client.get("/v1/feature-flags/tenant")
    assert disabled_view.status_code == 200
    assert disabled_view.json()["flags"]["admin_console_v2"] is False

    deleted = client.delete(f"/v1/feature-flags/admin/{flag['id']}", headers=owner_headers)
    assert deleted.status_code == 204

    listed_after_delete = client.get("/v1/feature-flags/admin", headers=owner_headers)
    assert listed_after_delete.status_code == 200
    assert listed_after_delete.json()["items"] == []
