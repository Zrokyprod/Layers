"""Tests for `app.services.regression_ci.orchestrator.run_regression_ci`.

End-to-end exercise of the pipeline using an in-memory sqlite DB,
deterministic stubs for the candidate resolver, embedder, and judge.

Coverage:
  - Happy path: 10 successful calls, candidate ≈ baseline → verdict=pass.
  - Regression: candidate ≠ baseline on most traces → verdict=fail.
  - Error tolerance: resolver returns None for >5% of traces → verdict=error.
  - Empty project: zero traces → verdict=error with note.
  - Persistence: ReplayRun + ReplayRunTrace rows written when persist_run=True.
  - Tenant isolation: orchestrator never reads another project's calls.
  - Blast-radius override flows through to the report.
  - PR markdown generated end-to-end is non-empty and contains run_id.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import Call, ReplayRun, ReplayRunTrace
from app.services.regression_ci.blast_radius import ChangedFile
from app.services.regression_ci.models import (
    BlastRadius,
    BlastRadiusCategory,
    BlastRadiusSource,
    DiffVerdict,
)
from app.services.regression_ci.orchestrator import (
    CandidateOutput,
    RegressionCIInputs,
    run_regression_ci,
)
from app.services.regression_ci.pr_comment import format_markdown


# ── fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "test_regression_ci_orchestrator.db"
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
    response_text: str,
    prompt_text: str = "what is the refund policy?",
    status: str = "success",
) -> Call:
    payload = {
        "messages": [{"role": "user", "content": prompt_text}],
        "model": "gpt-4o-mini",
        "response": response_text,
    }
    return Call(
        id=str(uuid4()),
        project_id=project_id,
        event_id=str(uuid4()),
        created_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        agent_name="primary",
        provider="openai",
        model="gpt-4o-mini",
        status=status,
        is_production=True,
        payload_json=json.dumps(payload),
    )


# ── stubs ──────────────────────────────────────────────────────────────────


@dataclass
class _StubEmbedder:
    text_to_vec: dict[str, list[float] | None]

    def generate_embedding(self, text: str) -> list[float] | None:
        return self.text_to_vec.get(text, [1.0, 0.0])  # default = "same"


def _resolver_echoes_baseline(call: Call) -> CandidateOutput:
    """Returns the baseline output unchanged → diff=identical → PASS."""
    payload = json.loads(call.payload_json)
    return CandidateOutput(
        text=str(payload.get("response", "")),
        cost_usd=0.001, latency_ms=42,
    )


def _resolver_returns_different(call: Call) -> CandidateOutput:
    """Returns a wildly different output → diff=FAIL."""
    return CandidateOutput(
        text="completely unrelated answer that does not match anything",
        cost_usd=0.002, latency_ms=55,
    )


def _resolver_always_errors(call: Call) -> CandidateOutput:
    return CandidateOutput(
        text=None, error_message="provider_5xx", cost_usd=0.0, latency_ms=0,
    )


# ── tests ──────────────────────────────────────────────────────────────────


class TestOrchestrator:
    def test_happy_path_pass(self, db_session) -> None:
        proj = "proj-happy"
        for i in range(10):
            db_session.add(_mk_call(
                project_id=proj,
                response_text=f"refund policy explanation number {i}",
            ))
        db_session.commit()

        inputs = RegressionCIInputs(
            project_id=proj,
            git_sha="abc123",
            pr_body=None,
            zroky_yaml=None,
            changed_files=[ChangedFile(path="prompts/tools/refund.md")],
            threshold=0.02,
            target_total_cap=10,
        )

        report = run_regression_ci(
            inputs,
            db=db_session,
            candidate_resolver=_resolver_echoes_baseline,
        )

        assert report.verdict == "pass"
        assert report.regressed_count == 0
        assert report.trace_count > 0
        assert report.blast_radius.category == BlastRadiusCategory.TOOL_PROMPT
        assert report.cost_usd > 0.0

    def test_regression_failure(self, db_session) -> None:
        proj = "proj-regress"
        for i in range(10):
            db_session.add(_mk_call(
                project_id=proj,
                response_text=f"the refund policy is thirty days for product {i}",
            ))
        db_session.commit()

        inputs = RegressionCIInputs(
            project_id=proj,
            git_sha="bad456",
            pr_body=None,
            zroky_yaml=None,
            changed_files=[ChangedFile(path="prompts/system.md")],
            threshold=0.02,
            target_total_cap=10,
        )

        report = run_regression_ci(
            inputs,
            db=db_session,
            candidate_resolver=_resolver_returns_different,
        )

        # Every trace produces a wildly-different output → most should regress.
        assert report.regressed_count > 0
        assert report.verdict == "fail"
        assert report.regression_rate > inputs.threshold

    def test_high_error_rate_yields_error_verdict(self, db_session) -> None:
        proj = "proj-errs"
        for _ in range(10):
            db_session.add(_mk_call(
                project_id=proj, response_text="some baseline response text here",
            ))
        db_session.commit()

        inputs = RegressionCIInputs(
            project_id=proj, git_sha="x", pr_body=None, zroky_yaml=None,
            changed_files=[ChangedFile(path="prompts/system.md")],
            target_total_cap=10,
        )
        report = run_regression_ci(
            inputs, db=db_session,
            candidate_resolver=_resolver_always_errors,
        )

        assert report.verdict == "error"
        assert report.error_count > 0
        assert report.error_rate >= 0.05
        assert any("error rate" in n for n in report.notes)

    def test_empty_project_errors_with_note(self, db_session) -> None:
        inputs = RegressionCIInputs(
            project_id="proj-empty",
            git_sha=None, pr_body=None, zroky_yaml=None,
            changed_files=[],
            target_total_cap=10,
        )
        report = run_regression_ci(
            inputs, db=db_session,
            candidate_resolver=_resolver_echoes_baseline,
        )
        assert report.verdict == "error"
        assert report.trace_count == 0
        assert any("no traces" in n for n in report.notes)

    def test_persistence_writes_run_and_trace_rows(self, db_session) -> None:
        proj = "proj-persist"
        for _ in range(5):
            db_session.add(_mk_call(
                project_id=proj, response_text="baseline answer",
            ))
        db_session.commit()

        inputs = RegressionCIInputs(
            project_id=proj, git_sha="sha-1", pr_body=None, zroky_yaml=None,
            changed_files=[ChangedFile(path="prompts/system.md")],
            target_total_cap=5,
        )
        report = run_regression_ci(
            inputs, db=db_session,
            candidate_resolver=_resolver_echoes_baseline,
            persist_run=True,
        )

        run_row = db_session.execute(
            select(ReplayRun).where(ReplayRun.id == report.run_id)
        ).scalar_one()
        assert run_row.status == report.verdict
        assert run_row.summary_json is not None
        summary = json.loads(run_row.summary_json)
        assert summary["schema_version"] == "v1"
        assert summary["run_id"] == report.run_id

        trace_rows = db_session.execute(
            select(ReplayRunTrace).where(ReplayRunTrace.replay_run_id == report.run_id)
        ).scalars().all()
        assert len(trace_rows) == report.trace_count

    def test_tenant_isolation_during_replay(self, db_session) -> None:
        # Plant calls in two projects. Orchestrator for proj-A must NEVER
        # ingest proj-B trace IDs.
        for _ in range(5):
            db_session.add(_mk_call(project_id="proj-A", response_text="A side"))
        for _ in range(5):
            db_session.add(_mk_call(project_id="proj-B", response_text="B side"))
        db_session.commit()

        inputs = RegressionCIInputs(
            project_id="proj-A", git_sha=None, pr_body=None, zroky_yaml=None,
            changed_files=[ChangedFile(path="prompts/system.md")],
            target_total_cap=20,
        )
        seen_project_ids: set[str] = set()

        def _resolver(call: Call) -> CandidateOutput:
            seen_project_ids.add(call.project_id)
            return CandidateOutput(text="A side", cost_usd=0.0)

        report = run_regression_ci(
            inputs, db=db_session, candidate_resolver=_resolver,
        )
        assert seen_project_ids == {"proj-A"} or seen_project_ids == set()

    def test_operator_override_flows_through(self, db_session) -> None:
        for _ in range(3):
            db_session.add(_mk_call(
                project_id="proj-override", response_text="x",
            ))
        db_session.commit()

        override = BlastRadius(
            category=BlastRadiusCategory.SYSTEM_PROMPT,
            source=BlastRadiusSource.OVERRIDE,
        )
        inputs = RegressionCIInputs(
            project_id="proj-override", git_sha=None, pr_body=None,
            zroky_yaml=None,
            changed_files=[ChangedFile(path="prompts/tools/refund.md")],  # would auto-detect TOOL_PROMPT
            target_total_cap=3,
        )

        report = run_regression_ci(
            inputs, db=db_session,
            candidate_resolver=_resolver_echoes_baseline,
            operator_override=override,
        )
        assert report.blast_radius.category == BlastRadiusCategory.SYSTEM_PROMPT
        assert report.blast_radius.source == BlastRadiusSource.OVERRIDE

    def test_pr_markdown_renders_end_to_end(self, db_session) -> None:
        for _ in range(5):
            db_session.add(_mk_call(
                project_id="proj-md", response_text="baseline answer",
            ))
        db_session.commit()

        inputs = RegressionCIInputs(
            project_id="proj-md", git_sha="cafe", pr_body=None, zroky_yaml=None,
            changed_files=[ChangedFile(path="prompts/system.md")],
            target_total_cap=5,
        )
        report = run_regression_ci(
            inputs, db=db_session,
            candidate_resolver=_resolver_echoes_baseline,
        )
        md = format_markdown(report, dashboard_base="https://app.zroky.com")
        assert report.run_id in md
        assert "Replay CI" in md
        assert "https://app.zroky.com" in md
