"""Event data models for the ZROKY SDK."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from uuid import uuid4

from zroky._internal.pii import hash_identifier, mask_error_message, mask_value


class CallType:
    CHAT = "chat"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    EMBEDDING = "embedding"


class ErrorCode:
    TOKEN_OVERFLOW = "TOKEN_OVERFLOW"
    RATE_LIMIT = "RATE_LIMIT"
    AUTH_FAILURE = "AUTH_FAILURE"
    TIMEOUT = "TIMEOUT"
    NETWORK_ERROR = "NETWORK_ERROR"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


@dataclass
class CallEvent:
    provider: str
    model: str
    messages: list[dict]
    call_type: str = CallType.CHAT

    # Identifiers
    call_id: str = field(default_factory=lambda: str(uuid4()))
    trace_id: str | None = None
    parent_call_id: str | None = None
    agent_name: str | None = None
    prompt_fingerprint: str | None = None
    user_id: str | None = None

    # Request
    tools: list[dict] | None = None
    estimated_prompt_tokens: int | None = None
    model_context_limit: int | None = None
    model_context_limit_source: str | None = None
    model_context_limit_source_detail: str | None = None
    model_context_limit_confidence: float | None = None
    model_context_limit_catalog_version: str | None = None
    model_context_limit_catalog_updated_at: str | None = None
    model_context_limit_catalog_stale: bool | None = None
    model_context_limit_catalog_stale_after_days: int | None = None
    token_estimator_version: str | None = None
    token_rules_version: str | None = None

    # Response
    status: str = "queued"
    latency_ms: float | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    output_content: str | None = None
    normalized_output: str | None = None
    output_fingerprint: str | None = None
    tool_calls_made: list[dict] | None = None
    tool_lifecycle_summary: list[dict] | None = None
    retry_metadata: dict | None = None

    # Cache
    cache_hit: bool = False

    # Budget
    estimated_cost_usd: float | None = None
    actual_cost_usd: float | None = None
    budget_remaining_usd: float | None = None
    budget_action_taken: str | None = None

    # Loop Guard
    loop_action_taken: str | None = None
    loop_call_count: int = 0
    loop_cumulative_cost_usd: float | None = None

    # Timeout
    timeout_triggered: bool = False

    # Fallback
    resolved_model: str | None = None
    fallback_chain: list[str] | None = None
    fallback_attempts: int = 0
    circuit_open_models: list[str] | None = None

    # Error
    error_code: str | None = None
    error_message: str | None = None
    failure_reason: dict | None = None

    # Timestamps
    created_at: float = field(default_factory=time.time)

    def to_ingest_payload(self) -> dict:
        return mask_value({
            "call_id": self.call_id,
            "provider": self.provider,
            "model": self.model,
            "call_type": self.call_type,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "prompt_tokens": self.prompt_tokens,
            "estimated_prompt_tokens": self.estimated_prompt_tokens,
            "model_context_limit": self.model_context_limit,
            "model_context_limit_source": self.model_context_limit_source,
            "model_context_limit_source_detail": self.model_context_limit_source_detail,
            "model_context_limit_confidence": self.model_context_limit_confidence,
            "model_context_limit_catalog_version": self.model_context_limit_catalog_version,
            "model_context_limit_catalog_updated_at": (
                self.model_context_limit_catalog_updated_at
            ),
            "model_context_limit_catalog_stale": self.model_context_limit_catalog_stale,
            "model_context_limit_catalog_stale_after_days": (
                self.model_context_limit_catalog_stale_after_days
            ),
            "token_estimator_version": self.token_estimator_version,
            "token_rules_version": self.token_rules_version,
            "completion_tokens": self.completion_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "cache_creation_tokens": self.cache_creation_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "normalized_output": self.normalized_output,
            "output_fingerprint": self.output_fingerprint,
            "tool_definitions": self.tools,
            "tool_calls_made": self.tool_calls_made,
            "tool_lifecycle_summary": self.tool_lifecycle_summary,
            "retry_metadata": self.retry_metadata,
            "cache_hit": self.cache_hit,
            "estimated_cost_usd": self.estimated_cost_usd,
            "actual_cost_usd": self.actual_cost_usd,
            "budget_remaining_usd": self.budget_remaining_usd,
            "budget_action_taken": self.budget_action_taken,
            "loop_action_taken": self.loop_action_taken,
            "loop_call_count": self.loop_call_count,
            "loop_cumulative_cost_usd": self.loop_cumulative_cost_usd,
            "timeout_triggered": self.timeout_triggered,
            "resolved_model": self.resolved_model,
            "fallback_chain": self.fallback_chain,
            "fallback_attempts": self.fallback_attempts,
            "circuit_open_models": self.circuit_open_models,
            "trace_id": self.trace_id,
            "parent_call_id": self.parent_call_id,
            "agent_name": self.agent_name,
            "prompt_fingerprint": self.prompt_fingerprint,
            "user_id": hash_identifier(self.user_id),
            "error_code": self.error_code,
            "error_message": mask_error_message(self.error_message) if self.error_message else None,
            "failure_reason": self.failure_reason,
            "created_at": self.created_at,
        })
