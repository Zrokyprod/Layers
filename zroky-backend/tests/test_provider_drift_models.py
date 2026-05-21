"""Layer 2 unit tests for `app.services.provider_drift.models`."""
from __future__ import annotations

from datetime import date

import pytest

from app.services.provider_drift.models import (
    DriftAlertSpec,
    DriftMetric,
    ModelSpec,
    ProbeOutcome,
    ProbeResult,
    PromptSpec,
)


class TestPromptSpec:
    def test_valid(self) -> None:
        s = PromptSpec(
            id="math_001",
            category="math",
            prompt_text="2+2?",
            expected_signal={"kind": "must_contain", "value": "4"},
        )
        assert s.id == "math_001"
        assert s.active is True
        assert s.version == 1

    def test_missing_id(self) -> None:
        with pytest.raises(ValueError, match="id required"):
            PromptSpec(id="", category="math", prompt_text="x", expected_signal={})

    def test_invalid_category(self) -> None:
        with pytest.raises(ValueError, match="category invalid"):
            PromptSpec(id="x", category="bogus", prompt_text="x", expected_signal={})

    @pytest.mark.parametrize("bad", [0, -1, 8193])
    def test_max_tokens_range(self, bad: int) -> None:
        with pytest.raises(ValueError, match="max_tokens"):
            PromptSpec(
                id="x",
                category="math",
                prompt_text="x",
                expected_signal={},
                max_tokens=bad,
            )

    def test_to_dict_roundtrip(self) -> None:
        s = PromptSpec(
            id="r_1",
            category="refusal",
            prompt_text="...",
            expected_signal={"kind": "must_refuse", "value": True},
            max_tokens=64,
        )
        d = s.to_dict()
        assert d["id"] == "r_1"
        assert d["expected_signal"]["value"] is True
        assert d["max_tokens"] == 64


class TestModelSpec:
    def test_valid(self) -> None:
        m = ModelSpec(
            id="openai_gpt_4o",
            provider="openai",
            model_id="gpt-4o",
            display_name="GPT-4o",
            family="gpt-4o",
        )
        assert m.active is True

    def test_invalid_provider(self) -> None:
        with pytest.raises(ValueError, match="provider"):
            ModelSpec(
                id="x",
                provider="aol",
                model_id="m",
                display_name="d",
                family="f",
            )


class TestProbeResult:
    def test_ok(self) -> None:
        r = ProbeResult(
            prompt_id="p1",
            model_id="m1",
            outcome=ProbeOutcome.OK,
            judge_pass=True,
            judge_score=0.95,
            cost_usd=0.001,
        )
        assert r.is_ok
        assert r.judge_pass is True

    def test_error_strips_judge(self) -> None:
        r = ProbeResult(
            prompt_id="p1",
            model_id="m1",
            outcome=ProbeOutcome.RATE_LIMITED,
            judge_pass=True,
            judge_score=0.95,
        )
        assert not r.is_ok
        assert r.judge_pass is None
        assert r.judge_score is None

    def test_invalid_outcome(self) -> None:
        with pytest.raises(ValueError, match="outcome invalid"):
            ProbeResult(prompt_id="p1", model_id="m1", outcome="bogus")

    def test_to_dict_serializes_embedding(self) -> None:
        r = ProbeResult(
            prompt_id="p",
            model_id="m",
            outcome=ProbeOutcome.OK,
            output_embedding=(0.1, 0.2, 0.3),
            embedding_model="text-embedding-3-small",
        )
        d = r.to_dict()
        assert d["output_embedding"] == [0.1, 0.2, 0.3]
        assert d["embedding_model"] == "text-embedding-3-small"


class TestDriftMetric:
    def test_delta_pp(self) -> None:
        m = DriftMetric(
            model_id="m",
            category="math",
            current_date=date(2026, 5, 18),
            baseline_start=date(2026, 5, 11),
            baseline_end=date(2026, 5, 17),
            pass_rate_current=0.50,
            pass_rate_baseline=0.80,
            pass_rate_stddev=0.05,
            judge_z=-6.0,
            embedding_z=-3.0,
            coverage_current=0.95,
            coverage_baseline_min=0.90,
            sample_size_current=20,
            sample_size_baseline=140,
        )
        assert m.delta_pp == pytest.approx(-30.0)
        assert m.to_dict()["delta_pp"] == pytest.approx(-30.0)


class TestDriftAlertSpec:
    def _base(self, **kw: object) -> DriftAlertSpec:
        defaults = dict(
            model_id="m",
            category="math",
            current_date=date(2026, 5, 18),
            baseline_start=date(2026, 5, 11),
            baseline_end=date(2026, 5, 17),
            pass_rate_current=0.5,
            pass_rate_baseline=0.8,
            judge_z=-6.0,
            embedding_z=-3.0,
            delta_pp=-30.0,
            severity="critical",
            headline="GPT-4o behavior shifted on 2026-05-18 (math: -30.0pp)",
        )
        defaults.update(kw)
        return DriftAlertSpec(**defaults)  # type: ignore[arg-type]

    def test_valid(self) -> None:
        a = self._base()
        assert a.severity == "critical"
        assert "math" in a.headline

    def test_invalid_severity(self) -> None:
        with pytest.raises(ValueError, match="severity"):
            self._base(severity="emergency")

    def test_empty_headline(self) -> None:
        with pytest.raises(ValueError, match="headline"):
            self._base(headline="")

    def test_evidence_json_deterministic(self) -> None:
        a = self._base(evidence={"b": 2, "a": 1})
        # Sorted keys → deterministic JSON
        assert a.evidence_json() == '{"a":1,"b":2}'
