from app.schemas.ingest import IngestBatchRequest


def test_js_sdk_capture_payload_matches_ingest_batch_contract() -> None:
    payload = {
        "events": [
            {
                "schema_version": "v2",
                "call_id": "call_123",
                "event_id": "call_123:capture",
                "request_id": "resp_123",
                "provider": "openai",
                "model": "gpt-4o-mini",
                "call_type": "chat",
                "status": "success",
                "latency_ms": 42,
                "prompt_tokens": 5,
                "completion_tokens": 6,
                "total_tokens": 11,
                "agent_name": "support-agent",
                "agent_framework": "custom-js",
                "session_id": "sess_1",
                "workflow_id": "wf_1",
                "workflow_name": "support-resolution",
                "prompt_version": "support-v42",
                "trace_id": "trace_1",
                "environment": "production",
                "output_content": "done",
                "finish_reason": "stop",
                "stop_reason": "stop",
                "tool_definitions": [{"type": "function", "function": {"name": "lookup"}}],
                "tool_calls": [{"id": "tool_1", "function": {"name": "lookup"}}],
                "outcome": {"type": "ticket_escalated", "amount_usd": 12.5},
                "metadata": {"release": "2026.05.23", "status_code": 200},
            }
        ]
    }

    model = IngestBatchRequest.model_validate(payload)
    event = model.events[0]

    assert event.call_id == "call_123"
    assert event.event_id == "call_123:capture"
    assert event.completion_tokens == 6
    assert event.agent_name == "support-agent"
    assert event.agent_framework == "custom-js"
    assert event.workflow_id == "wf_1"
    assert event.workflow_name == "support-resolution"
    assert event.prompt_version == "support-v42"
    assert event.finish_reason == "stop"
    assert event.stop_reason == "stop"
    assert event.tool_calls == [{"id": "tool_1", "function": {"name": "lookup"}}]
    assert event.outcome == {"type": "ticket_escalated", "amount_usd": 12.5}
