from __future__ import annotations

from app.db._internal.model_shared import *


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


class Subscription(Base):
    """Per-org subscription. Replaces `TenantSubscription`.

    `org_id` is the billing entity (plan §5.1). The `orgs` table does not
    yet exist; for now `org_id` equals the project_id of the org's primary
    project. When orgs are introduced, a FK will be added without renaming.
    """

    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    org_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payment_provider: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'razorpay'")
    )
    payment_customer_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payment_subscription_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payment_request_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    plan_code: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'active'")
    )
    seats: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    current_period_end: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    trial_end: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    # Module 12 / migration 0062 — Reliability SLA tier (plan §11.4).
    # 'none' for Free/Pro/Plus; 'team'/'enterprise' for tiers that
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
        UniqueConstraint(
            "payment_subscription_ref",
            name="ux_subscriptions_payment_subscription_ref",
        ),
        CheckConstraint(
            "status IN ('trialing', 'active', 'past_due', 'canceled', 'unpaid', 'incomplete')",
            name="ck_subscriptions_status",
        ),
        CheckConstraint(
            "sla_tier IN ('none', 'team', 'enterprise')",
            name="ck_subscriptions_sla_tier",
        ),
        Index("ix_subscriptions_payment_provider", "payment_provider"),
        Index("ix_subscriptions_payment_customer_ref", "payment_customer_ref"),
        Index("ix_subscriptions_payment_request_ref", "payment_request_ref"),
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


class BillingEvent(Base):
    """Provider-neutral billing event audit log.

    The table records each billing provider event before applying it to
    subscriptions and entitlements.
    """

    __tablename__ = "billing_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_created_at: Mapped[datetime | None] = mapped_column(
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
    affected_org_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_event_id",
            name="ux_billing_events_provider_event_id",
        ),
        CheckConstraint(
            "result IN ('pending', 'applied', 'skipped', 'failed')",
            name="ck_billing_events_result",
        ),
        Index("ix_billing_events_provider", "provider"),
        Index("ix_billing_events_event_type", "event_type"),
        Index("ix_billing_events_received_at", "received_at"),
        Index("ix_billing_events_affected_org_id", "affected_org_id"),
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
