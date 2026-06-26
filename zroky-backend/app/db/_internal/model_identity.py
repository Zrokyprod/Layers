from __future__ import annotations

from app.db._internal.model_shared import *


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
    scopes_json: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'[\"project:member\"]'"))
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    rotated_from_key_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
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
    slack_delivery_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'not_attempted'"),
    )
    slack_delivery_attempted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    slack_delivery_error: Mapped[str | None] = mapped_column(String(255), nullable=True)
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
    evaluation_settings_json: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'{}'"))
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
    approval_user_ids_json: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'[]'"))
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


# Event listeners: auto-sync email_hash when email is set on User

def _user_email_set_listener(target: User, value: str | None, oldvalue, initiator) -> None:
    """Automatically populate email_hash whenever User.email is assigned."""
    target.email_hash = compute_email_hash(value)


event.listen(User.email, "set", _user_email_set_listener)
