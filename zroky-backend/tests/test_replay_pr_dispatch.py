"""Tests for replay_pr_dispatch — replay-driven auto-fix PR dispatcher.

Coverage:
  * dispatch_replay_fix_pr gates — entitlement, kill_switch, tier2_enabled,
    not real_llm, no fix, low confidence, action not allowed, daily cap.
  * Happy path — generates fix, builds payload, opens PR (DryRun client).
  * Idempotency — second dispatch returns idempotent_hit.
  * PR client failures — transient and permanent errors.
  * Audit trail — every outcome writes a PilotAction row.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import (
    Anomaly,
    PilotAction,
    PilotPolicy,
    ReplayRun,
    ReplayRunTrace,
    GoldenTrace,
    Call,
)
from app.services.pilot import (
    DEFAULT_POLICY,
    get_or_create_policy,
    upsert_policy,
)
from app.services.pilot_pr_client import (
    DryRunPRClient,
    PRClientError,
    PRClientPermanentError,
    reset_pr_client,
)
from app.services.replay_pr_dispatch import (
    _DECISION_APPLIED,
    _DECISION_FAILED_PERMANENT,
    _DECISION_FAILED_TRANSIENT,
    _DECISION_IDEMPOTENT_HIT,
    _DECISION_SKIPPED_DAILY_CAP,
    _DECISION_SKIPPED_ENTITLEMENT,
    _DECISION_SKIPPED_KILL_SWITCH,
    _DECISION_SKIPPED_LOW_CONFIDENCE,
    _DECISION_SKIPPED_NO_FIX,
    _DECISION_SKIPPED_NOT_REAL_LLM,
    _DECISION_SKIPPED_TIER_DISABLED,
    dispatch_replay_fix_pr,
)


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "test_replay_pr_dispatch.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture(autouse=True)
def _reset_pr_client():
    reset_pr_client()


@pytest.fixture()
def mock_llm_client(monkeypatch: pytest.MonkeyPatch):
    """Install a fake LLM client returning a high-confidence prompt fix."""

    class _FakeClient:
        def chat_completions_create(self, *, model, messages, **kwargs):
            raw = json.dumps({
                "fix_type": "prompt_tweak",
                "confidence": 0.92,
                "regression_summary": "model drifted from JSON to markdown",
                "reasoning": "Add explicit JSON instruction.",
                "proposed_prompt_body": "Respond in JSON only.",
            })

            class _Msg:
                content = raw

            class _Choice:
                message = _Msg()

            class _Resp:
                choices = [_Choice()]

            return _Resp()

    def _install():
        from app.services import llm_client as llm_module
        monkeypatch.setattr(llm_module, "get_llm_client", lambda: _FakeClient())

    return _install


# ── helpers ────────────────────────────────────────────────────────────────


def _seed_run(
    session,
    *,
    project_id: str = "p1",
    run_id: str = "run-1",
    replay_mode: str = "real_llm",
    candidate_prompt_override: str | None = "new prompt",
    status: str = "fail",
    fail_count: int = 3,
    trace_count: int = 5,
) -> ReplayRun:
    summary = {
        "trace_count_at_dispatch": trace_count,
        "trace_count_executed": trace_count,
        "pass_count": trace_count - fail_count,
        "fail_count": fail_count,
        "error_count": 0,
        "replay_mode": replay_mode,
        "candidate_prompt_override": candidate_prompt_override,
        "candidate_model_override": None,
    }
    run = ReplayRun(
        id=run_id,
        project_id=project_id,
        golden_set_id="gs-x",
        trigger="manual",
        status=status,
        summary_json=json.dumps(summary, separators=(",", ":")),
        created_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def _seed_trace(
    session,
    *,
    run: ReplayRun,
    trace_id: str,
    expected: str = "expected",
    actual: str = "actual",
    reason: str = "exact_mismatch",
) -> ReplayRunTrace:
    gt = GoldenTrace(
        id=f"gt-{trace_id}",
        project_id=run.project_id,
        golden_set_id=run.golden_set_id,
        call_id="c-orig",
        expected_output_text=expected,
    )
    session.add(gt)
    session.commit()
    session.refresh(gt)

    call = Call(
        id=f"c-replayed-{trace_id}",
        project_id=run.project_id,
        event_id=f"evt-{trace_id}",
        provider="openrouter",
        model="claude-3-haiku",
        status="success",
        payload_json=json.dumps({"prompt": "orig", "model": "claude-3-haiku"}),
    )
    session.add(call)
    session.commit()
    session.refresh(call)

    rrt = ReplayRunTrace(
        id=trace_id,
        project_id=run.project_id,
        replay_run_id=run.id,
        golden_trace_id=gt.id,
        call_id_replayed=call.id,
        output_text=actual,
        status="fail",
        judge_scores_json=json.dumps(
            {"verdict": "fail", "confidence": 0.9, "reason": reason, "model": "claude-3-haiku"},
            separators=(",", ":"),
        ),
    )
    session.add(rrt)
    session.commit()
    session.refresh(rrt)
    return rrt


def _enable_tier2(
    session,
    *,
    project_id: str = "p1",
    tier2_enabled: bool = True,
    kill_switch: bool = False,
    tier2_actions: list[str] | None = None,
    tier2_daily_cap: int | None = None,
) -> PilotPolicy:
    payload = dict(DEFAULT_POLICY)
    payload["tier2_enabled"] = tier2_enabled
    payload["kill_switch"] = kill_switch
    if tier2_actions is not None:
        payload["tier2_actions"] = tier2_actions
    if tier2_daily_cap is not None:
        payload["tier2_daily_cap"] = tier2_daily_cap
    return upsert_policy(
        session, project_id=project_id, payload=payload, updated_by=None
    )


def _grant_entitlement(*args, **kwargs) -> bool:
    return True


# ── gate tests ─────────────────────────────────────────────────────────────


class TestEntitlementGate:
    def test_skipped_when_no_entitlement(self, db_session) -> None:
        run = _seed_run(db_session)
        _enable_tier2(db_session)
        outcome = dispatch_replay_fix_pr(
            db_session,
            replay_run=run,
            entitlement_check=lambda db, pid: False,
        )
        assert outcome.decision == _DECISION_SKIPPED_ENTITLEMENT
        assert outcome.action.status == "skipped"


class TestPolicyGates:
    def test_skipped_when_kill_switch_on(self, db_session) -> None:
        run = _seed_run(db_session)
        _enable_tier2(db_session, kill_switch=True)
        outcome = dispatch_replay_fix_pr(
            db_session,
            replay_run=run,
            entitlement_check=_grant_entitlement,
        )
        assert outcome.decision == _DECISION_SKIPPED_KILL_SWITCH

    def test_skipped_when_tier2_disabled(self, db_session) -> None:
        run = _seed_run(db_session)
        _enable_tier2(db_session, tier2_enabled=False)
        outcome = dispatch_replay_fix_pr(
            db_session,
            replay_run=run,
            entitlement_check=_grant_entitlement,
        )
        assert outcome.decision == _DECISION_SKIPPED_TIER_DISABLED


class TestReplayModeGate:
    def test_skipped_when_not_real_llm(self, db_session) -> None:
        run = _seed_run(db_session, replay_mode="stub")
        _enable_tier2(db_session)
        outcome = dispatch_replay_fix_pr(
            db_session,
            replay_run=run,
            entitlement_check=_grant_entitlement,
        )
        assert outcome.decision == _DECISION_SKIPPED_NOT_REAL_LLM


class TestFixEngineGate:
    def test_skipped_when_run_passes(self, db_session) -> None:
        run = _seed_run(db_session, status="pass", fail_count=0, trace_count=3)
        _enable_tier2(db_session)
        outcome = dispatch_replay_fix_pr(
            db_session,
            replay_run=run,
            entitlement_check=_grant_entitlement,
        )
        assert outcome.decision == _DECISION_SKIPPED_NO_FIX

    def test_skipped_when_no_failing_traces(self, db_session) -> None:
        run = _seed_run(db_session, status="fail", fail_count=2, trace_count=3)
        _enable_tier2(db_session)
        outcome = dispatch_replay_fix_pr(
            db_session,
            replay_run=run,
            entitlement_check=_grant_entitlement,
        )
        assert outcome.decision == _DECISION_SKIPPED_NO_FIX

    def test_skipped_when_low_confidence(self, db_session, mock_llm_client) -> None:
        run = _seed_run(db_session)
        _seed_trace(db_session, run=run, trace_id="t1")
        _enable_tier2(db_session)

        # Override LLM with low-confidence response.
        from app.services import llm_client as llm_module

        class _LowConf:
            def chat_completions_create(self, **kwargs):
                raw = json.dumps({
                    "fix_type": "prompt_tweak",
                    "confidence": 0.1,
                    "regression_summary": "summary",
                    "reasoning": "reason",
                    "proposed_prompt_body": "new prompt",
                })

                class _Msg:
                    content = raw

                class _Choice:
                    message = _Msg()

                class _Resp:
                    choices = [_Choice()]

                return _Resp()

        db_session._monkeypatch = True  # noqa: SLF001
        llm_module.get_llm_client = lambda: _LowConf()

        outcome = dispatch_replay_fix_pr(
            db_session,
            replay_run=run,
            entitlement_check=_grant_entitlement,
        )
        # Engine filters out below the confidence floor, so the
        # dispatcher sees no fix at all (engine + dispatcher share floor).
        assert outcome.decision == _DECISION_SKIPPED_NO_FIX


class TestActionTypeGate:
    def test_skipped_when_action_not_in_policy(self, db_session, mock_llm_client) -> None:
        run = _seed_run(db_session)
        _seed_trace(db_session, run=run, trace_id="t1")
        # Only allow legacy actions, not replay actions.
        _enable_tier2(db_session, tier2_actions=["prompt_revert_pr"])
        mock_llm_client()
        outcome = dispatch_replay_fix_pr(
            db_session,
            replay_run=run,
            entitlement_check=_grant_entitlement,
        )
        assert outcome.decision == "skipped_action_not_allowed"


class TestDailyCapGate:
    def test_skipped_when_cap_reached(self, db_session, mock_llm_client) -> None:
        run = _seed_run(db_session)
        _seed_trace(db_session, run=run, trace_id="t1")
        _enable_tier2(db_session, tier2_daily_cap=0)
        mock_llm_client()
        outcome = dispatch_replay_fix_pr(
            db_session,
            replay_run=run,
            entitlement_check=_grant_entitlement,
        )
        assert outcome.decision == _DECISION_SKIPPED_DAILY_CAP


# ── happy path ──────────────────────────────────────────────────────────────


class TestHappyPath:
    def test_applied_with_dry_run_client(self, db_session, mock_llm_client) -> None:
        run = _seed_run(db_session)
        _seed_trace(db_session, run=run, trace_id="t1")
        _seed_trace(db_session, run=run, trace_id="t2")
        _enable_tier2(db_session)
        mock_llm_client()
        pr_client = DryRunPRClient()

        outcome = dispatch_replay_fix_pr(
            db_session,
            replay_run=run,
            pr_client=pr_client,
            entitlement_check=_grant_entitlement,
        )
        assert outcome.decision == _DECISION_APPLIED
        assert outcome.action.status == "applied"
        assert outcome.action.pr_url.startswith("dry-run://")
        assert outcome.payload is not None
        assert outcome.payload.action_type == "replay_prompt_fix"
        assert outcome.fix_suggestion is not None

    def test_idempotent_second_dispatch(self, db_session, mock_llm_client) -> None:
        run = _seed_run(db_session)
        _seed_trace(db_session, run=run, trace_id="t1")
        _enable_tier2(db_session)
        mock_llm_client()
        pr_client = DryRunPRClient()

        o1 = dispatch_replay_fix_pr(
            db_session,
            replay_run=run,
            pr_client=pr_client,
            entitlement_check=_grant_entitlement,
        )
        assert o1.decision == _DECISION_APPLIED

        o2 = dispatch_replay_fix_pr(
            db_session,
            replay_run=run,
            pr_client=pr_client,
            entitlement_check=_grant_entitlement,
        )
        assert o2.decision == _DECISION_IDEMPOTENT_HIT
        # Only one real PR call despite two dispatches.
        assert len(pr_client.calls) == 1


# ── PR client failure paths ─────────────────────────────────────────────────


class TestClientFailures:
    def test_transient_failure(self, db_session, mock_llm_client) -> None:
        run = _seed_run(db_session)
        _seed_trace(db_session, run=run, trace_id="t1")
        _enable_tier2(db_session)
        mock_llm_client()

        class _Transient:
            def open_pr(self, payload):
                raise PRClientError("rate limited")

        outcome = dispatch_replay_fix_pr(
            db_session,
            replay_run=run,
            pr_client=_Transient(),
            entitlement_check=_grant_entitlement,
        )
        assert outcome.decision == _DECISION_FAILED_TRANSIENT
        assert outcome.action.status == "failed"

    def test_permanent_failure(self, db_session, mock_llm_client) -> None:
        run = _seed_run(db_session)
        _seed_trace(db_session, run=run, trace_id="t1")
        _enable_tier2(db_session)
        mock_llm_client()

        class _Permanent:
            def open_pr(self, payload):
                raise PRClientPermanentError("repo not found")

        outcome = dispatch_replay_fix_pr(
            db_session,
            replay_run=run,
            pr_client=_Permanent(),
            entitlement_check=_grant_entitlement,
        )
        assert outcome.decision == _DECISION_FAILED_PERMANENT
        assert outcome.action.status == "failed"


# ── audit trail ─────────────────────────────────────────────────────────────


class TestAuditTrail:
    def test_every_dispatch_writes_pilot_action(self, db_session) -> None:
        run = _seed_run(db_session)
        _enable_tier2(db_session)
        # No traces seeded → fix engine returns None.
        outcome = dispatch_replay_fix_pr(
            db_session,
            replay_run=run,
            entitlement_check=_grant_entitlement,
        )
        assert outcome.action is not None
        assert outcome.action.id is not None
        # Row is queryable.
        row = db_session.execute(
            select(PilotAction).where(PilotAction.id == outcome.action.id)
        ).scalar_one_or_none()
        assert row is not None
        assert row.project_id == "p1"
        assert row.tier == 2
