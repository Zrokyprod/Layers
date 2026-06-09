"""Tests for the Pilot-tier provider key vault (Module 4.5):

Covers three layers:

  1. `services.provider_key_cipher` — AES-256-GCM envelope round-trips,
     per-project AAD binding, KEK-unset failure, format guards.
  2. `services.provider_key_vault`  — store / list / get / revoke /
     get_active / decrypt_active, validation, dedup, rotation.
  3. `routes/providers.py`          — POST/GET/DELETE /v1/providers/keys
     with 422/409/503/404 mapping, tenant isolation, no-plaintext-leak.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import ApiKey, Project, ProviderKeyVault
from app.db.session import get_db_session, get_db_session_read
from app.main import app
from app.services.entitlements import set_override_entitlement
from app.services.provider_key_cipher import (
    EnvelopeFormatError,
    VaultCipherUnavailable,
    compute_fingerprint,
    decrypt_provider_key,
    encrypt_provider_key,
    last4_of,
)
from app.services.provider_key_vault import (
    DuplicateKeyError,
    InvalidKeyPlaintextError,
    InvalidProviderError,
    VALID_PROVIDERS,
    decrypt_active_provider_key,
    get_active_provider_key,
    get_provider_key,
    list_provider_keys,
    revoke_provider_key,
    serialize_vault_row,
    store_provider_key,
)
from app.services.security import generate_api_key_material


PROJECT_HEADER = "X-Project-Id"
_TEST_KEK = "test-kek-must-be-at-least-32-chars-yes!"
_DEFAULT_ROUTE_ENTITLED_PROJECTS = ("proj-1", "proj-A", "proj-B")


def _grant_provider_key_vault(session_factory, project_id: str) -> None:
    with session_factory() as session:
        set_override_entitlement(
            session,
            org_id=project_id,
            key="enterprise.provider_key_vault",
            value=True,
        )


def _create_member_api_key(client: TestClient, project_id: str = "proj-member") -> str:
    raw_key, key_prefix, key_hash = generate_api_key_material()
    session_factory = client._session_factory  # type: ignore[attr-defined]
    with session_factory() as session:
        if session.get(Project, project_id) is None:
            session.add(Project(id=project_id, name="Member Project"))
        session.add(
            ApiKey(
                project_id=project_id,
                name="member-key",
                key_prefix=key_prefix,
                key_hash=key_hash,
            )
        )
        session.commit()
    return raw_key


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _set_kek(monkeypatch: pytest.MonkeyPatch):
    """Every test gets a working KEK by default. Tests that need to
    exercise the unset-KEK path call `monkeypatch.delenv` themselves."""
    monkeypatch.setenv("PROVIDER_KEY_VAULT_KEK", _TEST_KEK)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "test_pkv_svc.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(tmp_path: Path):
    db_path = tmp_path / "test_pkv_route.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )

    def override_get_db_session():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_db_session_read] = override_get_db_session
    for project_id in _DEFAULT_ROUTE_ENTITLED_PROJECTS:
        _grant_provider_key_vault(session_factory, project_id)

    with TestClient(app) as test_client:
        test_client._session_factory = session_factory  # type: ignore[attr-defined]
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


# ── cipher: round-trip + AAD binding + KEK guards ────────────────────────────


class TestCipher:
    def test_encrypt_decrypt_round_trip(self) -> None:
        bundle = encrypt_provider_key(
            plaintext="sk-proj-abc-12345", project_id="proj-1"
        )
        assert isinstance(bundle.ciphertext, bytes)
        assert len(bundle.ciphertext) >= 12 + 16  # nonce + min tag
        assert bundle.key_fingerprint == compute_fingerprint("sk-proj-abc-12345")
        assert bundle.key_last4 == "2345"
        assert bundle.kms_key_id == "local-dev-kek-v1"
        plaintext = decrypt_provider_key(
            ciphertext=bundle.ciphertext, project_id="proj-1"
        )
        assert plaintext == "sk-proj-abc-12345"

    def test_two_encrypts_yield_different_ciphertext(self) -> None:
        # Random nonce — same plaintext + project should NOT produce the
        # same ciphertext twice.
        b1 = encrypt_provider_key(plaintext="sk-1234567890", project_id="p")
        b2 = encrypt_provider_key(plaintext="sk-1234567890", project_id="p")
        assert b1.ciphertext != b2.ciphertext
        assert b1.key_fingerprint == b2.key_fingerprint  # but fp is stable

    def test_cross_project_decrypt_blocked(self) -> None:
        bundle = encrypt_provider_key(plaintext="sk-cross-1234", project_id="A")
        with pytest.raises(EnvelopeFormatError):
            decrypt_provider_key(ciphertext=bundle.ciphertext, project_id="B")

    def test_decrypt_too_short_envelope(self) -> None:
        with pytest.raises(EnvelopeFormatError, match="too short"):
            decrypt_provider_key(ciphertext=b"\x00" * 10, project_id="p")

    def test_decrypt_wrong_type(self) -> None:
        with pytest.raises(EnvelopeFormatError, match="must be bytes"):
            decrypt_provider_key(ciphertext="not-bytes", project_id="p")  # type: ignore[arg-type]

    def test_decrypt_corrupted_tag(self) -> None:
        bundle = encrypt_provider_key(
            plaintext="sk-corrupt-1234", project_id="p"
        )
        # Flip one byte in the auth tag region (last bytes) to fail GCM
        bad = bytearray(bundle.ciphertext)
        bad[-1] ^= 0x01
        with pytest.raises(EnvelopeFormatError):
            decrypt_provider_key(ciphertext=bytes(bad), project_id="p")

    def test_encrypt_empty_plaintext_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            encrypt_provider_key(plaintext="   ", project_id="p")

    def test_kek_unset_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PROVIDER_KEY_VAULT_KEK", raising=False)
        get_settings.cache_clear()
        with pytest.raises(VaultCipherUnavailable):
            encrypt_provider_key(plaintext="sk-x-12345", project_id="p")

    def test_kek_too_short_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PROVIDER_KEY_VAULT_KEK", "tiny")
        get_settings.cache_clear()
        with pytest.raises(VaultCipherUnavailable, match="32"):
            encrypt_provider_key(plaintext="sk-x-12345", project_id="p")

    def test_last4_helper(self) -> None:
        assert last4_of("sk-1234567890") == "7890"
        assert last4_of("abc") == "abc"  # falls back when shorter than 4
        assert last4_of("abcd") == "abcd"

    def test_fingerprint_is_stable(self) -> None:
        assert (
            compute_fingerprint("sk-test-xyz") == compute_fingerprint("sk-test-xyz")
        )
        assert (
            compute_fingerprint("sk-test-xyz") != compute_fingerprint("sk-test-XYZ")
        )


# ── service: store_provider_key ──────────────────────────────────────────────


class TestStoreProviderKey:
    def test_happy_path(self, db_session) -> None:
        row = store_provider_key(
            db_session,
            project_id="proj-1",
            provider="openai",
            plaintext_key="sk-proj-1234567890",
            label="prod",
        )
        assert row.id
        assert row.is_active is True
        assert row.label == "prod"
        assert row.key_last4 == "7890"
        assert row.key_fingerprint == compute_fingerprint("sk-proj-1234567890")
        assert isinstance(row.ciphertext, bytes)
        # Plaintext is NOT stored
        assert b"1234567890" not in row.ciphertext

    def test_invalid_provider(self, db_session) -> None:
        with pytest.raises(InvalidProviderError):
            store_provider_key(
                db_session,
                project_id="p",
                provider="totally-fake",
                plaintext_key="sk-1234567890",
            )

    def test_provider_normalised(self, db_session) -> None:
        # "OpenAI" → "openai"
        row = store_provider_key(
            db_session,
            project_id="p",
            provider="  OpenAI  ",
            plaintext_key="sk-1234567890",
        )
        assert row.provider == "openai"

    def test_empty_plaintext_raises(self, db_session) -> None:
        with pytest.raises(InvalidKeyPlaintextError):
            store_provider_key(
                db_session,
                project_id="p",
                provider="openai",
                plaintext_key="   ",
            )

    def test_short_plaintext_raises(self, db_session) -> None:
        with pytest.raises(InvalidKeyPlaintextError, match="8"):
            store_provider_key(
                db_session,
                project_id="p",
                provider="openai",
                plaintext_key="sk-1",
            )

    def test_dedup_active_same_fingerprint(self, db_session) -> None:
        store_provider_key(
            db_session, project_id="p", provider="openai",
            plaintext_key="sk-aaa-12345",
        )
        with pytest.raises(DuplicateKeyError):
            store_provider_key(
                db_session, project_id="p", provider="openai",
                plaintext_key="sk-aaa-12345",
            )

    def test_rotation_revokes_previous_active(self, db_session) -> None:
        first = store_provider_key(
            db_session, project_id="p", provider="openai",
            plaintext_key="sk-first-1234",
        )
        first_id = first.id
        second = store_provider_key(
            db_session, project_id="p", provider="openai",
            plaintext_key="sk-second-5678",
        )

        # Refresh first from DB
        db_session.expire_all()
        rotated = db_session.get(ProviderKeyVault, first_id)
        assert rotated is not None
        assert rotated.is_active is False
        assert rotated.revoked_at is not None
        assert second.is_active is True

    def test_rotation_per_provider_only(self, db_session) -> None:
        # Adding an anthropic key should NOT revoke the active openai key
        openai_row = store_provider_key(
            db_session, project_id="p", provider="openai",
            plaintext_key="sk-openai-12345",
        )
        store_provider_key(
            db_session, project_id="p", provider="anthropic",
            plaintext_key="sk-ant-12345",
        )
        db_session.expire_all()
        still_active = db_session.get(ProviderKeyVault, openai_row.id)
        assert still_active is not None
        assert still_active.is_active is True

    def test_tenant_isolation_on_dedup(self, db_session) -> None:
        # Same plaintext, two tenants — both succeed
        store_provider_key(
            db_session, project_id="A", provider="openai",
            plaintext_key="sk-shared-1234",
        )
        # Different tenant, same fingerprint → no dedup conflict
        row_b = store_provider_key(
            db_session, project_id="B", provider="openai",
            plaintext_key="sk-shared-1234",
        )
        assert row_b.project_id == "B"

    def test_rejects_when_kek_unset(
        self, db_session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("PROVIDER_KEY_VAULT_KEK", raising=False)
        get_settings.cache_clear()
        with pytest.raises(VaultCipherUnavailable):
            store_provider_key(
                db_session, project_id="p", provider="openai",
                plaintext_key="sk-1234567890",
            )

    def test_label_stripped_and_empty_to_none(self, db_session) -> None:
        row = store_provider_key(
            db_session, project_id="p", provider="openai",
            plaintext_key="sk-aaa-12345",
            label="   ",
        )
        assert row.label is None


# ── service: revoke / get / list / active ───────────────────────────────────


class TestVaultReads:
    def test_revoke_idempotent(self, db_session) -> None:
        row = store_provider_key(
            db_session, project_id="p", provider="openai",
            plaintext_key="sk-1234567890",
        )
        revoked_once = revoke_provider_key(
            db_session, project_id="p", key_id=row.id
        )
        assert revoked_once is not None
        assert revoked_once.is_active is False
        revoked_twice = revoke_provider_key(
            db_session, project_id="p", key_id=row.id
        )
        # Same row, no errors
        assert revoked_twice is not None
        assert revoked_twice.id == row.id

    def test_revoke_missing_returns_none(self, db_session) -> None:
        assert revoke_provider_key(
            db_session, project_id="p", key_id="missing"
        ) is None

    def test_revoke_cross_tenant_returns_none(self, db_session) -> None:
        row = store_provider_key(
            db_session, project_id="A", provider="openai",
            plaintext_key="sk-aaa-12345",
        )
        assert revoke_provider_key(
            db_session, project_id="B", key_id=row.id
        ) is None

    def test_get_provider_key_tenant_scoped(self, db_session) -> None:
        row = store_provider_key(
            db_session, project_id="A", provider="openai",
            plaintext_key="sk-aaa-12345",
        )
        assert get_provider_key(
            db_session, project_id="A", key_id=row.id
        ).id == row.id
        assert get_provider_key(
            db_session, project_id="B", key_id=row.id
        ) is None

    def test_list_active_only_default(self, db_session) -> None:
        store_provider_key(
            db_session, project_id="p", provider="openai",
            plaintext_key="sk-aaa-12345",
        )
        # Rotate to a second key — the first becomes inactive
        store_provider_key(
            db_session, project_id="p", provider="openai",
            plaintext_key="sk-bbb-12345",
        )
        active = list_provider_keys(db_session, project_id="p")
        assert len(active) == 1
        assert active[0].is_active is True

    def test_list_include_revoked(self, db_session) -> None:
        store_provider_key(
            db_session, project_id="p", provider="openai",
            plaintext_key="sk-aaa-12345",
        )
        store_provider_key(
            db_session, project_id="p", provider="openai",
            plaintext_key="sk-bbb-12345",
        )
        all_rows = list_provider_keys(
            db_session, project_id="p", include_revoked=True
        )
        assert len(all_rows) == 2

    def test_list_filter_by_provider(self, db_session) -> None:
        store_provider_key(
            db_session, project_id="p", provider="openai",
            plaintext_key="sk-aaa-12345",
        )
        store_provider_key(
            db_session, project_id="p", provider="anthropic",
            plaintext_key="sk-ant-12345",
        )
        only_openai = list_provider_keys(
            db_session, project_id="p", provider="openai"
        )
        assert len(only_openai) == 1
        assert only_openai[0].provider == "openai"

    def test_list_invalid_provider_raises(self, db_session) -> None:
        with pytest.raises(InvalidProviderError):
            list_provider_keys(
                db_session, project_id="p", provider="bogus"
            )

    def test_list_tenant_isolation(self, db_session) -> None:
        store_provider_key(
            db_session, project_id="A", provider="openai",
            plaintext_key="sk-aaa-12345",
        )
        store_provider_key(
            db_session, project_id="B", provider="openai",
            plaintext_key="sk-bbb-12345",
        )
        a_rows = list_provider_keys(db_session, project_id="A")
        assert len(a_rows) == 1
        assert a_rows[0].project_id == "A"


# ── service: active key + decrypt-active (replay-worker contract) ────────────


class TestActiveKey:
    def test_get_active_returns_only_active(self, db_session) -> None:
        store_provider_key(
            db_session, project_id="p", provider="openai",
            plaintext_key="sk-old-12345",
        )
        store_provider_key(
            db_session, project_id="p", provider="openai",
            plaintext_key="sk-new-12345",
        )
        row = get_active_provider_key(
            db_session, project_id="p", provider="openai"
        )
        assert row is not None
        assert row.is_active is True
        assert row.key_last4 == "2345"  # both end in 2345; either is ok
        # But it must be the new one
        assert row.key_fingerprint == compute_fingerprint("sk-new-12345")

    def test_get_active_none_when_revoked(self, db_session) -> None:
        row = store_provider_key(
            db_session, project_id="p", provider="openai",
            plaintext_key="sk-1234567890",
        )
        revoke_provider_key(db_session, project_id="p", key_id=row.id)
        assert get_active_provider_key(
            db_session, project_id="p", provider="openai"
        ) is None

    def test_get_active_invalid_provider_returns_none(self, db_session) -> None:
        # Defensive — bogus provider from worker payload
        assert get_active_provider_key(
            db_session, project_id="p", provider="bogus"
        ) is None

    def test_decrypt_active_round_trip_and_marks_used(self, db_session) -> None:
        store_provider_key(
            db_session, project_id="p", provider="openai",
            plaintext_key="sk-1234567890",
        )
        plaintext = decrypt_active_provider_key(
            db_session, project_id="p", provider="openai"
        )
        assert plaintext == "sk-1234567890"
        # last_used_at should be set
        row = get_active_provider_key(
            db_session, project_id="p", provider="openai"
        )
        assert row is not None
        assert row.last_used_at is not None

    def test_decrypt_active_no_mark_when_disabled(self, db_session) -> None:
        store_provider_key(
            db_session, project_id="p", provider="openai",
            plaintext_key="sk-1234567890",
        )
        decrypt_active_provider_key(
            db_session, project_id="p", provider="openai", mark_used=False
        )
        row = get_active_provider_key(
            db_session, project_id="p", provider="openai"
        )
        assert row is not None
        assert row.last_used_at is None

    def test_decrypt_active_missing_returns_none(self, db_session) -> None:
        assert decrypt_active_provider_key(
            db_session, project_id="p", provider="openai"
        ) is None


# ── service: serializer never leaks plaintext or ciphertext ─────────────────


class TestSerializer:
    def test_no_plaintext_no_ciphertext(self, db_session) -> None:
        row = store_provider_key(
            db_session, project_id="p", provider="openai",
            plaintext_key="sk-secret-1234",
            label="prod",
        )
        wire = serialize_vault_row(row)
        # Required public fields
        assert wire["provider"] == "openai"
        assert wire["key_last4"] == "1234"
        assert len(wire["key_fingerprint"]) == 64
        assert wire["is_active"] is True
        # Critically — these MUST NOT appear
        assert "ciphertext" not in wire
        assert "plaintext" not in wire
        assert "plaintext_key" not in wire
        # And the plaintext literal must NOT appear in any string value
        assert all(
            "secret-1234" not in str(v) for v in wire.values()
        )


# ── routes: POST /v1/providers/keys ─────────────────────────────────────────


class TestCreateRoute:
    def test_201_happy_path(self, client: TestClient) -> None:
        response = client.post(
            "/v1/providers/keys",
            headers={PROJECT_HEADER: "proj-1"},
            json={
                "provider": "openai",
                "plaintext_key": "sk-proj-1234567890",
                "label": "prod",
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["provider"] == "openai"
        assert body["key_last4"] == "7890"
        assert body["is_active"] is True
        assert body["label"] == "prod"
        # No plaintext or ciphertext in response
        assert "plaintext_key" not in body
        assert "ciphertext" not in body
        assert "1234567890" not in str(body.get("key_fingerprint", ""))
        assert "sk-proj" not in str(body)

    def test_402_create_requires_provider_key_vault_entitlement(
        self, client: TestClient
    ) -> None:
        response = client.post(
            "/v1/providers/keys",
            headers={PROJECT_HEADER: "proj-free"},
            json={"provider": "openai", "plaintext_key": "sk-1234567890"},
        )
        assert response.status_code == 402
        detail = response.json()["detail"]
        assert detail["required_entitlement"] == "enterprise.provider_key_vault"

        session_factory = client._session_factory  # type: ignore[attr-defined]
        with session_factory() as session:
            count = session.execute(
                select(func.count())
                .select_from(ProviderKeyVault)
                .where(ProviderKeyVault.project_id == "proj-free")
            ).scalar_one()
        assert count == 0

    def test_422_bad_provider(self, client: TestClient) -> None:
        response = client.post(
            "/v1/providers/keys",
            headers={PROJECT_HEADER: "proj-1"},
            json={"provider": "bogus", "plaintext_key": "sk-1234567890"},
        )
        assert response.status_code == 422

    def test_422_short_plaintext_pydantic(self, client: TestClient) -> None:
        # Pydantic min_length=8 catches this before service layer.
        response = client.post(
            "/v1/providers/keys",
            headers={PROJECT_HEADER: "proj-1"},
            json={"provider": "openai", "plaintext_key": "sk-1"},
        )
        assert response.status_code == 422

    def test_409_duplicate_active(self, client: TestClient) -> None:
        client.post(
            "/v1/providers/keys",
            headers={PROJECT_HEADER: "proj-1"},
            json={"provider": "openai", "plaintext_key": "sk-1234567890"},
        )
        response = client.post(
            "/v1/providers/keys",
            headers={PROJECT_HEADER: "proj-1"},
            json={"provider": "openai", "plaintext_key": "sk-1234567890"},
        )
        assert response.status_code == 409

    def test_503_when_kek_missing(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("PROVIDER_KEY_VAULT_KEK", raising=False)
        get_settings.cache_clear()
        response = client.post(
            "/v1/providers/keys",
            headers={PROJECT_HEADER: "proj-1"},
            json={"provider": "openai", "plaintext_key": "sk-1234567890"},
        )
        assert response.status_code == 503

    def test_rotation_via_route(self, client: TestClient) -> None:
        first = client.post(
            "/v1/providers/keys",
            headers={PROJECT_HEADER: "proj-1"},
            json={"provider": "openai", "plaintext_key": "sk-old-12345"},
        ).json()
        second = client.post(
            "/v1/providers/keys",
            headers={PROJECT_HEADER: "proj-1"},
            json={"provider": "openai", "plaintext_key": "sk-new-12345"},
        ).json()
        # GET only active → just the new one
        active = client.get(
            "/v1/providers/keys", headers={PROJECT_HEADER: "proj-1"}
        ).json()
        assert active["total_in_page"] == 1
        assert active["items"][0]["id"] == second["id"]
        # GET include_revoked=true → both rows
        all_rows = client.get(
            "/v1/providers/keys?include_revoked=true",
            headers={PROJECT_HEADER: "proj-1"},
        ).json()
        ids = [r["id"] for r in all_rows["items"]]
        assert first["id"] in ids and second["id"] in ids


# ── routes: GET /v1/providers/keys ──────────────────────────────────────────


class TestListRoute:
    def test_empty(self, client: TestClient) -> None:
        response = client.get(
            "/v1/providers/keys", headers={PROJECT_HEADER: "proj-1"}
        )
        assert response.status_code == 200
        assert response.json()["items"] == []

    def test_member_api_key_cannot_list_provider_keys(
        self, client: TestClient
    ) -> None:
        api_key = _create_member_api_key(client)
        response = client.get("/v1/providers/keys", headers={"X-Api-Key": api_key})
        assert response.status_code == 403

    def test_filter_invalid_provider_422(self, client: TestClient) -> None:
        response = client.get(
            "/v1/providers/keys?provider=bogus",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 422

    def test_filter_by_provider(self, client: TestClient) -> None:
        client.post(
            "/v1/providers/keys",
            headers={PROJECT_HEADER: "proj-1"},
            json={"provider": "openai", "plaintext_key": "sk-aaa-12345"},
        )
        client.post(
            "/v1/providers/keys",
            headers={PROJECT_HEADER: "proj-1"},
            json={"provider": "anthropic", "plaintext_key": "sk-ant-12345"},
        )
        response = client.get(
            "/v1/providers/keys?provider=openai",
            headers={PROJECT_HEADER: "proj-1"},
        )
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["provider"] == "openai"

    def test_tenant_isolation(self, client: TestClient) -> None:
        client.post(
            "/v1/providers/keys",
            headers={PROJECT_HEADER: "proj-A"},
            json={"provider": "openai", "plaintext_key": "sk-a-12345"},
        )
        client.post(
            "/v1/providers/keys",
            headers={PROJECT_HEADER: "proj-B"},
            json={"provider": "openai", "plaintext_key": "sk-b-12345"},
        )
        a_rows = client.get(
            "/v1/providers/keys", headers={PROJECT_HEADER: "proj-A"}
        ).json()
        assert {r["project_id"] for r in a_rows["items"]} == {"proj-A"}


# ── routes: GET /v1/providers/keys/{id} ─────────────────────────────────────


class TestDetailRoute:
    def test_200_happy(self, client: TestClient) -> None:
        created = client.post(
            "/v1/providers/keys",
            headers={PROJECT_HEADER: "proj-1"},
            json={"provider": "openai", "plaintext_key": "sk-1234567890"},
        ).json()
        response = client.get(
            f"/v1/providers/keys/{created['id']}",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 200
        assert response.json()["id"] == created["id"]

    def test_404_missing(self, client: TestClient) -> None:
        response = client.get(
            "/v1/providers/keys/missing",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 404

    def test_404_cross_tenant(self, client: TestClient) -> None:
        created = client.post(
            "/v1/providers/keys",
            headers={PROJECT_HEADER: "proj-A"},
            json={"provider": "openai", "plaintext_key": "sk-1234567890"},
        ).json()
        response = client.get(
            f"/v1/providers/keys/{created['id']}",
            headers={PROJECT_HEADER: "proj-B"},
        )
        assert response.status_code == 404


# ── routes: DELETE /v1/providers/keys/{id} ──────────────────────────────────


class TestDeleteRoute:
    def test_revoke_200(self, client: TestClient) -> None:
        created = client.post(
            "/v1/providers/keys",
            headers={PROJECT_HEADER: "proj-1"},
            json={"provider": "openai", "plaintext_key": "sk-1234567890"},
        ).json()
        response = client.delete(
            f"/v1/providers/keys/{created['id']}",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["is_active"] is False
        assert body["revoked_at"] is not None

    def test_revoke_idempotent(self, client: TestClient) -> None:
        created = client.post(
            "/v1/providers/keys",
            headers={PROJECT_HEADER: "proj-1"},
            json={"provider": "openai", "plaintext_key": "sk-1234567890"},
        ).json()
        client.delete(
            f"/v1/providers/keys/{created['id']}",
            headers={PROJECT_HEADER: "proj-1"},
        )
        # Second DELETE returns the same 200 (idempotent)
        again = client.delete(
            f"/v1/providers/keys/{created['id']}",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert again.status_code == 200

    def test_revoke_404_missing(self, client: TestClient) -> None:
        response = client.delete(
            "/v1/providers/keys/missing",
            headers={PROJECT_HEADER: "proj-1"},
        )
        assert response.status_code == 404

    def test_revoke_404_cross_tenant(self, client: TestClient) -> None:
        created = client.post(
            "/v1/providers/keys",
            headers={PROJECT_HEADER: "proj-A"},
            json={"provider": "openai", "plaintext_key": "sk-1234567890"},
        ).json()
        response = client.delete(
            f"/v1/providers/keys/{created['id']}",
            headers={PROJECT_HEADER: "proj-B"},
        )
        assert response.status_code == 404


# ── invariants ──────────────────────────────────────────────────────────────


class TestInvariants:
    def test_valid_providers_match_migration_check_vocab(self) -> None:
        # Mirrors `_ALLOWED_PROVIDERS` in alembic/versions/0058_*.py.
        assert VALID_PROVIDERS == frozenset(
            {
                "openai", "anthropic", "gemini", "azure_openai", "vertex",
                "cohere", "mistral", "deepseek", "bedrock", "openrouter",
                "groq", "custom",
            }
        )
