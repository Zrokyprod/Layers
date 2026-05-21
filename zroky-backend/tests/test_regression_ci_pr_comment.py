"""Tests for `app.services.regression_ci.pr_comment` markdown formatter.

Coverage:
  - Verdict emoji + headline (pass / fail / error variants).
  - Hidden marker present and unchanged (`<!-- zroky-regression-ci -->`).
  - Stats table contains all key metrics.
  - Blast-radius section reflects category, source, target, files.
  - Cluster section renders top-N with collapsed sample input.
  - Stratification details collapsed in <details>.
  - Notes section appears when notes are non-empty, omitted otherwise.
  - Dashboard link uses provided base when set; placeholder otherwise.
  - Deterministic — same report yields identical bytes.
"""
from __future__ import annotations

import pytest

from app.services.regression_ci.models import (
    SCHEMA_VERSION,
    BlastRadius,
    BlastRadiusCategory,
    BlastRadiusSource,
    RegressionCIReport,
    RegressionCluster,
    SampleSpec,
    StratificationCounts,
)
from app.services.regression_ci.pr_comment import (
    COMMENT_MARKER,
    format_markdown,
)


# ── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture()
def base_blast() -> BlastRadius:
    return BlastRadius(
        category=BlastRadiusCategory.TOOL_PROMPT,
        source=BlastRadiusSource.DECLARED,
        files=("prompts/tools/refund.md",),
        target="refund",
        confidence=1.0,
    )


@pytest.fixture()
def base_spec(base_blast: BlastRadius) -> SampleSpec:
    return SampleSpec(
        target_total=200,
        stratification={
            "pass_history": 0.5,
            "fail_history": 0.3,
            "rare_cluster": 0.1,
            "recent_24h": 0.1,
        },
        blast_radius=base_blast,
    )


def _mk_report(
    *, base_blast: BlastRadius, base_spec: SampleSpec,
    verdict: str = "fail",
    trace_count: int = 200, regressed_count: int = 12,
    error_count: int = 0,
    threshold: float = 0.02,
    clusters: tuple[RegressionCluster, ...] = (),
    notes: tuple[str, ...] = (),
    outcome_attribution=None,
) -> RegressionCIReport:
    return RegressionCIReport(
        schema_version=SCHEMA_VERSION,
        run_id="run-abc",
        project_id="proj-x",
        git_sha="deadbeef",
        blast_radius=base_blast,
        sample_spec=base_spec,
        stratification_realised=StratificationCounts(
            pass_history=100, fail_history=60, rare_cluster=20, recent_24h=20,
        ),
        trace_count=trace_count,
        regressed_count=regressed_count,
        regression_rate=(regressed_count / trace_count) if trace_count else 0.0,
        threshold=threshold,
        verdict=verdict,
        error_count=error_count,
        error_rate=(error_count / trace_count) if trace_count else 0.0,
        judge_used_count=15,
        cost_usd=4.20,
        duration_seconds=89,
        clusters=clusters,
        outcome_attribution=outcome_attribution,
        notes=notes,
    )


# ── tests ──────────────────────────────────────────────────────────────────


class TestHeader:
    def test_pass_emoji(self, base_blast, base_spec) -> None:
        md = format_markdown(_mk_report(
            base_blast=base_blast, base_spec=base_spec,
            verdict="pass", regressed_count=1,
        ))
        assert "✅" in md
        assert "Replay CI passed" in md

    def test_fail_emoji(self, base_blast, base_spec) -> None:
        md = format_markdown(_mk_report(
            base_blast=base_blast, base_spec=base_spec, verdict="fail",
        ))
        assert "📉" in md
        assert "Replay CI regressed" in md

    def test_error_emoji(self, base_blast, base_spec) -> None:
        md = format_markdown(_mk_report(
            base_blast=base_blast, base_spec=base_spec,
            verdict="error", error_count=20,
        ))
        assert "⚠️" in md
        assert "Replay CI errored" in md

    def test_headline_includes_counts(self, base_blast, base_spec) -> None:
        md = format_markdown(_mk_report(
            base_blast=base_blast, base_spec=base_spec,
            trace_count=1000, regressed_count=12,
        ))
        assert "12 of 1000" in md
        assert "1.20%" in md  # 12/1000 = 1.20%


class TestStructure:
    def test_marker_present(self, base_blast, base_spec) -> None:
        md = format_markdown(_mk_report(
            base_blast=base_blast, base_spec=base_spec,
        ))
        assert md.lstrip().startswith(COMMENT_MARKER)

    def test_stats_table_has_all_rows(self, base_blast, base_spec) -> None:
        md = format_markdown(_mk_report(
            base_blast=base_blast, base_spec=base_spec,
        ))
        for label in [
            "Verdict",
            "Regression rate",
            "Error rate",
            "Judge invocations",
            "Cost",
            "Duration",
        ]:
            assert label in md, f"stats table missing {label!r}"

    def test_blast_radius_section_includes_target(self, base_blast, base_spec) -> None:
        md = format_markdown(_mk_report(
            base_blast=base_blast, base_spec=base_spec,
        ))
        assert "Blast radius" in md
        assert "`tool_prompt`" in md
        assert "`refund`" in md
        assert "prompts/tools/refund.md" in md

    def test_clusters_rendered(self, base_blast, base_spec) -> None:
        cluster = RegressionCluster(
            label="refund_de",
            keywords=("refund", "policy", "german"),
            size=6,
            sample_trace_id="t-99",
            sample_input="What is the refund policy in DE?",
        )
        md = format_markdown(_mk_report(
            base_blast=base_blast, base_spec=base_spec,
            clusters=(cluster,),
        ))
        assert "refund_de" in md
        assert "6 traces" in md
        assert "refund" in md and "policy" in md and "german" in md
        assert "t-99" in md
        assert "<details>" in md  # collapsed sample input

    def test_no_clusters_omits_section(self, base_blast, base_spec) -> None:
        md = format_markdown(_mk_report(
            base_blast=base_blast, base_spec=base_spec, clusters=(),
        ))
        assert "regression cluster" not in md.lower()

    def test_notes_rendered_when_present(self, base_blast, base_spec) -> None:
        md = format_markdown(_mk_report(
            base_blast=base_blast, base_spec=base_spec,
            notes=("stub mode active", "pass_history under-filled"),
        ))
        assert "### Notes" in md
        assert "stub mode active" in md
        assert "pass_history under-filled" in md

    def test_notes_section_omitted_when_empty(self, base_blast, base_spec) -> None:
        md = format_markdown(_mk_report(
            base_blast=base_blast, base_spec=base_spec, notes=(),
        ))
        assert "### Notes" not in md

    def test_stratification_collapsed(self, base_blast, base_spec) -> None:
        md = format_markdown(_mk_report(
            base_blast=base_blast, base_spec=base_spec,
        ))
        # The stratification block is inside a <details> to keep the comment small.
        assert "<details><summary>Sampling stratification" in md
        assert "pass_history" in md
        assert "realised total" in md.lower()


class TestFooter:
    def test_dashboard_link_when_base_provided(self, base_blast, base_spec) -> None:
        md = format_markdown(
            _mk_report(base_blast=base_blast, base_spec=base_spec),
            dashboard_base="https://app.zroky.ai",
        )
        assert "https://app.zroky.ai/replay-runs/run-abc" in md

    def test_placeholder_when_no_base(self, base_blast, base_spec) -> None:
        md = format_markdown(_mk_report(
            base_blast=base_blast, base_spec=base_spec,
        ))
        # When base not set, footer keeps a textual reference
        assert "/replay-runs/run-abc" in md

    def test_footer_metadata(self, base_blast, base_spec) -> None:
        md = format_markdown(_mk_report(
            base_blast=base_blast, base_spec=base_spec,
        ))
        assert "run-abc" in md
        assert "deadbeef" in md
        assert SCHEMA_VERSION in md


class TestDeterminism:
    def test_same_report_same_bytes(self, base_blast, base_spec) -> None:
        report = _mk_report(base_blast=base_blast, base_spec=base_spec)
        a = format_markdown(report)
        b = format_markdown(report)
        assert a == b


class TestOutcomeAttribution:
    """Wedge 4 — PR comment shows the cost-of-failure $-tag when the
    orchestrator attaches an outcome_attribution snapshot."""

    def test_section_omitted_when_none(self, base_blast, base_spec) -> None:
        md = format_markdown(_mk_report(
            base_blast=base_blast, base_spec=base_spec,
            outcome_attribution=None,
        ))
        assert "Cost-of-failure attribution" not in md
        assert "Estimated risk" not in md

    def test_renders_estimated_risk_line(self, base_blast, base_spec) -> None:
        snap = {
            "outcome_cost_30d_usd": 11840.0,
            "failed_call_count_30d": 247,
            "regressed_in_pr": 12,
            "cost_per_failed_call_usd": 47.94,
            "estimated_monthly_risk_usd": 575.30,
            "method": "linear_extrapolation",
        }
        md = format_markdown(_mk_report(
            base_blast=base_blast, base_spec=base_spec,
            outcome_attribution=snap,
        ))
        assert "Cost-of-failure attribution" in md
        assert "Estimated risk if merged" in md
        assert "$575" in md
        assert "12 regressed traces" in md
        assert "$11,840" in md
        assert "247" in md
        assert "linear extrapolation" in md.lower()

    def test_zero_regressed_renders_no_risk_message(self, base_blast, base_spec) -> None:
        snap = {
            "outcome_cost_30d_usd": 5000.0,
            "failed_call_count_30d": 80,
            "regressed_in_pr": 0,
            "cost_per_failed_call_usd": 62.5,
            "estimated_monthly_risk_usd": 0.0,
            "method": "linear_extrapolation",
        }
        md = format_markdown(_mk_report(
            base_blast=base_blast, base_spec=base_spec,
            verdict="pass", regressed_count=0,
            outcome_attribution=snap,
        ))
        assert "Cost-of-failure attribution" in md
        assert "no measurable" in md
        assert "$5,000" in md

    def test_section_appears_above_clusters(self, base_blast, base_spec) -> None:
        snap = {
            "outcome_cost_30d_usd": 1000.0, "failed_call_count_30d": 10,
            "regressed_in_pr": 2, "cost_per_failed_call_usd": 100.0,
            "estimated_monthly_risk_usd": 200.0, "method": "linear_extrapolation",
        }
        cluster = RegressionCluster(
            label="refund_de", keywords=("refund",), size=2,
            sample_trace_id="t-1", sample_input="x",
        )
        md = format_markdown(_mk_report(
            base_blast=base_blast, base_spec=base_spec,
            outcome_attribution=snap, clusters=(cluster,),
        ))
        attribution_pos = md.index("Cost-of-failure attribution")
        cluster_pos = md.index("regression cluster")
        assert attribution_pos < cluster_pos, (
            "Outcome attribution should be rendered above the clusters "
            "section so executives skim the $ first."
        )
