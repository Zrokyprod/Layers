"""Tests for Module 10 — Pilot Tier-2 auto-PR pipeline.

Coverage:
  * `pilot_pr_payload` — fingerprint determinism, evidence validation,
    title/body shape, unsupported / insufficient evidence errors,
    vocab cross-check with `pilot.DEFAULT_POLICY["tier2_actions"]`.
  * `pilot_pr_client` — DryRun / Recording / Raising backends +
    factory fail-CLOSED behavior on unknown settings.
  * `pilot_pr_dispatch.evaluate_tier2_dispatch` — every gate
    (entitlement / kill switch / tier disabled / action not allowed /
    daily cap / replay-pass gate / unsupported / insufficient
    evidence) + idempotency hit + applied path + transient/permanent
    failure mapping + cross-tenant guard.
  * Routes — POST /v1/pilot/actions/{id}/cancel + /retry covering
    404 / 409 / 422 / 200 paths.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import Anomaly, PilotAction, PilotPolicy, ReplayRun
from app.db.session import get_db_session, get_db_session_read
from app.main import app
from app.services.pilot import (
    DEFAULT_POLICY,
    get_or_create_policy,
    upsert_policy,
)
from app.services.pilot_pr_client import (
    DryRunPRClient,
    PRClientError,
    PRClientPermanentError,
    RaisingPRClient,
    RecordingPRClient,
    get_pr_client,
    reset_pr_client,
)
from app.services.pilot_pr_dispatch import (
    DECISION_APPLIED,
    DECISION_FAILED_PERMANENT,
    DECISION_FAILED_TRANSIENT,
    DECISION_IDEMPOTENT_HIT,
    DECISION_SKIPPED_ACTION_NOT_ALLOWED,
    DECISION_SKIPPED_DAILY_CAP,
    DECISION_SKIPPED_ENTITLEMENT,
    DECISION_SKIPPED_INSUFFICIENT_EVIDENCE,
    DECISION_SKIPPED_KILL_SWITCH,
    DECISION_SKIPPED_REPLAY_GATE,
    DECISION_SKIPPED_TIER_DISABLED,
    evaluate_tier2_dispatch,
)
from app.services.pilot_pr_payload import (
    SUPPORTED_TIER2_ACTIONS,
    InsufficientEvidenceError,
    UnsupportedActionTypeError,
    _check_action_vocab_in_sync,
    build_pr_payload,
    compute_pr_fingerprint,
)


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "test_pilot_pr_svc.db"
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


@pytest.fixture()
def client(tmp_path: Path):
    get_settings.cache_clear()
    reset_pr_client()
    db_path = tmp_path / "test_pilot_pr_route.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )

    def override_get_db_session():
        s = factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_db_session_read] = override_get_db_session

    with TestClient(app) as test_client:
        test_client._session_factory = factory  # type: ignore[attr-defined]
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    get_settings.cache_clear()
    reset_pr_client()


PROJECT_HEADER = "X-Project-Id"


@pytest.fixture(autouse=True)
def _grant_pilot_tier(monkeypatch):
    """Bypass the router-level 402 plan-gate so the route-level tests
    in this file exercise the *route* surface, not the gate (which is
    tested separately in test_plan_gates.py)."""
    from app.services import entitlements_resolver
    from app.services.billing_plans import PLAN_ENTITLEMENTS

    pro = dict(PLAN_ENTITLEMENTS["pro"])
    monkeypatch.setattr(
        entitlements_resolver, "has", lambda db, org_id, key: True
    )
    monkeypatch.setattr(
        entitlements_resolver,
        "get",
        lambda db, org_id, key, default=None: pro.get(key, default),
    )
    monkeypatch.setattr(
        entitlements_resolver, "resolve_all", lambda db, org_id: dict(pro)
    )
    monkeypatch.setattr(
        entitlements_resolver, "get_plan_code", lambda db, org_id: "pro"
    )


# ── helpers ──────────────────────────────────────────────────────────────────


def _seed_anomaly(
    session,
    *,
    project_id: str,
    anomaly_id: str = "anom-1",
    detector: str = "SCHEMA_VIOLATION",
    evidence: dict | None = None,
) -> Anomaly:
    now = datetime.now(timezone.utc)
    a = Anomaly(
        id=anomaly_id,
        project_id=project_id,
        fingerprint=f"fp-{anomaly_id}",
        detector=detector,
        severity="medium",
        status="open",
        first_seen_at=now,
        last_seen_at=now,
        occurrence_count=3,
        evidence_json=json.dumps(evidence) if evidence else None,
    )
    session.add(a)
    session.commit()
    return a


def _seed_passing_replay(
    session,
    *,
    project_id: str,
    run_id: str = "run-pass",
    pass_count: int = 10,
    trace_count: int = 10,
) -> ReplayRun:
    summary = {
        "trace_count_at_dispatch": trace_count,
        "pass_count": pass_count,
        "fail_count": trace_count - pass_count,
        "error_count": 0,
    }
    run = ReplayRun(
        id=run_id,
        project_id=project_id,
        golden_set_id="gs-x",
        trigger="github",
        git_sha="sha-aaa",
        status="pass" if pass_count == trace_count else "fail",
        summary_json=json.dumps(summary, separators=(",", ":")),
        created_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    session.add(run)
    session.commit()
    return run


def _enable_tier2(session, *, project_id: str, **overrides) -> PilotPolicy:
    payload = dict(DEFAULT_POLICY)
    payload["tier2_enabled"] = True
    payload.update(overrides)
    return upsert_policy(
        session, project_id=project_id, payload=payload, updated_by=None
    )


_PROMPT_EVIDENCE = {
    "prompt_path": "prompts/agent.txt",
    "prior_prompt_body": "Be concise.",
    "current_prompt_fingerprint": "deadbeef",
    "candidates": [
        {"signal": "model_swap", "confidence": 0.92},
        {"signal": "prompt_edit", "confidence": 0.74},
    ],
}

_SCHEMA_EVIDENCE = {
    "schema_path": "schemas/agent_output.json",
    "proposed_schema_body": '{"type":"object","required":["foo"]}',
    "current_schema_fingerprint": "cafebabe",
}


# ── pilot_pr_payload: builder + fingerprint ──────────────────────────────────


class TestPayloadBuilder:
    def test_prompt_revert_happy_path(self, db_session) -> None:
        anomaly = _seed_anomaly(
            db_session, project_id="p1", evidence=_PROMPT_EVIDENCE
        )
        payload = build_pr_payload(
            anomaly=anomaly, action_type="prompt_revert_pr"
        )
        assert payload.project_id == "p1"
        assert payload.anomaly_id == anomaly.id
        assert payload.action_type == "prompt_revert_pr"
        assert payload.base_branch == "main"
        assert payload.head_branch.startswith("zroky/autopilot/anomaly-")
        assert len(payload.files) == 1
        f = payload.files[0]
        assert f.path == "prompts/agent.txt"
        assert f.new_content == "Be concise."
        assert f.old_content_fingerprint == "deadbeef"
        assert "[zroky]" in payload.title
        assert "prompts/agent.txt" in payload.title
        assert anomaly.id in payload.body
        assert payload.evidence_summary["kind"] == "prompt_revert"

    def test_schema_fix_happy_path(self, db_session) -> None:
        anomaly = _seed_anomaly(
            db_session, project_id="p1", evidence=_SCHEMA_EVIDENCE
        )
        payload = build_pr_payload(
            anomaly=anomaly, action_type="schema_fix_pr"
        )
        assert payload.files[0].path == "schemas/agent_output.json"
        assert payload.evidence_summary["kind"] == "schema_fix"

    def test_unsupported_action_raises(self, db_session) -> None:
        anomaly = _seed_anomaly(
            db_session, project_id="p1", evidence=_PROMPT_EVIDENCE
        )
        with pytest.raises(UnsupportedActionTypeError):
            build_pr_payload(anomaly=anomaly, action_type="rewrite_world")

    def test_missing_evidence_raises(self, db_session) -> None:
        anomaly = _seed_anomaly(db_session, project_id="p1", evidence={})
        with pytest.raises(InsufficientEvidenceError):
            build_pr_payload(anomaly=anomaly, action_type="prompt_revert_pr")

    def test_evidence_missing_required_field(self, db_session) -> None:
        anomaly = _seed_anomaly(
            db_session,
            project_id="p1",
            evidence={"prompt_path": "p.txt"},  # missing prior_prompt_body
        )
        with pytest.raises(InsufficientEvidenceError, match="prior_prompt_body"):
            build_pr_payload(anomaly=anomaly, action_type="prompt_revert_pr")

    def test_fingerprint_deterministic(self, db_session) -> None:
        anomaly = _seed_anomaly(
            db_session, project_id="p1", evidence=_PROMPT_EVIDENCE
        )
        a = build_pr_payload(anomaly=anomaly, action_type="prompt_revert_pr")
        b = build_pr_payload(anomaly=anomaly, action_type="prompt_revert_pr")
        assert a.fingerprint == b.fingerprint

    def test_fingerprint_changes_when_evidence_changes(self, db_session) -> None:
        a = _seed_anomaly(
            db_session,
            project_id="p1",
            anomaly_id="anom-A",
            evidence={**_PROMPT_EVIDENCE, "prior_prompt_body": "v1"},
        )
        b = _seed_anomaly(
            db_session,
            project_id="p1",
            anomaly_id="anom-B",
            evidence={**_PROMPT_EVIDENCE, "prior_prompt_body": "v2"},
        )
        fp_a = build_pr_payload(anomaly=a, action_type="prompt_revert_pr").fingerprint
        fp_b = build_pr_payload(anomaly=b, action_type="prompt_revert_pr").fingerprint
        assert fp_a != fp_b

    def test_compute_pr_fingerprint_is_stable_across_orderings(self) -> None:
        from app.services.pilot_pr_payload import PatchFile

        files = (
            PatchFile(path="a.txt", new_content="x"),
            PatchFile(path="b.txt", new_content="y"),
        )
        fp1 = compute_pr_fingerprint(
            project_id="p1", anomaly_id="a1", action_type="prompt_revert_pr", files=files
        )
        fp2 = compute_pr_fingerprint(
            project_id="p1", anomaly_id="a1", action_type="prompt_revert_pr", files=files
        )
        assert fp1 == fp2
        assert len(fp1) == 64  # SHA-256 hex

    def test_payload_to_json_roundtrip(self, db_session) -> None:
        anomaly = _seed_anomaly(
            db_session, project_id="p1", evidence=_PROMPT_EVIDENCE
        )
        payload = build_pr_payload(
            anomaly=anomaly, action_type="prompt_revert_pr"
        )
        blob = payload.to_json()
        decoded = json.loads(blob)
        assert decoded["fingerprint"] == payload.fingerprint
        assert decoded["files"][0]["path"] == "prompts/agent.txt"

    def test_vocab_in_sync_with_policy_defaults(self) -> None:
        # Should NOT raise — guards against drift between the
        # payload generator and the policy seeder.
        _check_action_vocab_in_sync()
        assert SUPPORTED_TIER2_ACTIONS.issubset(
            set(DEFAULT_POLICY["tier2_actions"])
        )


# ── pilot_pr_client: backends + factory ──────────────────────────────────────


class TestPRClientBackends:
    def test_dry_run_records_and_returns_sentinel(self, db_session) -> None:
        anomaly = _seed_anomaly(
            db_session, project_id="p1", evidence=_PROMPT_EVIDENCE
        )
        payload = build_pr_payload(
            anomaly=anomaly, action_type="prompt_revert_pr"
        )
        client = DryRunPRClient()
        result = client.open_pr(payload)
        assert result.pr_url.startswith("dry-run://")
        assert result.dry_run is True
        assert len(client.calls) == 1
        assert client.calls[0].fingerprint == payload.fingerprint

    def test_dry_run_reset(self, db_session) -> None:
        anomaly = _seed_anomaly(
            db_session, project_id="p1", evidence=_PROMPT_EVIDENCE
        )
        payload = build_pr_payload(
            anomaly=anomaly, action_type="prompt_revert_pr"
        )
        client = DryRunPRClient()
        client.open_pr(payload)
        client.reset()
        assert client.calls == []

    def test_recording_client_returns_dry_run_url(self, db_session) -> None:
        anomaly = _seed_anomaly(
            db_session, project_id="p1", evidence=_PROMPT_EVIDENCE
        )
        payload = build_pr_payload(
            anomaly=anomaly, action_type="prompt_revert_pr"
        )
        result = RecordingPRClient().open_pr(payload)
        assert result.pr_url.startswith("recording://")
        assert result.dry_run is True

    def test_raising_client_raises(self, db_session) -> None:
        anomaly = _seed_anomaly(
            db_session, project_id="p1", evidence=_PROMPT_EVIDENCE
        )
        payload = build_pr_payload(
            anomaly=anomaly, action_type="prompt_revert_pr"
        )
        with pytest.raises(PRClientPermanentError):
            RaisingPRClient().open_pr(payload)

    def test_factory_defaults_to_dry_run(self) -> None:
        reset_pr_client()
        c = get_pr_client()
        assert isinstance(c, DryRunPRClient)

    def test_factory_fail_closed_on_unknown_backend(self, monkeypatch) -> None:
        reset_pr_client()
        s = get_settings()
        monkeypatch.setattr(s, "PILOT_PR_CLIENT_BACKEND", "not_a_real_backend")
        c = get_pr_client()
        assert isinstance(c, DryRunPRClient)  # fail-CLOSED to dry-run

    def test_factory_returns_recording_when_configured(self, monkeypatch) -> None:
        reset_pr_client()
        s = get_settings()
        monkeypatch.setattr(s, "PILOT_PR_CLIENT_BACKEND", "recording")
        c = get_pr_client()
        assert isinstance(c, RecordingPRClient)


# ── pilot_pr_dispatch: gates + idempotency + state machine ──────────────────


class TestDispatchGates:
    def _setup(self, db_session, *, evidence=None):
        anomaly = _seed_anomaly(
            db_session,
            project_id="p1",
            evidence=evidence or _PROMPT_EVIDENCE,
        )
        run = _seed_passing_replay(db_session, project_id="p1")
        _enable_tier2(db_session, project_id="p1")
        return anomaly, run

    def test_applied_happy_path(self, db_session) -> None:
        anomaly, run = self._setup(db_session)
        client = DryRunPRClient()
        outcome = evaluate_tier2_dispatch(
            db_session,
            anomaly=anomaly,
            action_type="prompt_revert_pr",
            replay_run=run,
            pr_client=client,
            entitlement_check=lambda db, pid: True,
        )
        assert outcome.decision == DECISION_APPLIED
        assert outcome.action.status == "applied"
        assert outcome.action.pr_url.startswith("dry-run://")
        assert outcome.action.pr_fingerprint is not None
        assert outcome.action.replay_run_id_gate == run.id
        assert outcome.action.tier == 2
        assert len(client.calls) == 1

    def test_skip_when_entitlement_missing(self, db_session) -> None:
        anomaly, run = self._setup(db_session)
        client = DryRunPRClient()
        outcome = evaluate_tier2_dispatch(
            db_session,
            anomaly=anomaly,
            action_type="prompt_revert_pr",
            replay_run=run,
            pr_client=client,
            entitlement_check=lambda db, pid: False,
        )
        assert outcome.decision == DECISION_SKIPPED_ENTITLEMENT
        assert outcome.action.status == "skipped"
        assert client.calls == []  # never reached the client

    def test_skip_when_kill_switch_on(self, db_session) -> None:
        anomaly, run = self._setup(db_session)
        _enable_tier2(db_session, project_id="p1", kill_switch=True)
        client = DryRunPRClient()
        outcome = evaluate_tier2_dispatch(
            db_session,
            anomaly=anomaly,
            action_type="prompt_revert_pr",
            replay_run=run,
            pr_client=client,
            entitlement_check=lambda db, pid: True,
        )
        assert outcome.decision == DECISION_SKIPPED_KILL_SWITCH
        assert client.calls == []

    def test_skip_when_tier2_disabled(self, db_session) -> None:
        anomaly, run = self._setup(db_session)
        upsert_policy(
            db_session,
            project_id="p1",
            payload={**dict(DEFAULT_POLICY), "tier2_enabled": False},
            updated_by=None,
        )
        client = DryRunPRClient()
        outcome = evaluate_tier2_dispatch(
            db_session,
            anomaly=anomaly,
            action_type="prompt_revert_pr",
            replay_run=run,
            pr_client=client,
            entitlement_check=lambda db, pid: True,
        )
        assert outcome.decision == DECISION_SKIPPED_TIER_DISABLED

    def test_skip_when_action_not_in_policy_allow_list(self, db_session) -> None:
        anomaly, run = self._setup(db_session)
        # Restrict policy to schema-fix only — prompt_revert is now denied.
        _enable_tier2(
            db_session, project_id="p1", tier2_actions=["schema_fix_pr"]
        )
        client = DryRunPRClient()
        outcome = evaluate_tier2_dispatch(
            db_session,
            anomaly=anomaly,
            action_type="prompt_revert_pr",
            replay_run=run,
            pr_client=client,
            entitlement_check=lambda db, pid: True,
        )
        assert outcome.decision == DECISION_SKIPPED_ACTION_NOT_ALLOWED

    def test_skip_when_replay_gate_below_threshold(self, db_session) -> None:
        anomaly = _seed_anomaly(
            db_session, project_id="p1", evidence=_PROMPT_EVIDENCE
        )
        # 5/10 pass → 0.5, well below the 0.95 default.
        run = _seed_passing_replay(
            db_session,
            project_id="p1",
            run_id="run-mid",
            pass_count=5,
            trace_count=10,
        )
        _enable_tier2(db_session, project_id="p1")
        client = DryRunPRClient()
        outcome = evaluate_tier2_dispatch(
            db_session,
            anomaly=anomaly,
            action_type="prompt_revert_pr",
            replay_run=run,
            pr_client=client,
            entitlement_check=lambda db, pid: True,
        )
        assert outcome.decision == DECISION_SKIPPED_REPLAY_GATE
        assert outcome.action.replay_run_id_gate == run.id
        assert client.calls == []

    def test_skip_when_replay_has_zero_traces(self, db_session) -> None:
        anomaly = _seed_anomaly(
            db_session, project_id="p1", evidence=_PROMPT_EVIDENCE
        )
        run = _seed_passing_replay(
            db_session,
            project_id="p1",
            run_id="run-empty",
            pass_count=0,
            trace_count=0,
        )
        _enable_tier2(db_session, project_id="p1")
        outcome = evaluate_tier2_dispatch(
            db_session,
            anomaly=anomaly,
            action_type="prompt_revert_pr",
            replay_run=run,
            pr_client=DryRunPRClient(),
            entitlement_check=lambda db, pid: True,
        )
        assert outcome.decision == DECISION_SKIPPED_REPLAY_GATE

    def test_replay_gate_bypassed_when_policy_disables_it(self, db_session) -> None:
        anomaly = _seed_anomaly(
            db_session, project_id="p1", evidence=_PROMPT_EVIDENCE
        )
        run = _seed_passing_replay(
            db_session,
            project_id="p1",
            pass_count=1,
            trace_count=10,
        )
        _enable_tier2(
            db_session, project_id="p1", tier2_require_replay_pass=False
        )
        outcome = evaluate_tier2_dispatch(
            db_session,
            anomaly=anomaly,
            action_type="prompt_revert_pr",
            replay_run=run,
            pr_client=DryRunPRClient(),
            entitlement_check=lambda db, pid: True,
        )
        assert outcome.decision == DECISION_APPLIED

    def test_skip_when_evidence_missing(self, db_session) -> None:
        anomaly = _seed_anomaly(db_session, project_id="p1", evidence={})
        run = _seed_passing_replay(db_session, project_id="p1")
        _enable_tier2(db_session, project_id="p1")
        outcome = evaluate_tier2_dispatch(
            db_session,
            anomaly=anomaly,
            action_type="prompt_revert_pr",
            replay_run=run,
            pr_client=DryRunPRClient(),
            entitlement_check=lambda db, pid: True,
        )
        assert outcome.decision == DECISION_SKIPPED_INSUFFICIENT_EVIDENCE
        assert outcome.action.status == "skipped"

    def test_cross_tenant_replay_run_fail_permanent(self, db_session) -> None:
        anomaly = _seed_anomaly(
            db_session, project_id="p1", evidence=_PROMPT_EVIDENCE
        )
        foreign = _seed_passing_replay(db_session, project_id="OTHER")
        _enable_tier2(db_session, project_id="p1")
        outcome = evaluate_tier2_dispatch(
            db_session,
            anomaly=anomaly,
            action_type="prompt_revert_pr",
            replay_run=foreign,
            pr_client=DryRunPRClient(),
            entitlement_check=lambda db, pid: True,
        )
        assert outcome.decision == DECISION_FAILED_PERMANENT


class TestDispatchIdempotency:
    def _setup(self, db_session):
        anomaly = _seed_anomaly(
            db_session, project_id="p1", evidence=_PROMPT_EVIDENCE
        )
        run = _seed_passing_replay(db_session, project_id="p1")
        _enable_tier2(db_session, project_id="p1")
        return anomaly, run

    def test_idempotent_hit_returns_existing_row(self, db_session) -> None:
        anomaly, run = self._setup(db_session)
        client = DryRunPRClient()
        first = evaluate_tier2_dispatch(
            db_session,
            anomaly=anomaly,
            action_type="prompt_revert_pr",
            replay_run=run,
            pr_client=client,
            entitlement_check=lambda db, pid: True,
        )
        second = evaluate_tier2_dispatch(
            db_session,
            anomaly=anomaly,
            action_type="prompt_revert_pr",
            replay_run=run,
            pr_client=client,
            entitlement_check=lambda db, pid: True,
        )
        assert first.decision == DECISION_APPLIED
        assert second.decision == DECISION_IDEMPOTENT_HIT
        assert second.action.id == first.action.id
        # Second call must NOT have hit the client a second time.
        assert len(client.calls) == 1


class TestDispatchFailures:
    def _setup(self, db_session):
        anomaly = _seed_anomaly(
            db_session, project_id="p1", evidence=_PROMPT_EVIDENCE
        )
        run = _seed_passing_replay(db_session, project_id="p1")
        _enable_tier2(db_session, project_id="p1")
        return anomaly, run

    def test_transient_failure_mapped(self, db_session) -> None:
        class _Transient:
            def open_pr(self, payload):
                raise PRClientError("timeout")

        anomaly, run = self._setup(db_session)
        outcome = evaluate_tier2_dispatch(
            db_session,
            anomaly=anomaly,
            action_type="prompt_revert_pr",
            replay_run=run,
            pr_client=_Transient(),
            entitlement_check=lambda db, pid: True,
        )
        assert outcome.decision == DECISION_FAILED_TRANSIENT
        assert outcome.action.status == "failed"
        assert outcome.action.pr_url is None
        # Replay gate evidence still stamped so /retry has what it needs.
        assert outcome.action.replay_run_id_gate == run.id

    def test_permanent_failure_mapped(self, db_session) -> None:
        class _Perm:
            def open_pr(self, payload):
                raise PRClientPermanentError("no install")

        anomaly, run = self._setup(db_session)
        outcome = evaluate_tier2_dispatch(
            db_session,
            anomaly=anomaly,
            action_type="prompt_revert_pr",
            replay_run=run,
            pr_client=_Perm(),
            entitlement_check=lambda db, pid: True,
        )
        assert outcome.decision == DECISION_FAILED_PERMANENT
        assert outcome.action.status == "failed"

    def test_unexpected_exception_mapped_permanent(self, db_session) -> None:
        class _Bug:
            def open_pr(self, payload):
                raise RuntimeError("kapow")

        anomaly, run = self._setup(db_session)
        outcome = evaluate_tier2_dispatch(
            db_session,
            anomaly=anomaly,
            action_type="prompt_revert_pr",
            replay_run=run,
            pr_client=_Bug(),
            entitlement_check=lambda db, pid: True,
        )
        assert outcome.decision == DECISION_FAILED_PERMANENT
        assert outcome.action.status == "failed"


class TestDailyCap:
    def test_dry_run_rows_do_not_count_toward_cap(self, db_session) -> None:
        # Set a low cap; even with N>cap dry-run-applied rows, the next
        # dispatch must still succeed because dry-run rows are excluded
        # from the cap counter.
        anomaly = _seed_anomaly(
            db_session, project_id="p1", evidence=_PROMPT_EVIDENCE
        )
        run = _seed_passing_replay(db_session, project_id="p1")
        _enable_tier2(db_session, project_id="p1", tier2_daily_cap=1)

        # First call applies (dry-run).
        out1 = evaluate_tier2_dispatch(
            db_session,
            anomaly=anomaly,
            action_type="prompt_revert_pr",
            replay_run=run,
            pr_client=DryRunPRClient(),
            entitlement_check=lambda db, pid: True,
        )
        assert out1.decision == DECISION_APPLIED

        # Second call (different anomaly, so different fingerprint)
        # would still be a dry-run apply — cap was 1 but dry-run is excluded.
        anomaly2 = _seed_anomaly(
            db_session,
            project_id="p1",
            anomaly_id="anom-2",
            evidence={**_PROMPT_EVIDENCE, "prior_prompt_body": "v2"},
        )
        out2 = evaluate_tier2_dispatch(
            db_session,
            anomaly=anomaly2,
            action_type="prompt_revert_pr",
            replay_run=run,
            pr_client=DryRunPRClient(),
            entitlement_check=lambda db, pid: True,
        )
        assert out2.decision == DECISION_APPLIED

    def test_real_pr_rows_count_toward_cap(self, db_session) -> None:
        # Seed an existing "applied" tier-2 row with a real (non-dry-run)
        # pr_url to simulate yesterday/today's real PRs. Then dispatch
        # again and expect skipped_daily_cap.
        from uuid import uuid4

        anomaly = _seed_anomaly(
            db_session, project_id="p1", evidence=_PROMPT_EVIDENCE
        )
        run = _seed_passing_replay(db_session, project_id="p1")
        _enable_tier2(db_session, project_id="p1", tier2_daily_cap=1)

        # 1 fake real-PR row already in the trailing-24h window.
        existing = PilotAction(
            id=str(uuid4()),
            project_id="p1",
            anomaly_id=anomaly.id,
            tier=2,
            action_type="prompt_revert_pr",
            status="applied",
            pr_url="https://github.com/foo/bar/pull/1",
            created_at=datetime.now(timezone.utc),
            applied_at=datetime.now(timezone.utc),
        )
        db_session.add(existing)
        db_session.commit()

        outcome = evaluate_tier2_dispatch(
            db_session,
            anomaly=anomaly,
            action_type="prompt_revert_pr",
            replay_run=run,
            pr_client=DryRunPRClient(),
            entitlement_check=lambda db, pid: True,
        )
        assert outcome.decision == DECISION_SKIPPED_DAILY_CAP


# ── routes: /cancel + /retry ────────────────────────────────────────────────


class TestCancelRoute:
    def test_cancel_pending_tier2_returns_skipped(
        self, client: TestClient
    ) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            anomaly = _seed_anomaly(
                session, project_id="p1", evidence=_PROMPT_EVIDENCE
            )
            from uuid import uuid4

            row = PilotAction(
                id=str(uuid4()),
                project_id="p1",
                anomaly_id=anomaly.id,
                tier=2,
                action_type="prompt_revert_pr",
                status="pending",
            )
            session.add(row)
            session.commit()
            row_id = row.id

        response = client.post(
            f"/v1/pilot/actions/{row_id}/cancel",
            headers={PROJECT_HEADER: "p1"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "skipped"

    def test_cancel_applied_returns_409(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            anomaly = _seed_anomaly(
                session, project_id="p1", evidence=_PROMPT_EVIDENCE
            )
            from uuid import uuid4

            row = PilotAction(
                id=str(uuid4()),
                project_id="p1",
                anomaly_id=anomaly.id,
                tier=2,
                action_type="prompt_revert_pr",
                status="applied",
                pr_url="dry-run://x",
            )
            session.add(row)
            session.commit()
            row_id = row.id

        response = client.post(
            f"/v1/pilot/actions/{row_id}/cancel",
            headers={PROJECT_HEADER: "p1"},
        )
        assert response.status_code == 409

    def test_cancel_tier1_returns_409(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            anomaly = _seed_anomaly(
                session, project_id="p1", evidence=_PROMPT_EVIDENCE
            )
            from uuid import uuid4

            row = PilotAction(
                id=str(uuid4()),
                project_id="p1",
                anomaly_id=anomaly.id,
                tier=1,
                action_type="model_rollback",
                status="pending",
            )
            session.add(row)
            session.commit()
            row_id = row.id

        response = client.post(
            f"/v1/pilot/actions/{row_id}/cancel",
            headers={PROJECT_HEADER: "p1"},
        )
        assert response.status_code == 409
        assert "/revert" in response.json()["detail"]

    def test_cancel_missing_returns_404(self, client: TestClient) -> None:
        response = client.post(
            "/v1/pilot/actions/does-not-exist/cancel",
            headers={PROJECT_HEADER: "p1"},
        )
        assert response.status_code == 404


class TestRetryRoute:
    def _seed_failed_tier2(self, session, *, action_type="prompt_revert_pr"):
        from uuid import uuid4

        anomaly = _seed_anomaly(
            session, project_id="p1", evidence=_PROMPT_EVIDENCE
        )
        run = _seed_passing_replay(session, project_id="p1")
        _enable_tier2(session, project_id="p1")
        row = PilotAction(
            id=str(uuid4()),
            project_id="p1",
            anomaly_id=anomaly.id,
            tier=2,
            action_type=action_type,
            status="failed",
            replay_run_id_gate=run.id,
            payload_json=json.dumps(
                {"decision": "failed_transient", "skip_reason": "timeout"}
            ),
        )
        session.add(row)
        session.commit()
        return row, anomaly, run

    def test_retry_failed_action_creates_new_applied_row(
        self, client: TestClient
    ) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            row, _, _ = self._seed_failed_tier2(session)
            row_id = row.id

        response = client.post(
            f"/v1/pilot/actions/{row_id}/retry",
            headers={PROJECT_HEADER: "p1"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["id"] != row_id  # new row
        assert body["decision"] == DECISION_APPLIED
        assert body["status"] == "applied"
        assert body["pr_url"].startswith("dry-run://")

    def test_retry_missing_returns_404(self, client: TestClient) -> None:
        response = client.post(
            "/v1/pilot/actions/missing/retry",
            headers={PROJECT_HEADER: "p1"},
        )
        assert response.status_code == 404

    def test_retry_tier1_returns_409(self, client: TestClient) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            from uuid import uuid4

            anomaly = _seed_anomaly(
                session, project_id="p1", evidence=_PROMPT_EVIDENCE
            )
            row = PilotAction(
                id=str(uuid4()),
                project_id="p1",
                anomaly_id=anomaly.id,
                tier=1,
                action_type="model_rollback",
                status="failed",
            )
            session.add(row)
            session.commit()
            row_id = row.id

        response = client.post(
            f"/v1/pilot/actions/{row_id}/retry",
            headers={PROJECT_HEADER: "p1"},
        )
        assert response.status_code == 409

    def test_retry_already_applied_returns_409(
        self, client: TestClient
    ) -> None:
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            from uuid import uuid4

            anomaly = _seed_anomaly(
                session, project_id="p1", evidence=_PROMPT_EVIDENCE
            )
            run = _seed_passing_replay(session, project_id="p1")
            row = PilotAction(
                id=str(uuid4()),
                project_id="p1",
                anomaly_id=anomaly.id,
                tier=2,
                action_type="prompt_revert_pr",
                status="applied",
                pr_url="dry-run://x",
                replay_run_id_gate=run.id,
            )
            session.add(row)
            session.commit()
            row_id = row.id

        response = client.post(
            f"/v1/pilot/actions/{row_id}/retry",
            headers={PROJECT_HEADER: "p1"},
        )
        assert response.status_code == 409

    def test_retry_without_gate_evidence_returns_422(
        self, client: TestClient
    ) -> None:
        # Skipped-before-gate rows lack replay_run_id_gate.
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            from uuid import uuid4

            anomaly = _seed_anomaly(
                session, project_id="p1", evidence=_PROMPT_EVIDENCE
            )
            row = PilotAction(
                id=str(uuid4()),
                project_id="p1",
                anomaly_id=anomaly.id,
                tier=2,
                action_type="prompt_revert_pr",
                status="skipped",
                replay_run_id_gate=None,
            )
            session.add(row)
            session.commit()
            row_id = row.id

        response = client.post(
            f"/v1/pilot/actions/{row_id}/retry",
            headers={PROJECT_HEADER: "p1"},
        )
        assert response.status_code == 422
