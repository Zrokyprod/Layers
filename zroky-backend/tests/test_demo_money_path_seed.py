from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import Anomaly, ApiKey, Call, DiagnosisJob, GoldenTrace, ProjectInvitation, ReplayRun
from app.services.issue_projection import issue_projection_from_anomaly


def _load_seed_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "seed_mvp_money_path_demo.py"
    spec = importlib.util.spec_from_file_location("seed_mvp_money_path_demo", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _json(raw: str | None) -> dict:
    assert raw
    parsed = json.loads(raw)
    assert isinstance(parsed, dict)
    return parsed


def test_seed_money_path_demo_creates_deterministic_product_loop(tmp_path: Path) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'money_path_demo.db'}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    seed_module = _load_seed_module()

    try:
        with session_factory() as session:
            summary = seed_module.seed_money_path_demo(session)
            seed_module.seed_money_path_demo(session)

            project_id = summary["project_id"]
            assert summary["email"] == "demo@zroky.local"
            assert summary["password"] == "ZrokyDemo123!"
            assert summary["call_id"] == "demo-call-refund-missed-tool"
            assert summary["issue_id"] == "demo-issue-refund-tool-not-called"
            assert summary["golden_set_id"] == "demo-golden-refund-status"
            assert summary["replay_run_id"] == "demo-replay-refund-fixed"
            assert summary["ci_run_id"] == "demo-ci-refund-tool-regression"
            assert summary["trace_id"] == "trace-demo-refund-missed-tool"
            assert summary["api_key_prefix"] == "zroky_api_live_demo"

            seeded_key = session.execute(
                select(ApiKey).where(ApiKey.id == summary["api_key_id"])
            ).scalar_one()
            assert seeded_key.project_id == project_id
            assert seeded_key.revoked_at is None

            invitation = session.execute(
                select(ProjectInvitation).where(ProjectInvitation.id == summary["invitation_id"])
            ).scalar_one()
            assert invitation.email == "teammate@zroky.local"
            assert invitation.revoked_at is None

            bad_call = session.execute(
                select(Call).where(Call.id == "demo-call-refund-missed-tool")
            ).scalar_one()
            payload = _json(bad_call.payload_json)
            tools = _json(bad_call.tool_lifecycle_summary_json)
            assert bad_call.project_id == project_id
            assert bad_call.status == "failed"
            assert bad_call.error_code == "TOOL_NOT_CALLED"
            assert "Refunds are usually processed within 5-10 business days" in payload["output"]
            assert tools["expected_tool"] == "get_refund_status"
            assert tools["tool_calls"] == []

            diagnosis = session.execute(
                select(DiagnosisJob).where(DiagnosisJob.id == "demo-diagnosis-refund-tool")
            ).scalar_one()
            diagnosis_result = _json(diagnosis.result_json)
            assert diagnosis_result["failure_code"] == "TOOL_NOT_CALLED"
            assert diagnosis_result["observed_tools"] == []

            anomaly = session.execute(
                select(Anomaly).where(Anomaly.id == "demo-issue-refund-tool-not-called")
            ).scalar_one()
            projection = issue_projection_from_anomaly(anomaly)
            assert anomaly.detector == "TOOL_SELECTION_FAILURE"
            assert projection.failure_code == "TOOL_NOT_CALLED"
            assert projection.status == "open"

            verified_replay = session.execute(
                select(ReplayRun).where(ReplayRun.id == "demo-replay-refund-fixed")
            ).scalar_one()
            verified_summary = _json(verified_replay.summary_json)
            assert verified_replay.status == "pass"
            assert verified_summary["verified_fix"] is True
            assert verified_summary["verification_status"] == "verified_fix"
            assert verified_summary["replay_mode"] == "mocked-tool"
            assert verified_summary["tool_behavior_diff"]["required_tool_called"] is True
            assert verified_summary["source_issue_id"] == "demo-issue-refund-tool-not-called"
            assert verified_summary["source_context"]["issue_id"] == "demo-issue-refund-tool-not-called"

            golden_trace = session.execute(
                select(GoldenTrace).where(GoldenTrace.id == "demo-golden-trace-refund-status")
            ).scalar_one()
            assert golden_trace.status == "active"
            assert golden_trace.expected_output_text is not None
            assert "RF-1001" in golden_trace.expected_output_text
            assert golden_trace.source_output_text == payload["output"]
            assert golden_trace.source_output_text != golden_trace.expected_output_text
            assert _json(golden_trace.criteria_json)["must_call_tools"] == ["get_refund_status"]

            ci_run = session.execute(
                select(ReplayRun).where(ReplayRun.id == "demo-ci-refund-tool-regression")
            ).scalar_one()
            ci_summary = _json(ci_run.summary_json)
            assert ci_run.status == "fail"
            assert ci_run.golden_set_id == "demo-golden-refund-status"
            assert ci_summary["verdict"] == "fail"
            assert ci_summary["regression_rate"] == 1.0
            assert ci_summary["regressed_count"] == 1
            assert ci_summary["verdict"] != "pass"
            assert ci_summary["source_issue_id"] == "demo-issue-refund-tool-not-called"
            assert "blocked this PR" in ci_summary["pr_comment_markdown"]
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
