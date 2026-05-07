"""Tests for SDK init + call error classification."""
from copy import deepcopy
from unittest.mock import MagicMock, patch

import pytest

import zroky
from zroky._internal.models import ErrorCode
from zroky._internal.prompt_fingerprint import generate_prompt_fingerprint


def _reset_sdk():
    """Reset SDK global state between tests."""
    zroky._config = None
    zroky._queue = None
    zroky._recent_preflight_calls.clear()
    zroky._payload_guard_logged_call_ids.clear()
    zroky._payload_guard_log_order.clear()


def test_init_sets_config(tmp_path, monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_API_KEY", "test-key-abc")
    monkeypatch.setenv("ZROKY_PROJECT", "my-project")

    with patch("zroky._internal.queue.IngestClient"):
        zroky.init()

    assert zroky._config is not None
    assert zroky._config.api_key == "test-key-abc"
    assert zroky._config.project == "my-project"
    zroky.shutdown()
    _reset_sdk()


def test_agent_context_sets_agent_name(monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_API_KEY", "test-key")
    monkeypatch.setenv("ZROKY_MODE", "local")

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init()

    captured_agent: list[str | None] = []

    def mock_enqueue(event):
        captured_agent.append(event.agent_name)

    zroky._queue.enqueue = mock_enqueue  # type: ignore[union-attr]

    with zroky.agent("research-agent"):
        assert zroky._get_agent() == "research-agent"
        from zroky._internal.models import CallEvent  # noqa: PLC0415
        zroky._queue.enqueue(CallEvent(  # type: ignore[union-attr]
            provider="test", model="test", messages=[],
            agent_name=zroky._get_agent(),
        ))

    assert captured_agent[0] == "research-agent"
    assert zroky._get_agent() is None  # restored after context
    zroky.shutdown()
    _reset_sdk()


def test_classify_error_token_overflow():
    exc = Exception("context_length_exceeded: tokens exceed 4096")
    assert zroky._classify_error(exc) == ErrorCode.TOKEN_OVERFLOW


def test_classify_error_token_overflow_provider_patterns():
    provider_errors = [
        "This model's maximum context length is 4096 tokens",
        "too many tokens in request body",
        "token-limit-exceeded by Azure deployment",
    ]
    for message in provider_errors:
        assert zroky._classify_error(Exception(message)) == ErrorCode.TOKEN_OVERFLOW


def test_classify_error_rate_limit():
    exc = Exception("429 Rate limit exceeded")
    assert zroky._classify_error(exc) == ErrorCode.RATE_LIMIT


def test_classify_error_auth_failure():
    exc = Exception("401 Invalid API key provided")
    assert zroky._classify_error(exc) == ErrorCode.AUTH_FAILURE


def test_classify_error_unknown():
    exc = Exception("some random error")
    assert zroky._classify_error(exc) == "UNKNOWN_ERROR"


def test_classify_error_uses_provider_status_code():
    class ProviderRateLimitError(Exception):
        status_code = 429

    assert zroky._classify_error(ProviderRateLimitError("provider rejected request")) == ErrorCode.RATE_LIMIT


def test_record_failure_includes_structured_failure_reason(monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")
    captured = []

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init()

    zroky._queue.enqueue = lambda e: captured.append(e)  # type: ignore[union-attr]

    class FakeResponse:
        status_code = 400
        headers = {"x-request-id": "req_123", "retry-after": "2"}

        def json(self):
            return {
                "error": {
                    "message": "Unknown parameter for user@example.com",
                    "type": "invalid_request_error",
                    "code": "unknown_parameter",
                    "param": "temperature",
                }
            }

    class ProviderBadRequestError(Exception):
        response = FakeResponse()
        request_id = "req_123"

    zroky.record(
        provider="openai",
        model="gpt-4o",
        request={"messages": [{"role": "user", "content": "hi"}]},
        error=ProviderBadRequestError("bad request for user@example.com"),
        latency_ms=12.0,
    )

    event = captured[0]
    assert event.error_code == ErrorCode.UNKNOWN_ERROR
    assert event.failure_reason["http_status"] == 400
    assert event.failure_reason["provider_error_code"] == "unknown_parameter"
    assert event.failure_reason["provider_error_param"] == "temperature"
    assert event.failure_reason["provider_request_id"] == "req_123"
    assert "user@example.com" not in event.failure_reason["message"]

    payload = event.to_ingest_payload()
    assert payload["failure_reason"]["provider_error_type"] == "invalid_request_error"
    assert payload["failure_reason"]["retry_after_seconds"] == 2.0

    zroky.shutdown()
    _reset_sdk()


def test_record_manual_capture(monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")
    captured = []

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init()

    zroky._queue.enqueue = lambda e: captured.append(e)  # type: ignore[union-attr]

    class FakeResponse:
        class usage:
            prompt_tokens = 100
            completion_tokens = 50
            input_tokens = None
            output_tokens = None
            completion_tokens_details = None
            cache_creation_input_tokens = 0
            cache_read_input_tokens = 0
        choices = []

    zroky.record(
        provider="openai",
        model="gpt-4o",
        request={"messages": [{"role": "user", "content": "hi"}]},
        response=FakeResponse(),
        latency_ms=42.0,
    )

    assert len(captured) == 1
    event = captured[0]
    assert event.provider == "openai"
    assert event.model == "gpt-4o"
    assert event.prompt_tokens == 100
    assert event.estimated_prompt_tokens is not None
    assert event.estimated_prompt_tokens > 0
    assert event.model_context_limit == 128000
    assert event.model_context_limit_source == "catalog_exact"
    assert event.model_context_limit_confidence == 0.95
    assert event.model_context_limit_catalog_version == "model_context_limits_2026_05_05"
    assert event.token_estimator_version == "chars_per_token_v1"
    assert event.token_rules_version == "token_rules_v2"
    assert event.latency_ms == 42.0
    assert isinstance(event.prompt_fingerprint, str)
    assert len(event.prompt_fingerprint) == 64
    ingest_payload = event.to_ingest_payload()
    assert ingest_payload["estimated_prompt_tokens"] == event.estimated_prompt_tokens
    assert ingest_payload["model_context_limit"] == 128000
    assert ingest_payload["model_context_limit_source"] == "catalog_exact"
    assert ingest_payload["model_context_limit_catalog_version"] == (
        "model_context_limits_2026_05_05"
    )
    assert ingest_payload["token_estimator_version"] == "chars_per_token_v1"
    assert ingest_payload["token_rules_version"] == "token_rules_v2"

    zroky.shutdown()
    _reset_sdk()


def test_record_uses_model_context_limit_override(monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")
    monkeypatch.setenv("ZROKY_MODEL_CONTEXT_LIMITS", '{"custom-model": 12345}')
    captured = []

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init()

    zroky._queue.enqueue = lambda e: captured.append(e)  # type: ignore[union-attr]

    zroky.record(
        provider="openai",
        model="custom-model",
        request={"messages": [{"role": "user", "content": "hi"}]},
        latency_ms=1.0,
    )

    assert captured[0].model_context_limit == 12345
    assert captured[0].model_context_limit_source == "env_override"
    assert captured[0].model_context_limit_source_detail == "ZROKY_MODEL_CONTEXT_LIMITS"

    zroky.shutdown()
    _reset_sdk()


def test_invalid_model_context_limit_override_warns(monkeypatch, caplog):
    monkeypatch.setenv(
        "ZROKY_MODEL_CONTEXT_LIMITS",
        "invalid-sdk-limit=0,custom-sdk-model=12345",
    )

    with caplog.at_level("WARNING", logger="zroky._internal.token_rules"):
        assert zroky._validation.known_model_context_limit("custom-sdk-model") == 12345

    assert "Ignoring invalid ZROKY_MODEL_CONTEXT_LIMITS entry" in caplog.text
    assert "invalid-sdk-limit=0" in caplog.text


def test_call_capture_sets_deterministic_prompt_fingerprint(monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")
    captured = []

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init()

    zroky._queue.enqueue = lambda e: captured.append(e)  # type: ignore[union-attr]

    class FakeResponse:
        class usage:
            prompt_tokens = 10
            completion_tokens = 5
            input_tokens = None
            output_tokens = None
            completion_tokens_details = None
            cache_creation_input_tokens = 0
            cache_read_input_tokens = 0

        choices = []

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = FakeResponse()

    messages_a = [{"role": "user", "content": "Summarize report id 123"}]
    messages_b = [{"role": "user", "content": "Summarize report id 999"}]
    tools = [{"type": "function", "function": {"name": "search"}}]

    zroky.call(
        provider="openai",
        model="gpt-4o",
        messages=messages_a,
        tools=tools,
        _client=mock_client,
    )
    zroky.call(
        provider="openai",
        model="gpt-4o",
        messages=messages_b,
        tools=tools,
        _client=mock_client,
    )

    assert len(captured) == 2
    expected_a = generate_prompt_fingerprint(messages_a, tools, "gpt-4o")
    expected_b = generate_prompt_fingerprint(messages_b, tools, "gpt-4o")

    assert captured[0].prompt_fingerprint == expected_a
    assert captured[1].prompt_fingerprint == expected_b
    assert captured[0].prompt_fingerprint == captured[1].prompt_fingerprint

    zroky.shutdown()
    _reset_sdk()


def test_call_uses_original_provider_payload_and_masked_telemetry(monkeypatch):
    _reset_sdk()
    captured = []

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init(mode="local", mask_pii=True)

    zroky._queue.enqueue = lambda e: captured.append(e)  # type: ignore[union-attr]

    class FakeResponse:
        class usage:
            prompt_tokens = 10
            completion_tokens = 5
            input_tokens = None
            output_tokens = None
            completion_tokens_details = None
            cache_creation_input_tokens = 0
            cache_read_input_tokens = 0

        choices = []

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = FakeResponse()

    messages = [{"role": "user", "content": "Email user@example.com"}]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "lookup",
                "description": "Lookup user@example.com",
            },
        }
    ]

    zroky.call(
        provider="openai",
        model="gpt-4o",
        messages=messages,
        tools=tools,
        _client=mock_client,
    )

    provider_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert provider_kwargs["messages"] == messages
    assert provider_kwargs["messages"] is not messages
    assert provider_kwargs["tools"] == tools
    assert provider_kwargs["tools"] is not tools
    assert provider_kwargs["messages"] is not captured[0].messages
    assert provider_kwargs["tools"] is not captured[0].tools
    assert captured[0].messages[0]["content"] == "Email [REDACTED_EMAIL]"
    assert captured[0].tools[0]["function"]["description"] == "Lookup [REDACTED_EMAIL]"
    assert messages[0]["content"] == "Email user@example.com"
    assert tools[0]["function"]["description"] == "Lookup user@example.com"

    zroky.shutdown()
    _reset_sdk()


def test_streaming_call_uses_original_provider_payload_and_masked_telemetry(monkeypatch):
    _reset_sdk()
    captured = []

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init(mode="local", mask_pii=True)

    zroky._queue.enqueue = lambda e: captured.append(e)  # type: ignore[union-attr]

    class FakeChunk:
        choices = []

        class usage:
            prompt_tokens = 8
            completion_tokens = 3
            total_tokens = 11

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = iter([FakeChunk()])

    messages = [{"role": "user", "content": "Stream user@example.com"}]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "lookup",
                "description": "Stream user@example.com",
            },
        }
    ]

    stream_iter = zroky.call(
        provider="openai",
        model="gpt-4o",
        messages=messages,
        tools=tools,
        stream=True,
        _client=mock_client,
    )
    list(stream_iter)

    provider_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert provider_kwargs["stream"] is True
    assert provider_kwargs["messages"] == messages
    assert provider_kwargs["messages"] is not messages
    assert provider_kwargs["tools"] == tools
    assert provider_kwargs["tools"] is not tools
    assert provider_kwargs["messages"] is not captured[0].messages
    assert provider_kwargs["tools"] is not captured[0].tools
    assert captured[0].messages[0]["content"] == "Stream [REDACTED_EMAIL]"
    assert captured[0].tools[0]["function"]["description"] == "Stream [REDACTED_EMAIL]"
    assert messages[0]["content"] == "Stream user@example.com"
    assert tools[0]["function"]["description"] == "Stream user@example.com"

    zroky.shutdown()
    _reset_sdk()


def test_call_error_path_uses_original_provider_payload_and_masked_telemetry(monkeypatch):
    _reset_sdk()
    captured = []

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init(mode="local", mask_pii=True)

    zroky._queue.enqueue = lambda e: captured.append(e)  # type: ignore[union-attr]

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RuntimeError("provider boom")

    messages = [{"role": "user", "content": "Fail user@example.com"}]

    with pytest.raises(RuntimeError, match="provider boom"):
        zroky.call(
            provider="openai",
            model="gpt-4o",
            messages=messages,
            _client=mock_client,
        )

    provider_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert provider_kwargs["messages"] == messages
    assert provider_kwargs["messages"] is not messages
    assert captured[0].status == "failed"
    assert captured[0].messages[0]["content"] == "Fail [REDACTED_EMAIL]"
    assert captured[0].error_message == "provider boom"
    assert messages[0]["content"] == "Fail user@example.com"

    zroky.shutdown()
    _reset_sdk()


def test_streaming_response_chunks_are_masked_in_telemetry(monkeypatch):
    _reset_sdk()
    captured = []

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init(mode="local", mask_pii=True)

    zroky._queue.enqueue = lambda e: captured.append(e)  # type: ignore[union-attr]

    class FakeFunction:
        name = "lookup"
        arguments = (
            '{"email":"stream-tool@example.com",'
            '"api_key":"sk-proj-abcdefghijklmnopqrstuvwxyz1234567890"}'
        )

    class FakeToolCall:
        id = "tool-1"
        type = "function"
        function = FakeFunction()

    class FakeDelta:
        content = "partial stream@example.com"
        tool_calls = [FakeToolCall()]

    class FakeChoice:
        delta = FakeDelta()

    class FakeChunk:
        choices = [FakeChoice()]
        usage = None

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = iter([FakeChunk()])

    stream_iter = zroky.call(
        provider="openai",
        model="gpt-4o",
        messages=[{"role": "user", "content": "safe"}],
        stream=True,
        _client=mock_client,
    )
    list(stream_iter)

    rendered_tool_calls = str(captured[0].tool_calls_made)
    assert "stream@example.com" not in captured[0].output_content
    assert "stream-tool@example.com" not in rendered_tool_calls
    assert "sk-proj-" not in rendered_tool_calls
    assert "[REDACTED_EMAIL]" in captured[0].output_content
    assert "[REDACTED_KEY]" in rendered_tool_calls

    zroky.shutdown()
    _reset_sdk()


def test_error_message_is_masked_before_telemetry(monkeypatch):
    _reset_sdk()
    captured = []

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init(mode="local", mask_pii=True)

    zroky._queue.enqueue = lambda e: captured.append(e)  # type: ignore[union-attr]

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RuntimeError(
        "provider failed for user@example.com with sk-proj-abcdefghijklmnopqrstuvwxyz1234567890"
    )

    with pytest.raises(RuntimeError):
        zroky.call(
            provider="openai",
            model="gpt-4o",
            messages=[{"role": "user", "content": "safe"}],
            _client=mock_client,
        )

    assert "user@example.com" not in captured[0].error_message
    assert "sk-proj-" not in captured[0].error_message
    assert "[REDACTED_EMAIL]" in captured[0].error_message
    assert "[REDACTED_KEY]" in captured[0].error_message

    zroky.shutdown()
    _reset_sdk()


def test_response_tool_call_arguments_are_masked(monkeypatch):
    _reset_sdk()
    captured = []

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init(mode="local", mask_pii=True)

    zroky._queue.enqueue = lambda e: captured.append(e)  # type: ignore[union-attr]

    class FakeFunction:
        name = "lookup"
        arguments = (
            '{"email":"tool@example.com",'
            '"api_key":"sk-proj-abcdefghijklmnopqrstuvwxyz1234567890"}'
        )

    class FakeToolCall:
        id = "tool-1"
        type = "function"
        function = FakeFunction()

    class FakeMessage:
        content = "Answer for result@example.com"
        tool_calls = [FakeToolCall()]

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        usage = None
        choices = [FakeChoice()]

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = FakeResponse()

    zroky.call(
        provider="openai",
        model="gpt-4o",
        messages=[{"role": "user", "content": "safe"}],
        _client=mock_client,
    )

    rendered_tool_calls = str(captured[0].tool_calls_made)
    assert "tool@example.com" not in rendered_tool_calls
    assert "sk-proj-" not in rendered_tool_calls
    assert "result@example.com" not in captured[0].output_content
    assert "[REDACTED_EMAIL]" in rendered_tool_calls
    assert "[REDACTED_KEY]" in rendered_tool_calls
    assert captured[0].output_fingerprint is not None
    assert "result@example.com" not in (captured[0].normalized_output or "")
    assert captured[0].tool_lifecycle_summary[0]["tool_name"] == "lookup"

    zroky.shutdown()
    _reset_sdk()


def test_call_error_payload_includes_token_estimate_without_usage(monkeypatch):
    _reset_sdk()
    captured = []

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init(mode="local", mask_pii=True)

    zroky._queue.enqueue = lambda e: captured.append(e)  # type: ignore[union-attr]

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RuntimeError(
        "maximum context length exceeded"
    )

    messages = [{"role": "user", "content": "x" * 16000}]

    with pytest.raises(RuntimeError, match="maximum context length exceeded"):
        zroky.call(
            provider="openai",
            model="gpt-3.5-turbo",
            messages=messages,
            _client=mock_client,
        )

    event = captured[0]
    assert event.error_code == ErrorCode.TOKEN_OVERFLOW
    assert event.prompt_tokens == 0
    assert event.estimated_prompt_tokens is not None
    assert event.estimated_prompt_tokens > 0
    assert event.model_context_limit == 4096
    assert event.model_context_limit_source == "catalog_exact"
    assert event.model_context_limit_catalog_version == "model_context_limits_2026_05_05"
    assert event.token_estimator_version == "chars_per_token_v1"
    assert event.token_rules_version == "token_rules_v2"
    ingest_payload = event.to_ingest_payload()
    assert ingest_payload["estimated_prompt_tokens"] == event.estimated_prompt_tokens
    assert ingest_payload["model_context_limit"] == 4096
    assert ingest_payload["model_context_limit_source"] == "catalog_exact"
    assert ingest_payload["model_context_limit_catalog_version"] == (
        "model_context_limits_2026_05_05"
    )
    assert ingest_payload["token_estimator_version"] == "chars_per_token_v1"
    assert ingest_payload["token_rules_version"] == "token_rules_v2"

    zroky.shutdown()
    _reset_sdk()


def test_provider_payload_guard_recovers_without_raising(caplog):
    original_messages = [{"role": "user", "content": "Email user@example.com"}]
    telemetry_messages = [{"role": "user", "content": "Email [REDACTED_EMAIL]"}]
    original_tools = [
        {
            "type": "function",
            "function": {
                "name": "lookup",
                "description": "Lookup user@example.com",
            },
        }
    ]
    telemetry_tools = [
        {
            "type": "function",
            "function": {
                "name": "lookup",
                "description": "Lookup [REDACTED_EMAIL]",
            },
        }
    ]

    with caplog.at_level("WARNING", logger="zroky"):
        provider_messages, provider_tools = zroky._ensure_provider_payload_is_isolated(
            original_messages=original_messages,
            provider_messages=telemetry_messages,
            telemetry_messages=telemetry_messages,
            original_tools=original_tools,
            provider_tools=telemetry_tools,
            telemetry_tools=telemetry_tools,
            model="gpt-4o",
            call_id="call-123",
            mode="stream",
        )

    assert provider_messages == original_messages
    assert provider_messages is not original_messages
    assert provider_messages is not telemetry_messages
    assert provider_tools == original_tools
    assert provider_tools is not original_tools
    assert provider_tools is not telemetry_tools
    assert "recovered provider payload" in caplog.text
    assert "model=gpt-4o" in caplog.text
    assert "call_id=call-123" in caplog.text
    assert "mode=stream" in caplog.text
    assert caplog.text.count("recovered provider payload") == 1


def test_provider_kwargs_removes_duplicate_payload_keys(caplog):
    kwargs = {
        "messages": [{"role": "user", "content": "ignored"}],
        "tools": [{"type": "function"}],
        "stream": False,
        "temperature": 0.2,
        "extra_body": {"metadata": {"safe": True}},
    }

    with caplog.at_level("ERROR", logger="zroky"):
        provider_kwargs = zroky._build_provider_kwargs(
            kwargs,
            model="gpt-4o",
            call_id="call-456",
            mode="non-stream",
        )

    assert "messages" not in provider_kwargs
    assert "tools" not in provider_kwargs
    assert "stream" not in provider_kwargs
    assert provider_kwargs["temperature"] == 0.2
    assert provider_kwargs["extra_body"] is kwargs["extra_body"]
    assert "messages" in kwargs
    assert "tools" in kwargs
    assert "stream" in kwargs
    assert "keys=messages,stream,tools" in caplog.text
    assert "model=gpt-4o" in caplog.text
    assert "call_id=call-456" in caplog.text
    assert "mode=non-stream" in caplog.text


def test_validate_does_not_mutate_input():
    payload = {
        "model": "gpt-4o",
        "api_key": "sk-example-1234567890",
        "messages": [{"role": "user", "content": "hello"}],
        "tools": [{"type": "function", "function": {"name": "search"}}],
        "meta": {"recent_calls": 2},
    }
    original = deepcopy(payload)

    result = zroky.validate(payload)

    assert isinstance(result, dict)
    assert payload == original


def test_verbose_logs_include_prompt_fingerprint(monkeypatch, capsys):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")
    monkeypatch.setenv("ZROKY_VERBOSE", "true")

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init()

    class FakeResponse:
        class usage:
            prompt_tokens = 10
            completion_tokens = 5
            input_tokens = None
            output_tokens = None
            completion_tokens_details = None
            cache_creation_input_tokens = 0
            cache_read_input_tokens = 0

        choices = []

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = FakeResponse()

    zroky.call(
        provider="openai",
        model="gpt-4o",
        messages=[{"role": "user", "content": "summarize report id 123"}],
        tools=[{"name": "search"}],
        _client=mock_client,
    )

    captured_stdout = capsys.readouterr().out
    assert "fp=" in captured_stdout
    assert "call captured" in captured_stdout.lower()

    zroky.shutdown()
    _reset_sdk()


def test_init_reads_preflight_validation_flag(monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")
    monkeypatch.setenv("ZROKY_VALIDATE_PREFLIGHT", "true")

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init()

    assert zroky._config is not None
    assert zroky._config.validate_preflight is True

    zroky.shutdown()
    _reset_sdk()


def test_init_reads_preflight_sample_rate(monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")
    monkeypatch.setenv("ZROKY_VALIDATE_PREFLIGHT", "true")
    monkeypatch.setenv("ZROKY_VALIDATE_PREFLIGHT_SAMPLE_RATE", "0.25")

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init()

    assert zroky._config is not None
    assert zroky._config.validate_preflight is True
    assert zroky._config.validate_preflight_sample_rate == pytest.approx(0.25)

    zroky.shutdown()
    _reset_sdk()


def test_init_reads_global_fallback_policy(monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")
    monkeypatch.setenv("ZROKY_FALLBACK_MODELS", "gpt-4o-mini,claude-3-haiku")
    monkeypatch.setenv("ZROKY_FALLBACK_ADAPTIVE", "true")
    monkeypatch.setenv("ZROKY_FALLBACK_MAX", "1")

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init()

    assert zroky._config is not None
    assert zroky._config.fallback_models == ("gpt-4o-mini", "claude-3-haiku")
    assert zroky._config.fallback_adaptive is True
    assert zroky._config.fallback_max == 1

    zroky.shutdown()
    _reset_sdk()


def test_init_reads_preflight_blocking_warning_types(monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")
    monkeypatch.setenv("ZROKY_PREFLIGHT_BLOCKING_WARNINGS", "auth_risk,rate_limit_risk")

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init()

    assert zroky._config is not None
    assert zroky._config.preflight_blocking_warning_types == (
        "AUTH_RISK",
        "RATE_LIMIT_RISK",
    )

    zroky.shutdown()
    _reset_sdk()


def test_init_rejects_invalid_preflight_sample_rate(monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")
    monkeypatch.setenv("ZROKY_VALIDATE_PREFLIGHT", "true")
    monkeypatch.setenv("ZROKY_VALIDATE_PREFLIGHT_SAMPLE_RATE", "1.5")

    with patch("zroky._internal.queue.LocalWriter"):
        with pytest.raises(ValueError):
            zroky.init()

    _reset_sdk()


def test_init_rejects_non_numeric_preflight_sample_rate(monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")
    monkeypatch.setenv("ZROKY_VALIDATE_PREFLIGHT", "true")
    monkeypatch.setenv("ZROKY_VALIDATE_PREFLIGHT_SAMPLE_RATE", "abc")

    with patch("zroky._internal.queue.LocalWriter"):
        with pytest.raises(ValueError, match="ZROKY_VALIDATE_PREFLIGHT_SAMPLE_RATE"):
            zroky.init()

    _reset_sdk()


def test_init_argument_overrides_preflight_env_values(monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")
    monkeypatch.setenv("ZROKY_VALIDATE_PREFLIGHT", "false")
    monkeypatch.setenv("ZROKY_VALIDATE_PREFLIGHT_SAMPLE_RATE", "0.10")

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init(
            validate_preflight=True,
            validate_preflight_sample_rate=0.75,
        )

    assert zroky._config is not None
    assert zroky._config.validate_preflight is True
    assert zroky._config.validate_preflight_sample_rate == pytest.approx(0.75)

    zroky.shutdown()
    _reset_sdk()


def test_call_preflight_prints_when_warnings_present(monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")
    monkeypatch.setenv("ZROKY_VALIDATE_PREFLIGHT", "true")

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init()

    class FakeResponse:
        class usage:
            prompt_tokens = 10
            completion_tokens = 5
            input_tokens = None
            output_tokens = None
            completion_tokens_details = None
            cache_creation_input_tokens = 0
            cache_read_input_tokens = 0

        choices = []

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = FakeResponse()

    validate_calls: list[dict] = []
    print_calls: list[dict] = []

    monkeypatch.setattr(
        zroky._validation,
        "validate",
        lambda payload: validate_calls.append(payload) or {
            "valid": False,
            "warnings": [
                {
                    "type": "TOKEN_OVERFLOW",
                    "confidence": 0.92,
                    "message": "High token usage.",
                    "suggested_fix": "Trim history.",
                }
            ],
        },
    )
    monkeypatch.setattr(
        zroky._validation,
        "print_validation",
        lambda result: print_calls.append(result),
    )

    zroky.call(
        provider="openai",
        model="gpt-4o",
        messages=[{"role": "user", "content": "hello"}],
        _client=mock_client,
    )

    assert len(validate_calls) == 1
    assert len(print_calls) == 1

    zroky.shutdown()
    _reset_sdk()


def test_call_preflight_sampling_zero_skips_validation(monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")
    monkeypatch.setenv("ZROKY_VALIDATE_PREFLIGHT", "true")
    monkeypatch.setenv("ZROKY_VALIDATE_PREFLIGHT_SAMPLE_RATE", "0.0")

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init()

    class FakeResponse:
        class usage:
            prompt_tokens = 10
            completion_tokens = 5
            input_tokens = None
            output_tokens = None
            completion_tokens_details = None
            cache_creation_input_tokens = 0
            cache_read_input_tokens = 0

        choices = []

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = FakeResponse()

    validate_calls: list[dict] = []
    print_calls: list[dict] = []

    monkeypatch.setattr(
        zroky._validation,
        "validate",
        lambda payload: validate_calls.append(payload) or {
            "valid": False,
            "warnings": [
                {
                    "type": "TOKEN_OVERFLOW",
                    "confidence": 0.92,
                    "message": "High token usage.",
                    "suggested_fix": "Trim history.",
                }
            ],
        },
    )
    monkeypatch.setattr(
        zroky._validation,
        "print_validation",
        lambda result: print_calls.append(result),
    )

    zroky.call(
        provider="openai",
        model="gpt-4o",
        messages=[{"role": "user", "content": "hello"}],
        _client=mock_client,
    )

    assert len(validate_calls) == 0
    assert len(print_calls) == 0

    zroky.shutdown()
    _reset_sdk()


def test_call_preflight_silent_when_no_warnings(monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")
    monkeypatch.setenv("ZROKY_VALIDATE_PREFLIGHT", "true")

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init()

    class FakeResponse:
        class usage:
            prompt_tokens = 10
            completion_tokens = 5
            input_tokens = None
            output_tokens = None
            completion_tokens_details = None
            cache_creation_input_tokens = 0
            cache_read_input_tokens = 0

        choices = []

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = FakeResponse()

    validate_calls: list[dict] = []
    print_calls: list[dict] = []

    monkeypatch.setattr(
        zroky._validation,
        "validate",
        lambda payload: validate_calls.append(payload) or {"valid": True, "warnings": []},
    )
    monkeypatch.setattr(
        zroky._validation,
        "print_validation",
        lambda result: print_calls.append(result),
    )

    zroky.call(
        provider="openai",
        model="gpt-4o",
        messages=[{"role": "user", "content": "hello"}],
        _client=mock_client,
    )

    assert len(validate_calls) == 1
    assert len(print_calls) == 0

    zroky.shutdown()
    _reset_sdk()


def test_call_preflight_failure_never_blocks_provider_call(monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")
    monkeypatch.setenv("ZROKY_VALIDATE_PREFLIGHT", "true")

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init()

    class FakeResponse:
        class usage:
            prompt_tokens = 10
            completion_tokens = 5
            input_tokens = None
            output_tokens = None
            completion_tokens_details = None
            cache_creation_input_tokens = 0
            cache_read_input_tokens = 0

        choices = []

    mock_client = MagicMock()
    expected_response = FakeResponse()
    mock_client.chat.completions.create.return_value = expected_response

    monkeypatch.setattr(
        zroky._validation,
        "validate",
        lambda _payload: (_ for _ in ()).throw(RuntimeError("validation boom")),
    )

    response = zroky.call(
        provider="openai",
        model="gpt-4o",
        messages=[{"role": "user", "content": "hello"}],
        _client=mock_client,
    )

    assert response is expected_response

    zroky.shutdown()
    _reset_sdk()


def test_call_preflight_blocking_auth_risk_records_blocked_event(monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    captured = []

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init(preflight_blocking_warning_types=["AUTH_RISK"])

    zroky._queue.enqueue = lambda e: captured.append(e)  # type: ignore[union-attr]

    with pytest.raises(zroky.ZrokyPreflightError):
        zroky.call(
            provider="openai",
            model="gpt-4o",
            messages=[{"role": "user", "content": "hi"}],
        )

    assert len(captured) == 1
    event = captured[0]
    assert event.status == "blocked"
    assert event.error_code == ErrorCode.AUTH_FAILURE
    assert event.failure_reason["schema_version"] == "zroky.preflight_block.v1"
    assert event.failure_reason["preflight_warning_types"] == ["AUTH_RISK"]

    zroky.shutdown()
    _reset_sdk()


def test_call_preflight_populates_recent_calls_meta(monkeypatch):
    _reset_sdk()
    monkeypatch.setenv("ZROKY_MODE", "local")
    monkeypatch.setenv("ZROKY_VALIDATE_PREFLIGHT", "true")

    with patch("zroky._internal.queue.LocalWriter"):
        zroky.init()

    class FakeResponse:
        class usage:
            prompt_tokens = 10
            completion_tokens = 5
            input_tokens = None
            output_tokens = None
            completion_tokens_details = None
            cache_creation_input_tokens = 0
            cache_read_input_tokens = 0

        choices = []

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = FakeResponse()

    captured_recent_calls: list[int] = []

    def _capture_validate(payload: dict):
        meta = payload.get("meta", {})
        captured_recent_calls.append(int(meta.get("recent_calls", 0)))
        return {"valid": True, "warnings": []}

    monkeypatch.setattr(zroky._validation, "validate", _capture_validate)

    zroky.call(
        provider="openai",
        model="gpt-4o",
        messages=[{"role": "user", "content": "hello world"}],
        _client=mock_client,
    )
    zroky.call(
        provider="openai",
        model="gpt-4o",
        messages=[{"role": "user", "content": "hello there"}],
        _client=mock_client,
    )

    assert len(captured_recent_calls) == 2
    assert captured_recent_calls[0] >= 1
    assert captured_recent_calls[1] >= captured_recent_calls[0]

    zroky.shutdown()
    _reset_sdk()


def test_preflight_sampling_is_deterministic_for_same_key() -> None:
    first = zroky._is_preflight_sampled_in(
        sample_rate=0.33,
        sample_key="openai|gpt-4o|fp-abc",
    )
    second = zroky._is_preflight_sampled_in(
        sample_rate=0.33,
        sample_key="openai|gpt-4o|fp-abc",
    )

    assert first == second
