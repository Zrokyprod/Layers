from __future__ import annotations

from app.db._internal.model_shared import *


class DiagnosisJob(Base):
    __tablename__ = "diagnosis_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    diagnosis_id: Mapped[str] = mapped_column(String(64), nullable=False)
    call_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("calls.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    agent_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prompt_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    call: Mapped["Call | None"] = relationship(back_populates="diagnosis_jobs")

    __table_args__ = (
        Index("ix_diagnosis_jobs_status", "status"),
        Index("ix_diagnosis_jobs_call_id", "call_id"),
        Index("ix_diagnosis_jobs_tenant_status", "tenant_id", "status"),
        Index("ix_diagnosis_jobs_tenant_call", "tenant_id", "call_id"),
        Index("ix_diagnosis_jobs_tenant_created", "tenant_id", "created_at"),
        Index("ix_diagnosis_jobs_tenant_prompt_created", "tenant_id", "prompt_fingerprint", "created_at"),
        Index(
            "ix_diagnosis_jobs_tenant_agent_prompt_created",
            "tenant_id",
            "agent_name",
            "prompt_fingerprint",
            "created_at",
        ),
        Index("ux_diagnosis_jobs_tenant_diagnosis", "tenant_id", "diagnosis_id", unique=True),
    )


class Call(Base):
    __tablename__ = "calls"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )
    agent_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    call_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider: Mapped[str] = mapped_column(String(120), nullable=False, server_default=text("'unknown'"))
    model: Mapped[str] = mapped_column(String(120), nullable=False, server_default=text("'unknown'"))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    reasoning_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    cost_total: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False, server_default=text("0"))
    reasoning_cost_total: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False, server_default=text("0"))
    cache_savings_total: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False, server_default=text("0"))
    pricing_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pricing_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pricing_last_updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    cost_currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'USD'"))
    token_unit: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'tokens'"))
    exchange_rate_usd_to_inr: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    exchange_rate_timestamp: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    exchange_rate_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cost_confidence: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'degraded'"))
    confidence_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    output_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_production: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    tool_lifecycle_summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    metadata_json: Mapped[str | None] = mapped_column("metadata", Text, nullable=True)

    diagnosis_jobs: Mapped[list[DiagnosisJob]] = relationship(back_populates="call")

    __table_args__ = (
        UniqueConstraint("project_id", "event_id", name="ux_calls_project_event"),
        Index("ix_calls_event_id", "event_id"),
        Index("ix_calls_project_created", "project_id", "created_at"),
        Index("ix_calls_project_is_production_created", "project_id", "is_production", "created_at"),
        Index("ix_calls_project_status", "project_id", "status"),
        Index("ix_calls_project_status_created", "project_id", "status", "created_at"),
        Index("ix_calls_project_provider", "project_id", "provider"),
        Index("ix_calls_project_provider_model_created", "project_id", "provider", "model", "created_at"),
        Index("ix_calls_project_agent_created", "project_id", "agent_name", "created_at"),
        Index("ix_calls_project_user_created", "project_id", "user_id", "created_at"),
        Index("ix_calls_project_call_type_created", "project_id", "call_type", "created_at"),
        Index("ix_calls_project_exchange_rate_timestamp", "project_id", "exchange_rate_timestamp"),
        Index("ix_calls_project_output_fingerprint_created", "project_id", "output_fingerprint", "created_at"),
    )


class TraceSpan(Base):
    __tablename__ = "trace_spans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(128), nullable=False)
    span_id: Mapped[str] = mapped_column(String(128), nullable=False)
    parent_span_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    call_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("calls.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    span_type: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'other'"))
    span_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    span_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    agent_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'completed'"))
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_total: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False, server_default=text("0"))
    input_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    retrieval_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    memory_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    handoff_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    versions_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    capture_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    masking_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pii_masked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
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
        UniqueConstraint("project_id", "span_id", name="ux_trace_spans_project_span"),
        UniqueConstraint("project_id", "event_id", name="ux_trace_spans_project_event"),
        Index("ix_trace_spans_project_trace", "project_id", "trace_id"),
        Index("ix_trace_spans_project_trace_index", "project_id", "trace_id", "span_index"),
        Index("ix_trace_spans_project_type_created", "project_id", "span_type", "created_at"),
        Index("ix_trace_spans_project_call", "project_id", "call_id"),
        Index("ix_trace_spans_project_parent", "project_id", "parent_span_id"),
    )


class TraceRun(Base):
    __tablename__ = "trace_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(128), nullable=False)
    root_span_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    root_call_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'completed'"))
    span_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    agent_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    agents_json: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'[]'"))
    providers_json: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'[]'"))
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    total_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_cost_usd: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False, server_default=text("0"))
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    has_failure: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    has_outcome: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    completeness_warnings_json: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'[]'"))
    capture_completeness_score: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    projection_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
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
        UniqueConstraint("project_id", "trace_id", name="ux_trace_runs_project_trace"),
        Index("ix_trace_runs_project_started", "project_id", "started_at"),
        Index("ix_trace_runs_project_status_started", "project_id", "status", "started_at"),
        Index("ix_trace_runs_project_failure_started", "project_id", "has_failure", "started_at"),
    )


class GatewayCaptureHealth(Base):
    __tablename__ = "gateway_capture_health"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    gateway_id: Mapped[str] = mapped_column(String(128), nullable=False)
    emit_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    durability_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    capture_status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'unknown'"))
    spool_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    spool_backlog: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    spool_bytes: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    spool_max_bytes: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    spool_reserved_bytes: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    spool_oldest_age_seconds: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    spool_high_watermark: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    emit_failures: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    enqueue_failures: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    flush_failures: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    flushed: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    loss_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    backpressure_rejections: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    heartbeat_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'{}'"))
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
        UniqueConstraint("project_id", "gateway_id", name="ux_gateway_capture_health_project_gateway"),
        Index("ix_gateway_capture_health_project_status", "project_id", "capture_status"),
        Index("ix_gateway_capture_health_project_heartbeat", "project_id", "heartbeat_at"),
    )


class DiagnosisFeedback(Base):
    __tablename__ = "diagnosis_feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    diagnosis_id: Mapped[str] = mapped_column(String(64), nullable=False)
    was_helpful: Mapped[bool] = mapped_column(Boolean, nullable=False)
    developer_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_diagnosis_feedback_tenant_diagnosis", "tenant_id", "diagnosis_id"),
        Index("ix_diagnosis_feedback_diagnosis_id", "diagnosis_id"),
        Index("ix_diagnosis_feedback_tenant_created", "tenant_id", "created_at"),
        Index("ix_diagnosis_feedback_created_at", "created_at"),
    )


class DiagnosisShareToken(Base):
    __tablename__ = "diagnosis_share_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    diagnosis_id: Mapped[str] = mapped_column(String(64), nullable=False)
    token_prefix: Mapped[str] = mapped_column(String(24), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
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
        Index("ux_diagnosis_share_tokens_hash", "token_hash", unique=True),
        Index("ix_diagnosis_share_tokens_tenant_diagnosis", "tenant_id", "diagnosis_id"),
        Index("ix_diagnosis_share_tokens_tenant_expires", "tenant_id", "expires_at"),
        Index("ix_diagnosis_share_tokens_tenant_revoked", "tenant_id", "revoked_at"),
        Index("ix_diagnosis_share_tokens_expires", "expires_at"),
    )


class DiagnosisFixWatch(Base):
    __tablename__ = "diagnosis_fix_watches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    diagnosis_id: Mapped[str] = mapped_column(String(64), nullable=False)
    target_categories_json: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'[]'"))
    resolved_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    watch_expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    created_by_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )


class DiagnosisUiState(Base):
    __tablename__ = "diagnosis_ui_state"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    diagnosis_id: Mapped[str] = mapped_column(String(64), nullable=False)
    assigned_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    snoozed_until: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    dismissed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
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
        UniqueConstraint("tenant_id", "diagnosis_id", name="ux_diagnosis_ui_state_tenant_diagnosis"),
        Index("ix_diagnosis_ui_state_tenant_updated", "tenant_id", "updated_at"),
        Index("ix_diagnosis_ui_state_diagnosis_id", "diagnosis_id"),
    )


class DiagnosisPullRequest(Base):
    __tablename__ = "diagnosis_pull_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    diagnosis_id: Mapped[str] = mapped_column(String(64), nullable=False)
    fix_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    repository_owner: Mapped[str] = mapped_column(String(255), nullable=False)
    repository_name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    branch_name: Mapped[str] = mapped_column(String(255), nullable=False)
    pull_request_number: Mapped[int] = mapped_column(Integer, nullable=False)
    pull_request_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    pull_request_title: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    merge_commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    merged_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_ci_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_ci_conclusion: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_ci_completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    generated_patch: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    replay_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    replay_status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'pending'"))
    replay_completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    judge_verdict: Mapped[str | None] = mapped_column(String(16), nullable=True)
    judge_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    judge_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    judge_ran_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
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
        UniqueConstraint("tenant_id", "diagnosis_id", "branch_name", name="ux_diag_pr_tenant_diag_branch"),
        UniqueConstraint("tenant_id", "diagnosis_id", "pull_request_url", name="ux_diag_pr_tenant_diag_url"),
        Index("ix_diag_pr_diagnosis_id", "diagnosis_id"),
        Index("ix_diag_pr_tenant_diagnosis", "tenant_id", "diagnosis_id"),
        Index("ix_diag_pr_tenant_created", "tenant_id", "created_at"),
        Index("ix_diag_pr_tenant_fix", "tenant_id", "fix_id"),
        Index("ix_diag_pr_repo_number", "repository_owner", "repository_name", "pull_request_number"),
        Index("ix_diag_pr_repo_branch", "repository_owner", "repository_name", "branch_name"),
    )


class FixEvent(Base):
    __tablename__ = "fix_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    diagnosis_id: Mapped[str] = mapped_column(String(64), nullable=False)
    fix_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'dashboard'"))
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    timestamp_bucket: Mapped[str] = mapped_column(String(16), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )
    metadata_json: Mapped[str] = mapped_column("metadata", Text, nullable=False, server_default=text("'{}'"))

    __table_args__ = (
        CheckConstraint(
            "event_type in ('shown','copied','pr_generated','pr_merged','applied','resolved','ignored','regressed')",
            name="ck_fix_events_event_type",
        ),
        UniqueConstraint("project_id", "idempotency_key", name="ux_fix_events_project_idempotency"),
        UniqueConstraint(
            "project_id",
            "fix_id",
            "event_type",
            "timestamp_bucket",
            name="ux_fix_events_project_fix_type_bucket",
        ),
        Index("ix_fix_events_idempotency_key", "idempotency_key"),
        Index("ix_fix_events_project_timestamp", "project_id", "timestamp"),
        Index("ix_fix_events_project_diagnosis", "project_id", "diagnosis_id"),
        Index("ix_fix_events_project_fix", "project_id", "fix_id"),
        Index("ix_fix_events_project_type_timestamp", "project_id", "event_type", "timestamp"),
    )


class FixEmbedding(Base):
    """Vector embeddings for fixes to enable semantic similarity search."""

    __tablename__ = "fix_embeddings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    diagnosis_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    fix_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    # Embedding text: concatenation of diagnosis type, error message, code snippet
    embedding_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Vector embedding (1536 dimensions for OpenAI text-embedding-3-small)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    # Model used to generate embedding (e.g., "text-embedding-3-small")
    embedding_model: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'text-embedding-3-small'"))
    # Metadata for the fix
    diagnosis_type: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0.0"))
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
        Index("ix_fix_embeddings_project_diagnosis", "project_id", "diagnosis_id"),
        Index("ix_fix_embeddings_project_fix", "project_id", "fix_id"),
        Index("ix_fix_embeddings_diagnosis_type", "project_id", "diagnosis_type"),
        UniqueConstraint("project_id", "fix_id", name="ux_fix_embeddings_project_fix"),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    diagnosis_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_audit_logs_tenant_created", "tenant_id", "created_at"),
        Index("ix_audit_logs_tenant_action_created", "tenant_id", "action", "created_at"),
        Index("ix_audit_logs_diagnosis_id", "diagnosis_id"),
        Index("ix_audit_logs_tenant_diagnosis_created", "tenant_id", "diagnosis_id", "created_at"),
    )
