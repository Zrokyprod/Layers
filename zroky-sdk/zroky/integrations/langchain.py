# SPDX-License-Identifier: FSL-1.1-MIT
# Copyright 2026 Zroky AI

"""LangChain callback handler for ZROKY SDK."""
from __future__ import annotations

import time
import uuid
from typing import Any

try:
    from langchain_core.callbacks import BaseCallbackHandler
    from langchain_core.outputs import LLMResult
except ImportError as e:
    raise ImportError(
        "langchain-core is required for ZROKYCallbackHandler. "
        "Install with: pip install zroky[langchain]"
    ) from e

import zroky
from zroky._internal.models import CallEvent, CallType
from zroky._internal.pii import mask_error_message, mask_messages


class ZROKYCallbackHandler(BaseCallbackHandler):
    """
    LangChain callback handler that captures LLM calls into ZROKY.

    V1 scope (explicit):
      - captures LLM calls only (prompt/response metadata, tokens, latency, errors)
      - does NOT capture chain graph steps
      - does NOT capture tool results inside chain
      - chain-step + tool-result capture deferred to V1.1

    Usage:
        from zroky.integrations import ZROKYCallbackHandler
        llm = ChatOpenAI(callbacks=[ZROKYCallbackHandler()])
    """

    def __init__(
        self,
        trace_id: str | None = None,
        agent_name: str | None = None,
    ) -> None:
        super().__init__()
        self._trace_id = trace_id
        self._agent_name = agent_name
        # Map run_id -> (event, start_ns)
        self._pending: dict[str, tuple[CallEvent, int]] = {}

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: uuid.UUID,
        **kwargs: Any,
    ) -> None:
        model = (
            serialized.get("kwargs", {}).get("model_name")
            or serialized.get("kwargs", {}).get("model")
            or "unknown"
        )
        provider = _infer_provider(serialized)
        messages = [{"role": "user", "content": p} for p in prompts]

        cfg, _ = zroky._ensure_init()
        messages = mask_messages(messages)

        event = CallEvent(
            provider=provider,
            model=model,
            messages=messages,
            call_type=CallType.CHAT,
            trace_id=self._trace_id,
            agent_name=self._agent_name or zroky._get_agent(),
            agent_framework=cfg.agent_framework or "langchain",
            prompt_version=cfg.prompt_version,
            session_id=cfg.session_id,
            workflow_id=cfg.workflow_id,
            workflow_name=cfg.workflow_name,
            environment=cfg.environment,
        )
        self._pending[str(run_id)] = (event, time.perf_counter_ns())

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: uuid.UUID,
        **kwargs: Any,
    ) -> None:
        entry = self._pending.pop(str(run_id), None)
        if entry is None:
            return

        event, start_ns = entry
        event.latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
        event.status = "success"

        # Extract token usage from LLMResult
        if response.llm_output:
            usage = response.llm_output.get("token_usage", {})
            event.prompt_tokens = usage.get("prompt_tokens", 0)
            event.completion_tokens = usage.get("completion_tokens", 0)

        _, queue = zroky._ensure_init()
        queue.enqueue(event)

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: uuid.UUID,
        **kwargs: Any,
    ) -> None:
        entry = self._pending.pop(str(run_id), None)
        if entry is None:
            return

        event, start_ns = entry
        event.latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
        event.status = "failed"
        event.error_code = zroky._classify_error(Exception(str(error)))
        event.error_message = mask_error_message(error)

        _, queue = zroky._ensure_init()
        queue.enqueue(event)


def _infer_provider(serialized: dict[str, Any]) -> str:
    id_list = serialized.get("id", [])
    if isinstance(id_list, list):
        id_str = " ".join(str(x).lower() for x in id_list)
        if "anthropic" in id_str:
            return "anthropic"
        if "openai" in id_str or "chat_openai" in id_str:
            return "openai"
        if "google" in id_str or "gemini" in id_str:
            return "google"
    return "unknown"
