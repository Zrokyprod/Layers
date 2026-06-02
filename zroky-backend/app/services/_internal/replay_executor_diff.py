from app.services._internal.replay_executor_common import *
from app.services._internal.replay_executor_live import _extract_tool_snapshot

def _simple_diff_metric(expected: str, actual: str) -> float:
    if not expected and not actual:
        return 0.0
    if not expected or not actual:
        return 1.0
    return round(1.0 - difflib.SequenceMatcher(None, expected, actual).ratio(), 4)


def _build_output_diff(*, expected: str, actual: str) -> dict[str, Any]:
    return {
        "changed": expected != actual,
        "expected_preview": expected[:1000],
        "actual_preview": actual[:1000],
        "diff_metric": _simple_diff_metric(expected, actual),
    }


def _build_tool_behavior_diff(
    *,
    source_call: Optional[Call],
    actual: ActualOutput | None = None,
) -> dict[str, Any]:
    if actual is not None and actual.metadata:
        metadata_diff = actual.metadata.get("tool_behavior_diff")
        if isinstance(metadata_diff, dict):
            return metadata_diff
    if source_call is None:
        return {
            "available": False,
            "changed": None,
            "reason": "source_call_missing",
        }
    snapshot = _extract_tool_snapshot(source_call)
    if snapshot is None:
        return {
            "available": False,
            "changed": None,
            "reason": "tool_snapshot_missing",
        }
    mode = (
        "frozen_recorded_summary"
        if snapshot["source"] == "tool_lifecycle_summary_json"
        else "frozen_recorded_payload"
    )
    return {
        "available": True,
        "changed": False,
        "baseline": snapshot["data"],
        "candidate": snapshot["data"],
        "mode": mode,
        "source": snapshot["source"],
    }


def _aggregate_trace_proof(
    db: Session,
    *,
    run_id: str,
    project_id: str,
) -> dict[str, Any]:
    rows = list(
        db.execute(
            select(ReplayRunTrace).where(
                ReplayRunTrace.project_id == project_id,
                ReplayRunTrace.replay_run_id == run_id,
            )
        ).scalars().all()
    )
    output_diffs: list[dict[str, Any]] = []
    tool_diffs: list[dict[str, Any]] = []
    cost_delta = 0.0
    latency_delta = 0
    for row in rows:
        scores = _safe_json_object(row.judge_scores_json)
        output = scores.get("output_diff")
        if isinstance(output, dict):
            output_diffs.append(output)
        tool = scores.get("tool_behavior_diff")
        if isinstance(tool, dict):
            tool_diffs.append(tool)
        cost_delta += float(scores.get("cost_delta_usd") or 0.0)
        latency_delta += int(scores.get("latency_delta_ms") or 0)
    return {
        "output_diff": {
            "changed_count": sum(1 for item in output_diffs if item.get("changed") is True),
            "items": output_diffs[:10],
        },
        "tool_behavior_diff": {
            "changed_count": sum(1 for item in tool_diffs if item.get("changed") is True),
            "missing_count": sum(1 for item in tool_diffs if item.get("available") is False),
            "items": tool_diffs[:10],
        },
        "cost_delta_usd": round(cost_delta, 8),
        "latency_delta_ms": latency_delta,
    }


def _source_failure_signal(
    db: Session,
    *,
    run: ReplayRun,
    existing: dict[str, Any],
) -> bool:
    if existing.get("source_issue_id") or existing.get("source_issue_failure_code"):
        return True

    call_ids = [
        row.call_id
        for row in db.execute(
            select(GoldenTrace.call_id).where(
                GoldenTrace.project_id == run.project_id,
                GoldenTrace.golden_set_id == run.golden_set_id,
                GoldenTrace.status == "active",
                GoldenTrace.call_id.is_not(None),
            )
        ).all()
        if row.call_id
    ]
    if not call_ids:
        return False

    calls = db.execute(
        select(Call).where(
            Call.project_id == run.project_id,
            Call.id.in_(call_ids),
        )
    ).scalars().all()
    return any(_call_has_failure_signal(call) for call in calls)


def _call_has_failure_signal(call: Call) -> bool:
    status_text = (call.status or "").strip().lower()
    success_statuses = {
        "ok",
        "success",
        "succeeded",
        "complete",
        "completed",
        "pass",
    }
    if call.error_code:
        return True
    if status_text and status_text not in success_statuses:
        return True

    payload = _safe_json_object(call.payload_json)
    for key in (
        "error",
        "error_code",
        "error_message",
        "failure_code",
        "failure_reason",
    ):
        value = payload.get(key)
        if value not in (None, "", [], {}):
            return True
    payload_status = str(payload.get("status") or "").strip().lower()
    return payload_status in {"failed", "error", "errored", "timeout"}


__all__ = [name for name in globals() if not name.startswith("__")]
