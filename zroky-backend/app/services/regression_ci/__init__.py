"""
Regression CI — Pre-deploy Replay CI Gate (Wedge 1).

Public surface (intentionally narrow). Everything else is internal.

Pipeline (orchestrator.run_regression_ci):
    1. Resolve BlastRadius     — blast_radius.detect()
    2. Resolve SampleSpec      — sampler.build_spec()
    3. Sample traces           — sampler.sample()
    4. Replay each trace       — (delegates to replay_executor with REAL_LLM resolver)
    5. Score diff per trace    — diff_metric.score()
    6. Cluster regressions     — cluster.cluster_regressions()
    7. Build RegressionCIReport — orchestrator assembles
    8. Format PR comment       — pr_comment.format_markdown()

Stability contract:
    - `RegressionCIReport` is a frozen schema (`schema_version="v1"`).
      Additive-only changes. Breaking changes require a new version.
    - All public dataclasses are JSON-serializable via `to_dict()`.
"""
from __future__ import annotations

from app.services.regression_ci.models import (
    SCHEMA_VERSION,
    BlastRadius,
    BlastRadiusCategory,
    BlastRadiusSource,
    DiffScore,
    DiffVerdict,
    RegressionCIReport,
    RegressionCluster,
    SampleSpec,
    SampleStratum,
    StratificationCounts,
    TraceResult,
)

__all__ = [
    "SCHEMA_VERSION",
    "BlastRadius",
    "BlastRadiusCategory",
    "BlastRadiusSource",
    "DiffScore",
    "DiffVerdict",
    "RegressionCIReport",
    "RegressionCluster",
    "SampleSpec",
    "SampleStratum",
    "StratificationCounts",
    "TraceResult",
]
