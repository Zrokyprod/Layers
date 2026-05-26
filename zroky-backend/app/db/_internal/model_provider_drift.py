from __future__ import annotations

from app.db._internal.model_shared import *


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
