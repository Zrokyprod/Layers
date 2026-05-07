"""Tests for column-level PII encryption (User.email)."""
import os

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select, text

# Configure encryption key BEFORE importing app modules
_TEST_KEY = Fernet.generate_key().decode("utf-8")
os.environ.setdefault("DATABASE_URL", "sqlite:///./.data/test_pii_encryption.db")
os.environ["PII_ENCRYPTION_KEY"] = _TEST_KEY
os.environ["PII_HMAC_KEY"] = "test-hmac-key-for-pii-encryption"
os.environ.setdefault("AUTH_JWT_SECRET", "test-secret-key-for-pii-tests")
os.environ.setdefault("ALLOW_PROJECT_HEADER_CONTEXT", "true")
os.environ.setdefault("REQUIRE_PROVISIONING_TOKEN", "false")

# Clear settings cache to pick up env changes
from app.core.config import get_settings  # noqa: E402
get_settings.cache_clear()

from app.db.base import Base  # noqa: E402
from app.db.models import User, compute_email_hash  # noqa: E402
from app.db.encrypted_types import EncryptedSearchableString  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def session():
    with SessionLocal() as s:
        yield s
        s.rollback()


# ---------------------------------------------------------------------------
# EncryptedSearchableString tests
# ---------------------------------------------------------------------------

def test_email_is_encrypted_at_rest(session):
    """Email value stored in DB should not match plaintext."""
    plaintext_email = "alice@example.com"
    user = User(subject=f"email:{plaintext_email}", email=plaintext_email)
    session.add(user)
    session.commit()
    user_id = user.id

    # Read raw column value bypassing the type decorator
    raw = session.execute(
        text("SELECT email FROM users WHERE id = :id"), {"id": user_id}
    ).scalar()
    assert raw is not None
    assert plaintext_email not in raw, "Plaintext email should not appear in raw DB value"


def test_email_decrypts_on_read(session):
    """Email value should round-trip through encryption transparently."""
    plaintext_email = "bob@example.com"
    user = User(subject=f"email:{plaintext_email}", email=plaintext_email)
    session.add(user)
    session.commit()

    # Reload via ORM
    session.expire_all()
    loaded = session.execute(select(User).where(User.id == user.id)).scalar_one()
    assert loaded.email == plaintext_email


def test_email_hash_is_populated_automatically(session):
    """Setting email should auto-populate email_hash via event listener."""
    user = User(subject="email:carol@example.com", email="carol@example.com")
    session.add(user)
    session.commit()

    assert user.email_hash is not None
    assert len(user.email_hash) == 64  # SHA-256 hex
    assert user.email_hash == compute_email_hash("carol@example.com")


def test_email_hash_lookup_works(session):
    """Should be able to find user by email_hash."""
    email = "dave@example.com"
    user = User(subject=f"email:{email}", email=email)
    session.add(user)
    session.commit()

    found = session.execute(
        select(User).where(User.email_hash == compute_email_hash(email))
    ).scalar_one_or_none()
    assert found is not None
    assert found.id == user.id


def test_email_hash_is_case_insensitive(session):
    """Email hash should be normalized to lowercase."""
    user = User(subject="email:eve@example.com", email="Eve@Example.COM")
    session.add(user)
    session.commit()

    # Lookup with different case should match
    found = session.execute(
        select(User).where(User.email_hash == compute_email_hash("eve@example.com"))
    ).scalar_one_or_none()
    assert found is not None
    assert found.id == user.id


def test_email_hash_is_deterministic():
    """Same email should always produce same hash."""
    h1 = compute_email_hash("user@example.com")
    h2 = compute_email_hash("user@example.com")
    assert h1 == h2


def test_email_hash_differs_for_different_emails():
    """Different emails should produce different hashes."""
    h1 = compute_email_hash("user1@example.com")
    h2 = compute_email_hash("user2@example.com")
    assert h1 != h2


def test_email_none_handled(session):
    """User with no email should have no email_hash."""
    user = User(subject="github:12345", email=None)
    session.add(user)
    session.commit()

    assert user.email is None
    assert user.email_hash is None


def test_email_update_resyncs_hash(session):
    """Updating email should update email_hash."""
    user = User(subject="email:fred@example.com", email="fred@example.com")
    session.add(user)
    session.commit()
    
    original_hash = user.email_hash

    user.email = "newfred@example.com"
    session.commit()

    assert user.email_hash != original_hash
    assert user.email_hash == compute_email_hash("newfred@example.com")


# ---------------------------------------------------------------------------
# Encryption type unit tests
# ---------------------------------------------------------------------------

def test_searchable_compute_search_hash():
    """compute_search_hash should produce deterministic 64-char hex."""
    t = EncryptedSearchableString()
    h = t.compute_search_hash("test@example.com")
    assert isinstance(h, str)
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)
