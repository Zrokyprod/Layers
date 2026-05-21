"""Tests for `app.services.regression_ci.models` — frozen schema invariants.

These tests are the contract guard. If any assertion changes, the
SCHEMA_VERSION must be bumped (or a new field is purely additive).
"""
from __future__ import annotations

import pytest

from app.services.regression_ci.models import (
    DEFAULT_SAMPLE_SIZES,
    DEFAULT_STRATIFICATION,
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
    VALID_CATEGORIES,
    VALID_SOURCES,
    VALID_VERDICTS,
)


# ── BlastRadius ─────────────────────────────────────────────────────────────


class TestBlastRadius:
    def test_valid_construction(self) -> None:
        br = BlastRadius(
            category=BlastRadiusCategory.TOOL_PROMPT,
            source=BlastRadiusSource.AUTO_DETECTED,
            files=("prompts/tools/refund.md",),
            target="refund",
            confidence=0.85,
        )
        assert br.category == "tool_prompt"
        assert br.confidence == 0.85
        assert br.to_dict()["files"] == ["prompts/tools/refund.md"]

    def test_invalid_category_rejected(self) -> None:
        with pytest.raises(ValueError, match="invalid blast radius category"):
            BlastRadius(
                category="not_a_real_category",
                source=BlastRadiusSource.AUTO_DETECTED,
            )

    def test_invalid_source_rejected(self) -> None:
        with pytest.raises(ValueError, match="invalid blast radius source"):
            BlastRadius(
                category=BlastRadiusCategory.SYSTEM_PROMPT,
                source="psychic_intuition",
            )

    def test_confidence_out_of_range_rejected(self) -> None:
        with pytest.raises(ValueError, match="confidence must be in"):
            BlastRadius(
                category=BlastRadiusCategory.UNKNOWN,
                source=BlastRadiusSource.AUTO_DETECTED,
                confidence=1.5,
            )

    def test_to_dict_round_trips_through_json(self) -> None:
        import json
        br = BlastRadius(
            category=BlastRadiusCategory.SYSTEM_PROMPT,
            source=BlastRadiusSource.DECLARED,
            files=("a.md", "b.md"),
            confidence=0.999999,
        )
        # Must be JSON-serializable; round to 4 places means 1.0 not 0.999999
        encoded = json.dumps(br.to_dict())
        decoded = json.loads(encoded)
        assert decoded["confidence"] == 1.0
        assert decoded["files"] == ["a.md", "b.md"]


class TestDefaultSampleSizes:
    """Lock the default sample sizes — these drive customer cost.

    If a test here fails after a code change, it's an intentional product
    decision and the customer-facing pricing/threshold docs MUST update.
    """

    def test_all_categories_have_defaults(self) -> None:
        assert set(DEFAULT_SAMPLE_SIZES.keys()) == VALID_CATEGORIES

    def test_system_prompt_is_largest(self) -> None:
        assert DEFAULT_SAMPLE_SIZES[BlastRadiusCategory.SYSTEM_PROMPT] >= 5000

    def test_tool_prompt_is_smallest(self) -> None:
        # smaller blast → smaller sample
        assert DEFAULT_SAMPLE_SIZES[BlastRadiusCategory.TOOL_PROMPT] <= 200

    def test_unknown_is_conservative(self) -> None:
        # UNKNOWN must sit between TOOL_PROMPT and SYSTEM_PROMPT
        unk = DEFAULT_SAMPLE_SIZES[BlastRadiusCategory.UNKNOWN]
        assert unk >= DEFAULT_SAMPLE_SIZES[BlastRadiusCategory.TOOL_PROMPT]
        assert unk <= DEFAULT_SAMPLE_SIZES[BlastRadiusCategory.SYSTEM_PROMPT]


# ── SampleSpec / Stratification ────────────────────────────────────────────


class TestSampleSpec:
    @pytest.fixture()
    def br(self) -> BlastRadius:
        return BlastRadius(
            category=BlastRadiusCategory.UNKNOWN,
            source=BlastRadiusSource.AUTO_DETECTED,
        )

    def test_default_stratification_sums_to_one(self) -> None:
        assert abs(sum(DEFAULT_STRATIFICATION.values()) - 1.0) < 1e-6

    def test_invalid_stratum_rejected(self, br: BlastRadius) -> None:
        with pytest.raises(ValueError, match="unknown stratum"):
            SampleSpec(
                target_total=1000,
                stratification={"made_up_stratum": 1.0},
                blast_radius=br,
            )

    def test_stratification_must_sum_to_one(self, br: BlastRadius) -> None:
        with pytest.raises(ValueError, match="stratification must sum"):
            SampleSpec(
                target_total=1000,
                stratification={SampleStratum.PASS_HISTORY: 0.5},
                blast_radius=br,
            )

    def test_per_stratum_target_floors(self, br: BlastRadius) -> None:
        spec = SampleSpec(
            target_total=10,
            stratification={
                SampleStratum.PASS_HISTORY: 0.50,
                SampleStratum.FAIL_HISTORY: 0.30,
                SampleStratum.RARE_CLUSTER: 0.10,
                SampleStratum.RECENT_24H: 0.10,
            },
            blast_radius=br,
        )
        targets = spec.per_stratum_target()
        assert targets[SampleStratum.PASS_HISTORY] == 5
        assert targets[SampleStratum.FAIL_HISTORY] == 3
        assert targets[SampleStratum.RARE_CLUSTER] == 1
        assert targets[SampleStratum.RECENT_24H] == 1


class TestStratificationCounts:
    def test_realised_total(self) -> None:
        c = StratificationCounts(
            pass_history=10, fail_history=20, rare_cluster=3, recent_24h=5,
        )
        assert c.realised_total == 38

    def test_to_dict_includes_total(self) -> None:
        c = StratificationCounts(pass_history=1, fail_history=2)
        d = c.to_dict()
        assert d["realised_total"] == 3


# ── DiffScore ───────────────────────────────────────────────────────────────


class TestDiffScore:
    def test_valid_pass(self) -> None:
        s = DiffScore(verdict=DiffVerdict.PASS, jaccard=0.95, cosine=0.97)
        assert s.verdict == "pass"
        assert s.judge_used is False

    def test_invalid_verdict(self) -> None:
        with pytest.raises(ValueError, match="invalid verdict"):
            DiffScore(verdict="maybe", jaccard=0.5)

    def test_jaccard_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="jaccard must be in"):
            DiffScore(verdict=DiffVerdict.PASS, jaccard=1.5)

    def test_cosine_optional(self) -> None:
        s = DiffScore(verdict=DiffVerdict.INCONCLUSIVE, jaccard=0.5, cosine=None)
        assert s.cosine is None
        assert s.to_dict()["cosine"] is None


# ── RegressionCIReport ──────────────────────────────────────────────────────


class TestRegressionCIReport:
    @pytest.fixture()
    def br(self) -> BlastRadius:
        return BlastRadius(
            category=BlastRadiusCategory.TOOL_PROMPT,
            source=BlastRadiusSource.DECLARED,
            target="refund",
        )

    @pytest.fixture()
    def spec(self, br: BlastRadius) -> SampleSpec:
        return SampleSpec(
            target_total=200,
            stratification=DEFAULT_STRATIFICATION,
            blast_radius=br,
        )

    def test_schema_version_pinned(self) -> None:
        # If this fails, an additive change accidentally bumped SCHEMA_VERSION
        # (or a breaking change correctly bumped it). Validate intent before
        # editing this assertion.
        assert SCHEMA_VERSION == "v1"

    def test_pass_verdict_round_trip(self, br: BlastRadius, spec: SampleSpec) -> None:
        report = RegressionCIReport(
            schema_version=SCHEMA_VERSION,
            run_id="run-123",
            project_id="proj-1",
            git_sha="abc123",
            blast_radius=br,
            sample_spec=spec,
            stratification_realised=StratificationCounts(pass_history=100),
            trace_count=100,
            regressed_count=1,
            regression_rate=0.01,
            threshold=0.02,
            verdict="pass",
        )
        d = report.to_dict()
        assert d["verdict"] == "pass"
        assert d["regression_rate"] == 0.01
        assert d["schema_version"] == "v1"

    def test_invalid_verdict_rejected(self, br: BlastRadius, spec: SampleSpec) -> None:
        with pytest.raises(ValueError, match="invalid run verdict"):
            RegressionCIReport(
                schema_version=SCHEMA_VERSION,
                run_id="r",
                project_id="p",
                git_sha=None,
                blast_radius=br,
                sample_spec=spec,
                stratification_realised=StratificationCounts(),
                trace_count=0,
                regressed_count=0,
                regression_rate=0.0,
                threshold=0.02,
                verdict="awesome",  # <-- invalid
            )

    def test_threshold_out_of_range(self, br: BlastRadius, spec: SampleSpec) -> None:
        with pytest.raises(ValueError, match="threshold out of range"):
            RegressionCIReport(
                schema_version=SCHEMA_VERSION,
                run_id="r",
                project_id="p",
                git_sha=None,
                blast_radius=br,
                sample_spec=spec,
                stratification_realised=StratificationCounts(),
                trace_count=0,
                regressed_count=0,
                regression_rate=0.0,
                threshold=2.0,  # invalid
                verdict="pass",
            )

    def test_clusters_serialize(self, br: BlastRadius, spec: SampleSpec) -> None:
        cluster = RegressionCluster(
            label="refund_de",
            keywords=("refund", "policy", "german"),
            size=5,
            sample_trace_id="t-1",
            sample_input="What's the refund policy in DE?",
        )
        report = RegressionCIReport(
            schema_version=SCHEMA_VERSION,
            run_id="r", project_id="p", git_sha=None,
            blast_radius=br, sample_spec=spec,
            stratification_realised=StratificationCounts(),
            trace_count=1, regressed_count=1,
            regression_rate=1.0, threshold=0.0,
            verdict="fail",
            clusters=(cluster,),
        )
        d = report.to_dict()
        assert d["clusters"][0]["label"] == "refund_de"
        assert d["clusters"][0]["size"] == 5
