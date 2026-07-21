from __future__ import annotations

from app.db._internal.model_shared import *


class FinalWorkflowIntent(Base):
    __tablename__ = "final_workflow_intents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    agent_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    intent_digest: Mapped[str] = mapped_column(String(80), nullable=False)
    intent_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'received'"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("project_id", "environment", "idempotency_key", name="ux_final_intents_scope_idempotency"),
        CheckConstraint(
            "status IN ('received','policy_denied','approval_required','authorized','expired')",
            name="ck_final_workflow_intents_status",
        ),
        Index("ix_final_intents_scope_status", "project_id", "environment", "status", "created_at"),
    )


class FinalPolicyDecision(Base):
    __tablename__ = "final_policy_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    intent_id: Mapped[str] = mapped_column(String(36), ForeignKey("final_workflow_intents.id", ondelete="CASCADE"), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    policy_digest: Mapped[str] = mapped_column(String(80), nullable=False)
    decision_json: Mapped[str] = mapped_column(Text, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "decision IN ('allow','deny','approval_required','observe_only')",
            name="ck_final_policy_decisions_decision",
        ),
        Index("ix_final_policy_scope_intent", "project_id", "environment", "intent_id"),
    )


class FinalApprovalRequirement(Base):
    __tablename__ = "final_approval_requirements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    intent_id: Mapped[str] = mapped_column(String(36), ForeignKey("final_workflow_intents.id", ondelete="CASCADE"), nullable=False)
    policy_decision_id: Mapped[str] = mapped_column(String(36), ForeignKey("final_policy_decisions.id", ondelete="CASCADE"), nullable=False)
    required_role: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'admin'"))
    binding_digest: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'pending'"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("project_id", "environment", "policy_decision_id", name="ux_final_approvals_scope_decision"),
        CheckConstraint("required_role IN ('admin','owner')", name="ck_final_approval_requirements_role"),
        CheckConstraint("status IN ('pending','approved','denied')", name="ck_final_approval_requirements_status"),
        Index("ix_final_approvals_scope_status", "project_id", "environment", "status", "created_at"),
    )


class FinalAgentRun(Base):
    __tablename__ = "final_agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    external_run_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    intent_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("final_workflow_intents.id", ondelete="SET NULL"), nullable=True)
    workflow_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    agent_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'declared'"))
    run_digest: Mapped[str] = mapped_column(String(80), nullable=False)
    run_json: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("project_id", "environment", "idempotency_key", name="ux_final_agent_runs_scope_idempotency"),
        CheckConstraint(
            "status IN ('declared','running','succeeded','failed','cancelled','unknown')",
            name="ck_final_agent_runs_status",
        ),
        Index("ix_final_agent_runs_scope_status", "project_id", "environment", "status", "created_at"),
        Index("ix_final_agent_runs_scope_external", "project_id", "environment", "external_run_id"),
        Index("ix_final_agent_runs_scope_intent", "project_id", "environment", "intent_id"),
    )


class FinalConnectorCapabilityDraft(Base):
    __tablename__ = "final_connector_capability_drafts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    capability_key: Mapped[str] = mapped_column(String(255), nullable=False)
    schema_digest: Mapped[str] = mapped_column(String(80), nullable=False)
    schema_json: Mapped[str] = mapped_column(Text, nullable=False)
    trust_status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'draft_untrusted'"))
    trusted_for_recovery: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("project_id", "environment", "source_kind", "capability_key", name="ux_final_capability_drafts_scope_key"),
        CheckConstraint("source_kind IN ('mcp','a2a','openapi','asyncapi')", name="ck_final_capability_drafts_source_kind"),
        CheckConstraint("trust_status IN ('draft_untrusted','reviewed','retired')", name="ck_final_capability_drafts_trust_status"),
        CheckConstraint("trusted_for_recovery = false", name="ck_final_capability_drafts_not_recovery_trusted"),
        Index("ix_final_capability_drafts_scope_source", "project_id", "environment", "source_kind", "created_at"),
    )


class FinalAssurancePack(Base):
    __tablename__ = "final_assurance_packs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    workflow_key: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    pack_digest: Mapped[str] = mapped_column(String(80), nullable=False)
    pack_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'active'"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("project_id", "environment", "workflow_key", "version", name="ux_final_assurance_packs_scope_version"),
        CheckConstraint("status IN ('active','retired')", name="ck_final_assurance_packs_status"),
        Index("ix_final_assurance_packs_scope_status", "project_id", "environment", "status"),
    )


class FinalObservation(Base):
    __tablename__ = "final_observations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    intent_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("final_workflow_intents.id", ondelete="SET NULL"), nullable=True)
    source_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_object_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    observation_digest: Mapped[str] = mapped_column(String(80), nullable=False)
    observation_json: Mapped[str] = mapped_column(Text, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("ix_final_observations_scope_object", "project_id", "environment", "observed_object_ref", "observed_at"),
        Index("ix_final_observations_scope_intent", "project_id", "environment", "intent_id"),
    )


class FinalOutcomeGraph(Base):
    __tablename__ = "final_outcome_graphs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    intent_id: Mapped[str] = mapped_column(String(36), ForeignKey("final_workflow_intents.id", ondelete="CASCADE"), nullable=False)
    graph_digest: Mapped[str] = mapped_column(String(80), nullable=False)
    graph_json: Mapped[str] = mapped_column(Text, nullable=False)
    verification_status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'pending'"))
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "verification_status IN ('pending','verified','failed','inconclusive')",
            name="ck_final_outcome_graphs_verification_status",
        ),
        Index("ix_final_outcome_graphs_scope_status", "project_id", "environment", "verification_status", "created_at"),
    )


class FinalOutcomeIncident(Base):
    __tablename__ = "final_outcome_incidents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome_graph_id: Mapped[str] = mapped_column(String(36), ForeignKey("final_outcome_graphs.id", ondelete="CASCADE"), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'open'"))
    incident_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    __table_args__ = (
        CheckConstraint("severity IN ('low','medium','high','critical')", name="ck_final_outcome_incidents_severity"),
        CheckConstraint("status IN ('open','recovering','resolved','unresolved')", name="ck_final_outcome_incidents_status"),
        Index("ix_final_incidents_scope_status", "project_id", "environment", "status", "created_at"),
    )


class FinalRecoveryPlan(Base):
    __tablename__ = "final_recovery_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    incident_id: Mapped[str] = mapped_column(String(36), ForeignKey("final_outcome_incidents.id", ondelete="CASCADE"), nullable=False)
    plan_digest: Mapped[str] = mapped_column(String(80), nullable=False)
    plan_json: Mapped[str] = mapped_column(Text, nullable=False)
    approval_status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'not_required'"))
    execution_status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'not_started'"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint(
            "approval_status IN ('not_required','required','approved','denied')",
            name="ck_final_recovery_plans_approval_status",
        ),
        CheckConstraint(
            "execution_status IN ('not_started','dispatched','succeeded','failed','ambiguous')",
            name="ck_final_recovery_plans_execution_status",
        ),
        Index("ix_final_recovery_plans_scope_status", "project_id", "environment", "execution_status", "created_at"),
    )


class FinalEvidenceBundle(Base):
    __tablename__ = "final_evidence_bundles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(36), nullable=False)
    bundle_digest: Mapped[str] = mapped_column(String(80), nullable=False)
    bundle_json: Mapped[str] = mapped_column(Text, nullable=False)
    signature_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("project_id", "environment", "bundle_digest", name="ux_final_evidence_bundles_scope_digest"),
        Index("ix_final_evidence_bundles_scope_subject", "project_id", "environment", "subject_type", "subject_id"),
    )


class FinalDomainOutboxJob(Base):
    __tablename__ = "final_domain_outbox_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(36), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
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
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("project_id", "environment", "idempotency_key", name="ux_final_outbox_scope_idempotency"),
        CheckConstraint(
            "job_type IN ('verify_outcome','plan_recovery','execute_recovery','generate_evidence')",
            name="ck_final_domain_outbox_jobs_type",
        ),
        CheckConstraint(
            "status IN ('pending','claimed','running','succeeded','retrying','dead')",
            name="ck_final_domain_outbox_jobs_status",
        ),
        Index("ix_final_outbox_scope_status", "project_id", "environment", "status", "available_at"),
        Index("ix_final_outbox_aggregate", "project_id", "environment", "aggregate_type", "aggregate_id"),
        Index("ix_final_outbox_lease", "status", "lease_expires_at"),
    )
