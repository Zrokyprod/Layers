from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import ActionContractVersion, ApiKey, McpToolBinding, Project
from app.db.session import get_db_session, get_db_session_read
from app.main import app
from app.mcp.canary import CANARY_ACTION_TYPE, CANARY_PROJECT_ID, CANARY_TOOL_NAME


def _client(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PROVISIONING_TOKEN", "test-provisioning-token")
    monkeypatch.setenv("REQUIRE_PROVISIONING_TOKEN", "true")
    monkeypatch.setenv("ALLOW_PROJECT_HEADER_CONTEXT", "false")
    get_settings.cache_clear()

    engine = create_engine(
        f"sqlite:///{tmp_path / 'mcp_canary.db'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def override():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override
    app.dependency_overrides[get_db_session_read] = override
    client = TestClient(app)
    client._session_factory = factory  # type: ignore[attr-defined]
    client._engine = engine  # type: ignore[attr-defined]
    return client


def _close(client: TestClient) -> None:
    engine = client._engine  # type: ignore[attr-defined]
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    get_settings.cache_clear()
    client.close()


def test_canary_upstream_is_inert_by_default(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    try:
        monkeypatch.setenv("MCP_CANARY_UPSTREAM_ENABLED", "false")
        get_settings.cache_clear()
        response = client.post(
            "/internal/mcp-canary/upstream",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
        assert response.status_code == 404
    finally:
        _close(client)


def test_canary_upstream_returns_matching_verification_hint(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    try:
        monkeypatch.setenv("MCP_CANARY_UPSTREAM_ENABLED", "true")
        get_settings.cache_clear()
        response = client.post(
            "/internal/mcp-canary/upstream",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": CANARY_TOOL_NAME,
                    "arguments": {"record_ref": "canary_1", "status": "completed"},
                },
            },
        )
        assert response.status_code == 200
        verification = response.json()["result"]["_meta"]["zroky"]["verification"]
        assert verification["claimed"] == verification["actual"]
        assert verification["match_fields"] == ["record_ref", "status"]
    finally:
        _close(client)


def test_canary_upstream_supports_initialize_and_notifications(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    try:
        monkeypatch.setenv("MCP_CANARY_UPSTREAM_ENABLED", "true")
        get_settings.cache_clear()
        initialized = client.post(
            "/internal/mcp-canary/upstream",
            json={"jsonrpc": "2.0", "id": "init", "method": "initialize", "params": {}},
        )
        assert initialized.status_code == 200
        assert initialized.json()["result"]["protocolVersion"] == "2025-06-18"

        notification = client.post(
            "/internal/mcp-canary/upstream",
            json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        )
        assert notification.status_code == 202
        assert notification.content == b""
    finally:
        _close(client)


def test_canary_setup_creates_binding_and_short_lived_api_key(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    try:
        response = client.post(
            "/internal/mcp-canary/setup",
            headers={"x-zroky-admin-token": "test-provisioning-token"},
            json={"api_key_expires_in_hours": 1},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["project_id"] == CANARY_PROJECT_ID
        assert body["tool_name"] == CANARY_TOOL_NAME
        assert body["api_key"].startswith("zk_live_")

        with client._session_factory() as session:  # type: ignore[attr-defined]
            assert session.get(Project, CANARY_PROJECT_ID) is not None
            contract = session.execute(
                select(ActionContractVersion).where(
                    ActionContractVersion.project_id == CANARY_PROJECT_ID,
                    ActionContractVersion.action_type == CANARY_ACTION_TYPE,
                )
            ).scalar_one()
            assert contract.contract_key == "zroky.mcp.canary.inventory_adjust"
            binding = session.execute(
                select(McpToolBinding).where(
                    McpToolBinding.project_id == CANARY_PROJECT_ID,
                    McpToolBinding.tool_name == CANARY_TOOL_NAME,
                )
            ).scalar_one()
            assert binding.protected is True
            assert binding.fail_posture == "fail_closed"
            assert session.execute(
                select(ApiKey).where(ApiKey.project_id == CANARY_PROJECT_ID)
            ).scalar_one().expires_at is not None

        auth_check = client.get(
            "/v1/action-intents",
            headers={"X-Project-Id": CANARY_PROJECT_ID, "X-API-Key": body["api_key"]},
        )
        assert auth_check.status_code == 200, auth_check.text
    finally:
        _close(client)
