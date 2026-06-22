from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import AuditLog
from app.db.session import get_db_session
from app.main import app


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def set(self, key: str, value: str) -> bool:
        self.store[key] = value
        return True

    def delete(self, key: str) -> int:
        existed = key in self.store
        self.store.pop(key, None)
        return int(existed)


@pytest.fixture()
def client(tmp_path: Path):
    db_path = tmp_path / "owner_mutation_audit.db"
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
        yield TestClient(app), session_factory
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()
        engine.dispose()


def _set_owner_auth(monkeypatch: pytest.MonkeyPatch, token: str = "owner-token") -> dict[str, str]:
    monkeypatch.setenv("REQUIRE_PROVISIONING_TOKEN", "false")
    monkeypatch.setenv("PROVISIONING_TOKEN", token)
    get_settings.cache_clear()
    return {"x-zroky-admin-token": token}


def _patch_owner_redis(monkeypatch: pytest.MonkeyPatch) -> _FakeRedis:
    fake = _FakeRedis()
    for module_name in (
        "app.api.routes._internal.owner_health",
        "app.api.routes._internal.owner_pricing_audit",
        "app.api.routes._internal.owner_rate_audit_llm",
    ):
        monkeypatch.setattr(f"{module_name}._redis_ok", lambda: True)
        monkeypatch.setattr(f"{module_name}.get_redis_client", lambda fake=fake: fake)
    return fake


def _audit_rows(session_factory) -> list[AuditLog]:
    with session_factory() as db:
        return list(db.scalars(select(AuditLog).order_by(AuditLog.created_at.asc())).all())


def test_owner_pricing_get_handles_missing_filesystem_fallback(
    client,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    test_client, _ = client
    owner_headers = _set_owner_auth(monkeypatch)
    monkeypatch.delenv("PRICING_CONFIG_PATH", raising=False)
    monkeypatch.setattr("app.api.routes._internal.owner_pricing_audit._redis_ok", lambda: False)

    res = test_client.get("/v1/owner/pricing", headers=owner_headers)

    assert res.status_code == 200
    payload = res.json()
    assert isinstance(payload["config"], dict)
    assert isinstance(payload["exists"], bool)
    assert payload["path"].endswith("pricing_config.json")

    monkeypatch.setenv("PRICING_CONFIG_PATH", str(tmp_path / "missing-pricing-config.json"))
    missing_res = test_client.get("/v1/owner/pricing", headers=owner_headers)

    assert missing_res.status_code == 200
    payload = missing_res.json()
    assert payload["config"] == {}
    assert payload["exists"] is False
    assert payload["path"].endswith("missing-pricing-config.json")


def test_owner_redis_mutations_write_audit_events(client, monkeypatch: pytest.MonkeyPatch) -> None:
    test_client, session_factory = client
    owner_headers = _set_owner_auth(monkeypatch)
    _patch_owner_redis(monkeypatch)

    maintenance = test_client.post(
        "/v1/owner/maintenance",
        headers=owner_headers,
        json={"enabled": True, "message": "scheduled cutover"},
    )
    assert maintenance.status_code == 200

    pricing = test_client.put(
        "/v1/owner/pricing",
        headers=owner_headers,
        json={"config": {"launch_plan": "pro", "risk_anchor": "protected_actions"}},
    )
    assert pricing.status_code == 200

    rate_limit_set = test_client.put(
        "/v1/owner/rate-limits/overrides",
        headers=owner_headers,
        json={"overrides": {"ingest_soft_limit_rpm": 600, "ingest_enforce_rate_limit": True}},
    )
    assert rate_limit_set.status_code == 200

    rate_limit_clear = test_client.delete("/v1/owner/rate-limits/overrides", headers=owner_headers)
    assert rate_limit_clear.status_code == 200

    rows = _audit_rows(session_factory)
    actions = [row.action for row in rows]
    assert actions == [
        "owner.maintenance.set",
        "owner.pricing.update",
        "owner.rate_limit_overrides.set",
        "owner.rate_limit_overrides.clear",
    ]
    assert all(row.tenant_id == "PLATFORM" for row in rows)
    assert all(row.diagnosis_id == "owner_action" for row in rows)

    pricing_metadata = json.loads(rows[1].metadata_json)
    assert pricing_metadata["target_id"] == "pricing_config"
    assert pricing_metadata["config_keys"] == ["launch_plan", "risk_anchor"]

    rate_metadata = json.loads(rows[2].metadata_json)
    assert rate_metadata["override_keys"] == ["ingest_enforce_rate_limit", "ingest_soft_limit_rpm"]
