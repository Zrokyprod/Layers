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
    # (No additional updated_at or duplicate table args; indexes/constraints defined above.)


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


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    owner_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    # Module 9: default golden set used by the GitHub Action when its
    # workflow does not name an explicit set. NULL means "no default
    # configured; dispatch endpoint requires explicit golden_set_id".
    # Migration 0060.
    default_golden_set_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True
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

    api_keys: Mapped[list["ApiKey"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    memberships: Mapped[list["ProjectMembership"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    dashboard_config: Mapped["ProjectDashboardConfig"] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        uselist=False,
    )
    subscription: Mapped["TenantSubscription | None"] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        uselist=False,
    )
    slack_install: Mapped["TenantSlackInstall | None"] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        uselist=False,
    )
    teams_install: Mapped["TenantTeamsInstall | None"] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        uselist=False,
    )

    __table_args__ = (
        Index("ix_projects_owner_ref", "owner_ref"),
        Index("ix_projects_is_active", "is_active"),
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    # Encrypted email - stored with hash prefix for searchable queries
    email: Mapped[str | None] = mapped_column(EncryptedSearchableString, nullable=True)
    # Deterministic hash of email for exact-match lookups (encrypted at application layer)
    email_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    github_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    google_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    github_login: Mapped[str | None] = mapped_column(String(120), nullable=True)
    github_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    github_token_scopes: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    github_token_connected_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    github_token_updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    email_verification_token: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    memberships: Mapped[list["ProjectMembership"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ux_users_subject", "subject", unique=True),
        # Use email_hash for unique constraint since email is encrypted
        Index("ux_users_email_hash", "email_hash", unique=True),
        Index("ux_users_github_id", "github_id", unique=True),
        Index("ux_users_google_id", "google_id", unique=True),
        Index("ix_users_is_active", "is_active"),
    )


class ProjectMembership(Base):
    __tablename__ = "project_memberships"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("member"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    project: Mapped[Project] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")

    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="ux_project_memberships_project_user"),
        Index("ix_project_memberships_project_active", "project_id", "is_active"),
        Index("ix_project_memberships_user_active", "user_id", "is_active"),
    )


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(24), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
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

    project: Mapped[Project] = relationship(back_populates="api_keys")

    __table_args__ = (
        Index("ix_api_keys_project_revoked", "project_id", "revoked_at"),
        Index("ux_api_keys_key_hash", "key_hash", unique=True),
    )


class ProjectAlert(Base):
    __tablename__ = "project_alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    diagnosis_id: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("medium"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("OPEN"))
    source: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("diagnosis_engine"))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    evidence_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
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
        UniqueConstraint("tenant_id", "diagnosis_id", "category", name="ux_project_alerts_tenant_diagnosis_category"),
        Index("ix_project_alerts_tenant_created", "tenant_id", "created_at"),
        Index("ix_project_alerts_tenant_status_created", "tenant_id", "status", "created_at"),
        Index("ix_project_alerts_tenant_category", "tenant_id", "category"),
    )


class ProjectDashboardConfig(Base):
    __tablename__ = "project_dashboard_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    monthly_budget_usd: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    budget_threshold_percentage: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False, server_default=text("80"))
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("30"))
    pii_custom_patterns_json: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'[]'"))
    notifications_json: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'{}'"))
    provider_verifications_json: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'{}'"))
    pricing_validation_json: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'{}'"))
    rollback_drill_json: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    project: Mapped[Project] = relationship(back_populates="dashboard_config")

    __table_args__ = (
        UniqueConstraint("tenant_id", name="ux_project_dashboard_configs_tenant"),
        Index("ix_project_dashboard_configs_updated_at", "updated_at"),
    )


class TenantSlackInstall(Base):
    __tablename__ = "tenant_slack_install"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    team_id: Mapped[str] = mapped_column(String(64), nullable=False)
    team_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    access_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    webhook_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    channel_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    channel_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bot_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    installed_by_user: Mapped[str | None] = mapped_column(String(255), nullable=True)
    installed_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    project: Mapped[Project] = relationship(back_populates="slack_install")

    __table_args__ = (
        UniqueConstraint("tenant_id", name="ux_tenant_slack_install_tenant"),
        Index("ix_tenant_slack_install_team_id", "team_id"),
        Index("ix_tenant_slack_install_channel_id", "channel_id"),
    )


class TenantTeamsInstall(Base):
    __tablename__ = "tenant_teams_install"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    webhook_url_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    channel_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    connector_type: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'webhook'"))
    installed_by_user: Mapped[str | None] = mapped_column(String(255), nullable=True)
    installed_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    project: Mapped[Project] = relationship(back_populates="teams_install")

    __table_args__ = (
        UniqueConstraint("tenant_id", name="ux_tenant_teams_install_tenant"),
        Index("ix_tenant_teams_install_updated_at", "updated_at"),
    )


class ProjectInvitation(Base):
    __tablename__ = "project_invitations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'member'"))
    invited_by_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
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
        UniqueConstraint("project_id", "email", name="ux_project_invitations_project_email"),
        Index("ix_project_invitations_token_hash", "token_hash", unique=True),
        Index("ix_project_invitations_project_id", "project_id"),
        Index("ix_project_invitations_email", "email"),
    )


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'general'"))
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    action_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_notifications_user_id", "user_id"),
        Index("ix_notifications_user_read", "user_id", "is_read"),
        Index("ix_notifications_created_at", "created_at"),
    )


class PlatformLlmUsage(Base):
    __tablename__ = "platform_llm_usage"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    purpose: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(120), nullable=False, server_default=text("'openrouter'"))
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    cost_usd: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False, server_default=text("0"))
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    request_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    diagnosis_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_platform_llm_usage_purpose", "purpose"),
        Index("ix_platform_llm_usage_created", "created_at"),
        Index("ix_platform_llm_usage_tenant", "tenant_id"),
    )


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
    diff_metric: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    stdout_tail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    __table_args__ = (
        Index("ix_replay_jobs_tenant_status", "tenant_id", "status"),
        Index("ix_replay_jobs_tenant_created", "tenant_id", "created_at"),
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


# ---------------------------------------------------------------------------
# Pilot tier — Golden Sets + Golden Traces (migration 0049, plan §5.2)
# ---------------------------------------------------------------------------


class GoldenSet(Base):
    """A named collection of canonical traces for replay-based regression.

    Owned by a project. Holds the judge config applied when replaying every
    trace in the set. See ZROKY-TECHNICAL-PLAN-V2 §5.2 / §6.4.
    """

    __tablename__ = "golden_sets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    judge_config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    traces: Mapped[list["GoldenTrace"]] = relationship(
        "GoldenTrace",
        back_populates="golden_set",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint("project_id", "name", name="ux_golden_sets_project_name"),
        Index("ix_golden_sets_project_created", "project_id", "created_at"),
    )


class GoldenTrace(Base):
    """One canonical call promoted to "expected behaviour" inside a golden set.

    Stores the expected output text and baseline tokens/cost/latency, plus
    per-trace judge criteria (criteria_json may include `expected_schema_json`
    for SCHEMA_VIOLATION detection). `project_id` is denormalised from the
    parent golden_set so the Postgres RLS policy can filter by tenant
    without a JOIN.
    """

    __tablename__ = "golden_traces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    golden_set_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("golden_sets.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    call_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("calls.id", ondelete="SET NULL"),
        nullable=True,
    )
    expected_output_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expected_cost_usd: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    expected_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    criteria_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    weight: Mapped[float] = mapped_column(
        Numeric(8, 4), nullable=False, server_default=text("1.0")
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    golden_set: Mapped["GoldenSet"] = relationship("GoldenSet", back_populates="traces")

    __table_args__ = (
        Index("ix_golden_traces_set_id", "golden_set_id"),
        Index("ix_golden_traces_project_created", "project_id", "created_at"),
        Index("ix_golden_traces_call_id", "call_id"),
    )


# ---------------------------------------------------------------------------
# Pilot tier — Replay Runs + Replay Run Traces (migration 0050, plan §5.2 / §6.4)
# ---------------------------------------------------------------------------


class ReplayRun(Base):
    """One batch invocation of a golden_set replay against current model+prompt config.

    Triggered by `manual` user action, `github` Action on push, or
    `schedule` cron. Aggregate pass/fail summary lives in summary_json.
    Distinct from the legacy `replay_jobs` table (single-fix customer-hosted).
    """

    __tablename__ = "replay_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    golden_set_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("golden_sets.id", ondelete="CASCADE"),
        nullable=False,
    )
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)
    git_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )

    traces: Mapped[list["ReplayRunTrace"]] = relationship(
        "ReplayRunTrace",
        back_populates="run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint(
            "trigger IN ('manual', 'github', 'schedule')",
            name="ck_replay_runs_trigger",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'pass', 'fail', 'error')",
            name="ck_replay_runs_status",
        ),
        Index("ix_replay_runs_project_created", "project_id", "created_at"),
        Index("ix_replay_runs_project_status", "project_id", "status"),
        Index("ix_replay_runs_golden_set_id", "golden_set_id"),
    )


class ReplayRunTrace(Base):
    """Per-trace outcome inside a replay_run.

    `golden_trace_id` is SET NULL on parent trace deletion so historical run
    rows survive even if a trace is later removed from the golden set.
    `project_id` is denormalised from the parent run for RLS-without-JOIN.
    """

    __tablename__ = "replay_run_traces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    replay_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("replay_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    golden_trace_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("golden_traces.id", ondelete="SET NULL"),
        nullable=True,
    )
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    call_id_replayed: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("calls.id", ondelete="SET NULL"),
        nullable=True,
    )
    judge_scores_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    diff_metric: Mapped[float | None] = mapped_column(Float, nullable=True)
    output_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )

    run: Mapped["ReplayRun"] = relationship("ReplayRun", back_populates="traces")

    __table_args__ = (
        CheckConstraint(
            "status IN ('pass', 'fail', 'error')",
            name="ck_replay_run_traces_status",
        ),
        Index("ix_replay_run_traces_run_id", "replay_run_id"),
        Index("ix_replay_run_traces_golden_trace_id", "golden_trace_id"),
        Index("ix_replay_run_traces_project_created", "project_id", "created_at"),
        Index("ix_replay_run_traces_run_status", "replay_run_id", "status"),
    )


# ---------------------------------------------------------------------------
# Pilot tier — Anomalies (migration 0051, plan §5.2 / §6)
# Phase A of the `issues → anomalies` rename. Legacy `Issue` model stays
# until Phase B (later migration) backfills + drops.
# ---------------------------------------------------------------------------


class Anomaly(Base):
    """One grouped detection event (replacement for legacy `Issue`).

    One row per (project_id, fingerprint) group. `fingerprint` is a hash of
    (detector, model, prompt_fingerprint, agent, …) emitted by the detector
    pipeline. `evidence_json` carries the Diagnose engine's ranked candidates.
    Demoted-to-guidance detectors (TOKEN_OVERFLOW, RATE_LIMIT, AUTH_FAILURE,
    PROVIDER_ERROR) do NOT create rows here — they are SDK-side preflight
    warnings only (plan §6.1).
    """

    __tablename__ = "anomalies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    detector: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'low'")
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'open'")
    )
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    occurrence_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    sample_call_ids_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id", "fingerprint",
            name="ux_anomalies_project_fingerprint",
        ),
        CheckConstraint(
            "detector IN ("
            "'LOOP_DETECTED', 'COST_SPIKE', "
            "'ACCURACY_REGRESSION', 'HALLUCINATION_RISK', "
            "'SCHEMA_VIOLATION', 'LATENCY_REGRESSION'"
            ")",
            name="ck_anomalies_detector",
        ),
        CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_anomalies_severity",
        ),
        CheckConstraint(
            "status IN ('open', 'acknowledged', 'resolved', 'muted')",
            name="ck_anomalies_status",
        ),
        Index("ix_anomalies_project_status", "project_id", "status"),
        Index(
            "ix_anomalies_project_status_last_seen",
            "project_id", "status", "last_seen_at",
        ),
        Index("ix_anomalies_project_severity", "project_id", "severity"),
        Index("ix_anomalies_project_detector", "project_id", "detector"),
        Index("ix_anomalies_project_last_seen", "project_id", "last_seen_at"),
        Index("ix_anomalies_fingerprint", "fingerprint"),
    )


# ---------------------------------------------------------------------------
# Pilot tier — Autopilot Actions + Policies (migration 0052, plan §5.2 / §6.3)
# ---------------------------------------------------------------------------


class PilotAction(Base):
    """One autopilot decision against an anomaly.

    `tier` semantics (plan §6.3):
        1 = auto-revert (model_rollback, fallback_swap, retry_tune)
        2 = auto-PR    (open_pr)
        3 = alert      (alert)
    `audit_user` is NULL when the action came from autopilot, set to the
    user_id of a manual override otherwise.
    """

    __tablename__ = "pilot_actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    anomaly_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("anomalies.id", ondelete="CASCADE"),
        nullable=False,
    )
    tier: Mapped[int] = mapped_column(Integer, nullable=False)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    reverted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    audit_user: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Module 10 (migration 0061) — Tier-2 auto-PR columns. Stay NULL on
    # tier-1 / tier-3 rows. See migration docstring for semantics.
    pr_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    pr_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    replay_run_id_gate: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("tier IN (1, 2, 3)", name="ck_pilot_actions_tier"),
        CheckConstraint(
            "status IN ('pending', 'applied', 'reverted', 'failed', 'skipped')",
            name="ck_pilot_actions_status",
        ),
        Index("ix_pilot_actions_project_created", "project_id", "created_at"),
        Index("ix_pilot_actions_project_status", "project_id", "status"),
        Index(
            "ix_pilot_actions_project_tier_status",
            "project_id", "tier", "status",
        ),
        Index("ix_pilot_actions_anomaly_id", "anomaly_id"),
        # Module 10 — fast idempotency lookup by (project, fingerprint).
        Index(
            "ix_pilot_actions_project_pr_fingerprint",
            "project_id", "pr_fingerprint",
        ),
    )


class PilotPolicy(Base):
    """Per-project autopilot policy. Single row per project.

    `policy_json` carries per-tier configuration: enable flags, allowed
    action types, min_confidence thresholds, max_blast_radius, daily caps,
    kill-switch — see plan §6.3 for the canonical schema.
    """

    __tablename__ = "pilot_policies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("project_id", name="ux_pilot_policies_project"),
    )


# ---------------------------------------------------------------------------
# Pilot tier — Weekly Digests (migration 0053, plan §5.2)
# Drives the weekly summary email rendered by digest_engine.py
# (promoted from weekly_impact.py) and read by /v1/digest/{week}.
# ---------------------------------------------------------------------------


class Digest(Base):
    """One weekly digest row per (project_id, week_start).

    `summary_json` carries the structured aggregate (counts, USD saved,
    incidents-caught, fix-cycle stats). `html_blob` is the pre-rendered
    email body. `sent_at IS NULL` means the row is queued.
    """

    __tablename__ = "digests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    html_blob: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_to_emails: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("project_id", "week_start", name="ux_digests_project_week"),
        Index("ix_digests_project_week_start", "project_id", "week_start"),
        Index("ix_digests_project_sent_at", "project_id", "sent_at"),
        Index("ix_digests_pending_sent_at", "sent_at"),
    )


# ---------------------------------------------------------------------------
# Billing rewrite — Subscriptions + Entitlements (migration 0054, plan §5.2 / §10)
# Phase A: live alongside legacy `subscription_plans` + `tenant_subscriptions`
# until app code switches reads/writes.
# ---------------------------------------------------------------------------


class Subscription(Base):
    """Stripe-aligned per-org subscription. Replaces `TenantSubscription`.

    `org_id` is the billing entity (plan §5.1). The `orgs` table does not
    yet exist; for now `org_id` equals the project_id of the org's primary
    project. When orgs are introduced, a FK will be added without renaming.
    """

    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    org_id: Mapped[str] = mapped_column(String(64), nullable=False)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stripe_sub_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    plan_code: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'active'")
    )
    seats: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    current_period_end: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    trial_end: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    # Module 12 / migration 0062 — Reliability SLA tier (plan §11.4).
    # 'none' for Free/Starter/Pro; 'team'/'enterprise' for tiers that
    # carry the refund-on-miss SLA contract. Mutated only by the
    # Founder Console; the Module 12 lifecycle sweep does NOT touch
    # this column on auto-downgrade (a customer who lapses keeps
    # their SLA-tier history for audit/refund eligibility).
    sla_tier: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'none'")
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("org_id", name="ux_subscriptions_org"),
        UniqueConstraint("stripe_sub_id", name="ux_subscriptions_stripe_sub_id"),
        CheckConstraint(
            "status IN ('trialing', 'active', 'past_due', 'canceled', 'unpaid', 'incomplete')",
            name="ck_subscriptions_status",
        ),
        CheckConstraint(
            "sla_tier IN ('none', 'team', 'enterprise')",
            name="ck_subscriptions_sla_tier",
        ),
        Index("ix_subscriptions_stripe_customer_id", "stripe_customer_id"),
        Index("ix_subscriptions_status", "status"),
        Index("ix_subscriptions_plan_code", "plan_code"),
        Index("ix_subscriptions_current_period_end", "current_period_end"),
    )


class Entitlement(Base):
    """Per-org capability flag/limit. Replaces `SubscriptionPlan.features_json` + caps.

    Multiple rows per (org_id, key) are allowed when they have different
    `source` values; the application resolver merges by precedence:
        override > trial > plan
    """

    __tablename__ = "entitlements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    org_id: Mapped[str] = mapped_column(String(64), nullable=False)
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "org_id", "key", "source",
            name="ux_entitlements_org_key_source",
        ),
        CheckConstraint(
            "source IN ('plan', 'override', 'trial')",
            name="ck_entitlements_source",
        ),
        Index("ix_entitlements_org_key", "org_id", "key"),
        Index("ix_entitlements_org_expires_at", "org_id", "expires_at"),
    )


# ---------------------------------------------------------------------------
# Intel Pulse — external signal ingestion (migration 0055, plan §5.2 / §9)
# Global (not tenant-scoped): shared intelligence across all orgs.
# ---------------------------------------------------------------------------


class IntelSignal(Base):
    """One external signal ingested by the Intel Pulse scrapers.

    Covers provider outages, model deprecations, CVEs, and pricing changes.
    Global to the deployment — no project/org scope, no RLS. Filtering for
    "currently active" signals is
        now BETWEEN valid_from AND COALESCE(valid_to, 'infinity')
    """

    __tablename__ = "intel_signals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    model_affected: Mapped[str | None] = mapped_column(String(128), nullable=True)
    severity: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'low'")
    )
    confidence: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=text("1.0")
    )
    valid_from: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "kind IN ('outage', 'deprecation', 'cve', 'pricing_change', 'advisory')",
            name="ck_intel_signals_kind",
        ),
        CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_intel_signals_severity",
        ),
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_intel_signals_confidence_range",
        ),
        Index("ix_intel_signals_source_kind", "source", "kind"),
        Index("ix_intel_signals_model_affected", "model_affected"),
        Index("ix_intel_signals_valid_to", "valid_to"),
        Index("ix_intel_signals_valid_from", "valid_from"),
        Index("ix_intel_signals_severity", "severity"),
        Index("ix_intel_signals_created_at", "created_at"),
    )


# ---------------------------------------------------------------------------
# Conversational support — Threads + Messages (migration 0056, plan §5.2)
# Phase A: live alongside legacy `support_tickets` until app code switches.
# ---------------------------------------------------------------------------


class SupportThread(Base):
    """One conversational support thread per row.

    `last_activity_at` is bumped on every new message so the inbox sort
    `ORDER BY last_activity_at DESC` is index-backed without touching
    `support_messages`. Replaces the flat `SupportTicket` model.
    """

    __tablename__ = "support_threads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'open'")
    )
    priority: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'medium'")
    )
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    assigned_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_activity_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list["SupportMessage"]] = relationship(
        "SupportMessage",
        back_populates="thread",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'pending', 'on_hold', 'resolved', 'closed')",
            name="ck_support_threads_status",
        ),
        CheckConstraint(
            "priority IN ('low', 'medium', 'high', 'urgent')",
            name="ck_support_threads_priority",
        ),
        Index(
            "ix_support_threads_project_status_activity",
            "project_id", "status", "last_activity_at",
        ),
        Index(
            "ix_support_threads_project_last_activity",
            "project_id", "last_activity_at",
        ),
        Index("ix_support_threads_project_status", "project_id", "status"),
        Index("ix_support_threads_assigned_to", "assigned_to"),
        Index("ix_support_threads_created_by_user_id", "created_by_user_id"),
    )


class SupportMessage(Base):
    """Append-only message under a SupportThread.

    `sender_role = 'system'` covers auto-generated notes (status changes,
    assignment events). `project_id` is denormalised for RLS-without-JOIN.
    """

    __tablename__ = "support_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    thread_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("support_threads.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    sender_user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    sender_role: Mapped[str] = mapped_column(String(16), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    attachments_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )

    thread: Mapped["SupportThread"] = relationship(
        "SupportThread", back_populates="messages"
    )

    __table_args__ = (
        CheckConstraint(
            "sender_role IN ('user', 'support', 'system')",
            name="ck_support_messages_sender_role",
        ),
        Index("ix_support_messages_thread_created", "thread_id", "created_at"),
        Index("ix_support_messages_project_created", "project_id", "created_at"),
        Index("ix_support_messages_sender_user_id", "sender_user_id"),
    )


# ---------------------------------------------------------------------------
# Admin / Owner action trail (migration 0057, plan §5.2)
# Distinct from the tenant-scoped `audit_logs` table. No RLS — admin-only.
# ---------------------------------------------------------------------------


class AuditLogAdmin(Base):
    """Audit trail for actions taken by ZROKY staff (or the platform itself).

    `before_json` / `after_json` snapshot entity state to enable
    point-in-time diffs in the admin console.
    """

    __tablename__ = "audit_log_admin"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    actor_user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    ua: Mapped[str | None] = mapped_column(String(512), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    before_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "actor_role IN ('owner', 'support', 'admin', 'system')",
            name="ck_audit_log_admin_actor_role",
        ),
        Index("ix_audit_log_admin_actor_created", "actor_user_id", "created_at"),
        Index(
            "ix_audit_log_admin_target",
            "target_type", "target_id", "created_at",
        ),
        Index("ix_audit_log_admin_action_created", "action", "created_at"),
        Index("ix_audit_log_admin_created_at", "created_at"),
    )


# ---------------------------------------------------------------------------
# Provider key vault (migration 0058, plan §5.2 + §14.2)
# Per-project encrypted provider API keys for replay-worker reconstruction.
# AES-256-GCM envelope under per-org KMS KEK; tenant-scoped with RLS.
# ---------------------------------------------------------------------------


_PROVIDER_KEYS_VAULT_PROVIDERS = (
    "openai",
    "anthropic",
    "gemini",
    "azure_openai",
    "vertex",
    "cohere",
    "mistral",
    "deepseek",
    "bedrock",
    "openrouter",
    "groq",
    "custom",
)


class ProviderKeyVault(Base):
    """Encrypted customer provider API keys (per project, per provider).

    The replay worker reads these to reconstruct a provider client during
    pre-action verification (plan §6.4). Plaintext keys are never stored;
    `ciphertext` holds an AES-256-GCM envelope (`nonce || ciphertext || tag`)
    encrypted under the project's per-org KEK from the configured KMS.
    """

    __tablename__ = "provider_keys_vault"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    key_last4: Mapped[str | None] = mapped_column(String(8), nullable=True)
    kms_key_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"), default=True
    )
    label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    last_used_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "provider IN ("
            + ", ".join(f"'{p}'" for p in _PROVIDER_KEYS_VAULT_PROVIDERS)
            + ")",
            name="ck_provider_keys_vault_provider",
        ),
        UniqueConstraint(
            "project_id", "provider", "key_fingerprint",
            name="ux_provider_keys_vault_project_provider_fp",
        ),
        Index(
            "ix_provider_keys_vault_project_provider_active",
            "project_id", "provider", "is_active",
        ),
        Index(
            "ix_provider_keys_vault_project_created",
            "project_id", "created_at",
        ),
        Index(
            "ix_provider_keys_vault_created_by_user_id",
            "created_by_user_id",
        ),
        Index(
            "ix_provider_keys_vault_key_fingerprint",
            "key_fingerprint",
        ),
    )


# ---------------------------------------------------------------------------
# Stripe webhook idempotency log (migration 0059, plan §11.3 + §17.1 risk #3)
# Global table — no tenant scope. The webhook authenticates via Stripe
# HMAC signature, not a project header.
# ---------------------------------------------------------------------------


class StripeEvent(Base):
    """One row per Stripe webhook event we have ever seen.

    `stripe_event_id` is UNIQUE so the dispatcher can use INSERT-or-conflict
    semantics for idempotent claim. Duplicates short-circuit with HTTP 200
    so Stripe stops retrying.
    """

    __tablename__ = "stripe_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    stripe_event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    stripe_created_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime, nullable=True
    )
    received_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime, nullable=True
    )
    result: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    affected_org_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "stripe_event_id", name="ux_stripe_events_stripe_event_id"
        ),
        CheckConstraint(
            "result IN ('pending', 'applied', 'skipped', 'failed')",
            name="ck_stripe_events_result",
        ),
        Index("ix_stripe_events_event_type", "event_type"),
        Index("ix_stripe_events_received_at", "received_at"),
        Index("ix_stripe_events_affected_org_id", "affected_org_id"),
    )


class FeatureInterestVote(Base):
    """Customer vote on a "coming soon" feature (Module 9 smoke test).

    Plan ref: Module 9 alternative — validate Tier-1 autonomy demand
    before building the executor. Customer dashboard renders a
    grayed-out feature row + a thumbs-up/down poll backed by this
    table. One vote per (subject, feature_key); upsert on conflict.
    """

    __tablename__ = "feature_interest_votes"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    project_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    feature_key: Mapped[str] = mapped_column(String(64), nullable=False)
    vote: Mapped[str] = mapped_column(String(16), nullable=False)
    use_case: Mapped[str | None] = mapped_column(Text, nullable=True)
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
            "subject", "feature_key",
            name="ux_feature_votes_subject_feature",
        ),
        CheckConstraint(
            "vote IN ('interested', 'not_interested')",
            name="ck_feature_votes_vote",
        ),
        Index("ix_feature_votes_key_vote", "feature_key", "vote"),
        Index("ix_feature_votes_project", "project_id"),
        Index("ix_feature_votes_created", "created_at"),
    )


# ---------------------------------------------------------------------------
# Wedge 2 — Provider Silent-Update Detector ("Provider Drift Watch")
# Migration 0064. PUBLIC service tables: no project_id, no RLS.
# ---------------------------------------------------------------------------


class ProviderDriftPrompt(Base):
    """One canonical prompt in the deterministic suite.

    Versioned: bump `version` and clear `active` when prompt_text needs to
    change. Old rows are retained so historical probes remain joinable.
    """

    __tablename__ = "provider_drift_prompts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("512")
    )
    expected_signal: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "category IN ('math','refusal','code','summarization',"
            "'multi_turn','tool_use','factuality','instruction_following')",
            name="ck_provider_drift_prompts_category",
        ),
        Index(
            "ix_provider_drift_prompts_category_active",
            "category",
            "active",
        ),
    )


class ProviderDriftModel(Base):
    """One model under continuous observation."""

    __tablename__ = "provider_drift_models"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model_id: Mapped[str] = mapped_column(String(120), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    family: Mapped[str] = mapped_column(String(32), nullable=False)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "provider", "model_id", name="ux_provider_drift_models_provider_model"
        ),
        CheckConstraint(
            "provider IN ('openai','anthropic','google','meta','mistral','xai','other')",
            name="ck_provider_drift_models_provider",
        ),
        Index("ix_provider_drift_models_active", "active"),
    )


class ProviderDriftRun(Base):
    """One day's worth of probes for a single model."""

    __tablename__ = "provider_drift_runs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    model_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("provider_drift_models.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    prompts_total: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    prompts_ok: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    prompts_error: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    cost_usd: Mapped[float] = mapped_column(
        Numeric(18, 8), nullable=False, server_default=text("0")
    )
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "model_id", "run_date", name="ux_provider_drift_runs_model_date"
        ),
        CheckConstraint(
            "status IN ('pending','running','complete','partial','error')",
            name="ck_provider_drift_runs_status",
        ),
        Index("ix_provider_drift_runs_run_date", "run_date"),
        Index("ix_provider_drift_runs_model_date", "model_id", "run_date"),
    )


class ProviderDriftProbe(Base):
    """Outcome of a single (run, prompt) pair."""

    __tablename__ = "provider_drift_probes"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("provider_drift_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    prompt_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("provider_drift_prompts.id", ondelete="CASCADE"),
        nullable=False,
    )
    model_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("provider_drift_models.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_date: Mapped[date] = mapped_column(Date, nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    output_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_embedding: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    judge_pass: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    judge_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float] = mapped_column(
        Numeric(18, 8), nullable=False, server_default=text("0")
    )
    outcome: Mapped[str] = mapped_column(String(24), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "run_id", "prompt_id", name="ux_provider_drift_probes_run_prompt"
        ),
        CheckConstraint(
            "outcome IN ('ok','rate_limited','timeout','content_filtered',"
            "'budget_exceeded','error')",
            name="ck_provider_drift_probes_outcome",
        ),
        Index(
            "ix_provider_drift_probes_model_date_category",
            "model_id",
            "run_date",
            "category",
        ),
        Index(
            "ix_provider_drift_probes_prompt_date", "prompt_id", "run_date"
        ),
    )


class ProviderDriftAlert(Base):
    """Drift signal computed by the aggregator."""

    __tablename__ = "provider_drift_alerts"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    model_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("provider_drift_models.id", ondelete="CASCADE"),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    current_date: Mapped[date] = mapped_column(Date, nullable=False)
    baseline_start: Mapped[date] = mapped_column(Date, nullable=False)
    baseline_end: Mapped[date] = mapped_column(Date, nullable=False)
    pass_rate_current: Mapped[float] = mapped_column(Float, nullable=False)
    pass_rate_baseline: Mapped[float] = mapped_column(Float, nullable=False)
    judge_z: Mapped[float] = mapped_column(Float, nullable=False)
    embedding_z: Mapped[float] = mapped_column(Float, nullable=False)
    delta_pp: Mapped[float] = mapped_column(Float, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    headline: Mapped[str] = mapped_column(String(255), nullable=False)
    evidence_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_candidate: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    published_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "model_id",
            "category",
            "current_date",
            name="ux_provider_drift_alerts_model_category_date",
        ),
        CheckConstraint(
            "severity IN ('info','warn','critical')",
            name="ck_provider_drift_alerts_severity",
        ),
        Index("ix_provider_drift_alerts_published", "published_at"),
        Index(
            "ix_provider_drift_alerts_model_date", "model_id", "current_date"
        ),
    )


# ---------------------------------------------------------------------------
# Calibrated Judge — golden_labels + judge_calibration_runs + judge_mode_overrides
# (migration 0065). See ZROKY-TECHNICAL-PLAN — Calibrated Judge wedge.
# ---------------------------------------------------------------------------


class GoldenLabel(Base):
    """Human ground-truth verdict attached to a `GoldenTrace`.

    Multi-labeler ready: many rows per trace, only one with `active=True`.
    Versioned so prior labels are preserved for audit even after edits.
    The presence of an active label is what makes a trace eligible for
    daily judge calibration.

    `project_id` is denormalised from the parent trace so RLS filters
    without a JOIN.
    """

    __tablename__ = "golden_labels"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    golden_trace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("golden_traces.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    labeler_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "verdict IN ('pass','fail','inconclusive')",
            name="ck_golden_labels_verdict",
        ),
        Index("ix_golden_labels_trace_active", "golden_trace_id", "active"),
        Index("ix_golden_labels_project_created", "project_id", "created_at"),
    )


class JudgeCalibrationRun(Base):
    """One daily calibration snapshot for a (project, judge_model) pair.

    Idempotent — UNIQUE on (project_id, judge_model, run_date) so retries
    no-op. The 3x3 confusion matrix is the canonical record; accuracy /
    P/R/F1 / kappa are derived on read so future verdict-class additions
    don't need a migration.
    """

    __tablename__ = "judge_calibration_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    judge_model: Mapped[str] = mapped_column(String(128), nullable=False)
    run_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'complete'")
    )
    sample_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    agreement_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    accuracy: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=text("0")
    )
    kappa: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=text("0")
    )
    low_confidence_pct: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=text("0")
    )
    confusion_matrix_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    per_class_metrics_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost_usd: Mapped[float] = mapped_column(
        Numeric(18, 8), nullable=False, server_default=text("0")
    )
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "judge_model",
            "run_date",
            name="ux_judge_calibration_runs_project_model_date",
        ),
        CheckConstraint(
            "status IN ('pending','running','complete','partial','error','skipped')",
            name="ck_judge_calibration_runs_status",
        ),
        CheckConstraint(
            "accuracy >= 0 AND accuracy <= 1",
            name="ck_judge_calibration_runs_accuracy",
        ),
        Index(
            "ix_judge_calibration_runs_project_date",
            "project_id",
            "run_date",
        ),
        Index(
            "ix_judge_calibration_runs_project_model_date",
            "project_id",
            "judge_model",
            "run_date",
        ),
    )


class JudgeModeOverride(Base):
    """Active mode (blocking|advisory) for a (project, judge_model) pair.

    The auto-downgrade safety net upserts here when accuracy crosses the
    configured thresholds. The regression-CI route reads this once per
    invocation and degrades gracefully to 'blocking' on any read failure.
    """

    __tablename__ = "judge_mode_overrides"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    judge_model: Mapped[str] = mapped_column(String(128), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    triggered_by_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    accuracy_at_change: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "judge_model",
            name="ux_judge_mode_overrides_project_model",
        ),
        CheckConstraint(
            "mode IN ('blocking','advisory')",
            name="ck_judge_mode_overrides_mode",
        ),
        Index("ix_judge_mode_overrides_project", "project_id"),
    )


# ---------------------------------------------------------------------------
# Cost-of-Failure Attribution (migration 0066)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Ablation Root-Cause Attribution (migration 0067)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Agent Reliability Scorecard (migration 0068)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Reliability Intelligence Queue (migration 0069)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Event listeners: auto-sync email_hash when email is set on User
# ---------------------------------------------------------------------------

@event.listens_for(User.email, "set", propagate=True)
def _user_email_set_listener(target: User, value: str | None, oldvalue, initiator) -> None:
    """Automatically populate email_hash whenever User.email is assigned."""
    target.email_hash = compute_email_hash(value)
