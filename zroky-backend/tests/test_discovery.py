from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import Anomaly
from app.services.discovery import (
    BaselineConfig,
    PromotionInputs,
    aggregate_cluster,
    behavior_key,
    build_baselines_in_memory,
    decide_tier,
    extract_features,
    score,
)
from app.services.discovery.promote import TIER_SURFACED, TIER_WATCHING
from app.services.discovery.sink import DISCOVERY_DETECTOR, sink_candidates


PROJECT_ID = "proj-discovery"
AGENT_NAME = "refund-agent"
WORKFLOW_NAME = "refund-status"


@pytest.fixture()
def db_session(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'discovery.db'}",
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
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _created_at(index: int) -> datetime:
    return datetime(2026, 6, 1, tzinfo=UTC) + timedelta(minutes=index * 30)


def _normal_record(index: int, *, workflow_name: str | None = WORKFLOW_NAME) -> dict:
    eta_days = 2 + (index % 3)
    output = {
        "status": "pending",
        "eta_days": eta_days,
        "message": f"Refund is pending for {eta_days} days.",
        "next_step": "wait",
    }
    record = {
        "call_id": f"normal-{index:03d}",
        "project_id": PROJECT_ID,
        "agent_name": AGENT_NAME,
        "workflow_name": workflow_name,
        "status": "completed",
        "latency_ms": 600 + (index % 20),
        "cost_usd": 0.002 + ((index % 4) * 0.0001),
        "tool_calls": [
            {"name": "lookup_order"},
            {"name": "get_refund_status"},
            {"name": "render_refund_answer"},
        ],
        "output_content": json.dumps(output, separators=(",", ":")),
        "finish_reason": "stop",
        "outcome": {"success": True},
    }
    if workflow_name is None:
        record.pop("workflow_name")
    return record


def _features_stream(records: list[dict]) -> list[tuple[object, datetime]]:
    return [
        (extract_features(record), _created_at(index))
        for index, record in enumerate(records)
    ]


def _active_baseline() -> tuple[str, dict]:
    records = [_normal_record(index) for index in range(220)]
    baselines = build_baselines_in_memory(
        _features_stream(records),
        BaselineConfig(warmup_min_traces=200, warmup_min_days=3),
    )
    assert len(baselines) == 1
    key, baseline = next(iter(baselines.items()))
    assert baseline["status"] == "active"
    return key, baseline


def test_extract_features_prefers_persisted_fields_and_falls_back_to_agent_key() -> None:
    record = {
        "id": "call-top",
        "project_id": "project-top",
        "agent_name": "agent-top",
        "status": "completed",
        "cost_total": "0.003",
        "tool_lifecycle_summary_json": json.dumps([{"tool_name": "lookup_order"}]),
        "payload_json": json.dumps(
            {
                "call_id": "call-payload",
                "project_id": "project-payload",
                "agent_name": "agent-payload",
                "workflow_name": "",
                "cost_usd": 99,
                "tool_calls": [{"name": "wrong_tool"}],
                "output_content": "{\"ok\":true}",
                "outcome": {"success": True},
            }
        ),
    }

    features = extract_features(record)
    key, specificity = behavior_key(features)

    assert features.call_id == "call-top"
    assert features.project_id == "project-top"
    assert features.agent_name == "agent-top"
    assert features.workflow_name is None
    assert features.cost_usd == 0.003
    assert features.tool_names == ("lookup_order",)
    assert features.output_shape == "json:{ok}"
    assert specificity == "agent_only"
    assert key == "project=project-top|agent=agent-top|workflow=*"


def test_baseline_stays_learning_until_trace_and_day_warmup() -> None:
    records = [_normal_record(index) for index in range(199)]

    baselines = build_baselines_in_memory(
        _features_stream(records),
        BaselineConfig(warmup_min_traces=200, warmup_min_days=3),
    )

    baseline = next(iter(baselines.values()))
    assert baseline["status"] == "learning"
    assert baseline["sample_count"] == 199


def test_baseline_marks_missing_workflow_as_low_specificity() -> None:
    records = [_normal_record(index, workflow_name=None) for index in range(220)]

    baselines = build_baselines_in_memory(
        _features_stream(records),
        BaselineConfig(warmup_min_traces=200, warmup_min_days=3),
    )

    key, baseline = next(iter(baselines.items()))
    assert key == f"project={PROJECT_ID}|agent={AGENT_NAME}|workflow=*"
    assert baseline["status"] == "active"
    assert baseline["low_specificity"] is True
    assert baseline["specificity"] == "agent_only"


def test_baseline_marks_high_error_learning_window_as_suspect() -> None:
    records = []
    for index in range(220):
        record = _normal_record(index)
        record["status"] = "failed" if index % 2 == 0 else "completed"
        record["error_code"] = "TOOL_ERROR" if index % 2 == 0 else None
        records.append(record)

    baselines = build_baselines_in_memory(
        _features_stream(records),
        BaselineConfig(warmup_min_traces=200, warmup_min_days=3),
    )

    baseline = next(iter(baselines.values()))
    assert baseline["status"] == "suspect"
    assert baseline["error_rate"] >= 0.2


def test_missing_critical_tool_recurring_cluster_surfaces() -> None:
    key, baseline = _active_baseline()
    candidates = []
    for index in range(3):
        record = _normal_record(300 + index)
        record["call_id"] = f"missing-tool-{index}"
        record["tool_calls"] = [{"name": "lookup_order"}]
        record["output_content"] = "Refund looks complete."
        candidate = score(extract_features(record), baseline, behavior_key=key)
        assert candidate is not None
        candidates.append(candidate)

    agg = aggregate_cluster(candidates)
    tier = decide_tier(
        PromotionInputs(
            occurrence_count=agg["occurrence_count"],
            max_confidence=agg["max_confidence"],
            has_outcome=agg["has_outcome"],
            has_strong_structural=agg["has_strong_structural"],
            has_multi_dim=agg["has_multi_dim"],
            baseline_suspect=False,
        )
    )

    assert tier == TIER_SURFACED
    assert agg["occurrence_count"] == 3
    assert "missing critical tool" in agg["reason"]


def test_latency_only_cluster_stays_watching_without_structural_corroboration() -> None:
    key, baseline = _active_baseline()
    candidates = []
    for index in range(8):
        record = _normal_record(400 + index)
        record["call_id"] = f"slow-{index}"
        record["latency_ms"] = 5000 + index
        candidate = score(extract_features(record), baseline, behavior_key=key)
        assert candidate is not None
        candidates.append(candidate)

    agg = aggregate_cluster(candidates)
    tier = decide_tier(
        PromotionInputs(
            occurrence_count=agg["occurrence_count"],
            max_confidence=agg["max_confidence"],
            has_outcome=agg["has_outcome"],
            has_strong_structural=agg["has_strong_structural"],
            has_multi_dim=agg["has_multi_dim"],
            baseline_suspect=False,
        )
    )

    assert tier == TIER_WATCHING
    assert agg["has_strong_structural"] is False
    assert agg["has_multi_dim"] is False


def test_sink_writes_only_surfaced_clusters_to_anomalies(db_session) -> None:
    key, baseline = _active_baseline()
    surfaced_candidates = []
    for index in range(3):
        record = _normal_record(500 + index)
        record["call_id"] = f"sink-missing-tool-{index}"
        record["tool_calls"] = [{"name": "lookup_order"}]
        record["output_content"] = "Refund looks complete."
        candidate = score(extract_features(record), baseline, behavior_key=key)
        assert candidate is not None
        surfaced_candidates.append(candidate)

    watching_candidates = []
    for index in range(8):
        record = _normal_record(600 + index)
        record["call_id"] = f"sink-slow-{index}"
        record["latency_ms"] = 5000 + index
        candidate = score(extract_features(record), baseline, behavior_key=key)
        assert candidate is not None
        watching_candidates.append(candidate)

    written = sink_candidates(
        db_session,
        project_id=PROJECT_ID,
        candidates=[*surfaced_candidates, *watching_candidates],
        now=datetime.now(timezone.utc),
    )

    rows = db_session.execute(
        select(Anomaly).where(Anomaly.project_id == PROJECT_ID)
    ).scalars().all()
    assert len(written) == 1
    assert len(rows) == 1
    assert rows[0].detector == DISCOVERY_DETECTOR
    evidence = json.loads(rows[0].evidence_json or "{}")
    assert evidence["source"] == "discovery"
    assert evidence["primary_dimension"] == "missing_critical_tool"

