from __future__ import annotations

from app.db._internal.model_shared import *


class IssueOccurrence(Base):
    """Per-trace evidence index for a grouped customer-facing issue."""

    __tablename__ = "issue_occurrences"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    issue_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("anomalies.id", ondelete="CASCADE"),
        nullable=False,
    )
    occurrence_key: Mapped[str] = mapped_column(String(160), nullable=False)
    call_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("calls.id", ondelete="SET NULL"),
        nullable=True,
    )
    diagnosis_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    failure_code: Mapped[str] = mapped_column(String(64), nullable=False)
    detector: Mapped[str] = mapped_column(String(32), nullable=False)
    grouping_signature: Mapped[str | None] = mapped_column(String(255), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    evidence_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "issue_id",
            "occurrence_key",
            name="ux_issue_occurrences_project_issue_key",
        ),
        Index("ix_issue_occurrences_project_issue_seen", "project_id", "issue_id", "occurred_at"),
        Index("ix_issue_occurrences_project_call", "project_id", "call_id"),
        Index("ix_issue_occurrences_project_trace", "project_id", "trace_id"),
        Index("ix_issue_occurrences_project_user", "project_id", "user_id"),
    )
