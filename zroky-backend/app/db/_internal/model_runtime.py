from __future__ import annotations

from app.db._internal.model_shared import *


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    monthly_cost_usd: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, server_default=text("0"))
    annual_cost_usd: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, server_default=text("0"))
    max_projects: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    max_members_per_project: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("5"))
    max_calls_per_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_tokens_per_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    features_json: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'[]'"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_subscription_plans_slug", "slug", unique=True),
        Index("ix_subscription_plans_active", "is_active"),
    )


class TenantSubscription(Base):
    __tablename__ = "tenant_subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    plan_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("subscription_plans.id", ondelete="RESTRICT"),
        nullable=False,
    )
    billing_interval: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'monthly'"))
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'active'"))
    trial_ends_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    current_period_start: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())
    current_period_end: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())
    canceled_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    seats: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    plan: Mapped[SubscriptionPlan] = relationship()
    project: Mapped[Project] = relationship(back_populates="subscription")

    __table_args__ = (
        Index("ix_tenant_subscriptions_tenant", "tenant_id", unique=True),
        Index("ix_tenant_subscriptions_plan", "plan_id"),
        Index("ix_tenant_subscriptions_status", "status"),
    )


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'general'"))
    priority: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'medium'"))
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'open'"))
    assigned_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list["SupportTicketMessage"]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="SupportTicketMessage.created_at.asc()",
    )

    __table_args__ = (
        Index("ix_support_tickets_tenant", "tenant_id"),
        Index("ix_support_tickets_user", "user_id"),
        Index("ix_support_tickets_status", "status"),
        Index("ix_support_tickets_created_at", "created_at"),
    )


class SupportTicketMessage(Base):
    """Legacy child message of SupportTicket.

    Renamed from `SupportMessage` (table `support_messages`) in migration
    0056 to free the canonical name for the new thread-message schema.
    Both class name and `__tablename__` are now `support_ticket_messages`.
    """

    __tablename__ = "support_ticket_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    ticket_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("support_tickets.id", ondelete="CASCADE"),
        nullable=False,
    )
    sender_type: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'user'"))
    sender_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_internal: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())

    ticket: Mapped["SupportTicket"] = relationship(back_populates="messages")

    __table_args__ = (
        Index("ix_support_ticket_messages_ticket", "ticket_id"),
        Index("ix_support_ticket_messages_created_at", "created_at"),
    )


class FeatureFlag(Base):
    __tablename__ = "feature_flags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled_globally: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    enabled_tenants_json: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'[]'"))
    disabled_tenants_json: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'[]'"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_feature_flags_key", "key", unique=True),
    )


class Issue(Base):
    __tablename__ = "issues"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    failure_code: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agent_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'open'"))
    severity: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'low'"))
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    blast_radius_usd: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False, server_default=text("0"))
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    sample_call_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sample_diagnosis_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sample_evidence_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_fix_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    resolution_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id", "failure_code", "prompt_fingerprint", "agent_name",
            name="ux_issues_group_key",
        ),
        Index("ix_issues_project_status", "project_id", "status"),
        Index("ix_issues_project_status_last_seen", "project_id", "status", "last_seen_at"),
        Index("ix_issues_project_failure_code", "project_id", "failure_code"),
        Index("ix_issues_project_agent", "project_id", "agent_name"),
        Index("ix_issues_project_created", "project_id", "created_at"),
    )


class EventCount(Base):
    """Per-tenant per-month event metering ledger.  Used for billing enforcement."""

    __tablename__ = "event_counts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    month: Mapped[str] = mapped_column(String(7), nullable=False, comment="YYYY-MM")
    event_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    last_event_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "month", name="ux_event_counts_tenant_month"),
        Index("ix_event_counts_tenant_month", "tenant_id", "month"),
    )


class ReplayJob(Base):
    """Replay jobs dispatched to the customer-hosted replay-worker."""

    __tablename__ = "replay_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    call_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("calls.id", ondelete="SET NULL"), nullable=True)
    pr_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("diagnosis_pull_requests.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'pending'"))
    candidate_fix_diff: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    artifact_signature: Mapped[str | None] = mapped_column(String(128), nullable=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("300"))
    claimed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    diff_metric: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    stdout_tail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    __table_args__ = (
        Index("ix_replay_jobs_tenant_status", "tenant_id", "status"),
        Index("ix_replay_jobs_tenant_created", "tenant_id", "created_at"),
        Index("ix_replay_jobs_status_lease", "status", "lease_expires_at"),
        Index("ix_replay_jobs_call_id", "call_id"),
        Index("ix_replay_jobs_pr_id", "pr_id"),
    )


class PolicyDocument(Base):
    __tablename__ = "policy_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_policy_documents_project_active", "project_id", "active"),
        Index("ix_policy_documents_project_created", "project_id", "created_at"),
    )


class RuntimePolicyDecision(Base):
    """Durable runtime policy decision and approval queue item.

    Agent SDKs/gateways call the runtime policy check before risky tool
    execution. Every decision is tenant-scoped and can be projected into the
    trace graph as policy evidence.
    """

    __tablename__ = "runtime_policy_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    call_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("calls.id", ondelete="SET NULL"),
        nullable=True,
    )
    agent_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    reasons_json: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'[]'"))
    request_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    intended_action_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    trace_context_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_hit_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_impact_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_scope_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        server_default=func.now(),
    )
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolution_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    consumed_by_decision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "decision IN ('allow', 'block', 'requires_approval')",
            name="ck_runtime_policy_decisions_decision",
        ),
        CheckConstraint(
            "status IN ('allowed', 'blocked', 'pending_approval', 'approved', 'rejected', 'expired')",
            name="ck_runtime_policy_decisions_status",
        ),
        Index("ix_runtime_policy_decisions_project_status_created", "project_id", "status", "created_at"),
        Index("ix_runtime_policy_decisions_project_trace_created", "project_id", "trace_id", "created_at"),
        Index("ix_runtime_policy_decisions_project_tool_created", "project_id", "tool_name", "created_at"),
        Index("ix_runtime_policy_decisions_project_scope", "project_id", "approval_scope_hash"),
        Index("ix_runtime_policy_decisions_project_created", "project_id", "created_at"),
    )


class RuntimePolicyAuditEvent(Base):
    __tablename__ = "runtime_policy_audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    decision_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("runtime_policy_decisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    before_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_runtime_policy_audit_project_decision_created", "project_id", "decision_id", "created_at"),
        Index("ix_runtime_policy_audit_project_created", "project_id", "created_at"),
    )
