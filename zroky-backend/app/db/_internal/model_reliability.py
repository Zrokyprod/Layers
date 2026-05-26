from __future__ import annotations

from app.db._internal.model_shared import *


class OutcomeEvent(Base):
    """One business-outcome event linked to a Zroky call.

    Customers emit these via:
      SDK:    zroky.outcome(call_id=..., type="refund_issued", amount_usd=49)
      API:    POST /v1/outcomes
      Webhooks: /v1/outcomes/webhooks/{stripe|zendesk|salesforce}

    ``call_id`` is nullable — some outcomes arrive before the SDK call_id
    is known or are attached post-facto.  Attribution queries LEFT JOIN to
    ``calls`` and ``diagnosis_jobs`` on ``call_id``.

    Idempotency: UNIQUE(project_id, idempotency_key) WHERE NOT NULL so
    webhook re-delivers and SDK retries never double-count.
    """

    __tablename__ = "outcome_events"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    call_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    outcome_type: Mapped[str] = mapped_column(String(64), nullable=False)
    amount_usd: Mapped[float] = mapped_column(
        Numeric(14, 4), nullable=False, server_default=text("0")
    )
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default=text("'USD'")
    )
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'api'")
    )
    external_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("amount_usd >= 0", name="ck_outcome_events_amount_positive"),
        CheckConstraint(
            "source IN ('sdk','api','stripe','zendesk','salesforce','csv')",
            name="ck_outcome_events_source",
        ),
        Index("ix_outcome_events_project_occurred", "project_id", "occurred_at"),
        Index("ix_outcome_events_call_id", "call_id"),
    )


class AblationJob(Base):
    """Root-cause analysis job for a single failing call.

    Phases: determinism probe → control group → axis scoring → synthesis.
    One job per (project_id, call_id) analysis trigger.
    """

    __tablename__ = "ablation_jobs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    call_id: Mapped[str] = mapped_column(String(64), nullable=False)
    diagnosis_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default=text("'pending'")
    )
    determinism_class: Mapped[str | None] = mapped_column(String(24), nullable=True)
    determinism_probe_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    control_group_size: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    root_cause_narrative: Mapped[str | None] = mapped_column(Text, nullable=True)
    fix_suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)
    fix_difficulty: Mapped[str | None] = mapped_column(String(8), nullable=True)
    synthesis_confidence: Mapped[float | None] = mapped_column(
        Numeric(4, 3), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )

    axes: Mapped[list["AblationAxis"]] = relationship(
        "AblationAxis",
        back_populates="job",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AblationAxis.confidence.desc()",
    )

    __table_args__ = (
        Index("ix_ablation_jobs_project_call", "project_id", "call_id"),
        Index("ix_ablation_jobs_project_created", "project_id", "created_at"),
    )


class AblationAxis(Base):
    """One variable axis tested in an ablation job.

    Holds the statistical evidence comparing the failing trace's axis value
    against the control group's distribution, plus the resulting confidence
    score (0-1) representing how much this axis explains the failure.
    """

    __tablename__ = "ablation_axes"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    ablation_job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ablation_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    axis_type: Mapped[str] = mapped_column(String(32), nullable=False)
    axis_label: Mapped[str] = mapped_column(String(255), nullable=False)
    failing_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(
        Numeric(5, 4), nullable=False, server_default=text("0")
    )
    evidence_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )

    job: Mapped["AblationJob"] = relationship("AblationJob", back_populates="axes")

    __table_args__ = (
        Index("ix_ablation_axes_job_id", "ablation_job_id"),
    )


class AgentReliabilityScore(Base):
    """Daily computed health score per (project, agent).

    health_score 0-100:
      fail_rate_score        (35%) + cost_efficiency_score (25%)
      + determinism_score    (25%) + regression_trend_score (15%)

    Idempotent: unique on (project_id, agent_name, score_date).
    """

    __tablename__ = "agent_reliability_scores"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(255), nullable=False)
    score_date: Mapped[datetime] = mapped_column(Date, nullable=False)

    health_score: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, server_default=text("0")
    )
    fail_rate: Mapped[float] = mapped_column(
        Numeric(6, 5), nullable=False, server_default=text("0")
    )
    fail_rate_score: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, server_default=text("0")
    )
    cost_efficiency_score: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, server_default=text("0")
    )
    determinism_score: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, server_default=text("0")
    )
    regression_trend_score: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, server_default=text("0")
    )
    call_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    avg_cost_usd: Mapped[float] = mapped_column(
        Numeric(18, 8), nullable=False, server_default=text("0")
    )
    p95_latency_ms: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    prev_week_fail_rate: Mapped[float | None] = mapped_column(
        Numeric(6, 5), nullable=True
    )
    determinism_breakdown_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    top_failure_axis: Mapped[str | None] = mapped_column(String(32), nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id", "agent_name", "score_date",
            name="ux_agent_reliability_project_agent_date",
        ),
        Index("ix_ars_project_date", "project_id", "score_date"),
        Index("ix_ars_project_agent", "project_id", "agent_name"),
    )


class ReliabilityRecommendation(Base):
    """Prioritised, actionable fix item auto-generated from ablation + cost data.

    Types: axis_causal | determinism_high | cost_spike | score_drop
    Priority: critical | high | medium | low
    Status:   open | acknowledged | resolved | dismissed | snoozed

    impact_score = determinism_confidence × avg_failure_cost × call_count
                   × (100 − health_score)
    Idempotent on (project_id, agent_name, recommendation_type, top_axis,
    generated_date).
    """

    __tablename__ = "reliability_recommendations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(255), nullable=False)
    recommendation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    priority: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'medium'")
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    fix_suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)
    fix_difficulty: Mapped[str | None] = mapped_column(String(16), nullable=True)
    top_axis: Mapped[str | None] = mapped_column(String(32), nullable=True)
    axis_confidence: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    estimated_monthly_impact_usd: Mapped[float | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    impact_score: Mapped[float] = mapped_column(
        Numeric(24, 6), nullable=False, server_default=text("0")
    )
    health_score_at_generation: Mapped[float | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    fail_rate_at_generation: Mapped[float | None] = mapped_column(
        Numeric(6, 5), nullable=True
    )
    call_count_window: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ablation_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'open'")
    )
    actioned_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actioned_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    snoozed_until: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    generated_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id", "agent_name", "recommendation_type", "top_axis", "generated_date",
            name="ux_rec_project_agent_type_axis_date",
        ),
        Index("ix_rec_project_status", "project_id", "status"),
        Index("ix_rec_project_agent", "project_id", "agent_name"),
        Index("ix_rec_impact_score", "project_id", "impact_score"),
    )
