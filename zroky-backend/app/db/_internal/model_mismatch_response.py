from __future__ import annotations

from app.db._internal.model_shared import *


class OutcomeMismatchResponse(Base):
    """Owner-facing response case for a confirmed SOR mismatch.

    The response is separate from the immutable reconciliation observation. It
    tracks the human response and a non-executing compensating-action
    suggestion; it can never perform a rollback itself.
    """

    __tablename__ = "outcome_mismatch_responses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    reconciliation_check_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("outcome_reconciliation_checks.id", ondelete="CASCADE"),
        nullable=False,
    )
    action_intent_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("action_intents.id", ondelete="SET NULL"),
        nullable=True,
    )
    alert_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("project_alerts.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'OPEN'"))
    resolution_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    remediation_json: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'{}'"))
    acknowledged_by_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    resolved_by_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "reconciliation_check_id",
            name="ux_outcome_mismatch_responses_project_check",
        ),
        CheckConstraint(
            "status IN ('OPEN','ACKNOWLEDGED','RESOLVED')",
            name="ck_outcome_mismatch_responses_status",
        ),
        CheckConstraint(
            "resolution_code IS NULL OR resolution_code IN ('confirmed_mismatch','expected_change','false_positive','unresolved')",
            name="ck_outcome_mismatch_responses_resolution_code",
        ),
        Index("ix_outcome_mismatch_responses_project_status_created", "project_id", "status", "created_at"),
        Index("ix_outcome_mismatch_responses_project_action", "project_id", "action_intent_id"),
    )
