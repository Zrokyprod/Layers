"""Layer 3 tests for the probe runner."""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Sequence

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import (
    ProviderDriftModel,
    ProviderDriftProbe,
    ProviderDriftRun,
)
from app.services.provider_drift.models import (
    ModelSpec,
    ProbeOutcome,
    PromptSpec,
)
from app.services.provider_drift.runner import (
    BudgetTracker,
    ProviderCallResult,
    call_with_retry,
    execute_run,
    load_active_models,
    load_active_prompts,
)
from app.services.provider_drift.prompt_suite import sync_prompts_to_db
from app.services.provider_drift.registry import sync_models_to_db


# ── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture()
def session(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'pdw.db'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    s = factory()
    try:
        yield s
    finally:
        s.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def model_spec() -> ModelSpec:
    return ModelSpec(
        id="openai_gpt_4o_mini",
        provider="openai",
        model_id="gpt-4o-mini",
        display_name="GPT-4o mini",
        family="gpt-4o",
    )


def _prompts(*, n: int = 3, category: str = "math") -> tuple[PromptSpec, ...]:
    return tuple(
        PromptSpec(
            id=f"{category}_{i:03d}",
            category=category,
            prompt_text=f"prompt {i}",
            expected_signal={"kind": "must_contain", "value": str(i)},
            max_tokens=32,
        )
        for i in range(n)
    )


# ── stub clients ────────────────────────────────────────────────────────────


class StubClient:
    """Returns a fixed sequence of ProviderCallResult."""

    def __init__(self, results: Sequence[ProviderCallResult]) -> None:
        self._results = list(results)
        self.calls: list[tuple[str, str]] = []

    def call(self, *, model_spec: ModelSpec, prompt: PromptSpec) -> ProviderCallResult:
        self.calls.append((model_spec.id, prompt.id))
        if not self._results:
            raise AssertionError("StubClient ran out of pre-canned results")
        return self._results.pop(0)


class CycleClient:
    """Always returns the same ProviderCallResult."""

    def __init__(self, result: ProviderCallResult) -> None:
        self._result = result
        self.calls = 0

    def call(self, *, model_spec: ModelSpec, prompt: PromptSpec) -> ProviderCallResult:
        self.calls += 1
        return self._result


class StubEmbedder:
    def __init__(self, dim: int = 4) -> None:
        self._dim = dim
        self.model_tag = "stub-embedder-v1"
        self.calls = 0

    def embed(self, text: str) -> tuple[float, ...] | None:
        self.calls += 1
        # Deterministic embedding based on text length.
        return tuple(float((len(text) + i) % 7) / 7.0 for i in range(self._dim))


class FlakyEmbedder:
    """Always raises."""

    def __init__(self) -> None:
        self.model_tag = "flaky"

    def embed(self, text: str) -> tuple[float, ...] | None:
        raise RuntimeError("embedder boom")


# ── BudgetTracker ───────────────────────────────────────────────────────────


class TestBudgetTracker:
    def test_basic_charging(self) -> None:
        b = BudgetTracker(1.0)
        assert b.remaining == 1.0
        b.charge(0.3)
        assert b.spent == pytest.approx(0.3)
        assert b.remaining == pytest.approx(0.7)

    def test_would_exceed(self) -> None:
        b = BudgetTracker(1.0)
        b.charge(0.7)
        assert b.would_exceed(0.4) is True
        assert b.would_exceed(0.2) is False

    def test_negative_charge_ignored(self) -> None:
        b = BudgetTracker(1.0)
        b.charge(-0.5)
        assert b.spent == 0.0

    def test_negative_budget_rejected(self) -> None:
        with pytest.raises(ValueError):
            BudgetTracker(-1.0)


# ── call_with_retry ─────────────────────────────────────────────────────────


class TestCallWithRetry:
    def test_no_retry_on_ok(self, model_spec) -> None:
        client = StubClient([
            ProviderCallResult(outcome=ProbeOutcome.OK, output_text="x"),
        ])
        result = call_with_retry(
            client, model_spec=model_spec, prompt=_prompts(n=1)[0],
            sleep=lambda _s: None,
        )
        assert result.outcome == ProbeOutcome.OK
        assert len(client.calls) == 1

    def test_retries_rate_limited(self, model_spec) -> None:
        client = StubClient([
            ProviderCallResult(outcome=ProbeOutcome.RATE_LIMITED),
            ProviderCallResult(outcome=ProbeOutcome.RATE_LIMITED),
            ProviderCallResult(outcome=ProbeOutcome.OK, output_text="x"),
        ])
        result = call_with_retry(
            client, model_spec=model_spec, prompt=_prompts(n=1)[0],
            max_attempts=3, sleep=lambda _s: None,
        )
        assert result.outcome == ProbeOutcome.OK
        assert len(client.calls) == 3

    def test_gives_up_after_max(self, model_spec) -> None:
        client = CycleClient(ProviderCallResult(outcome=ProbeOutcome.TIMEOUT))
        result = call_with_retry(
            client, model_spec=model_spec, prompt=_prompts(n=1)[0],
            max_attempts=3, sleep=lambda _s: None,
        )
        assert result.outcome == ProbeOutcome.TIMEOUT
        assert client.calls == 3

    def test_does_not_retry_terminal_error(self, model_spec) -> None:
        client = StubClient([
            ProviderCallResult(outcome=ProbeOutcome.ERROR, error_code="HTTP_500"),
        ])
        result = call_with_retry(
            client, model_spec=model_spec, prompt=_prompts(n=1)[0],
            max_attempts=3, sleep=lambda _s: None,
        )
        assert result.outcome == ProbeOutcome.ERROR
        assert len(client.calls) == 1


# ── execute_run ─────────────────────────────────────────────────────────────


class TestExecuteRun:
    def test_happy_path_complete(self, session, model_spec) -> None:
        # Seed model + prompts
        sync_models_to_db(session, registry=(model_spec,))
        prompts = (
            PromptSpec(
                id="math_001",
                category="math",
                prompt_text="2 + 2?",
                expected_signal={"kind": "must_contain", "value": "4"},
            ),
            PromptSpec(
                id="math_002",
                category="math",
                prompt_text="3 * 3?",
                expected_signal={"kind": "must_contain", "value": "9"},
            ),
        )
        sync_prompts_to_db(session, suite=prompts)
        session.commit()

        client = StubClient([
            ProviderCallResult(
                outcome=ProbeOutcome.OK, output_text="4", cost_usd=0.0001
            ),
            ProviderCallResult(
                outcome=ProbeOutcome.OK, output_text="9", cost_usd=0.0001
            ),
        ])

        outcome = execute_run(
            db=session,
            model_spec=model_spec,
            run_date=date(2026, 5, 18),
            prompts=prompts,
            provider_client=client,
            embedder=StubEmbedder(),
            budget_usd=1.0,
            sleep=lambda _s: None,
        )

        assert outcome.status == "complete"
        assert outcome.prompts_total == 2
        assert outcome.prompts_ok == 2
        assert outcome.prompts_error == 0
        assert outcome.cost_usd == pytest.approx(0.0002)

        probes = session.execute(select(ProviderDriftProbe)).scalars().all()
        assert len(probes) == 2
        for p in probes:
            assert p.outcome == "ok"
            assert p.judge_pass is True
            assert p.output_embedding is not None
            assert p.embedding_model == "stub-embedder-v1"

    def test_idempotent_terminal_run(self, session, model_spec) -> None:
        sync_models_to_db(session, registry=(model_spec,))
        prompts = _prompts(n=1)
        sync_prompts_to_db(session, suite=prompts)
        session.commit()

        client = StubClient([
            ProviderCallResult(outcome=ProbeOutcome.OK, output_text="0", cost_usd=0.0),
        ])
        first = execute_run(
            db=session,
            model_spec=model_spec,
            run_date=date(2026, 5, 18),
            prompts=prompts,
            provider_client=client,
            embedder=None,
            budget_usd=1.0,
            sleep=lambda _s: None,
        )
        assert first.status == "complete"

        # Second call: same date → no new probes, no new client calls.
        second = execute_run(
            db=session,
            model_spec=model_spec,
            run_date=date(2026, 5, 18),
            prompts=prompts,
            provider_client=client,
            embedder=None,
            budget_usd=1.0,
            sleep=lambda _s: None,
        )
        assert second.run_id == first.run_id
        probes = session.execute(select(ProviderDriftProbe)).scalars().all()
        assert len(probes) == 1  # not duplicated

    def test_budget_exceeded_marks_remaining(self, session, model_spec) -> None:
        sync_models_to_db(session, registry=(model_spec,))
        prompts = _prompts(n=4)
        sync_prompts_to_db(session, suite=prompts)
        session.commit()

        # Each call costs 0.6; budget is 1.0 → second call still fits
        # (would exceed gate is *post* charge), third is gated out.
        client = CycleClient(
            ProviderCallResult(
                outcome=ProbeOutcome.OK, output_text="x", cost_usd=0.6
            )
        )
        outcome = execute_run(
            db=session,
            model_spec=model_spec,
            run_date=date(2026, 5, 18),
            prompts=prompts,
            provider_client=client,
            embedder=None,
            budget_usd=1.0,
            sleep=lambda _s: None,
        )
        # First call charged → spent=0.6, remaining=0.4. Second call charged
        # → spent=1.2, remaining=0. Third+fourth → budget_exceeded.
        assert outcome.status == "partial"
        probes = session.execute(
            select(ProviderDriftProbe).order_by(ProviderDriftProbe.prompt_id)
        ).scalars().all()
        outcomes = [p.outcome for p in probes]
        assert outcomes.count("ok") == 2
        assert outcomes.count("budget_exceeded") == 2

    def test_partial_status_on_mixed_outcomes(self, session, model_spec) -> None:
        sync_models_to_db(session, registry=(model_spec,))
        prompts = _prompts(n=2)
        sync_prompts_to_db(session, suite=prompts)
        session.commit()
        client = StubClient([
            ProviderCallResult(outcome=ProbeOutcome.OK, output_text="0", cost_usd=0),
            ProviderCallResult(outcome=ProbeOutcome.ERROR, error_code="HTTP_500"),
        ])
        outcome = execute_run(
            db=session,
            model_spec=model_spec,
            run_date=date(2026, 5, 18),
            prompts=prompts,
            provider_client=client,
            embedder=None,
            budget_usd=1.0,
            sleep=lambda _s: None,
        )
        assert outcome.status == "partial"
        assert outcome.prompts_ok == 1
        assert outcome.prompts_error == 1

    def test_all_errors_status_error(self, session, model_spec) -> None:
        sync_models_to_db(session, registry=(model_spec,))
        prompts = _prompts(n=2)
        sync_prompts_to_db(session, suite=prompts)
        session.commit()
        client = CycleClient(
            ProviderCallResult(outcome=ProbeOutcome.ERROR, error_code="HTTP_500")
        )
        outcome = execute_run(
            db=session,
            model_spec=model_spec,
            run_date=date(2026, 5, 18),
            prompts=prompts,
            provider_client=client,
            embedder=None,
            budget_usd=1.0,
            sleep=lambda _s: None,
        )
        assert outcome.status == "error"
        assert outcome.prompts_ok == 0
        assert outcome.prompts_error == 2

    def test_embedder_failure_is_soft(self, session, model_spec) -> None:
        sync_models_to_db(session, registry=(model_spec,))
        prompts = _prompts(n=1)
        sync_prompts_to_db(session, suite=prompts)
        session.commit()
        client = StubClient([
            ProviderCallResult(outcome=ProbeOutcome.OK, output_text="0", cost_usd=0)
        ])
        outcome = execute_run(
            db=session,
            model_spec=model_spec,
            run_date=date(2026, 5, 18),
            prompts=prompts,
            provider_client=client,
            embedder=FlakyEmbedder(),
            budget_usd=1.0,
            sleep=lambda _s: None,
        )
        assert outcome.status == "complete"
        probe = session.execute(select(ProviderDriftProbe)).scalar_one()
        assert probe.outcome == "ok"
        assert probe.output_embedding is None  # embedder failed, judge still ran
        assert probe.judge_pass is True

    def test_empty_prompts_rejected(self, session, model_spec) -> None:
        with pytest.raises(ValueError):
            execute_run(
                db=session,
                model_spec=model_spec,
                run_date=date(2026, 5, 18),
                prompts=(),
                provider_client=CycleClient(
                    ProviderCallResult(outcome=ProbeOutcome.OK)
                ),
                budget_usd=1.0,
            )


# ── DB load helpers ─────────────────────────────────────────────────────────


class TestLoaders:
    def test_load_active(self, session, model_spec) -> None:
        sync_models_to_db(session, registry=(model_spec,))
        prompts = _prompts(n=2)
        sync_prompts_to_db(session, suite=prompts)
        session.commit()

        loaded_prompts = load_active_prompts(session)
        loaded_models = load_active_models(session)

        assert {p.id for p in loaded_prompts} == {p.id for p in prompts}
        assert {m.id for m in loaded_models} == {model_spec.id}

    def test_inactive_filtered(self, session, model_spec) -> None:
        # Insert an inactive model directly
        sync_models_to_db(session, registry=(model_spec,))
        row = session.execute(
            select(ProviderDriftModel).where(ProviderDriftModel.id == model_spec.id)
        ).scalar_one()
        row.active = False
        session.commit()
        assert load_active_models(session) == ()
