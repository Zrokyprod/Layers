from __future__ import annotations

from datetime import date, datetime
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sqlalchemy import event

from app.db.base import Base
from app.db.encrypted_types import EncryptedSearchableString
from app.db.utc_datetime import UTCDateTime


def compute_email_hash(email: str | None) -> str | None:
    """Compute deterministic search hash for an email address."""
    if email is None:
        return None
    normalized = email.strip().lower()
    if not normalized:
        return None
    return EncryptedSearchableString().compute_search_hash(normalized)
