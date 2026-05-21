"""Tests for `app.services.regression_ci.sampler`.

Phase 1 (`build_spec`) — pure-functional, no DB.
Phase 2 (`sample`)     — integration-style with sqlite fixture.

The DB tests follow the same fixture pattern as `test_replay_runs.py`
to keep conftest behavior consistent (TESTING=true, sqlite path).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import Call
from app.services.regression_ci.blast_radius import ChangedFile
from app.services.regression_ci.models import (
    DEFAULT_SAMPLE_SIZES,
    DEFAULT_STRATIFICATION,
    BlastRadius,
    BlastRadiusCategory,
    BlastRadiusSource,
    SampleStratum,
)
from app.services.regression_ci.sampler import build_spec, sample


# ── Phase 1 — build_spec ────────────────────────────────────────────────────


@pytest.fixture()
def br_unknown() -> BlastRadius:
    return BlastRadius(
        category=BlastRadiusCategory.UNKNOWN,
        source=BlastRadiusSource.AUTO_DETECTED,
    )


@pytest.fixture()
def br_tool_prompt() -> BlastRadius:
    return BlastRadius(
        category=BlastRadiusCategory.TOOL_PROMPT,
        source=BlastRadiusSource.DECLARED,
        target="refund",
    )


class TestBuildSpec:
    def test_default_size_for_unknown(self, br_unknown: BlastRadius) -> None:
        spec = build_spec(br_unknown)
        assert spec.target_total == DEFAULT_SAMPLE_SIZES[BlastRadiusCategory.UNKNOWN]
        assert spec.stratification == DEFAULT_STRATIFICATION

    def test_tool_prompt_smallest(self, br_tool_prompt: BlastRadius) -> None:
        spec = build_spec(br_tool_prompt)
        assert spec.target_total == DEFAULT_SAMPLE_SIZES[BlastRadiusCategory.TOOL_PROMPT]

    def test_project_override_applied(self, br_tool_prompt: BlastRadius) -> None:
        spec = build_spec(
            br_tool_prompt,
            project_overrides={BlastRadiusCategory.TOOL_PROMPT: 50},
        )
        assert spec.target_total == 50

    def test_invalid_override_ignored(self, br_tool_prompt: BlastRadius) -> None:
        spec = build_spec(
            br_tool_prompt,
            project_overrides={BlastRadiusCategory.TOOL_PROMPT: -10},  # invalid
        )
        # Falls back to default
        assert spec.target_total == DEFAULT_SAMPLE_SIZES[BlastRadiusCategory.TOOL_PROMPT]

    def test_target_total_cap_applied(self, br_unknown: BlastRadius) -> None:
        # Free-tier scenario: cap at 100 regardless of category default.
        spec = build_spec(br_unknown, target_total_cap=100)
        assert spec.target_total == 100

    def test_cap_does_not_inflate(self, br_tool_prompt: BlastRadius) -> None:
        # Cap is a ceiling, not a floor.
        spec = build_spec(br_tool_prompt, target_total_cap=10000)
        # Tool prompt default is 200, cap of 10000 should NOT raise it.
        assert spec.target_total == DEFAULT_SAMPLE_SIZES[BlastRadiusCategory.TOOL_PROMPT]

    def test_custom_stratification(self, br_unknown: BlastRadius) -> None:
        custom = {
            SampleStratum.PASS_HISTORY: 1.0,
            SampleStratum.FAIL_HISTORY: 0.0,
            SampleStratum.RARE_CLUSTER: 0.0,
            SampleStratum.RECENT_24H: 0.0,
        }
        spec = build_spec(br_unknown, stratification_override=custom)
        targets = spec.per_stratum_target()
        assert targets[SampleStratum.PASS_HISTORY] == spec.target_total
        assert targets[SampleStratum.FAIL_HISTORY] == 0


# ── Phase 2 — sample (DB integration) ───────────────────────────────────────


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "test_regression_ci_sampler.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _mk_call(
    *,
    project_id: str,
    status: str = "success",
    agent: str | None = "primary",
    is_production: bool = True,
    age_minutes: int = 60,
) -> Call:
    """Helper: build a Call row at `now - age_minutes`."""
    created = datetime.now(timezone.utc) - timedelta(minutes=age_minutes)
    return Call(
        id=str(uuid4()),
        project_id=project_id,
        event_id=str(uuid4()),
        created_at=created,
        agent_name=agent,
        provider="openai",
        model="gpt-4o",
        status=status,
        is_production=is_production,
        payload_json="{}",
    )


class TestSampleIntegration:
    def test_empty_project_returns_empty_strata(self, db_session) -> None:
        spec = build_spec(BlastRadius(
            category=BlastRadiusCategory.UNKNOWN,
            source=BlastRadiusSource.AUTO_DETECTED,
        ))
        result = sample(spec, db=db_session, project_id="proj-empty")
        assert result.realised.realised_total == 0
        assert len(result.notes) >= 1  # at least one under-fill note

    def test_pass_history_filled(self, db_session) -> None:
        proj = "proj-pass"
        for _ in range(20):
            db_session.add(_mk_call(project_id=proj, status="success"))
        db_session.commit()

        spec = build_spec(
            BlastRadius(category=BlastRadiusCategory.UNKNOWN,
                         source=BlastRadiusSource.AUTO_DETECTED),
            target_total_cap=10,  # easier to assert
        )
        result = sample(spec, db=db_session, project_id=proj)
        # With default stratification 50/30/10/10 against target=10:
        # pass_history target = 5, fail = 3, rare = 1, recent = 1.
        # We have 20 success calls but no failures/rare-clusters; recent should
        # also fill from those calls (they're production within 24h).
        assert result.realised.pass_history >= 1

    def test_fail_history_prefers_failed_calls(self, db_session) -> None:
        proj = "proj-fail"
        for _ in range(5):
            db_session.add(_mk_call(project_id=proj, status="failed"))
        for _ in range(10):
            db_session.add(_mk_call(project_id=proj, status="success"))
        db_session.commit()

        spec = build_spec(
            BlastRadius(category=BlastRadiusCategory.UNKNOWN,
                         source=BlastRadiusSource.AUTO_DETECTED),
            target_total_cap=10,
        )
        result = sample(spec, db=db_session, project_id=proj)
        assert result.realised.fail_history >= 1

    def test_tenant_isolation(self, db_session) -> None:
        # Cross-project leak test — sample must NEVER return another project's IDs.
        for _ in range(10):
            db_session.add(_mk_call(project_id="proj-a", status="success"))
        for _ in range(10):
            db_session.add(_mk_call(project_id="proj-b", status="success"))
        db_session.commit()

        spec = build_spec(
            BlastRadius(category=BlastRadiusCategory.UNKNOWN,
                         source=BlastRadiusSource.AUTO_DETECTED),
            target_total_cap=20,
        )
        result_a = sample(spec, db=db_session, project_id="proj-a")
        proj_b_ids = {c.id for c in db_session.query(Call).filter_by(project_id="proj-b")}

        for tid in result_a.all_trace_ids():
            assert tid not in proj_b_ids, "tenant isolation breach"

    def test_excludes_non_production(self, db_session) -> None:
        proj = "proj-prod"
        prod = _mk_call(project_id=proj, status="success", is_production=True)
        non_prod = _mk_call(project_id=proj, status="success", is_production=False)
        db_session.add(prod)
        db_session.add(non_prod)
        db_session.commit()

        spec = build_spec(
            BlastRadius(category=BlastRadiusCategory.UNKNOWN,
                         source=BlastRadiusSource.AUTO_DETECTED),
            target_total_cap=10,
        )
        result = sample(spec, db=db_session, project_id=proj)
        all_ids = result.all_trace_ids()
        assert prod.id in all_ids or len(all_ids) == 0  # may also be 0 if stratum quotas are 0
        assert non_prod.id not in all_ids

    def test_no_duplicates_across_strata(self, db_session) -> None:
        proj = "proj-dup"
        for _ in range(50):
            db_session.add(_mk_call(project_id=proj, status="success"))
        db_session.commit()

        spec = build_spec(
            BlastRadius(category=BlastRadiusCategory.UNKNOWN,
                         source=BlastRadiusSource.AUTO_DETECTED),
            target_total_cap=20,
        )
        result = sample(spec, db=db_session, project_id=proj)
        all_ids = list(result.all_trace_ids())
        assert len(all_ids) == len(set(all_ids)), "duplicate trace_id across strata"

    def test_stratum_for_reverse_lookup(self, db_session) -> None:
        proj = "proj-rev"
        c = _mk_call(project_id=proj, status="failed")
        db_session.add(c)
        db_session.commit()

        spec = build_spec(
            BlastRadius(category=BlastRadiusCategory.UNKNOWN,
                         source=BlastRadiusSource.AUTO_DETECTED),
            target_total_cap=10,
        )
        result = sample(spec, db=db_session, project_id=proj)
        if c.id in result.all_trace_ids():
            assert result.stratum_for(c.id) is not None
        assert result.stratum_for("not-a-real-id") is None
