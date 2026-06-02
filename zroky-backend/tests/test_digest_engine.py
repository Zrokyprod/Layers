"""Module 11 — Digest engine binding tests.

Covers the WRITE side of the digest pipeline (compute_summary,
render_*, generate_weekly_digest, list_pending_digests,
mark_digest_sent, resolve_recipient_emails) and the
two-stage Celery split + admin trigger route. The READ side
(parse_week_param, get_digest, list_digests, /v1/digest GET)
already has dedicated coverage in `test_digest.py`.

Plan §10.5 binding map → tests:
  - audience shape       → TestComputeSummaryAudience
  - aggregation reads    → TestComputeSummaryBlocks
  - HTML escape + tier   → TestRenderHtml / TestRenderPlain
  - UPSERT idempotency   → TestGenerateWeeklyDigest
  - sent_at preservation → TestGenerateWeeklyDigest::test_regen_preserves_sent_at
  - cohort task          → TestGenerateWeeklyDigestsTask
  - send task contract   → TestSendPendingDigestsTask
  - admin trigger        → TestAdminTriggerRoute
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import (
    Anomaly,
    Call,
    Digest,
    PilotAction,
    Project,
    ProjectMembership,
    ReplayRun,
    User,
)
from app.db.session import get_db_session, get_db_session_read
from app.main import app
from app.services import digest_engine
from app.services.digest_engine import (
    AUDIENCES,
    DEFAULT_AUDIENCE,
    UnknownAudienceError,
    compute_summary,
    generate_weekly_digest,
    list_pending_digests,
    mark_digest_sent,
    monday_of,
    render_html,
    render_plain,
    resolve_audience,
    resolve_recipient_emails,
)


# ── fixtures ─────────────────────────────────────────────────────────────────


WEEK = date(2026, 5, 11)  # Monday
WEEK_START_DT = datetime(2026, 5, 11, 0, 0, 0, tzinfo=timezone.utc)
WEEK_END_DT = WEEK_START_DT + timedelta(days=7)


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "test_digest_engine.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(tmp_path: Path):
    get_settings.cache_clear()
    db_path = tmp_path / "test_digest_route.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )

    def _override_db():
        s = session_factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db_session] = _override_db
    app.dependency_overrides[get_db_session_read] = _override_db

    with TestClient(app) as test_client:
        test_client._session_factory = session_factory  # type: ignore[attr-defined]
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    get_settings.cache_clear()


# ── seed helpers ─────────────────────────────────────────────────────────────


def _seed_project(session, project_id: str = "proj-1", *, is_active: bool = True) -> Project:
    project = Project(id=project_id, name=f"Project {project_id}", is_active=is_active)
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


def _seed_call(
    session,
    *,
    project_id: str,
    created_at: datetime,
    status: str = "success",
    cost_total: float = 0.10,
    error_code: str | None = None,
    call_id: str | None = None,
) -> Call:
    call = Call(
        id=call_id or f"call-{created_at.isoformat()}-{status}",
        project_id=project_id,
        event_id=f"evt-{call_id or created_at.isoformat()}-{status}",
        created_at=created_at,
        provider="openai",
        model="gpt-4o",
        status=status,
        error_code=error_code,
        cost_total=cost_total,
        payload_json="{}",
    )
    session.add(call)
    session.commit()
    return call


def _seed_anomaly(
    session,
    *,
    project_id: str,
    detector: str = "LOOP_DETECTED",
    severity: str = "high",
    fingerprint: str | None = None,
    first_seen_at: datetime | None = None,
    last_seen_at: datetime | None = None,
    status: str = "open",
) -> Anomaly:
    fp = fingerprint or f"fp-{detector}-{first_seen_at.isoformat() if first_seen_at else 'x'}"
    seen = first_seen_at or WEEK_START_DT + timedelta(hours=1)
    anom = Anomaly(
        project_id=project_id,
        fingerprint=fp,
        detector=detector,
        severity=severity,
        status=status,
        first_seen_at=seen,
        last_seen_at=last_seen_at or seen,
        occurrence_count=1,
    )
    session.add(anom)
    session.commit()
    session.refresh(anom)
    return anom


def _seed_pilot_action(
    session,
    *,
    project_id: str,
    anomaly_id: str,
    tier: int = 1,
    action_type: str = "model_rollback",
    status: str = "applied",
    pr_url: str | None = None,
    created_at: datetime | None = None,
) -> PilotAction:
    pa = PilotAction(
        project_id=project_id,
        anomaly_id=anomaly_id,
        tier=tier,
        action_type=action_type,
        status=status,
        pr_url=pr_url,
        created_at=created_at or WEEK_START_DT + timedelta(hours=2),
    )
    session.add(pa)
    session.commit()
    session.refresh(pa)
    return pa


def _seed_replay_run(
    session,
    *,
    project_id: str,
    status: str = "pass",
    pass_count: int = 4,
    trace_count_at_dispatch: int = 5,
    created_at: datetime | None = None,
) -> ReplayRun:
    # NOTE: replay_runs.golden_set_id has a FK to golden_sets, but
    # SQLite (default test DB) doesn't enforce FKs unless explicitly
    # enabled — we exploit that to keep this test fixture lightweight.
    # The aggregator only reads project_id + summary_json + status,
    # so a dangling FK is irrelevant to the units under test.
    run = ReplayRun(
        project_id=project_id,
        golden_set_id="gs-fake",
        trigger="manual",
        status=status,
        summary_json=json.dumps({
            "pass_count": pass_count,
            "trace_count_at_dispatch": trace_count_at_dispatch,
        }),
        created_at=created_at or WEEK_START_DT + timedelta(hours=3),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def _seed_admin(
    session,
    *,
    project_id: str,
    email: str,
    role: str = "admin",
    is_active: bool = True,
) -> User:
    user = User(subject=f"email:{email}", email=email, is_active=is_active)
    session.add(user)
    session.commit()
    session.refresh(user)
    membership = ProjectMembership(
        project_id=project_id,
        user_id=user.id,
        role=role,
        is_active=is_active,
    )
    session.add(membership)
    session.commit()
    return user


# ── M11.2 — compute_summary audience binding ────────────────────────────────


class TestComputeSummaryAudience:
    """Plan §11.2: audience determines which blocks are present."""

    def test_unknown_audience_raises(self, db_session) -> None:
        _seed_project(db_session)
        with pytest.raises(UnknownAudienceError):
            compute_summary(
                db_session, project_id="proj-1",
                week_start=WEEK, audience="founder",  # not in vocab
            )

    def test_engineer_omits_pilot_replay_trend(self, db_session) -> None:
        _seed_project(db_session)
        s = compute_summary(
            db_session, project_id="proj-1",
            week_start=WEEK, audience="engineer",
        )
        assert s["audience"] == "engineer"
        assert "calls" in s and "cost" in s and "anomalies" in s
        assert "recommendation" in s
        # engineer-tier MUST NOT include manager/exec sections
        assert "pilot" not in s
        assert "replay" not in s
        assert "trend" not in s

    def test_manager_includes_pilot_replay_omits_trend(self, db_session) -> None:
        _seed_project(db_session)
        s = compute_summary(
            db_session, project_id="proj-1",
            week_start=WEEK, audience="manager",
        )
        assert s["audience"] == "manager"
        assert "pilot" in s
        assert "replay" in s
        # No prior digest seeded → no trend even if audience were exec.
        assert "trend" not in s

    def test_executive_includes_trend_when_prior_exists(self, db_session) -> None:
        _seed_project(db_session)
        # Seed a prior digest row (week-1) so trend can compute.
        prior = WEEK - timedelta(days=7)
        prior_summary = {
            "calls": {"total": 50},
            "cost": {"total_usd": 100.0},
            "anomalies": {"total": 4},
        }
        db_session.add(Digest(
            project_id="proj-1",
            week_start=prior,
            summary_json=json.dumps(prior_summary),
        ))
        db_session.commit()

        s = compute_summary(
            db_session, project_id="proj-1",
            week_start=WEEK, audience="executive",
        )
        assert s["audience"] == "executive"
        assert "pilot" in s and "replay" in s
        assert "trend" in s
        # WoW shape
        for key in ("calls", "cost", "anomalies"):
            assert key in s["trend"]
            assert "wow_pct" in s["trend"][key]
            assert "prior_value" in s["trend"][key]

    def test_executive_omits_trend_when_no_prior(self, db_session) -> None:
        _seed_project(db_session)
        s = compute_summary(
            db_session, project_id="proj-1",
            week_start=WEEK, audience="executive",
        )
        # Brand-new project — no trend, NOT zero-filled.
        assert "trend" not in s


class TestComputeSummaryBlocks:
    """Aggregation correctness — verify each block reads the right
    table and respects the [week_start, +7d) window."""

    def test_calls_block_counts_failures(self, db_session) -> None:
        _seed_project(db_session)
        # 3 success + 2 failed inside the window
        for i in range(3):
            _seed_call(
                db_session, project_id="proj-1",
                created_at=WEEK_START_DT + timedelta(hours=i),
                status="success",
                call_id=f"ok-{i}",
            )
        _seed_call(
            db_session, project_id="proj-1",
            created_at=WEEK_START_DT + timedelta(hours=4),
            status="error",
            call_id="err-1",
        )
        _seed_call(
            db_session, project_id="proj-1",
            created_at=WEEK_START_DT + timedelta(hours=5),
            status="timeout",
            call_id="err-2",
        )
        # OUTSIDE the window — must be excluded.
        _seed_call(
            db_session, project_id="proj-1",
            created_at=WEEK_START_DT - timedelta(days=1),
            status="error",
            call_id="prev-week",
        )

        s = compute_summary(
            db_session, project_id="proj-1",
            week_start=WEEK, audience="engineer",
        )
        assert s["calls"]["total"] == 5
        assert s["calls"]["failed"] == 2
        assert s["calls"]["failure_rate"] == round(2 / 5, 4)

    def test_cost_block_sums_usd(self, db_session) -> None:
        _seed_project(db_session)
        _seed_call(
            db_session, project_id="proj-1",
            created_at=WEEK_START_DT + timedelta(hours=1),
            status="success", cost_total=1.50, call_id="c1",
        )
        _seed_call(
            db_session, project_id="proj-1",
            created_at=WEEK_START_DT + timedelta(hours=2),
            status="error", cost_total=2.25, call_id="c2",
        )
        s = compute_summary(
            db_session, project_id="proj-1",
            week_start=WEEK, audience="engineer",
        )
        assert s["cost"]["total_usd"] == pytest.approx(3.75)
        assert s["cost"]["failed_usd"] == pytest.approx(2.25)
        # No pilot actions → no prevented waste.
        assert s["cost"]["prevented_waste_usd"] == 0.0

    def test_anomalies_block_top_detector_and_severity(self, db_session) -> None:
        _seed_project(db_session)
        _seed_anomaly(
            db_session, project_id="proj-1",
            detector="LOOP_DETECTED", severity="high",
            first_seen_at=WEEK_START_DT + timedelta(hours=1),
            fingerprint="fp-loop-1",
        )
        _seed_anomaly(
            db_session, project_id="proj-1",
            detector="LOOP_DETECTED", severity="critical",
            first_seen_at=WEEK_START_DT + timedelta(hours=2),
            fingerprint="fp-loop-2",
        )
        _seed_anomaly(
            db_session, project_id="proj-1",
            detector="COST_SPIKE", severity="medium",
            first_seen_at=WEEK_START_DT + timedelta(hours=3),
            fingerprint="fp-cost-1",
        )
        s = compute_summary(
            db_session, project_id="proj-1",
            week_start=WEEK, audience="engineer",
        )
        # By-detector ordered DESC by count.
        by_det = s["anomalies"]["by_detector"]
        assert by_det[0]["detector"] == "LOOP_DETECTED"
        assert by_det[0]["count"] == 2
        # All four severity buckets present (stable shape).
        assert set(s["anomalies"]["by_severity"].keys()) == {
            "low", "medium", "high", "critical"
        }
        assert s["anomalies"]["by_severity"]["high"] == 1
        assert s["anomalies"]["by_severity"]["critical"] == 1
        assert s["anomalies"]["by_severity"]["medium"] == 1

    def test_pilot_block_tiers_and_pr_urls(self, db_session) -> None:
        _seed_project(db_session)
        a = _seed_anomaly(db_session, project_id="proj-1")
        # Tier-1 applied + reverted
        _seed_pilot_action(
            db_session, project_id="proj-1", anomaly_id=a.id,
            tier=1, status="applied", action_type="model_rollback",
        )
        _seed_pilot_action(
            db_session, project_id="proj-1", anomaly_id=a.id,
            tier=1, status="reverted", action_type="model_rollback",
        )
        # Tier-2 applied with a real PR URL + a dry-run sentinel.
        _seed_pilot_action(
            db_session, project_id="proj-1", anomaly_id=a.id,
            tier=2, status="applied", action_type="open_pr",
            pr_url="https://github.com/acme/repo/pull/42",
        )
        _seed_pilot_action(
            db_session, project_id="proj-1", anomaly_id=a.id,
            tier=2, status="applied", action_type="open_pr",
            pr_url="dry-run://abc123",
        )
        # Tier-2 skipped + failed.
        _seed_pilot_action(
            db_session, project_id="proj-1", anomaly_id=a.id,
            tier=2, status="skipped", action_type="open_pr",
        )
        _seed_pilot_action(
            db_session, project_id="proj-1", anomaly_id=a.id,
            tier=2, status="failed", action_type="open_pr",
        )

        s = compute_summary(
            db_session, project_id="proj-1",
            week_start=WEEK, audience="manager",
        )
        p = s["pilot"]
        assert p["tier1_applied"] == 1
        assert p["tier1_reverted"] == 1
        assert p["tier2_applied"] == 2
        assert p["tier2_skipped"] == 1
        assert p["tier2_failed"] == 1
        # Sentinels (dry-run://, recording://) MUST NOT leak into manager
        # email — only real GitHub URLs.
        assert p["tier2_pr_urls"] == [
            "https://github.com/acme/repo/pull/42"
        ]

    def test_replay_block_pass_rate_weighted(self, db_session) -> None:
        _seed_project(db_session)
        # Run 1: 4/5 passes; Run 2: 3/3 passes
        _seed_replay_run(
            db_session, project_id="proj-1",
            pass_count=4, trace_count_at_dispatch=5, status="fail",
        )
        _seed_replay_run(
            db_session, project_id="proj-1",
            pass_count=3, trace_count_at_dispatch=3, status="pass",
        )
        s = compute_summary(
            db_session, project_id="proj-1",
            week_start=WEEK, audience="manager",
        )
        # Weighted = (4 + 3) / (5 + 3) = 7/8 = 0.875
        assert s["replay"]["runs"] == 2
        assert s["replay"]["passed_runs"] == 1
        assert s["replay"]["trace_pass_rate"] == pytest.approx(0.875)

    def test_replay_block_pass_rate_none_without_denom(self, db_session) -> None:
        _seed_project(db_session)
        # Run with summary_json missing trace_count_at_dispatch — must
        # be excluded from the rate calc, NOT counted as a fail.
        run = ReplayRun(
            project_id="proj-1",
            golden_set_id="gs-fake",
            trigger="manual",
            status="pass",
            summary_json=json.dumps({"pass_count": 2}),
            created_at=WEEK_START_DT + timedelta(hours=4),
        )
        db_session.add(run)
        db_session.commit()
        s = compute_summary(
            db_session, project_id="proj-1",
            week_start=WEEK, audience="manager",
        )
        assert s["replay"]["runs"] == 1
        # No denom → unknown rate, NOT 0.
        assert s["replay"]["trace_pass_rate"] is None

    def test_recommendation_no_calls(self, db_session) -> None:
        _seed_project(db_session)
        s = compute_summary(
            db_session, project_id="proj-1",
            week_start=WEEK, audience="engineer",
        )
        assert "No calls" in s["recommendation"]

    def test_recommendation_top_detector_hint(self, db_session) -> None:
        _seed_project(db_session)
        _seed_call(
            db_session, project_id="proj-1",
            created_at=WEEK_START_DT + timedelta(hours=1),
            status="success", call_id="c1",
        )
        _seed_anomaly(
            db_session, project_id="proj-1",
            detector="LOOP_DETECTED", severity="high",
            first_seen_at=WEEK_START_DT + timedelta(hours=1),
            fingerprint="fp-loop",
        )
        s = compute_summary(
            db_session, project_id="proj-1",
            week_start=WEEK, audience="engineer",
        )
        assert "LOOP_DETECTED" in s["recommendation"]


# ── M11.3 — renderers ────────────────────────────────────────────────────────


def _summary_for(audience: str, **overrides: Any) -> dict[str, Any]:
    """Hand-rolled summary so renderer tests don't depend on
    compute_summary correctness."""
    base = {
        "audience": audience,
        "week_start": "2026-05-11",
        "week_end": "2026-05-18",
        "calls": {"total": 100, "failed": 7, "failure_rate": 0.07},
        "cost": {
            "total_usd": 12.34, "failed_usd": 1.23,
            "prevented_waste_usd": 4.56,
        },
        "anomalies": {
            "total": 3,
            "by_detector": [{"detector": "LOOP_DETECTED", "count": 2}],
            "by_severity": {"low": 1, "medium": 1, "high": 1, "critical": 0},
            "open_at_week_end": 2,
        },
        "recommendation": "Most common issue this week: LOOP_DETECTED (2 occurrences).",
    }
    if audience in ("manager", "executive"):
        base["pilot"] = {
            "tier1_applied": 1, "tier1_reverted": 0,
            "tier2_applied": 1, "tier2_skipped": 0, "tier2_failed": 0,
            "tier2_pr_urls": ["https://github.com/acme/repo/pull/9"],
        }
        base["replay"] = {
            "runs": 2, "passed_runs": 1, "trace_pass_rate": 0.875,
        }
    if audience == "executive":
        base["trend"] = {
            "calls": {"wow_pct": 0.10, "prior_value": 90},
            "cost": {"wow_pct": -0.05, "prior_value": 13.0},
            "anomalies": {"wow_pct": None, "prior_value": 0},
        }
    base.update(overrides)
    return base


class TestRenderHtml:
    def test_engineer_omits_pilot_replay_sections(self) -> None:
        html = render_html(_summary_for("engineer"))
        assert "ZROKY weekly digest" in html
        assert "engineer view" in html
        # Engineer body MUST NOT mention Autopilot / Replay headings.
        assert "Autopilot" not in html
        assert "Replay" not in html

    def test_manager_includes_pilot_and_replay(self) -> None:
        html = render_html(_summary_for("manager"))
        assert "Autopilot" in html
        assert "Replay" in html
        assert "https://github.com/acme/repo/pull/9" in html

    def test_executive_includes_trend(self) -> None:
        html = render_html(_summary_for("executive"))
        assert "Week-over-week" in html

    def test_unknown_audience_raises(self) -> None:
        with pytest.raises(UnknownAudienceError):
            render_html({"audience": "founder"})

    def test_html_escapes_recommendation(self) -> None:
        # Defensive — recommendation strings are server-built today,
        # but the escape layer is the policy seam if that ever changes.
        html = render_html(
            _summary_for("engineer", recommendation="<script>x</script>")
        )
        assert "<script>x</script>" not in html
        assert "&lt;script&gt;x&lt;/script&gt;" in html


class TestRenderPlain:
    def test_engineer_basic_lines(self) -> None:
        plain = render_plain(_summary_for("engineer"))
        assert "ZROKY weekly digest (engineer)" in plain
        assert "Calls:" in plain
        assert "Cost:" in plain
        assert "Issues:" in plain
        # No manager/exec sections in engineer plain output.
        assert "Pilot:" not in plain
        assert "Replay:" not in plain
        assert "Week-over-week" not in plain

    def test_manager_includes_pilot_replay(self) -> None:
        plain = render_plain(_summary_for("manager"))
        assert "Pilot:" in plain
        assert "Replay:" in plain
        assert "https://github.com/acme/repo/pull/9" in plain

    def test_executive_includes_trend_block(self) -> None:
        plain = render_plain(_summary_for("executive"))
        assert "Week-over-week" in plain
        assert "calls:" in plain
        assert "cost:" in plain

    def test_unknown_audience_raises(self) -> None:
        with pytest.raises(UnknownAudienceError):
            render_plain({"audience": "founder"})


# ── M11.4 — generate_weekly_digest UPSERT contract ───────────────────────────


class TestGenerateWeeklyDigest:
    def test_creates_new_row_with_sent_at_null(
        self, db_session, monkeypatch
    ) -> None:
        # Force the audience resolver fail-open path so we don't
        # depend on entitlements_resolver setup for this unit test.
        monkeypatch.setattr(
            digest_engine, "resolve_audience",
            lambda db, pid: "engineer",
        )
        _seed_project(db_session)
        digest = generate_weekly_digest(
            db_session, project_id="proj-1", week_start=WEEK,
        )
        assert digest.id is not None
        assert digest.project_id == "proj-1"
        assert digest.week_start == WEEK
        assert digest.sent_at is None  # queued
        assert digest.html_blob and "engineer view" in digest.html_blob
        # summary_json round-trips.
        parsed = json.loads(digest.summary_json)
        assert parsed["audience"] == "engineer"

    def test_regen_is_in_place_upsert(
        self, db_session, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            digest_engine, "resolve_audience",
            lambda db, pid: "engineer",
        )
        _seed_project(db_session)
        first = generate_weekly_digest(
            db_session, project_id="proj-1", week_start=WEEK,
        )
        first_id = first.id

        # Seed a new call → next regen produces a different summary.
        _seed_call(
            db_session, project_id="proj-1",
            created_at=WEEK_START_DT + timedelta(hours=1),
            status="success", call_id="new-call",
        )
        second = generate_weekly_digest(
            db_session, project_id="proj-1", week_start=WEEK,
        )
        # Same row — UPSERT semantics, not a new insert.
        assert second.id == first_id
        # Body refreshed.
        parsed = json.loads(second.summary_json)
        assert parsed["calls"]["total"] == 1

    def test_regen_preserves_sent_at(
        self, db_session, monkeypatch
    ) -> None:
        """Critical idempotency invariant: a regen AFTER the email
        task ran MUST NOT reset sent_at — otherwise the next send
        beat would email the same digest twice."""
        monkeypatch.setattr(
            digest_engine, "resolve_audience",
            lambda db, pid: "engineer",
        )
        _seed_project(db_session)
        digest = generate_weekly_digest(
            db_session, project_id="proj-1", week_start=WEEK,
        )
        # Simulate Stage 2 having already run.
        sent_marker = datetime(2026, 5, 18, 12, 0, 0, tzinfo=timezone.utc)
        digest.sent_at = sent_marker
        digest.sent_to_emails = json.dumps(["a@example.com"])
        db_session.commit()

        # Regen.
        regen = generate_weekly_digest(
            db_session, project_id="proj-1", week_start=WEEK,
        )
        assert regen.id == digest.id
        # sent_at survived; sent_to_emails survived.
        assert regen.sent_at is not None
        # Compare as ISO since SQLite may round-trip naive.
        assert regen.sent_at.replace(tzinfo=timezone.utc) == sent_marker
        assert json.loads(regen.sent_to_emails) == ["a@example.com"]

    def test_audience_override_used_inline(
        self, db_session, monkeypatch
    ) -> None:
        # Resolver returns engineer, but caller forces manager.
        monkeypatch.setattr(
            digest_engine, "resolve_audience",
            lambda db, pid: "engineer",
        )
        _seed_project(db_session)
        digest = generate_weekly_digest(
            db_session, project_id="proj-1",
            week_start=WEEK, audience="manager",
        )
        parsed = json.loads(digest.summary_json)
        assert parsed["audience"] == "manager"
        # And manager-only pilot block is present.
        assert "pilot" in parsed

    def test_invalid_audience_override_raises(
        self, db_session
    ) -> None:
        _seed_project(db_session)
        with pytest.raises(UnknownAudienceError):
            generate_weekly_digest(
                db_session, project_id="proj-1",
                week_start=WEEK, audience="founder",
            )


# ── M11.4 — list_pending + mark_sent + recipients ────────────────────────────


class TestListPendingDigests:
    def test_empty(self, db_session) -> None:
        assert list_pending_digests(db_session) == []

    def test_filters_to_sent_at_null(self, db_session) -> None:
        _seed_project(db_session, "proj-A")
        _seed_project(db_session, "proj-B")
        # One pending, one already sent.
        d1 = Digest(project_id="proj-A", week_start=WEEK, summary_json="{}")
        d2 = Digest(
            project_id="proj-B", week_start=WEEK, summary_json="{}",
            sent_at=datetime(2026, 5, 18, tzinfo=timezone.utc),
        )
        db_session.add_all([d1, d2])
        db_session.commit()

        pending = list_pending_digests(db_session)
        assert len(pending) == 1
        assert pending[0].project_id == "proj-A"

    def test_week_filter(self, db_session) -> None:
        _seed_project(db_session, "proj-A")
        prior = WEEK - timedelta(days=7)
        db_session.add_all([
            Digest(project_id="proj-A", week_start=WEEK, summary_json="{}"),
            Digest(project_id="proj-A", week_start=prior, summary_json="{}"),
        ])
        db_session.commit()

        narrowed = list_pending_digests(db_session, week_start=WEEK)
        assert len(narrowed) == 1
        assert narrowed[0].week_start == WEEK

    def test_invalid_limit_raises(self, db_session) -> None:
        with pytest.raises(ValueError, match="limit"):
            list_pending_digests(db_session, limit=0)


class TestMarkDigestSent:
    def test_stamps_sent_at_and_recipients(self, db_session) -> None:
        _seed_project(db_session)
        digest = Digest(
            project_id="proj-1", week_start=WEEK, summary_json="{}"
        )
        db_session.add(digest)
        db_session.commit()
        db_session.refresh(digest)

        sent_marker = datetime(2026, 5, 18, 12, 0, 0, tzinfo=timezone.utc)
        mark_digest_sent(
            db_session, digest=digest,
            sent_to_emails=["a@x.com", "  ", "b@x.com"],
            sent_at=sent_marker,
        )
        db_session.refresh(digest)
        assert digest.sent_at is not None
        # Empty / whitespace addresses filtered.
        assert json.loads(digest.sent_to_emails) == ["a@x.com", "b@x.com"]


class TestResolveRecipientEmails:
    def test_admin_and_owner_only(self, db_session) -> None:
        _seed_project(db_session)
        _seed_admin(db_session, project_id="proj-1", email="admin@example.com", role="admin")
        _seed_admin(db_session, project_id="proj-1", email="owner@example.com", role="owner")
        _seed_admin(db_session, project_id="proj-1", email="member@example.com", role="member")

        emails = resolve_recipient_emails(db_session, "proj-1")
        assert set(emails) == {"admin@example.com", "owner@example.com"}

    def test_skips_inactive_users(self, db_session) -> None:
        _seed_project(db_session)
        _seed_admin(db_session, project_id="proj-1", email="active@example.com", role="admin")
        _seed_admin(
            db_session, project_id="proj-1",
            email="inactive@example.com", role="admin",
            is_active=False,
        )
        emails = resolve_recipient_emails(db_session, "proj-1")
        assert "inactive@example.com" not in emails

    def test_empty_when_no_admins(self, db_session) -> None:
        _seed_project(db_session)
        assert resolve_recipient_emails(db_session, "proj-1") == []


class TestResolveAudience:
    """Fail-open contract — resolver failure must NOT block digest gen."""

    def test_falls_back_to_default_on_resolver_exception(
        self, db_session, monkeypatch
    ) -> None:
        from app.services import entitlements_resolver

        def boom(*a, **kw):
            raise RuntimeError("DB outage simulation")

        monkeypatch.setattr(entitlements_resolver, "get", boom)
        # MUST NOT raise — fall back to engineer.
        result = resolve_audience(db_session, "proj-1")
        assert result == DEFAULT_AUDIENCE

    def test_falls_back_on_unknown_value(
        self, db_session, monkeypatch
    ) -> None:
        from app.services import entitlements_resolver
        monkeypatch.setattr(
            entitlements_resolver, "get",
            lambda *a, **kw: "founder",  # garbage value
        )
        assert resolve_audience(db_session, "proj-1") == DEFAULT_AUDIENCE


# ── M11.5 — Celery task split ────────────────────────────────────────────────


class TestGenerateWeeklyDigestsTask:
    """Stage 1 task — cohort walk + per-project failure isolation."""

    def test_skipped_when_disabled(self, db_session, monkeypatch) -> None:
        from app.worker import tasks as task_module

        # Force DIGEST_ENABLED=False via a fresh settings stub.
        class _S:
            DIGEST_ENABLED = False
            DIGEST_SEND_BATCH_SIZE = 100
        monkeypatch.setattr(task_module, "get_settings", lambda: _S())

        result = task_module.generate_weekly_digests.run()
        assert result == {"skipped": True, "reason": "DIGEST_ENABLED=false"}

    def test_walks_active_projects_only(
        self, db_session, monkeypatch
    ) -> None:
        from app.worker import tasks as task_module

        class _S:
            DIGEST_ENABLED = True
            DIGEST_SEND_BATCH_SIZE = 100
        monkeypatch.setattr(task_module, "get_settings", lambda: _S())
        # Use the test session for the task.
        monkeypatch.setattr(
            task_module, "SessionLocal",
            lambda: db_session,
        )
        # Stub the close so the task doesn't kill our fixture session.
        db_session.close = lambda: None  # type: ignore[method-assign]
        # Stub resolve_audience to engineer for both projects.
        monkeypatch.setattr(
            digest_engine, "resolve_audience",
            lambda db, pid: "engineer",
        )

        _seed_project(db_session, "proj-active", is_active=True)
        _seed_project(db_session, "proj-inactive", is_active=False)

        result = task_module.generate_weekly_digests.run(
            week_start_iso=WEEK.isoformat()
        )
        assert result["generated"] == 1
        assert result["failed"] == 0
        # Only the active project got a digest row.
        rows = db_session.query(Digest).all()
        assert len(rows) == 1
        assert rows[0].project_id == "proj-active"

    def test_per_project_failure_does_not_break_cohort(
        self, db_session, monkeypatch
    ) -> None:
        from app.worker import tasks as task_module

        class _S:
            DIGEST_ENABLED = True
            DIGEST_SEND_BATCH_SIZE = 100
        monkeypatch.setattr(task_module, "get_settings", lambda: _S())
        monkeypatch.setattr(
            task_module, "SessionLocal", lambda: db_session,
        )
        db_session.close = lambda: None  # type: ignore[method-assign]

        _seed_project(db_session, "proj-good")
        _seed_project(db_session, "proj-bad")

        call_count = {"n": 0}

        def fake_generate(db, *, project_id, week_start, audience=None):
            call_count["n"] += 1
            if project_id == "proj-bad":
                raise RuntimeError("simulated compute_summary failure")
            # Deferred to real impl for the good project.
            return generate_weekly_digest(
                db, project_id=project_id,
                week_start=week_start, audience="engineer",
            )

        monkeypatch.setattr(
            task_module, "generate_weekly_digest", fake_generate
        )

        result = task_module.generate_weekly_digests.run(
            week_start_iso=WEEK.isoformat()
        )
        assert call_count["n"] == 2  # both attempted
        assert result["generated"] == 1
        assert result["failed"] == 1
        # Verify the failed entry is captured in results for ops triage.
        statuses = [r["status"] for r in result["results"]]
        assert sorted(statuses) == ["failed", "ok"]


class TestSendPendingDigestsTask:
    """Stage 2 task — drain pending rows, stamp sent_at on success."""

    def test_skipped_when_disabled(self, db_session, monkeypatch) -> None:
        from app.worker import tasks as task_module

        class _S:
            DIGEST_ENABLED = False
            DIGEST_SEND_BATCH_SIZE = 100
        monkeypatch.setattr(task_module, "get_settings", lambda: _S())

        result = task_module.send_pending_digests.run()
        assert result == {"skipped": True, "reason": "DIGEST_ENABLED=false"}

    def test_skips_row_with_no_recipients(
        self, db_session, monkeypatch
    ) -> None:
        from app.worker import tasks as task_module

        class _S:
            DIGEST_ENABLED = True
            DIGEST_SEND_BATCH_SIZE = 100
        monkeypatch.setattr(task_module, "get_settings", lambda: _S())
        monkeypatch.setattr(
            task_module, "SessionLocal", lambda: db_session,
        )
        db_session.close = lambda: None  # type: ignore[method-assign]
        # No recipients seeded for this project.
        _seed_project(db_session, "proj-x")
        db_session.add(Digest(
            project_id="proj-x",
            week_start=WEEK,
            summary_json=json.dumps({"cost": {"prevented_waste_usd": 0}}),
            html_blob="<html></html>",
        ))
        db_session.commit()

        sent_calls: list[Any] = []
        monkeypatch.setattr(
            task_module, "send_email",
            lambda *a, **kw: sent_calls.append((a, kw)) or True,
        )

        result = task_module.send_pending_digests.run()
        assert result["skipped_no_recipients"] == 1
        assert result["sent"] == 0
        # send_email MUST NOT be invoked when there are no recipients.
        assert sent_calls == []
        # Row remains pending.
        row = db_session.query(Digest).filter_by(project_id="proj-x").one()
        assert row.sent_at is None

    def test_does_not_stamp_when_send_email_returns_false(
        self, db_session, monkeypatch
    ) -> None:
        from app.worker import tasks as task_module

        class _S:
            DIGEST_ENABLED = True
            DIGEST_SEND_BATCH_SIZE = 100
        monkeypatch.setattr(task_module, "get_settings", lambda: _S())
        monkeypatch.setattr(
            task_module, "SessionLocal", lambda: db_session,
        )
        db_session.close = lambda: None  # type: ignore[method-assign]
        _seed_project(db_session, "proj-y")
        _seed_admin(
            db_session, project_id="proj-y", email="ops@example.com",
        )
        db_session.add(Digest(
            project_id="proj-y", week_start=WEEK,
            summary_json=json.dumps({
                "audience": "engineer",
                "week_start": WEEK.isoformat(),
                "week_end": (WEEK + timedelta(days=7)).isoformat(),
                "calls": {"total": 0, "failed": 0, "failure_rate": 0.0},
                "cost": {"total_usd": 0, "failed_usd": 0, "prevented_waste_usd": 0},
                "anomalies": {
                    "total": 0, "by_detector": [],
                    "by_severity": {"low": 0, "medium": 0, "high": 0, "critical": 0},
                    "open_at_week_end": 0,
                },
                "recommendation": "",
            }),
            html_blob="<html></html>",
        ))
        db_session.commit()

        # Simulate transient SMTP failure.
        monkeypatch.setattr(
            task_module, "send_email", lambda *a, **kw: False,
        )

        result = task_module.send_pending_digests.run()
        assert result["sent"] == 0
        assert result["failed"] == 1
        # Row STILL pending so the next beat tick retries.
        row = db_session.query(Digest).filter_by(project_id="proj-y").one()
        assert row.sent_at is None

    def test_stamps_sent_at_and_recipients_on_success(
        self, db_session, monkeypatch
    ) -> None:
        from app.worker import tasks as task_module

        class _S:
            DIGEST_ENABLED = True
            DIGEST_SEND_BATCH_SIZE = 100
        monkeypatch.setattr(task_module, "get_settings", lambda: _S())
        monkeypatch.setattr(
            task_module, "SessionLocal", lambda: db_session,
        )
        db_session.close = lambda: None  # type: ignore[method-assign]
        _seed_project(db_session, "proj-z")
        _seed_admin(
            db_session, project_id="proj-z", email="ceo@example.com",
            role="owner",
        )
        summary = {
            "audience": "engineer",
            "week_start": WEEK.isoformat(),
            "week_end": (WEEK + timedelta(days=7)).isoformat(),
            "calls": {"total": 0, "failed": 0, "failure_rate": 0.0},
            "cost": {
                "total_usd": 0, "failed_usd": 0,
                "prevented_waste_usd": 12.34,
            },
            "anomalies": {
                "total": 0, "by_detector": [],
                "by_severity": {"low": 0, "medium": 0, "high": 0, "critical": 0},
                "open_at_week_end": 0,
            },
            "recommendation": "",
        }
        db_session.add(Digest(
            project_id="proj-z", week_start=WEEK,
            summary_json=json.dumps(summary),
            html_blob="<html>OK</html>",
        ))
        db_session.commit()

        captured: dict[str, Any] = {}

        def fake_send(to, subject, html_body, *, plain_body=None):
            captured["to"] = list(to)
            captured["subject"] = subject
            captured["html_body"] = html_body
            captured["plain_body"] = plain_body
            return True

        monkeypatch.setattr(task_module, "send_email", fake_send)

        result = task_module.send_pending_digests.run()
        assert result["sent"] == 1
        assert result["failed"] == 0
        # Subject derived from prevented_waste_usd.
        assert "12.34" in captured["subject"]
        # Plain body rendered on the fly.
        assert captured["plain_body"] is not None
        assert "engineer" in captured["plain_body"]
        # Row stamped.
        row = db_session.query(Digest).filter_by(project_id="proj-z").one()
        assert row.sent_at is not None
        assert json.loads(row.sent_to_emails) == ["ceo@example.com"]


# ── M11.6 — admin trigger route ──────────────────────────────────────────────


class TestAdminTriggerRoute:
    # The internal router is mounted at `/internal` (not `/v1/internal`)
    # — same prefix as the existing owner admin endpoints. Tests bind
    # to the actual mount point rather than the plan's aspirational path.
    URL = "/internal/digests/generate"

    def test_inline_mode_returns_serialized_digest(
        self, client, monkeypatch
    ) -> None:
        # Force resolve_audience to engineer so the test is hermetic.
        monkeypatch.setattr(
            digest_engine, "resolve_audience",
            lambda db, pid: "engineer",
        )
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_project(session, "proj-1")

        resp = client.post(
            self.URL,
            json={
                "project_id": "proj-1",
                "week_start": WEEK.isoformat(),
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["mode"] == "inline"
        assert body["week_start"] == WEEK.isoformat()
        assert body["digest"]["project_id"] == "proj-1"
        assert body["digest"]["week_start"] == WEEK.isoformat()
        # Row was actually written.
        with factory() as session:
            row = session.query(Digest).filter_by(project_id="proj-1").one()
            assert row.sent_at is None  # Stage 1 — not yet sent.

    def test_inline_mode_audience_override_propagates(
        self, client, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            digest_engine, "resolve_audience",
            lambda db, pid: "engineer",
        )
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_project(session, "proj-1")

        resp = client.post(
            self.URL,
            json={
                "project_id": "proj-1",
                "week_start": WEEK.isoformat(),
                "audience": "manager",
            },
        )
        assert resp.status_code == 200
        digest_row = resp.json()["digest"]
        # Manager audience → pilot block in summary.
        assert digest_row["summary"]["audience"] == "manager"
        assert "pilot" in digest_row["summary"]

    def test_404_when_project_missing(self, client) -> None:
        resp = client.post(
            self.URL,
            json={
                "project_id": "ghost",
                "week_start": WEEK.isoformat(),
            },
        )
        assert resp.status_code == 404

    def test_422_when_project_inactive(self, client, monkeypatch) -> None:
        monkeypatch.setattr(
            digest_engine, "resolve_audience",
            lambda db, pid: "engineer",
        )
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_project(session, "proj-dead", is_active=False)
        resp = client.post(
            self.URL,
            json={
                "project_id": "proj-dead",
                "week_start": WEEK.isoformat(),
            },
        )
        assert resp.status_code == 422

    def test_422_when_audience_invalid(self, client) -> None:
        # Validator rejects pre-route.
        resp = client.post(
            self.URL,
            json={
                "project_id": "proj-1",
                "week_start": WEEK.isoformat(),
                "audience": "founder",
            },
        )
        assert resp.status_code == 422

    def test_non_monday_week_start_is_coerced(
        self, client, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            digest_engine, "resolve_audience",
            lambda db, pid: "engineer",
        )
        factory = client._session_factory  # type: ignore[attr-defined]
        with factory() as session:
            _seed_project(session, "proj-1")
        # Wednesday 2026-05-13 → coerced to Monday 2026-05-11.
        resp = client.post(
            self.URL,
            json={
                "project_id": "proj-1",
                "week_start": "2026-05-13",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["week_start"] == WEEK.isoformat()

    def test_cohort_mode_enqueues_task(
        self, client, monkeypatch
    ) -> None:
        # Patch the task .delay call so we don't need a live broker.
        from app.worker import tasks as task_module

        captured: dict[str, Any] = {}

        class _FakeAsyncResult:
            id = "fake-task-id-123"

        def fake_delay(week_start_iso=None):
            captured["week_start_iso"] = week_start_iso
            return _FakeAsyncResult()

        monkeypatch.setattr(
            task_module.generate_weekly_digests, "delay", fake_delay
        )

        resp = client.post(
            self.URL,
            json={"week_start": WEEK.isoformat()},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["mode"] == "async"
        assert body["task_id"] == "fake-task-id-123"
        assert body["week_start"] == WEEK.isoformat()
        assert captured["week_start_iso"] == WEEK.isoformat()


# ── audience vocab cross-check (import-time sanity) ──────────────────────────


def test_audience_vocab_in_sync_with_billing_plans() -> None:
    """If billing_plans.DIGEST_AUDIENCE_VALUES drifts from
    digest_engine.AUDIENCES, every audience-keyed read in the wild
    breaks silently. Catch that drift in CI."""
    digest_engine._check_audience_vocab_in_sync()
    # Sanity: vocab is exactly the documented three.
    assert set(AUDIENCES) == {"engineer", "manager", "executive"}
