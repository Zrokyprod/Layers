"""Durable, owner-approved exceptions for proven low-risk action patterns."""
from __future__ import annotations

from app.db._internal.model_shared import *


class ApprovalAdaptationRule(Base):
    """A short-lived, exact-scope approval exemption backed by matched proof."""

    __tablename__ = "approval_adaptation_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action_type: Mapped[str] = mapped_column(String(160), nullable=False)
    operation_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    contract_key: Mapped[str] = mapped_column(String(160), nullable=False)
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_approved_count: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_matched_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'active'"))
    activated_by_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    revoked_by_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "operation_kind IN ('UPDATE')",
            name="ck_approval_adaptation_rules_operation_kind",
        ),
        CheckConstraint(
            "status IN ('active','revoked')",
            name="ck_approval_adaptation_rules_status",
        ),
        CheckConstraint(
            "evidence_approved_count >= 1",
            name="ck_approval_adaptation_rules_approved_count",
        ),
        CheckConstraint(
            "evidence_matched_count >= 1",
            name="ck_approval_adaptation_rules_matched_count",
        ),
        Index(
            "ix_approval_adaptation_rules_project_scope_status_expiry",
            "project_id",
            "scope_hash",
            "status",
            "expires_at",
        ),
        Index(
            "ix_approval_adaptation_rules_project_status_expiry",
            "project_id",
            "status",
            "expires_at",
        ),
    )
