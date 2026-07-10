from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.dependencies.tenant import TenantContext, require_tenant_context
from app.core.config import get_settings
from app.db.base import Base
from app.db.models import Project, SystemOfRecordConnectorConfig
from app.db.session import get_db_session, get_db_session_read
from app.main import app
from app.services.connectors.sor.runtime import StripeRefundConnector
from app.services.connector_credentials import (
    ConnectorCredentialError,
    CredentialNotFoundError,
    RemoteCredentialResolutionRequired,
    bind_connector_credential,
    create_connector_credential,
    get_connector_credential,
    list_connector_credential_audit_events,
    resolve_connector_credential,
    rotate_connector_credential,
    serialize_connector_credential,
    serialize_connector_credential_audit_event,
)
from app.services.provider_key_cipher import encrypt_provider_key
from app.services.outcome_reconciliation import SourceRecord


def _session_factory(path: Path):
    engine = create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    return engine, sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def _seed_project(factory, project_id: str) -> None:
    with factory() as db:
        db.add(Project(id=project_id, name=project_id))
        db.commit()


def _seed_config(db, project_id: str, *, connector_type: str = "stripe_refund"):
    row = SystemOfRecordConnectorConfig(
        project_id=project_id,
        connector_type=connector_type,
        base_url="https://api.example.test",
        path_template="/v1/refunds/{refund_id}",
        is_active=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture(autouse=True)
def _vault_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PROVIDER_KEY_VAULT_KEK", "test-connector-custody-kek-12345678901234567890")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_managed_rotation_moves_binding_and_never_serializes_secret(tmp_path: Path) -> None:
    engine, factory = _session_factory(tmp_path / "managed_rotation.db")
    try:
        _seed_project(factory, "project-a")
        with factory() as db:
            config = _seed_config(db, "project-a")
            first = create_connector_credential(
                db,
                project_id="project-a",
                name="stripe-verification-readonly",
                credential_kind="bearer_token",
                custody_mode="zroky_managed",
                plaintext_secret="stripe-readonly-v1-secret",
                secret_ref=None,
                scopes=["refunds:read"],
                allowed_connector_types=["stripe_refund"],
                expires_at=None,
                rotation_due_at=None,
                actor_subject="owner-1",
            )
            bound = bind_connector_credential(
                db,
                project_id="project-a",
                connector_type=config.connector_type,
                credential_id=first.id,
                purpose="bearer_token",
                actor_subject="owner-1",
            )
            assert resolve_connector_credential(
                db, row=bound, project_id="project-a", purpose="bearer_token"
            ) == "stripe-readonly-v1-secret"

            replacement = rotate_connector_credential(
                db,
                project_id="project-a",
                credential_id=first.id,
                custody_mode="zroky_managed",
                plaintext_secret="stripe-readonly-v2-secret",
                secret_ref=None,
                scopes=["refunds:read"],
                allowed_connector_types=["stripe_refund"],
                expires_at=None,
                rotation_due_at=None,
                actor_subject="owner-2",
            )
            db.refresh(bound)
            assert bound.bearer_credential_id == replacement.id
            assert get_connector_credential(
                db, project_id="project-a", credential_id=first.id
            ).is_active is False
            assert resolve_connector_credential(
                db, row=bound, project_id="project-a", purpose="bearer_token"
            ) == "stripe-readonly-v2-secret"

            serialized = json.dumps(serialize_connector_credential(replacement), default=str)
            audit = [
                serialize_connector_credential_audit_event(event)
                for event in list_connector_credential_audit_events(
                    db, project_id="project-a", credential_id=replacement.id
                )
            ]
            audit_serialized = json.dumps(audit, default=str)
            assert "stripe-readonly-v2-secret" not in serialized
            assert "stripe-readonly-v2-secret" not in audit_serialized
            assert "key_fingerprint" not in serialized
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_private_runner_binding_removes_legacy_secret_and_fails_closed(tmp_path: Path) -> None:
    engine, factory = _session_factory(tmp_path / "private_runner.db")
    try:
        _seed_project(factory, "project-a")
        with factory() as db:
            config = _seed_config(db, "project-a")
            legacy = encrypt_provider_key(
                plaintext="legacy-stripe-secret", project_id="project-a"
            )
            config.bearer_token_ciphertext = legacy.ciphertext
            config.bearer_token_fingerprint = legacy.key_fingerprint
            config.bearer_token_last4 = legacy.key_last4
            db.add(config)
            db.commit()

            credential = create_connector_credential(
                db,
                project_id="project-a",
                name="stripe-private-runner",
                credential_kind="bearer_token",
                custody_mode="private_runner",
                plaintext_secret=None,
                secret_ref="customer-runner-secret://finance-vpc/stripe-readonly",
                scopes=["refunds:read"],
                allowed_connector_types=["stripe_refund"],
                expires_at=None,
                rotation_due_at=None,
                actor_subject="owner-1",
            )
            bound = bind_connector_credential(
                db,
                project_id="project-a",
                connector_type=config.connector_type,
                credential_id=credential.id,
                purpose="bearer_token",
                actor_subject="owner-1",
            )
            assert bound.bearer_token_ciphertext is None
            assert bound.bearer_token_fingerprint is None
            with pytest.raises(RemoteCredentialResolutionRequired):
                resolve_connector_credential(
                    db, row=bound, project_id="project-a", purpose="bearer_token"
                )
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_private_runner_rejects_unrecognized_runner_reference(tmp_path: Path) -> None:
    engine, factory = _session_factory(tmp_path / "private_runner_reference.db")
    try:
        _seed_project(factory, "project-a")
        with factory() as db:
            with pytest.raises(ConnectorCredentialError, match="customer-runner-secret"):
                create_connector_credential(
                    db,
                    project_id="project-a",
                    name="invalid-private-runner-ref",
                    credential_kind="bearer_token",
                    custody_mode="private_runner",
                    plaintext_secret=None,
                    secret_ref="runner://finance-vpc/stripe-readonly",
                    scopes=["refunds:read"],
                    allowed_connector_types=["stripe_refund"],
                    expires_at=None,
                    rotation_due_at=None,
                    actor_subject="owner-1",
                )
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_bound_managed_credential_executes_through_saved_connector_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, factory = _session_factory(tmp_path / "bound_route.db")
    _seed_project(factory, "project-a")

    with factory() as db:
        config = _seed_config(db, "project-a")
        credential = create_connector_credential(
            db,
            project_id="project-a",
            name="stripe-route-readonly",
            credential_kind="bearer_token",
            custody_mode="zroky_managed",
            plaintext_secret="stripe-route-readonly-secret",
            secret_ref=None,
            scopes=["refunds:read"],
            allowed_connector_types=["stripe_refund"],
            expires_at=None,
            rotation_due_at=None,
            actor_subject="owner-1",
        )
        bind_connector_credential(
            db,
            project_id="project-a",
            connector_type=config.connector_type,
            credential_id=credential.id,
            purpose="bearer_token",
            actor_subject="owner-1",
        )

    def override_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    def owner_context() -> TenantContext:
        return TenantContext(tenant_id="project-a", role="owner", subject="owner-1")

    def fake_fetch(self: StripeRefundConnector) -> SourceRecord:
        assert self.bearer_token == "stripe-route-readonly-secret"
        return SourceRecord(
            record={"refund_id": self.refund_id, "status": "succeeded"},
            record_found=True,
            metadata={"connector_type": "stripe_refund", "http_status": 200, "attempts": 1},
        )

    monkeypatch.setattr(StripeRefundConnector, "fetch", fake_fetch)
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_db_session_read] = override_db
    app.dependency_overrides[require_tenant_context] = owner_context
    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/integrations/system-of-record/stripe-refund/test",
                json={
                    "refund_id": "re_bound_1",
                    "claimed": {"refund_id": "re_bound_1", "status": "succeeded"},
                    "match_fields": ["refund_id", "status"],
                },
            )
        assert response.status_code == 201, response.text
        assert response.json()["check"]["verdict"] == "matched"
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_binding_is_tenant_scoped_and_connector_type_scoped(tmp_path: Path) -> None:
    engine, factory = _session_factory(tmp_path / "credential_scope.db")
    try:
        _seed_project(factory, "project-a")
        _seed_project(factory, "project-b")
        with factory() as db:
            config = _seed_config(db, "project-a")
            _seed_config(db, "project-b")
            credential = create_connector_credential(
                db,
                project_id="project-a",
                name="stripe-only",
                credential_kind="bearer_token",
                custody_mode="customer_managed",
                plaintext_secret=None,
                secret_ref="vault://tenant-a/stripe-readonly",
                scopes=["refunds:read"],
                allowed_connector_types=["stripe_refund"],
                expires_at=None,
                rotation_due_at=None,
                actor_subject="owner-1",
            )
            with pytest.raises(CredentialNotFoundError):
                bind_connector_credential(
                    db,
                    project_id="project-b",
                    connector_type=config.connector_type,
                    credential_id=credential.id,
                    purpose="bearer_token",
                    actor_subject="owner-2",
                )
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_credential_api_is_owner_only_and_metadata_only(tmp_path: Path) -> None:
    engine, factory = _session_factory(tmp_path / "credential_api.db")
    _seed_project(factory, "project-a")

    def override_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    def owner_context() -> TenantContext:
        return TenantContext(tenant_id="project-a", role="owner", subject="owner-1")

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_db_session_read] = override_db
    app.dependency_overrides[require_tenant_context] = owner_context
    try:
        with TestClient(app) as client:
            created = client.post(
                "/v1/integrations/system-of-record/credentials",
                json={
                    "name": "customer-vault-stripe",
                    "credential_kind": "bearer_token",
                    "custody_mode": "customer_managed",
                    "secret_ref": "vault://tenant-a/stripe-readonly",
                    "scopes": ["refunds:read"],
                    "allowed_connector_types": ["stripe_refund"],
                },
            )
            assert created.status_code == 201
            body = created.json()
            assert body["reference_configured"] is True
            assert body["reference_scheme"] == "vault"
            assert "vault://tenant-a/stripe-readonly" not in json.dumps(body)
            assert "secret_ref" not in body

            audit = client.get(
                f"/v1/integrations/system-of-record/credentials/{body['id']}/audit"
            )
            assert audit.status_code == 200
            assert "vault://tenant-a/stripe-readonly" not in json.dumps(audit.json())

        def admin_context() -> TenantContext:
            return TenantContext(tenant_id="project-a", role="admin", subject="admin-1")

        app.dependency_overrides[require_tenant_context] = admin_context
        with TestClient(app) as client:
            denied = client.get("/v1/integrations/system-of-record/credentials")
            assert denied.status_code == 403
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
