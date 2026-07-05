from __future__ import annotations

from app.db._internal.model_shared import *


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
    is_flaky: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    blocks_ci: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
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
    """One canonical call captured for a golden set.

    Active traces store explicit expected behavior in `expected_output_text`
    or `criteria_json`. Draft traces can retain source evidence without
    affecting replay pass/fail results. `project_id` is denormalised from
    the parent golden_set so the Postgres RLS policy can filter by tenant
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
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'draft'")
    )
    expected_output_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_output_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_evidence_json: Mapped[str | None] = mapped_column(Text, nullable=True)
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
        CheckConstraint(
            "status IN ('draft', 'active')",
            name="ck_golden_traces_status",
        ),
        Index("ix_golden_traces_set_id", "golden_set_id"),
        Index("ix_golden_traces_set_status", "golden_set_id", "status"),
        Index("ix_golden_traces_project_created", "project_id", "created_at"),
        Index("ix_golden_traces_call_id", "call_id"),
    )


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
    repository: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pull_request_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    head_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    base_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    workflow_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    workflow_attempt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    contract_version_ids_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    runner_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    run_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    run_token_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    superseded_by_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    candidate_release_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_releases.id", ondelete="SET NULL"), nullable=True
    )
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
            "status IN ('pending', 'running', 'pass', 'warn', 'fail', 'not_verified', 'error')",
            name="ck_replay_runs_status",
        ),
        Index("ix_replay_runs_project_created", "project_id", "created_at"),
        Index("ix_replay_runs_project_status", "project_id", "status"),
        Index("ix_replay_runs_project_head_sha", "project_id", "head_sha"),
        Index("ix_replay_runs_project_pr_created", "project_id", "repository", "pull_request_number", "created_at"),
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
            "status IN ('pass', 'fail', 'not_verified', 'error')",
            name="ck_replay_run_traces_status",
        ),
        Index("ix_replay_run_traces_run_id", "replay_run_id"),
        Index("ix_replay_run_traces_golden_trace_id", "golden_trace_id"),
        Index("ix_replay_run_traces_project_created", "project_id", "created_at"),
        Index("ix_replay_run_traces_run_status", "replay_run_id", "status"),
    )


class GoldenHistory(Base):
    """Audit trail for Golden set/trace contract changes."""

    __tablename__ = "golden_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    golden_set_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("golden_sets.id", ondelete="SET NULL"),
        nullable=True,
    )
    golden_trace_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("golden_traces.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    before_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_golden_history_project_created", "project_id", "created_at"),
        Index("ix_golden_history_set_created", "golden_set_id", "created_at"),
        Index("ix_golden_history_trace_created", "golden_trace_id", "created_at"),
    )


class CiGateOverride(Base):
    """Operator override for a regression-CI gate result."""

    __tablename__ = "ci_gate_overrides"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("replay_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    actor_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    original_status: Mapped[str] = mapped_column(String(16), nullable=False)
    effective_status: Mapped[str] = mapped_column(String(16), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "original_status IN ('pass', 'fail', 'warn', 'not_verified', 'error')",
            name="ck_ci_gate_overrides_original_status",
        ),
        CheckConstraint(
            "effective_status IN ('pass', 'warn')",
            name="ck_ci_gate_overrides_effective_status",
        ),
        Index("ix_ci_gate_overrides_project_run_created", "project_id", "run_id", "created_at"),
        Index("ix_ci_gate_overrides_run_created", "run_id", "created_at"),
    )


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
            "'SCHEMA_VIOLATION', 'LATENCY_REGRESSION', "
            "'TOOL_SELECTION_FAILURE', 'TOOL_CALL_FAILURE', "
            "'TOOL_ARGUMENT_MISMATCH', 'RAG_RETRIEVAL_MISSING', "
            "'RAG_GROUNDING_FAILURE', 'RETRIEVAL_MISSING', "
            "'UNSAFE_ACTION', 'TASK_OUTCOME_FAILURE', "
            "'TOKEN_USAGE_DRIFT', 'TOKEN_OVERFLOW', "
            "'RATE_LIMIT', 'AUTH_FAILURE', 'PROVIDER_ERROR', "
            "'LATENCY_ANOMALY', 'LATENCY_DRIFT', 'ERROR_RATE_DRIFT', "
            "'EMPTY_OUTPUT', 'OUTPUT_TRUNCATED', 'OUTPUT_LENGTH_DRIFT', "
            "'REPEATED_OUTPUT', 'BEHAVIORAL_DRIFT', 'UNKNOWN'"
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


class PilotAction(Base):
    """One autopilot decision against an anomaly.

    `tier` semantics (plan §6.3):
        1 = auto-revert (model_rollback, fallback_swap, retry_tune)
        2 = auto-PR    (open PR)
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
