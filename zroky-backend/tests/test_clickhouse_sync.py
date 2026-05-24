import json
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.services.clickhouse_sync import _call_to_row


def test_call_to_row_uses_call_columns_not_payload_usage() -> None:
    created_at = datetime(2026, 5, 24, 12, 30, tzinfo=timezone.utc)
    call = SimpleNamespace(
        id="call_1",
        project_id="proj_1",
        provider="openai",
        model="gpt-4o-mini",
        call_type="chat",
        created_at=created_at,
        latency_ms=42.5,
        input_tokens=11,
        output_tokens=7,
        total_tokens=18,
        cost_total=Decimal("0.00012345"),
        status="error",
        error_code="SCHEMA_VIOLATION",
        agent_name="refund-agent",
        metadata_json=json.dumps({"status_code": 422}),
        payload_json=json.dumps(
            {
                "usage": {
                    "prompt_tokens": 999,
                    "completion_tokens": 999,
                    "total_tokens": 1998,
                }
            }
        ),
    )

    row = _call_to_row(call)

    assert row["event_id"] == "call_1"
    assert row["project_id"] == "proj_1"
    assert row["timestamp_utc"] == created_at
    assert row["prompt_tokens"] == 11
    assert row["output_tokens"] == 7
    assert row["total_tokens"] == 18
    assert row["cost_usd"] == float(Decimal("0.00012345"))
    assert row["status"] == "error"
    assert row["status_code"] == 422
    assert row["failure_code"] == "SCHEMA_VIOLATION"
    assert row["agent_name"] == "refund-agent"


def test_call_to_row_infers_status_code_when_no_metadata_code() -> None:
    call = SimpleNamespace(
        id="call_2",
        project_id="proj_1",
        provider="anthropic",
        model="claude",
        call_type="streaming",
        created_at=None,
        latency_ms=None,
        input_tokens=0,
        output_tokens=0,
        total_tokens=0,
        cost_total=0,
        status="timeout",
        error_code="TIMEOUT",
        agent_name=None,
        metadata_json=None,
        payload_json="{}",
    )

    row = _call_to_row(call)

    assert row["status_code"] == 408
    assert row["failure_code"] == "TIMEOUT"


def test_call_to_row_handles_empty_payload_json() -> None:
    call = SimpleNamespace(
        id="call_3",
        project_id="proj_1",
        provider="openai",
        model="gpt-4o-mini",
        call_type="chat",
        created_at=None,
        latency_ms=None,
        input_tokens=3,
        output_tokens=4,
        total_tokens=7,
        cost_total=Decimal("0.00000123"),
        status="completed",
        error_code=None,
        agent_name="support-agent",
        metadata_json=None,
        payload_json="",
    )

    row = _call_to_row(call)

    assert row["prompt_tokens"] == 3
    assert row["output_tokens"] == 4
    assert row["total_tokens"] == 7
    assert row["cost_usd"] == float(Decimal("0.00000123"))
    assert row["status"] == "completed"
    assert row["status_code"] == 200
    assert row["failure_code"] == ""
