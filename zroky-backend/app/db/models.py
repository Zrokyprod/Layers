from datetime import datetime
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
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

    messages: Mapped[list["SupportMessage"]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="SupportMessage.created_at.asc()",
    )

    __table_args__ = (
        Index("ix_support_tickets_tenant", "tenant_id"),
        Index("ix_support_tickets_user", "user_id"),
        Index("ix_support_tickets_status", "status"),
        Index("ix_support_tickets_created_at", "created_at"),
    )


class SupportMessage(Base):
    __tablename__ = "support_messages"

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
        Index("ix_support_messages_ticket", "ticket_id"),
        Index("ix_support_messages_created_at", "created_at"),
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


# ---------------------------------------------------------------------------
# Event listeners: auto-sync email_hash when email is set on User
# ---------------------------------------------------------------------------

@event.listens_for(User.email, "set", propagate=True)
def _user_email_set_listener(target: User, value: str | None, oldvalue, initiator) -> None:
    """Automatically populate email_hash whenever User.email is assigned."""
    target.email_hash = compute_email_hash(value)
