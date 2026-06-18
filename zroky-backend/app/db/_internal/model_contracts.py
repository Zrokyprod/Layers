from __future__ import annotations

from app.db._internal.model_shared import *


class Environment(Base):
    """Project-scoped execution environment for captured and replayed agent runs."""

    __tablename__ = "environments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'custom'"))
    retention_policy_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    capture_policy_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("project_id", "name", name="ux_environments_project_name"),
        CheckConstraint(
            "type IN ('production', 'staging', 'development', 'ci', 'custom')",
            name="ck_environments_type",
        ),
        Index("ix_environments_project_type", "project_id", "type"),
        Index("ix_environments_project_created", "project_id", "created_at"),
    )


class Agent(Base):
    """A named agent within a project."""

    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    releases: Mapped[list["AgentRelease"]] = relationship(
        "AgentRelease",
        back_populates="agent",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint("project_id", "slug", name="ux_agents_project_slug"),
        Index("ix_agents_project_created", "project_id", "created_at"),
    )


class AgentRelease(Base):
    """Immutable-ish release identity derived from captured version metadata."""

    __tablename__ = "agent_releases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    environment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("environments.id", ondelete="CASCADE"), nullable=False
    )
    git_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    application_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_provider: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model_parameters_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tool_schema_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retrieval_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    release_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    deployed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )

    agent: Mapped[Agent] = relationship("Agent", back_populates="releases")

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "agent_id",
            "environment_id",
            "release_fingerprint",
            name="ux_agent_releases_project_agent_env_fp",
        ),
        Index("ix_agent_releases_project_created", "project_id", "created_at"),
        Index("ix_agent_releases_project_git_sha", "project_id", "git_sha"),
        Index("ix_agent_releases_project_fingerprint", "project_id", "release_fingerprint"),
    )


class RegressionContract(Base):
    """Stable product object for incident-to-regression protection."""

    __tablename__ = "regression_contracts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_issue_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'medium'"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'draft'"))
    active_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    owner_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    versions: Mapped[list["RegressionContractVersion"]] = relationship(
        "RegressionContractVersion",
        back_populates="contract",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="RegressionContractVersion.contract_id",
    )

    __table_args__ = (
        UniqueConstraint("project_id", "name", name="ux_regression_contracts_project_name"),
        CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_regression_contracts_severity",
        ),
        CheckConstraint(
            "status IN ('draft', 'active', 'quarantined', 'retired')",
            name="ck_regression_contracts_status",
        ),
        Index("ix_regression_contracts_project_status", "project_id", "status"),
        Index("ix_regression_contracts_project_created", "project_id", "created_at"),
    )


class RegressionContractVersion(Base):
    """Immutable contract specification version pinned by replay/CI evidence."""

    __tablename__ = "regression_contract_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    contract_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("regression_contracts.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    spec_version: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("'regression_contract_v1'")
    )
    spec_json: Mapped[str] = mapped_column(Text, nullable=False)
    fixture_set_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("golden_sets.id", ondelete="SET NULL"), nullable=True
    )
    baseline_release_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_releases.id", ondelete="SET NULL"), nullable=True
    )
    trial_policy_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'{\"required_trials\":10,\"critical_violation_tolerance\":0}'"),
    )
    evaluator_bundle_version: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("'default-v1'")
    )
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )

    contract: Mapped[RegressionContract] = relationship(
        "RegressionContract",
        back_populates="versions",
        foreign_keys=[contract_id],
    )

    __table_args__ = (
        UniqueConstraint(
            "contract_id",
            "version_number",
            name="ux_regression_contract_versions_contract_version",
        ),
        Index("ix_regression_contract_versions_project_created", "project_id", "created_at"),
        Index("ix_regression_contract_versions_project_fixture", "project_id", "fixture_set_id"),
    )


class RegressionContractRunResult(Base):
    """Per-contract-version verdict produced by repository or managed replay."""

    __tablename__ = "regression_contract_run_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    replay_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("replay_runs.id", ondelete="CASCADE"), nullable=False
    )
    contract_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("regression_contracts.id", ondelete="CASCADE"), nullable=False
    )
    contract_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("regression_contract_versions.id", ondelete="CASCADE"), nullable=False
    )
    candidate_release_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_releases.id", ondelete="SET NULL"), nullable=True
    )
    candidate_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    trial_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    required_trials: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("10"))
    critical_violation_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    evaluator_bundle_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    evidence_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "replay_run_id",
            "contract_version_id",
            name="ux_regression_contract_run_results_run_version",
        ),
        CheckConstraint(
            "status IN ('pass', 'fail', 'not_verified', 'error')",
            name="ck_regression_contract_run_results_status",
        ),
        Index("ix_regression_contract_run_results_project_run", "project_id", "replay_run_id"),
        Index(
            "ix_regression_contract_run_results_project_version",
            "project_id",
            "contract_version_id",
        ),
    )
