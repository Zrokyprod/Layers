from __future__ import annotations

from app.db._internal.model_shared import *


class BehavioralBaseline(Base):
    """Learned "normal" behavior for one (project, agent, workflow) key.

    Discovery pillar (Discover → Prove → Guard). The baseline is the
    label-free model of how a workflow normally behaves; the scorer measures
    deviation against it. Versioned so a rolling re-baseline supersedes the
    prior version instead of mutating it in place (audit + poisoning defence).

    This table is genuinely NEW — the existing schema has no equivalent. The
    discovery *output* (surfaced deviations) is written to the existing
    `anomalies` table via a new detector source, NOT a parallel findings
    table; this baseline is the one new persistent artifact discovery needs.

    `specificity`:
        'exact'        — (project, agent, workflow)
        'agent_only'   — workflow missing; coarser key, higher surface bar
        'project_only' — agent missing; coarsest key, highest surface bar
    `status`:
        'learning'   — warmup not met → emits NO behavioral findings
        'active'     — warm + healthy
        'suspect'    — learned from high-error traffic → never surfaces
        'superseded' — replaced by a newer version
    `features_json` carries the learned distributions (tool sequences,
    critical tools, output-shape mix, numeric stats, outcome mix).
    """

    __tablename__ = "behavioral_baselines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    workflow_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    behavior_key: Mapped[str] = mapped_column(String(512), nullable=False)
    specificity: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'exact'")
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'learning'")
    )
    sample_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    distinct_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    error_rate: Mapped[float] = mapped_column(
        Numeric(8, 6), nullable=False, server_default=text("0")
    )
    window_start_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    window_end_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    features_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id", "behavior_key", "version",
            name="ux_behavioral_baselines_key_version",
        ),
        CheckConstraint(
            "specificity IN ('exact', 'agent_only', 'project_only')",
            name="ck_behavioral_baselines_specificity",
        ),
        CheckConstraint(
            "status IN ('learning', 'active', 'suspect', 'superseded')",
            name="ck_behavioral_baselines_status",
        ),
        Index(
            "ix_behavioral_baselines_project_key_status",
            "project_id", "behavior_key", "status",
        ),
        Index("ix_behavioral_baselines_project_status", "project_id", "status"),
    )


class DiscoveryScanState(Base):
    """Per-project watermark for idempotent Discovery scans.

    The scorer reads append-only production calls. Without a durable watermark,
    every scheduled scan would re-score the same rows and inflate recurrence /
    occurrence counts for already-surfaced behavioral anomalies.
    """

    __tablename__ = "discovery_scan_state"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    last_scanned_call_created_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime, nullable=True
    )
    last_scanned_call_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("project_id", name="uq_discovery_scan_state_project_id"),
        Index(
            "ix_discovery_scan_state_project_watermark",
            "project_id",
            "last_scanned_call_created_at",
        ),
    )
