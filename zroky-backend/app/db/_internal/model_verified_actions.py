from __future__ import annotations

from app.db._internal.model_shared import *


class ActionContractVersion(Base):
    """Immutable typed contract for one protected action family/version."""

    __tablename__ = "action_contract_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    contract_key: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    action_type: Mapped[str] = mapped_column(String(160), nullable=False)
    operation_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    domain_family: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_digest: Mapped[str] = mapped_column(String(80), nullable=False)
    schema_json: Mapped[str] = mapped_column(Text, nullable=False)
    risk_class: Mapped[str] = mapped_column(String(8), nullable=False, server_default=text("'R2'"))
    verification_profile_json: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'{}'"))
    connector_family: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'active'"))
    created_by_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "contract_key",
            "version",
            name="ux_action_contract_versions_project_key_version",
        ),
        CheckConstraint(
            "operation_kind IN ('READ_SENSITIVE','EXPORT','CREATE','UPDATE','DELETE','TRANSFER','SEND','APPROVE','GRANT','EXECUTE','DEPLOY','ROTATE_OR_REVOKE')",
            name="ck_action_contract_versions_operation_kind",
        ),
        CheckConstraint(
            "risk_class IN ('R0','R1','R2','R3','R4')",
            name="ck_action_contract_versions_risk_class",
        ),
        CheckConstraint(
            "status IN ('active','retired')",
            name="ck_action_contract_versions_status",
        ),
        Index("ix_action_contract_versions_project_action", "project_id", "action_type"),
        Index("ix_action_contract_versions_project_status", "project_id", "status"),
    )


class ActionIntent(Base):
    """Concrete immutable protected action proposed by an agent/application."""

    __tablename__ = "action_intents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
    )
    contract_version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("action_contract_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    contract_key: Mapped[str] = mapped_column(String(160), nullable=False)
    contract_version: Mapped[str] = mapped_column(String(32), nullable=False)
    action_type: Mapped[str] = mapped_column(String(160), nullable=False)
    operation_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    environment: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'production'"))
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    intent_digest: Mapped[str] = mapped_column(String(80), nullable=False)
    canonical_intent_json: Mapped[str] = mapped_column(Text, nullable=False)
    principal_json: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'{}'"))
    actor_chain_json: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'[]'"))
    purpose_json: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'{}'"))
    resource_json: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'{}'"))
    parameters_json: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'{}'"))
    execution_request_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_profile: Mapped[str | None] = mapped_column(String(160), nullable=True)
    trace_context_json: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'{}'"))
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'validated'"))
    proof_status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'not_started'"))
    receipt_status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'missing'"))
    runtime_policy_decision_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("runtime_policy_decisions.id", ondelete="SET NULL"),
        nullable=True,
    )
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    authorized_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "idempotency_key",
            name="ux_action_intents_project_idempotency",
        ),
        CheckConstraint(
            "status IN ('validated','deciding','denied','approval_pending','authorized','expired')",
            name="ck_action_intents_status",
        ),
        CheckConstraint(
            "proof_status IN ('not_started','pending','matched','mismatched','not_verified')",
            name="ck_action_intents_proof_status",
        ),
        CheckConstraint(
            "receipt_status IN ('missing','pending','generated','failed')",
            name="ck_action_intents_receipt_status",
        ),
        Index("ix_action_intents_project_created", "project_id", "created_at"),
        Index("ix_action_intents_project_digest", "project_id", "intent_digest"),
        Index("ix_action_intents_project_policy_decision", "project_id", "runtime_policy_decision_id"),
        Index("ix_action_intents_project_status", "project_id", "status", "created_at"),
        Index("ix_action_intents_project_proof", "project_id", "proof_status", "created_at"),
        Index("ix_action_intents_project_agent_created", "project_id", "agent_id", "created_at"),
    )


class ActionRunner(Base):
    """Registered protected-action runner that executes without exposing secrets to agents."""

    __tablename__ = "action_runners"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    runner_type: Mapped[str] = mapped_column(String(32), nullable=False)
    environment: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'production'"))
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'registered'"))
    supported_operation_kinds_json: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'[]'"))
    credential_scope_json: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'{}'"))
    heartbeat_payload_json: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'{}'"))
    capability_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    registered_by_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
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
            "name",
            "environment",
            name="ux_action_runners_project_name_environment",
        ),
        CheckConstraint(
            "runner_type IN ('managed_sandbox','customer_hosted')",
            name="ck_action_runners_runner_type",
        ),
        CheckConstraint(
            "status IN ('registered','online','degraded','offline','disabled')",
            name="ck_action_runners_status",
        ),
        Index("ix_action_runners_project_status", "project_id", "status"),
        Index("ix_action_runners_project_environment", "project_id", "environment"),
    )


class ActionExecutionAttempt(Base):
    """Plan-before-execute record for one protected action execution attempt."""

    __tablename__ = "action_execution_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action_intent_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("action_intents.id", ondelete="CASCADE"),
        nullable=False,
    )
    runner_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("action_runners.id", ondelete="RESTRICT"),
        nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'planned'"))
    credential_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    plan_digest: Mapped[str] = mapped_column(String(80), nullable=False)
    plan_json: Mapped[str] = mapped_column(Text, nullable=False)
    result_summary_json: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'{}'"))
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    protected_credential_returned: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    requested_by_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
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
            "action_intent_id",
            "idempotency_key",
            name="ux_action_execution_attempts_project_intent_idempotency",
        ),
        CheckConstraint(
            "status IN ('planned','dispatched','running','succeeded','failed','ambiguous','cancelled')",
            name="ck_action_execution_attempts_status",
        ),
        CheckConstraint(
            "protected_credential_returned = false",
            name="ck_action_execution_attempts_no_returned_credential",
        ),
        Index("ix_action_execution_attempts_project_created", "project_id", "created_at"),
        Index("ix_action_execution_attempts_project_intent", "project_id", "action_intent_id"),
        Index("ix_action_execution_attempts_project_runner", "project_id", "runner_id"),
        Index("ix_action_execution_attempts_project_status", "project_id", "status", "created_at"),
    )


class PrivateRunnerVerificationJob(Base):
    """Read-only SOR verification work claimed by one customer-hosted runner."""

    __tablename__ = "private_runner_verification_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action_intent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("action_intents.id", ondelete="CASCADE"), nullable=False
    )
    execution_attempt_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("action_execution_attempts.id", ondelete="CASCADE"), nullable=False
    )
    runner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("action_runners.id", ondelete="RESTRICT"), nullable=False
    )
    connector_type: Mapped[str] = mapped_column(String(64), nullable=False)
    credential_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'queued'"))
    plan_json: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'{}'"))
    context_json: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'{}'"))
    result_json: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'{}'"))
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "execution_attempt_id",
            name="ux_private_runner_verify_project_attempt",
        ),
        CheckConstraint(
            "status IN ('queued','claimed','succeeded','failed','cancelled')",
            name="ck_private_runner_verify_status",
        ),
        Index(
            "ix_private_runner_verify_project_runner_status",
            "project_id",
            "runner_id",
            "status",
            "created_at",
        ),
    )


class VerificationDispatchState(Base):
    """Durable round-robin state for post-execution verification work.

    This state is deliberately in Postgres rather than Redis: Redis can help
    coordinate a connector fetch, but it must never become the source of truth
    for whether a protected action still needs a receipt or proof.
    """

    __tablename__ = "verification_dispatch_states"

    project_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_dispatched_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    dispatch_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index("ix_verification_dispatch_states_last_dispatched", "last_dispatched_at"),
    )


class ActionTimelineEvent(Base):
    """Append-only lifecycle event for a protected action intent."""

    __tablename__ = "action_timeline_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action_intent_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("action_intents.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_digest: Mapped[str] = mapped_column(String(80), nullable=False)
    event_payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("ix_action_timeline_events_project_intent_created", "project_id", "action_intent_id", "created_at"),
        Index("ix_action_timeline_events_project_type_created", "project_id", "event_type", "created_at"),
    )


class ActionReceipt(Base):
    """Signed machine-verifiable receipt for one protected action."""

    __tablename__ = "action_receipts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action_intent_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("action_intents.id", ondelete="CASCADE"),
        nullable=False,
    )
    receipt_digest: Mapped[str] = mapped_column(String(80), nullable=False)
    receipt_json: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
    signature_algorithm: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'Ed25519'"))
    signature: Mapped[str] = mapped_column(String(128), nullable=False)
    signing_key_id: Mapped[str] = mapped_column(String(128), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("project_id", "action_intent_id", name="ux_action_receipts_project_intent"),
        Index("ix_action_receipts_project_created", "project_id", "created_at"),
        Index("ix_action_receipts_project_digest", "project_id", "receipt_digest"),
    )


class ActionPostExecutionJob(Base):
    """Transactional outbox job for backend-owned verification and receipt generation."""

    __tablename__ = "action_post_execution_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action_intent_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("action_intents.id", ondelete="CASCADE"),
        nullable=False,
    )
    execution_attempt_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("action_execution_attempts.id", ondelete="CASCADE"),
        nullable=False,
    )
    job_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'pending'"))
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'{}'"))
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("3"))
    claimed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    available_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
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
            "action_intent_id",
            "execution_attempt_id",
            "job_type",
            name="ux_action_post_execution_jobs_project_attempt_type",
        ),
        CheckConstraint(
            "job_type IN ('verify_outcome','generate_receipt')",
            name="ck_action_post_execution_jobs_type",
        ),
        CheckConstraint(
            "status IN ('pending','claimed','running','succeeded','retrying','dead')",
            name="ck_action_post_execution_jobs_status",
        ),
        Index("ix_action_post_execution_jobs_project_status", "project_id", "status", "available_at"),
        Index("ix_action_post_execution_jobs_attempt", "project_id", "execution_attempt_id"),
        Index("ix_action_post_execution_jobs_action", "project_id", "action_intent_id"),
        Index("ix_action_post_execution_jobs_lease", "status", "lease_expires_at"),
    )
