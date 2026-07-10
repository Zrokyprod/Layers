from __future__ import annotations

from app.db._internal.model_shared import *


class OutcomeEvent(Base):
    """One business-outcome event linked to a Zroky call.

    Customers emit these via:
      SDK:    zroky.outcome(call_id=..., type="refund_issued", amount_usd=49)
      API:    POST /v1/outcomes
      Webhooks: /v1/outcomes/webhooks/{zendesk|salesforce}

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
            "source IN ('sdk','api','zendesk','salesforce','csv')",
            name="ck_outcome_events_source",
        ),
        Index("ix_outcome_events_project_occurred", "project_id", "occurred_at"),
        Index("ix_outcome_events_call_id", "call_id"),
    )


class OutcomeReconciliationCheck(Base):
    """Claimed-vs-actual outcome check against a system of record."""

    __tablename__ = "outcome_reconciliation_checks"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    call_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("calls.id", ondelete="SET NULL"),
        nullable=True,
    )
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    runtime_policy_decision_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("runtime_policy_decisions.id", ondelete="SET NULL"),
        nullable=True,
    )
    action_intent_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("action_intents.id", ondelete="SET NULL"),
        nullable=True,
    )
    action_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    connector_type: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("'api_record'")
    )
    system_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    verdict: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    proof_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    proof_reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    proof_observed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    proof_deadline_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    proof_next_check_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    amount_usd: Mapped[float | None] = mapped_column(Numeric(14, 4), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    claimed_json: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'{}'"))
    actual_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    comparison_json: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'{}'"))
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "verdict IN ('matched','mismatched','not_verified')",
            name="ck_outcome_reconciliation_verdict",
        ),
        CheckConstraint(
            "proof_status IS NULL OR proof_status IN ('matched','mismatched','pending','unverifiable','partial','cancelled')",
            name="ck_outcome_reconciliation_proof_status",
        ),
        UniqueConstraint(
            "project_id",
            "idempotency_key",
            name="ux_outcome_reconciliation_project_idempotency",
        ),
        Index("ix_outcome_reconciliation_project_checked", "project_id", "checked_at"),
        Index("ix_outcome_reconciliation_project_verdict_checked", "project_id", "verdict", "checked_at"),
        Index("ix_outcome_reconciliation_project_proof_checked", "project_id", "proof_status", "checked_at"),
        Index("ix_outcome_reconciliation_pending_reverify", "project_id", "proof_status", "proof_next_check_at"),
        Index("ix_outcome_reconciliation_call", "call_id"),
        Index("ix_outcome_reconciliation_trace", "project_id", "trace_id"),
        Index("ix_outcome_reconciliation_action", "project_id", "action_intent_id"),
    )
class SourceMutationRecord(Base):
    """System-of-record mutation observed from webhooks/audit logs for bypass detection."""

    __tablename__ = "source_mutation_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    mutation_id: Mapped[str] = mapped_column(String(255), nullable=False)
    action_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    system_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actor_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    zroky_action_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("action_intents.id", ondelete="SET NULL"),
        nullable=True,
    )
    action_receipt_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("action_receipts.id", ondelete="SET NULL"),
        nullable=True,
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    classification: Mapped[str] = mapped_column(String(32), nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'{}'"))
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "classification IN ('matched_receipt','authorized_external','legacy_path','unmanaged_agent_action','policy_bypass','unknown_actor')",
            name="ck_source_mutation_records_classification",
        ),
        UniqueConstraint(
            "project_id",
            "source_system",
            "mutation_id",
            name="ux_source_mutation_project_source_mutation",
        ),
        Index("ix_source_mutation_project_classification", "project_id", "classification", "occurred_at"),
        Index("ix_source_mutation_project_resource", "project_id", "resource_type", "resource_id"),
        Index("ix_source_mutation_project_action", "project_id", "zroky_action_id"),
        Index("ix_source_mutation_project_receipt", "project_id", "action_receipt_id"),
        Index("ix_source_mutation_project_occurred", "project_id", "occurred_at"),
    )


class ConnectorCredential(Base):
    """Versioned, tenant-scoped connector credential metadata.

    Secrets live here only when the customer explicitly chooses
    ``zroky_managed`` custody. Customer-managed and private-runner
    credentials retain an opaque reference only; the reference is never
    returned from the API or copied to audit metadata.
    """

    __tablename__ = "connector_credentials"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    credential_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    custody_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    secret_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    key_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    key_last4: Mapped[str | None] = mapped_column(String(8), nullable=True)
    kms_key_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    scopes_json: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'[]'")
    )
    allowed_connector_types_json: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'[]'")
    )
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    rotation_due_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime, nullable=True
    )
    supersedes_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("connector_credentials.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"), default=True
    )
    created_by_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
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
        CheckConstraint(
            "credential_kind IN ('bearer_token','oauth_refresh_token','database_url')",
            name="ck_connector_credentials_kind",
        ),
        CheckConstraint(
            "custody_mode IN ('zroky_managed','customer_managed','private_runner')",
            name="ck_connector_credentials_custody",
        ),
        CheckConstraint(
            "(custody_mode = 'zroky_managed' AND ciphertext IS NOT NULL AND secret_ref IS NULL) "
            "OR (custody_mode IN ('customer_managed','private_runner') "
            "AND ciphertext IS NULL AND secret_ref IS NOT NULL)",
            name="ck_connector_credentials_custody_payload",
        ),
        UniqueConstraint(
            "project_id", "name", "version", name="ux_connector_credentials_project_name_version"
        ),
        Index(
            "ix_connector_credentials_project_name_active",
            "project_id",
            "name",
            "is_active",
        ),
        Index(
            "ix_connector_credentials_project_rotation_due",
            "project_id",
            "rotation_due_at",
        ),
    )


class ConnectorCredentialAuditEvent(Base):
    """Append-only credential lifecycle audit; secret material is excluded."""

    __tablename__ = "connector_credential_audit_events"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    credential_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("connector_credentials.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'{}'")
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "event_type IN ('created','rotated','bound','revoked','used')",
            name="ck_connector_credential_audit_event_type",
        ),
        Index(
            "ix_connector_credential_audit_project_created",
            "project_id",
            "created_at",
        ),
        Index(
            "ix_connector_credential_audit_credential_created",
            "credential_id",
            "created_at",
        ),
    )


class SystemOfRecordConnectorConfig(Base):
    """Tenant-scoped connector config for outcome verification."""

    __tablename__ = "system_of_record_connector_configs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    connector_type: Mapped[str] = mapped_column(String(64), nullable=False)
    base_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    path_template: Mapped[str] = mapped_column(
        String(512), nullable=False, server_default=text("'/refunds/{refund_id}'")
    )
    record_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    query_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    read_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    bearer_token_ciphertext: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True
    )
    bearer_token_fingerprint: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    bearer_token_last4: Mapped[str | None] = mapped_column(String(8), nullable=True)
    oauth_refresh_token_ciphertext: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True
    )
    oauth_refresh_token_fingerprint: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    oauth_refresh_token_last4: Mapped[str | None] = mapped_column(
        String(8), nullable=True
    )
    database_url_ciphertext: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True
    )
    database_url_fingerprint: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    database_url_last4: Mapped[str | None] = mapped_column(String(8), nullable=True)
    bearer_credential_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("connector_credentials.id", ondelete="SET NULL"), nullable=True
    )
    oauth_refresh_credential_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("connector_credentials.id", ondelete="SET NULL"), nullable=True
    )
    database_url_credential_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("connector_credentials.id", ondelete="SET NULL"), nullable=True
    )
    kms_key_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_by_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_by_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
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
        CheckConstraint(
            "connector_type IN ('ledger_refund_api','customer_record_api','generic_rest_api','postgres_read','hubspot_crm','zendesk_ticket','salesforce_crm','zoho_crm','jira_issue','stripe_refund','stripe_payment','razorpay_refund','netsuite_finance','shopify_admin')",
            name="ck_sor_connector_type",
        ),
        UniqueConstraint(
            "project_id",
            "connector_type",
            name="ux_sor_connector_project_type",
        ),
        Index(
            "ix_sor_connector_project_type_active",
            "project_id",
            "connector_type",
            "is_active",
        ),
        Index("ix_sor_connector_project_updated", "project_id", "updated_at"),
        Index("ix_sor_connector_bearer_credential", "bearer_credential_id"),
        Index("ix_sor_connector_oauth_credential", "oauth_refresh_credential_id"),
        Index("ix_sor_connector_database_credential", "database_url_credential_id"),
    )


class SourceMutationPollState(Base):
    """Per-connector cursor for active source-of-record bypass monitoring."""

    __tablename__ = "source_mutation_poll_states"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    connector_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    cursor_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_polled_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
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
            "connector_type",
            name="ux_source_mutation_poll_project_connector",
        ),
        Index(
            "ix_source_mutation_poll_project_connector",
            "project_id",
            "connector_type",
        ),
        Index("ix_source_mutation_poll_last_polled", "last_polled_at"),
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
